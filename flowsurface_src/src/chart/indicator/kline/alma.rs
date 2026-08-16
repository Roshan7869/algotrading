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

/// ALMA indicator point — stores the computed ALMA value.
#[derive(Debug, Clone, Copy, Default)]
pub struct AlmaPoint {
    pub alma: f32,
}

pub struct AlmaIndicator {
    cache: Caches,
    data: BasisSeries<AlmaPoint>,
    period: usize,
    offset: f32,
    sigma: f32,
}

impl AlmaIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            period: 9,
            offset: 0.85,
            sigma: 6.0,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &AlmaPoint, _next: Option<&AlmaPoint>| {
            PlotTooltip::new(format!("ALMA: {:.2}", point.alma))
        };

        let value_fn = |point: &AlmaPoint| point.alma;

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
                let close_vals: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                if close_vals.len() < self.period + 1 { return; }
                let alma_vals = ta::alma_series(&close_vals, self.period, self.offset, self.sigma);
                let result: std::collections::BTreeMap<UnixMs, AlmaPoint> = ts.datapoints.iter().zip(alma_vals.iter())
                    .filter_map(|((&t, _), alma_opt)| {
                        alma_opt.map(|v| (t, AlmaPoint { alma: v }))
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let close_vals: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                if close_vals.len() < self.period + 1 { return; }
                let alma_vals = ta::alma_series(&close_vals, self.period, self.offset, self.sigma);
                let result: std::collections::BTreeMap<u64, AlmaPoint> = tick.datapoints.iter().enumerate().zip(alma_vals.iter())
                    .filter_map(|((i, _), alma_opt)| {
                        alma_opt.map(|v| (i as u64, AlmaPoint { alma: v }))
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for AlmaIndicator {
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

        match &self.data {
            BasisSeries::Time(map) => {
                let er = UnixMs(earliest);
                let lr = UnixMs(latest);
                let pts: Vec<(u64, &AlmaPoint)> = map.range(er..=lr).map(|(&k, v)| (k.0, v)).collect();
                Self::draw_line(frame, ctx, &pts);
            }
            BasisSeries::Tick(map) => {
                let pts: Vec<(u64, &AlmaPoint)> = map.range(earliest..=latest).map(|(&k, v)| (k, v)).collect();
                Self::draw_line(frame, ctx, &pts);
            }
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
        if let IndicatorConfig::Alma { period, offset, sigma } = config {
            self.period = *period;
            self.offset = *offset;
            self.sigma = *sigma;
        }
    }
}

impl AlmaIndicator {
    fn draw_line(
        frame: &mut Frame,
        ctx: &ViewState,
        points: &[(u64, &AlmaPoint)],
    ) {
        if points.len() < 2 {
            return;
        }

        let path = Path::new(|builder| {
            let mut first = true;
            for &(ts, pt) in points {
                let x = ctx.interval_to_x(ts);
                let y = ctx.price_to_y(Price::from_f32_lossy(pt.alma));
                if first {
                    builder.move_to(Point::new(x, y));
                    first = false;
                } else {
                    builder.line_to(Point::new(x, y));
                }
            }
        });

        frame.stroke(
            &path,
            Stroke::default()
                .with_width(1.2)
                .with_color(Color::from_rgb(0.9, 0.5, 0.1)),
        );
    }
}