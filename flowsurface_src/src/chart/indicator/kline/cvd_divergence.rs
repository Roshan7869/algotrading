use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{BasisSeries, BasisSeriesExt, KlineIndicatorImpl},
        plot::{PlotTooltip, bar::{BarClass, BarPlot}},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{
    PlotData,
    kline::KlineDataPoint,
};
use exchange::{Kline, Trade, unit::{Price, UnixMs}};

use iced::widget::canvas::{Frame, Path, Stroke};
use iced::{Color, Point, Theme};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct CvdDivPoint {
    pub direction: i8,
}

fn datapoint_delta(dp: &KlineDataPoint) -> f32 {
    if dp.footprint.trades.is_empty() {
        dp.kline.volume.buy_sell()
            .map(|(buy, sell)| (buy - sell).to_f32_lossy())
            .unwrap_or(0.0)
    } else {
        dp.footprint.trades.values()
            .fold(exchange::unit::Qty::ZERO, |acc, group| acc + group.delta_qty())
            .to_f32_lossy()
    }
}

fn tick_delta(dp: &data::aggr::ticks::TickAccumulation) -> f32 {
    if dp.footprint.trades.is_empty() {
        dp.kline.volume.buy_sell()
            .map(|(buy, sell)| (buy - sell).to_f32_lossy())
            .unwrap_or(0.0)
    } else {
        dp.footprint.trades.values()
            .fold(exchange::unit::Qty::ZERO, |acc, group| acc + group.delta_qty())
            .to_f32_lossy()
    }
}

pub struct CvdDivergenceIndicator {
    cache: Caches,
    data: BasisSeries<CvdDivPoint>,
    lookback: usize,
}

impl CvdDivergenceIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            lookback: 20,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &CvdDivPoint, _next: Option<&CvdDivPoint>| {
            match point.direction {
                1 => PlotTooltip::new("Bullish CVD Divergence".to_string()),
                -1 => PlotTooltip::new("Bearish CVD Divergence".to_string()),
                _ => PlotTooltip::new("No divergence".to_string()),
            }
        };

        let value_fn = |point: &CvdDivPoint| point.direction as f32;
        let bar_kind = |point: &CvdDivPoint| BarClass::Overlay { overlay: point.direction as f32 };

        let plot = BarPlot::new(value_fn, bar_kind)
            .bar_width_factor(0.6)
            .padding(0.08)
            .with_tooltip(tooltip);

        indicator_row(
            main_chart,
            &self.cache,
            data_labels_always_visible,
            plot,
            self.data.as_plot_series(),
            visible_range,
        )
    }

    fn compute_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        match source {
            PlotData::TimeBased(ts) => {
                let highs: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                let cvd: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| datapoint_delta(dp)).collect();
                let timestamps: Vec<UnixMs> = ts.datapoints.iter().map(|(&t, _)| t).collect();

                if cvd.len() < self.lookback * 2 { return; }

                let divergences =
                    data::chart::ta::detect_cvd_divergence(&highs, &lows, &closes, &cvd, self.lookback);

                let result: std::collections::BTreeMap<UnixMs, CvdDivPoint> = divergences.iter()
                    .filter_map(|d| timestamps.get(d.index).map(|&t| (t, CvdDivPoint { direction: d.direction })))
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let highs: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                let cvd: Vec<f32> = tick.datapoints.iter().map(|dp| tick_delta(dp)).collect();

                if cvd.len() < self.lookback * 2 { return; }

                let divergences =
                    data::chart::ta::detect_cvd_divergence(&highs, &lows, &closes, &cvd, self.lookback);

                let result: std::collections::BTreeMap<u64, CvdDivPoint> = divergences.iter()
                    .map(|d| (d.index as u64, CvdDivPoint { direction: d.direction }))
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for CvdDivergenceIndicator {
    fn clear_all_caches(&mut self) { self.cache.clear_all(); }
    fn clear_crosshair_caches(&mut self) { self.cache.clear_crosshair(); }

    fn is_overlay(&self) -> bool {
        true
    }

    fn draw_overlay(
        &self,
        frame: &mut Frame,
        ctx: &ViewState,
        _theme: &Theme,
        visible_range: RangeInclusive<u64>,
    ) {
        let earliest = *visible_range.start();
        let latest = *visible_range.end();

        let points: Vec<(u64, &CvdDivPoint)> = match &self.data {
            BasisSeries::Time(map) => {
                let er = UnixMs(earliest);
                let lr = UnixMs(latest);
                map.range(er..=lr).map(|(&k, v)| (k.0, v)).collect()
            }
            BasisSeries::Tick(map) => {
                map.range(earliest..=latest).map(|(&k, v)| (k, v)).collect()
            }
        };

        for &(ts, pt) in &points {
            if pt.direction == 0 { continue; }
            let x = ctx.interval_to_x(ts);
            let y_top = ctx.price_to_y(Price::from_f32_lossy(0.0));
            let y_bot = ctx.price_to_y(Price::from_f32_lossy(100000.0));
            let y_range = (y_top - y_bot).abs();
            let y = y_bot + y_range * 0.15;

            let color = if pt.direction > 0 {
                Color::from_rgb(1.0, 0.5, 0.0)
            } else {
                Color::from_rgb(0.5, 0.0, 1.0)
            };

            let marker = Path::new(|builder| {
                let dy = 6.0_f32;
                if pt.direction > 0 {
                    builder.move_to(Point::new(x - 4.0, y + dy));
                    builder.line_to(Point::new(x, y));
                    builder.line_to(Point::new(x + 4.0, y + dy));
                } else {
                    builder.move_to(Point::new(x - 4.0, y - dy));
                    builder.line_to(Point::new(x, y));
                    builder.line_to(Point::new(x + 4.0, y - dy));
                }
                builder.close();
            });

            frame.stroke(&marker, Stroke::default().with_width(2.0).with_color(color));
        }
    }

    fn element<'a>(
        &'a self,
        chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        self.indicator_elem(chart, data_labels_always_visible, visible_range)
    }

    fn rebuild_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn on_insert_klines(&mut self, _klines: &[Kline], source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn on_insert_trades(
        &mut self,
        _trades: &[Trade],
        _old_dp_len: usize,
        source: &PlotData<KlineDataPoint>,
    ) {
        self.compute_from_source(source);
    }

    fn on_basis_change(&mut self, source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn apply_config(&mut self, config: &IndicatorConfig) {
        if let IndicatorConfig::CvdDivergence { lookback } = config {
            self.lookback = *lookback;
        }
    }
}
