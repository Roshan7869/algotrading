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

/// FVG indicator point — stores the gap top, gap bottom, and direction.
#[derive(Debug, Clone, Copy, Default)]
pub struct FvgPoint {
    /// Upper bound of the Fair Value Gap zone.
    pub gap_top: f32,
    /// Lower bound of the Fair Value Gap zone.
    pub gap_bottom: f32,
    /// Midpoint of the gap zone (for line rendering).
    pub midpoint: f32,
    /// true = bullish FVG, false = bearish.
    pub is_bullish: bool,
}

pub struct FvgIndicator {
    cache: Caches,
    data: BasisSeries<FvgPoint>,
}

impl FvgIndicator {
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
        let tooltip = |point: &FvgPoint, _next: Option<&FvgPoint>| {
            let dir = if point.is_bullish { "Bull" } else { "Bear" };
            PlotTooltip::new(format!(
                "FVG ({dir})\nGap: {:.2} - {:.2}",
                point.gap_bottom, point.gap_top
            ))
        };

        // Render the midpoint as a line; bullish above zero, bearish below
        let value_fn = |point: &FvgPoint| {
            if point.is_bullish {
                point.midpoint
            } else {
                -point.midpoint
            }
        };

        let plot = LinePlot::new(value_fn)
            .stroke_width(1.5)
            .show_points(true)
            .point_radius_factor(0.3)
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
                let mut highs: Vec<f32> = Vec::new();
                let mut lows: Vec<f32> = Vec::new();
                let mut timestamps: Vec<UnixMs> = Vec::new();
                for (&t, dp) in &ts.datapoints {
                    highs.push(dp.kline.high.to_f32());
                    lows.push(dp.kline.low.to_f32());
                    timestamps.push(t);
                }
                if highs.len() < 3 {
                    return;
                }
                let gaps = ta::fair_value_gaps(&highs, &lows);
                let result: std::collections::BTreeMap<UnixMs, FvgPoint> = gaps
                    .iter()
                    .filter_map(|g| {
                        timestamps.get(g.index).map(|&t| {
                            (
                                t,
                                FvgPoint {
                                    gap_top: g.gap_top,
                                    gap_bottom: g.gap_bottom,
                                    midpoint: (g.gap_top + g.gap_bottom) / 2.0,
                                    is_bullish: g.is_bullish,
                                },
                            )
                        })
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let mut highs: Vec<f32> = Vec::new();
                let mut lows: Vec<f32> = Vec::new();
                for dp in &tick.datapoints {
                    highs.push(dp.kline.high.to_f32());
                    lows.push(dp.kline.low.to_f32());
                }
                if highs.len() < 3 {
                    return;
                }
                let gaps = ta::fair_value_gaps(&highs, &lows);
                let result: std::collections::BTreeMap<u64, FvgPoint> = gaps
                    .iter()
                    .filter_map(|g| {
                        let idx = g.index as u64;
                        Some((idx, FvgPoint {
                            gap_top: g.gap_top,
                            gap_bottom: g.gap_bottom,
                            midpoint: (g.gap_top + g.gap_bottom) / 2.0,
                            is_bullish: g.is_bullish,
                        }))
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for FvgIndicator {
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

        let points: Vec<(u64, &FvgPoint)> = match &self.data {
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
            if pt.gap_top == 0.0 && pt.gap_bottom == 0.0 {
                continue;
            }
            let x = ctx.interval_to_x(ts);
            let y_top = ctx.price_to_y(Price::from_f32_lossy(pt.gap_top));
            let y_bot = ctx.price_to_y(Price::from_f32_lossy(pt.gap_bottom));
            let color = if pt.is_bullish {
                Color::from_rgba(0.0, 0.8, 0.0, 0.25)
            } else {
                Color::from_rgba(0.8, 0.0, 0.0, 0.25)
            };
            frame.fill_rectangle(
                Point::new(x - 5.0, y_top.min(y_bot)),
                iced::Size::new(10.0, (y_top - y_bot).abs()),
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

    fn apply_config(&mut self, _config: &IndicatorConfig) {}
}