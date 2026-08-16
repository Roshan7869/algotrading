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

/// Candlestick pattern indicator point.
/// Each point stores a numeric code for the detected pattern type.
#[derive(Debug, Clone, Copy, Default)]
pub struct CandlePatternPoint {
    /// Pattern code: 1=WicklessBull, 2=WicklessBear, 3=Doji, 4=BullEngulf, 5=BearEngulf, 6=Hammer, 7=ShootingStar
    pub pattern_code: u8,
    /// Pattern magnitude (body size relative to ATR, used for bar height)
    pub magnitude: f32,
}

impl CandlePatternPoint {
    pub fn pattern_name(&self) -> &'static str {
        match self.pattern_code {
            1 => "Wickless Bull",
            2 => "Wickless Bear",
            3 => "Doji",
            4 => "Bull Engulf",
            5 => "Bear Engulf",
            6 => "Hammer",
            7 => "Shooting Star",
            _ => "Unknown",
        }
    }

    pub fn is_bullish(&self) -> bool {
        matches!(self.pattern_code, 1 | 4 | 6)
    }
}

pub struct CandlestickPatternIndicator {
    cache: Caches,
    data: BasisSeries<CandlePatternPoint>,
    wickless_threshold: f32,
    doji_threshold: f32,
    engulf_ratio: f32,
    hammer_lower_ratio: f32,
    star_upper_ratio: f32,
}

impl CandlestickPatternIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            wickless_threshold: 0.05,
            doji_threshold: 0.1,
            engulf_ratio: 0.5,
            hammer_lower_ratio: 2.0,
            star_upper_ratio: 2.0,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &CandlePatternPoint, _next: Option<&CandlePatternPoint>| {
            let dir = if point.is_bullish() { "▲" } else { "▼" };
            PlotTooltip::new(format!(
                "{} {}\nMagnitude: {:.2}",
                dir,
                point.pattern_name(),
                point.magnitude
            ))
        };

        let value_fn = |point: &CandlePatternPoint| {
            // Positive for bullish, negative for bearish
            if point.is_bullish() {
                point.magnitude
            } else {
                -point.magnitude
            }
        };

        let classify_fn = |point: &CandlePatternPoint| -> BarClass {
            if point.is_bullish() {
                BarClass::Overlay { overlay: point.magnitude }
            } else {
                BarClass::Overlay { overlay: -point.magnitude }
            }
        };

        let plot = BarPlot::new(value_fn, classify_fn)
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
                if closes.len() < 3 {
                    return;
                }
                let patterns = ta::detect_candlestick_patterns(
                    &opens,
                    &highs,
                    &lows,
                    &closes,
                    self.wickless_threshold,
                    self.doji_threshold,
                    self.engulf_ratio,
                    self.hammer_lower_ratio,
                    0.3,
                    self.star_upper_ratio,
                    0.3,
                );
                let result: std::collections::BTreeMap<UnixMs, CandlePatternPoint> = patterns
                    .iter()
                    .filter_map(|p| {
                        timestamps.get(p.index).map(|&t| {
                            (
                                t,
                                CandlePatternPoint {
                                    pattern_code: p.pattern_code,
                                    magnitude: p.magnitude,
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
                if closes.len() < 3 {
                    return;
                }
                let patterns = ta::detect_candlestick_patterns(
                    &opens,
                    &highs,
                    &lows,
                    &closes,
                    self.wickless_threshold,
                    self.doji_threshold,
                    self.engulf_ratio,
                    self.hammer_lower_ratio,
                    0.3,
                    self.star_upper_ratio,
                    0.3,
                );
                let result: std::collections::BTreeMap<u64, CandlePatternPoint> = patterns
                    .iter()
                    .filter_map(|p| {
                        let idx = p.index as u64;
                        Some((
                            idx,
                            CandlePatternPoint {
                                pattern_code: p.pattern_code,
                                magnitude: p.magnitude,
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

impl KlineIndicatorImpl for CandlestickPatternIndicator {
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

        let points: Vec<(u64, &CandlePatternPoint)> = match &self.data {
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
            if pt.pattern_code == 0 { continue; }
            let x = ctx.interval_to_x(ts);
            let y = ctx.price_to_y(Price::from_f32_lossy(pt.magnitude));
            let color = if pt.is_bullish() {
                Color::from_rgb(0.0, 0.8, 0.0)
            } else {
                Color::from_rgb(0.8, 0.0, 0.0)
            };
            let marker = Path::new(|builder| {
                builder.move_to(Point::new(x, y - 4.0));
                builder.line_to(Point::new(x + 4.0, y));
                builder.line_to(Point::new(x, y + 4.0));
                builder.line_to(Point::new(x - 4.0, y));
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
        if let IndicatorConfig::Candlestick {
            wickless_threshold, doji_threshold, engulf_ratio,
            hammer_lower_ratio, star_upper_ratio,
        } = config {
            self.wickless_threshold = *wickless_threshold;
            self.doji_threshold = *doji_threshold;
            self.engulf_ratio = *engulf_ratio;
            self.hammer_lower_ratio = *hammer_lower_ratio;
            self.star_upper_ratio = *star_upper_ratio;
        }
    }
}