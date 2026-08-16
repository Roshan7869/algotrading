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
use iced::{Color, Point, Size, Theme};

use std::ops::RangeInclusive;

/// Order Block indicator point.
#[derive(Debug, Clone, Copy, Default)]
pub struct OrderBlockPoint {
    /// Top of the OB zone.
    pub ob_top: f32,
    /// Bottom of the OB zone.
    pub ob_bottom: f32,
    /// Midpoint for line rendering.
    pub midpoint: f32,
    /// true = bullish OB, false = bearish.
    pub is_bullish: bool,
}

pub struct OrderBlockIndicator {
    cache: Caches,
    data: BasisSeries<OrderBlockPoint>,
    body_threshold: f32,
    impulse_count: usize,
    lookback: usize,
}

impl OrderBlockIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            body_threshold: 0.5,
            impulse_count: 2,
            lookback: 60,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &OrderBlockPoint, _next: Option<&OrderBlockPoint>| {
            let dir = if point.is_bullish { "Bull" } else { "Bear" };
            PlotTooltip::new(format!(
                "OB ({dir})\nZone: {:.2} - {:.2}",
                point.ob_bottom, point.ob_top
            ))
        };

        let value_fn = |point: &OrderBlockPoint| {
            // Positive for bullish, negative for bearish to separate on sub-chart
            if point.is_bullish {
                point.midpoint
            } else {
                -point.midpoint
            }
        };

        let plot = LinePlot::new(value_fn)
            .stroke_width(2.0)
            .show_points(true)
            .point_radius_factor(0.35)
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
                let mut opens: Vec<f32> = Vec::new();
                let mut highs: Vec<f32> = Vec::new();
                let mut lows: Vec<f32> = Vec::new();
                let mut closes: Vec<f32> = Vec::new();
                let mut timestamps: Vec<UnixMs> = Vec::new();
                for (&t, dp) in &ts.datapoints {
                    opens.push(dp.kline.open.to_f32());
                    highs.push(dp.kline.high.to_f32());
                    lows.push(dp.kline.low.to_f32());
                    closes.push(dp.kline.close.to_f32());
                    timestamps.push(t);
                }
                if closes.len() < self.impulse_count + 1 {
                    return;
                }
                let blocks = ta::order_blocks(
                    &opens,
                    &highs,
                    &lows,
                    &closes,
                    self.body_threshold,
                    self.impulse_count,
                    self.lookback,
                );
                let result: std::collections::BTreeMap<UnixMs, OrderBlockPoint> = blocks
                    .iter()
                    .filter_map(|ob| {
                        timestamps.get(ob.index).map(|&t| {
                            (
                                t,
                                OrderBlockPoint {
                                    ob_top: ob.ob_top,
                                    ob_bottom: ob.ob_bottom,
                                    midpoint: (ob.ob_top + ob.ob_bottom) / 2.0,
                                    is_bullish: ob.is_bullish,
                                },
                            )
                        })
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let mut opens: Vec<f32> = Vec::new();
                let mut highs: Vec<f32> = Vec::new();
                let mut lows: Vec<f32> = Vec::new();
                let mut closes: Vec<f32> = Vec::new();
                for dp in &tick.datapoints {
                    opens.push(dp.kline.open.to_f32());
                    highs.push(dp.kline.high.to_f32());
                    lows.push(dp.kline.low.to_f32());
                    closes.push(dp.kline.close.to_f32());
                }
                if closes.len() < self.impulse_count + 1 {
                    return;
                }
                let blocks = ta::order_blocks(
                    &opens,
                    &highs,
                    &lows,
                    &closes,
                    self.body_threshold,
                    self.impulse_count,
                    self.lookback,
                );
                let result: std::collections::BTreeMap<u64, OrderBlockPoint> = blocks
                    .iter()
                    .filter_map(|ob| {
                        let idx = ob.index as u64;
                        Some((
                            idx,
                            OrderBlockPoint {
                                ob_top: ob.ob_top,
                                ob_bottom: ob.ob_bottom,
                                midpoint: (ob.ob_top + ob.ob_bottom) / 2.0,
                                is_bullish: ob.is_bullish,
                            },
                        ))
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for OrderBlockIndicator {
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

        let points: Vec<(u64, &OrderBlockPoint)> = match &self.data {
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
            if pt.ob_top == 0.0 && pt.ob_bottom == 0.0 {
                continue;
            }
            let x = ctx.interval_to_x(ts);
            let y_top = ctx.price_to_y(Price::from_f32_lossy(pt.ob_top));
            let y_bot = ctx.price_to_y(Price::from_f32_lossy(pt.ob_bottom));
            let color = if pt.is_bullish {
                Color::from_rgba(0.0, 0.5, 0.8, 0.25)
            } else {
                Color::from_rgba(0.8, 0.3, 0.0, 0.25)
            };
            frame.fill_rectangle(
                Point::new(x - 6.0, y_top.min(y_bot)),
                Size::new(12.0, (y_top - y_bot).abs()),
                color,
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
        if let IndicatorConfig::OrderBlock { body_threshold, impulse_count, lookback } = config {
            self.body_threshold = *body_threshold;
            self.impulse_count = *impulse_count;
            self.lookback = *lookback;
        }
    }
}