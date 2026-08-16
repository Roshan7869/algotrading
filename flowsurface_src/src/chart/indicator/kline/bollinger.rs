use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{BasisSeries, BasisSeriesExt, KlineIndicatorImpl},
        plot::{PlotTooltip, line::LinePlot},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{PlotData, kline::KlineDataPoint, ta};
use exchange::{Kline, unit::{Price, UnixMs}};

use iced::widget::canvas::{Frame, Path, Stroke};
use iced::{Color, Point, Theme};

use std::ops::RangeInclusive;

/// Bollinger Bands indicator point — upper/mid/lower/bandwidth/%b.
#[derive(Debug, Clone, Copy, Default)]
pub struct BollingerPoint {
    pub upper: f32,
    pub mid: f32,
    pub lower: f32,
    pub bandwidth: f32,
    pub percent_b: f32,
}

pub struct BollingerIndicator {
    cache: Caches,
    data: BasisSeries<BollingerPoint>,
    period: usize,
    stddev: f32,
}

impl BollingerIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            period: 20,
            stddev: 2.0,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &BollingerPoint, _next: Option<&BollingerPoint>| {
            PlotTooltip::new(format!(
                "BB Upper: {:.2}\nBB Mid: {:.2}\nBB Lower: {:.2}\nBW: {:.3}\n%B: {:.2}",
                point.upper, point.mid, point.lower, point.bandwidth, point.percent_b
            ))
        };

        // Display %b as the sub-pane value (oscillates 0-1)
        let value_fn = |point: &BollingerPoint| point.percent_b;

        let plot = LinePlot::new(value_fn)
            .stroke_width(1.5)
            .show_points(true)
            .point_radius_factor(0.2)
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
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period { return; }
                let bb_result = ta::bollinger_bands(&closes, self.period, self.stddev);
                let result: std::collections::BTreeMap<UnixMs, BollingerPoint> = ts.datapoints.iter().zip(bb_result.iter())
                    .filter_map(|((&t, _), bb_opt)| {
                        bb_opt.map(|v| (t, BollingerPoint {
                            upper: v.upper,
                            mid: v.mid,
                            lower: v.lower,
                            bandwidth: v.bandwidth,
                            percent_b: v.percent_b,
                        }))
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period { return; }
                let bb_result = ta::bollinger_bands(&closes, self.period, self.stddev);
                let result: std::collections::BTreeMap<u64, BollingerPoint> = tick.datapoints.iter().enumerate().zip(bb_result.iter())
                    .filter_map(|((i, _), bb_opt)| {
                        bb_opt.map(|v| (i as u64, BollingerPoint {
                            upper: v.upper,
                            mid: v.mid,
                            lower: v.lower,
                            bandwidth: v.bandwidth,
                            percent_b: v.percent_b,
                        }))
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for BollingerIndicator {
    fn clear_all_caches(&mut self) {
        self.cache.clear_all();
    }

    fn clear_crosshair_caches(&mut self) {
        self.cache.clear_crosshair();
    }

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

        let points: Vec<(u64, &BollingerPoint)> = match &self.data {
            BasisSeries::Time(map) => {
                let er = UnixMs(earliest);
                let lr = UnixMs(latest);
                map.range(er..=lr).map(|(&k, v)| (k.0, v)).collect()
            }
            BasisSeries::Tick(map) => {
                map.range(earliest..=latest).map(|(&k, v)| (k, v)).collect()
            }
        };

        if points.len() < 2 {
            return;
        }

        let build_line = |get_val: fn(&BollingerPoint) -> f32| -> Path {
            Path::new(|builder| {
                let mut first = true;
                for &(ts, pt) in &points {
                    let x = ctx.interval_to_x(ts);
                    let y = ctx.price_to_y(Price::from_f32_lossy(get_val(pt)));
                    if first {
                        builder.move_to(Point::new(x, y));
                        first = false;
                    } else {
                        builder.line_to(Point::new(x, y));
                    }
                }
            })
        };

        let mid = build_line(|pt| pt.mid);
        let upper = build_line(|pt| pt.upper);
        let lower = build_line(|pt| pt.lower);

        let blue = Color::from_rgb(0.3, 0.5, 0.9);
        frame.stroke(&mid, Stroke::default().with_width(1.2).with_color(blue));
        frame.stroke(
            &upper,
            Stroke::default().with_width(0.8).with_color(Color::from_rgba(0.3, 0.5, 0.9, 0.6)),
        );
        frame.stroke(
            &lower,
            Stroke::default().with_width(0.8).with_color(Color::from_rgba(0.3, 0.5, 0.9, 0.6)),
        );
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
        if let IndicatorConfig::BollingerBands { period, stddev } = config {
            self.period = *period;
            self.stddev = *stddev;
        }
    }
}