use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{BasisSeries, BasisSeriesExt, KlineIndicatorImpl},
        plot::{PlotTooltip, bar::{BarClass, BarPlot}},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{PlotData, kline::KlineDataPoint, ta};
use exchange::{Kline, unit::{Price, UnixMs}};

use iced::widget::canvas::{Frame, Path, Stroke};
use iced::{Color, Point, Theme};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct MssPoint {
    pub direction: i8,
    pub break_level: f32,
}

pub struct MssIndicator {
    cache: Caches,
    data: BasisSeries<MssPoint>,
    swing_lookback: usize,
    confirmation_bars: usize,
}

impl MssIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            swing_lookback: 5,
            confirmation_bars: 1,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &MssPoint, _next: Option<&MssPoint>| {
            match point.direction {
                1 => PlotTooltip::new(format!("Bullish MSS\nBreak: {:.4}", point.break_level)),
                -1 => PlotTooltip::new(format!("Bearish MSS\nBreak: {:.4}", point.break_level)),
                _ => PlotTooltip::new("No MSS".to_string()),
            }
        };

        let value_fn = |point: &MssPoint| point.direction as f32;
        let bar_kind = |point: &MssPoint| BarClass::Overlay { overlay: point.direction as f32 };

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
                let timestamps: Vec<UnixMs> = ts.datapoints.iter().map(|(&t, _)| t).collect();

                if closes.len() < self.swing_lookback * 2 + 2 { return; }

                let mss = ta::mss_series(&highs, &lows, &closes, self.swing_lookback, self.confirmation_bars);
                let signals = ta::detect_mss(&highs, &lows, &closes, self.swing_lookback, self.confirmation_bars);

                let result: std::collections::BTreeMap<UnixMs, MssPoint> = timestamps.iter().enumerate()
                    .map(|(i, &t)| {
                        let dir = if i < mss.len() { mss[i] } else { 0i8 };
                        let bl = signals.iter()
                            .find(|s| s.index == i)
                            .map(|s| s.break_level)
                            .unwrap_or(0.0);
                        (t, MssPoint { direction: dir, break_level: bl })
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let highs: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();

                if closes.len() < self.swing_lookback * 2 + 2 { return; }

                let mss = ta::mss_series(&highs, &lows, &closes, self.swing_lookback, self.confirmation_bars);
                let signals = ta::detect_mss(&highs, &lows, &closes, self.swing_lookback, self.confirmation_bars);

                let result: std::collections::BTreeMap<u64, MssPoint> = mss.iter().enumerate()
                    .map(|(i, &dir)| {
                        let bl = signals.iter()
                            .find(|s| s.index == i)
                            .map(|s| s.break_level)
                            .unwrap_or(0.0);
                        (i as u64, MssPoint { direction: dir, break_level: bl })
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for MssIndicator {
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

        let points: Vec<(u64, &MssPoint)> = match &self.data {
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
            let y = if pt.break_level != 0.0 {
                ctx.price_to_y(Price::from_f32_lossy(pt.break_level))
            } else {
                continue;
            };

            let arrow = Path::new(|builder| {
                let dy = if pt.direction > 0 { 5.0_f32 } else { -5.0_f32 };
                builder.move_to(Point::new(x - 4.0, y + dy));
                builder.line_to(Point::new(x, y));
                builder.line_to(Point::new(x + 4.0, y + dy));
                builder.close();
            });

            frame.stroke(&arrow, Stroke::default().with_width(1.5).with_color(
                if pt.direction > 0 { Color::from_rgb(0.0, 0.8, 0.0) } else { Color::from_rgb(0.8, 0.0, 0.0) }
            ));
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

    fn on_basis_change(&mut self, source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn apply_config(&mut self, config: &IndicatorConfig) {
        if let IndicatorConfig::Mss { swing_lookback, confirmation_bars } = config {
            self.swing_lookback = *swing_lookback;
            self.confirmation_bars = *confirmation_bars;
        }
    }
}
