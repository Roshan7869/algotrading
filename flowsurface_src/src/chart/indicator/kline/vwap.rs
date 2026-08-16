use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{BasisSeries, BasisSeriesExt, KlineIndicatorImpl},
        plot::{PlotTooltip, line::LinePlot},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{PlotData, kline::KlineDataPoint};
use exchange::{Kline, unit::{Price, UnixMs}};

use iced::widget::canvas::{Frame, Path, Stroke};
use iced::{Color, Point, Theme};

use std::ops::RangeInclusive;

/// VWAP indicator point — single value overlaid on price chart.
#[derive(Debug, Clone, Copy, Default)]
pub struct VwapPoint {
    pub vwap: f32,
}

pub struct VwapIndicator {
    cache: Caches,
    data: BasisSeries<VwapPoint>,
}

impl VwapIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &VwapPoint, _next: Option<&VwapPoint>| {
            PlotTooltip::new(format!("VWAP: {:.2}", point.vwap))
        };

        let value_fn = |point: &VwapPoint| point.vwap;

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
                if ts.datapoints.is_empty() { return; }
                let mut cum_tp_vol = 0.0_f32;
                let mut cum_vol = 0.0_f32;
                let mut result: std::collections::BTreeMap<UnixMs, VwapPoint> = std::collections::BTreeMap::new();
                for (&t, dp) in ts.datapoints.iter() {
                    let h = dp.kline.high.to_f32();
                    let l = dp.kline.low.to_f32();
                    let c = dp.kline.close.to_f32();
                    let v = dp.kline.volume.total().to_f32_lossy();
                    if v <= 0.0 { continue; }
                    let typical = (h + l + c) / 3.0;
                    cum_tp_vol += typical * v;
                    cum_vol += v;
                    let vwap = if cum_vol > 0.0 { cum_tp_vol / cum_vol } else { c };
                    result.insert(t, VwapPoint { vwap });
                }
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                if tick.datapoints.is_empty() { return; }
                let mut cum_tp_vol = 0.0_f32;
                let mut cum_vol = 0.0_f32;
                let mut result: std::collections::BTreeMap<u64, VwapPoint> = std::collections::BTreeMap::new();
                for (i, dp) in tick.datapoints.iter().enumerate() {
                    let h = dp.kline.high.to_f32();
                    let l = dp.kline.low.to_f32();
                    let c = dp.kline.close.to_f32();
                    let v = dp.kline.volume.total().to_f32_lossy();
                    if v <= 0.0 { continue; }
                    let typical = (h + l + c) / 3.0;
                    cum_tp_vol += typical * v;
                    cum_vol += v;
                    let vwap = if cum_vol > 0.0 { cum_tp_vol / cum_vol } else { c };
                    result.insert(i as u64, VwapPoint { vwap });
                }
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for VwapIndicator {
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

        let path = Path::new(|builder| {
            let mut first = true;
            match &self.data {
                BasisSeries::Time(map) => {
                    let er = UnixMs(earliest);
                    let lr = UnixMs(latest);
                    for (&ts, pt) in map.range(er..=lr) {
                        let x = ctx.interval_to_x(ts.0);
                        let y = ctx.price_to_y(Price::from_f32_lossy(pt.vwap));
                        if first {
                            builder.move_to(Point::new(x, y));
                            first = false;
                        } else {
                            builder.line_to(Point::new(x, y));
                        }
                    }
                }
                BasisSeries::Tick(map) => {
                    for (&ts, pt) in map.range(earliest..=latest) {
                        let x = ctx.interval_to_x(ts);
                        let y = ctx.price_to_y(Price::from_f32_lossy(pt.vwap));
                        if first {
                            builder.move_to(Point::new(x, y));
                            first = false;
                        } else {
                            builder.line_to(Point::new(x, y));
                        }
                    }
                }
            }
        });

        frame.stroke(
            &path,
            Stroke::default()
                .with_width(1.5)
                .with_color(Color::from_rgb(1.0, 0.84, 0.0)),
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

    fn apply_config(&mut self, _config: &IndicatorConfig) {}
}