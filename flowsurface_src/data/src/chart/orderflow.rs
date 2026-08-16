use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize)]
pub struct Config {
    pub delta_aggr_seconds: u32,
    pub cvd_smoothing: u32,
    pub show_footprint_numbers: bool,
    /// Volume multiplier threshold for absorption detection.
    /// Bar absorbed if buy_or_sell_volume >= avg_volume * absorption_multiplier.
    /// Default: 1.5 (50% above average = strong absorption).
    pub absorption_multiplier: f32,
    /// Range multiplier threshold for absorption detection.
    /// Bar absorbed if candle_range <= avg_range * absorption_range_multiplier.
    /// Default: 0.5 (half or less of average range = compressed candle).
    pub absorption_range_multiplier: f32,
    /// Volume ratio threshold for exhaustion detection.
    /// Bar exhausted if min(buy, sell) / max(buy, sell) >= exhaustion_ratio.
    /// Default: 0.5 (50% counter-party volume = potential exhaustion).
    pub exhaustion_ratio: f32,
    /// Lookback window for Delta Z-Score normalization.
    /// Default: 20 bars.
    pub delta_zscore_lookback: u32,
    /// Rolling window for Imbalance Ratio smoothing.
    /// Default: 14 bars.
    pub imbalance_ratio_window: u32,
    pub color_bid: Color,
    pub color_ask: Color,
    pub color_cvd: Color,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            delta_aggr_seconds: 30,
            cvd_smoothing: 1,
            show_footprint_numbers: true,
            absorption_multiplier: 1.5,
            absorption_range_multiplier: 0.5,
            exhaustion_ratio: 0.5,
            delta_zscore_lookback: 20,
            imbalance_ratio_window: 14,
            color_bid: Color::Blue,
            color_ask: Color::Red,
            color_cvd: Color::Yellow,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize)]
pub enum Color {
    Blue,
    Red,
    Green,
    Yellow,
    Cyan,
    Magenta,
    Orange,
    White,
}

impl Color {
    pub fn to_iced(&self) -> iced_core::Color {
        match self {
            Color::Blue => iced_core::Color::from_rgb(0.13, 0.59, 0.95),
            Color::Red => iced_core::Color::from_rgb(0.96, 0.26, 0.21),
            Color::Green => iced_core::Color::from_rgb(0.30, 0.69, 0.31),
            Color::Yellow => iced_core::Color::from_rgb(1.0, 0.92, 0.23),
            Color::Cyan => iced_core::Color::from_rgb(0.0, 0.74, 0.83),
            Color::Magenta => iced_core::Color::from_rgb(0.91, 0.12, 0.39),
            Color::Orange => iced_core::Color::from_rgb(1.0, 0.60, 0.0),
            Color::White => iced_core::Color::WHITE,
        }
    }
}
