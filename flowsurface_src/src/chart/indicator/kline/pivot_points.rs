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

#[derive(Debug, Clone, Copy, Default)]
pub struct PivotPoint {
    pub pivot: f32,
    pub r1: f32,
    pub s1: f32,
}

pub struct PivotPointsIndicator {
    cache: Caches,
    data: BasisSeries<PivotPoint>,
    pivot_type: String,
}

impl PivotPointsIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            pivot_type: "classic".to_string(),
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &PivotPoint, _next: Option<&PivotPoint>| {
            PlotTooltip::new(format!(
                "PP: {:.2}\nR1: {:.2}\nS1: {:.2}",
                point.pivot, point.r1, point.s1
            ))
        };

        let value_fn = |point: &PivotPoint| point.pivot;

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
                let highs: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                let timestamps: Vec<UnixMs> = ts.datapoints.iter().map(|(&t, _)| t).collect();

                let pivots = ta::pivot_points_series(&highs, &lows, &closes);
                let result: std::collections::BTreeMap<UnixMs, PivotPoint> = timestamps.iter().zip(pivots.iter())
                    .filter_map(|(&t, p)| p.map(|v| (t, PivotPoint { pivot: v.pivot, r1: v.r1, s1: v.s1 })))
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let highs: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();

                let pivots = ta::pivot_points_series(&highs, &lows, &closes);
                let result: std::collections::BTreeMap<u64, PivotPoint> = pivots.iter().enumerate()
                    .filter_map(|(i, p)| p.map(|v| (i as u64, PivotPoint { pivot: v.pivot, r1: v.r1, s1: v.s1 })))
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for PivotPointsIndicator {
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
        let x0 = ctx.interval_to_x(earliest);
        let x1 = ctx.interval_to_x(latest);

        let levels: Vec<(f32, &str)> = match &self.data {
            BasisSeries::Time(map) => {
                let er = UnixMs(earliest);
                let lr = UnixMs(latest);
                map.range(er..=lr).last().map_or(vec![], |(_, pt)| {
                    vec![(pt.r1, "R1"), (pt.pivot, "PP"), (pt.s1, "S1")]
                })
            }
            BasisSeries::Tick(map) => {
                map.range(earliest..=latest).last().map_or(vec![], |(_, pt)| {
                    vec![(pt.r1, "R1"), (pt.pivot, "PP"), (pt.s1, "S1")]
                })
            }
        };

        let gold = Color::from_rgb(1.0, 0.84, 0.0);
        for &(price, label) in &levels {
            if price == 0.0 { continue; }
            let y = ctx.price_to_y(Price::from_f32_lossy(price));
            let path = Path::new(|builder| {
                builder.move_to(Point::new(x0, y));
                builder.line_to(Point::new(x1, y));
            });
            let is_pp = label == "PP";
            frame.stroke(
                &path,
                Stroke::default()
                    .with_width(if is_pp { 1.2 } else { 0.8 })
                    .with_color(Color::from_rgba(gold.r, gold.g, gold.b, if is_pp { 0.8 } else { 0.4f32 })),
            );
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
        if let IndicatorConfig::PivotPoints { pivot_type } = config {
            self.pivot_type = pivot_type.clone();
        }
    }
}
