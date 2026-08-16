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
pub struct LvnPoint {
    /// Distance from candle close to nearest LVN/HVN zone midpoint (positive = near LVN, negative = near HVN)
    pub zone_proximity: f32,
    pub zone_type: u8, // 0=none, 1=LVN, 2=HVN
}

pub struct LvnIndicator {
    cache: Caches,
    data: BasisSeries<LvnPoint>,
    lvn_threshold: f32,
    hvn_threshold: f32,
    min_bins: usize,
    value_area_pct: f32,
}

impl LvnIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            lvn_threshold: 0.5,
            hvn_threshold: 1.5,
            min_bins: 3,
            value_area_pct: 0.7,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &LvnPoint, _next: Option<&LvnPoint>| {
            match point.zone_type {
                1 => PlotTooltip::new(format!("LVN zone\nProx: {:.2}", point.zone_proximity)),
                2 => PlotTooltip::new(format!("HVN zone\nProx: {:.2}", point.zone_proximity)),
                _ => PlotTooltip::new("No zone".to_string()),
            }
        };

        let value_fn = |point: &LvnPoint| point.zone_proximity;

        let bar_kind = |point: &LvnPoint| BarClass::Overlay { overlay: point.zone_proximity };

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
        let num_bins = 24.max(self.min_bins + 1);
        match source {
            PlotData::TimeBased(ts) => {
                let highs: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.low.to_f32()).collect();
                let volumes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.volume.total().to_f32_lossy()).collect();
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                let timestamps: Vec<UnixMs> = ts.datapoints.iter().map(|(&t, _)| t).collect();

                let zones = ta::detect_lvn_hvn(
                    &highs, &lows, &volumes, num_bins,
                    self.lvn_threshold, self.hvn_threshold, self.min_bins,
                );

                let result: std::collections::BTreeMap<UnixMs, LvnPoint> = timestamps.iter().enumerate()
                    .map(|(i, &t)| {
                        let close = closes[i];
                        let mut best = LvnPoint::default();
                        for z in &zones {
                            if close >= z.price_low && close <= z.price_high {
                                let mid = (z.price_low + z.price_high) / 2.0;
                                let prox = (close - mid) / (z.price_high - z.price_low + 0.01);
                                let dist = (close - mid).abs();
                                if best.zone_type == 0 || dist < best.zone_proximity.abs() {
                                    best.zone_type = if z.is_lvn { 1 } else { 2 };
                                    best.zone_proximity = if z.is_lvn { prox.abs() } else { -prox.abs() };
                                }
                            }
                        }
                        (t, best)
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let highs: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.low.to_f32()).collect();
                let volumes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.volume.total().to_f32_lossy()).collect();
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();

                let zones = ta::detect_lvn_hvn(
                    &highs, &lows, &volumes, num_bins,
                    self.lvn_threshold, self.hvn_threshold, self.min_bins,
                );

                let result: std::collections::BTreeMap<u64, LvnPoint> = closes.iter().enumerate()
                    .map(|(i, &close)| {
                        let mut best = LvnPoint::default();
                        for z in &zones {
                            if close >= z.price_low && close <= z.price_high {
                                let mid = (z.price_low + z.price_high) / 2.0;
                                let prox = (close - mid) / (z.price_high - z.price_low + 0.01);
                                let dist = (close - mid).abs();
                                if best.zone_type == 0 || dist < best.zone_proximity.abs() {
                                    best.zone_type = if z.is_lvn { 1 } else { 2 };
                                    best.zone_proximity = if z.is_lvn { prox.abs() } else { -prox.abs() };
                                }
                            }
                        }
                        (i as u64, best)
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for LvnIndicator {
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

        let points: Vec<(u64, &LvnPoint)> = match &self.data {
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
            if pt.zone_type == 0 { continue; }
            let x = ctx.interval_to_x(ts);
            let y = ctx.price_to_y(Price::from_f32_lossy(pt.zone_proximity));
            let color = if pt.zone_type == 1 {
                Color::from_rgba(1.0, 0.5, 0.0, 0.6)
            } else {
                Color::from_rgba(0.0, 0.5, 1.0, 0.6)
            };
            let marker = Path::new(|builder| {
                builder.move_to(Point::new(x - 8.0, y));
                builder.line_to(Point::new(x, y - 4.0));
                builder.line_to(Point::new(x + 8.0, y));
                builder.line_to(Point::new(x, y + 4.0));
                builder.close();
            });
            frame.stroke(&marker, Stroke::default().with_width(1.5).with_color(color));
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
        if let IndicatorConfig::Lvn { lvn_threshold, hvn_threshold, min_bins, value_area_pct } = config {
            self.lvn_threshold = *lvn_threshold;
            self.hvn_threshold = *hvn_threshold;
            self.min_bins = *min_bins;
            self.value_area_pct = *value_area_pct;
        }
    }
}
