use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize)]
pub struct Config {
    pub value_area_pct: f32,
    pub show_naked_poc: bool,
    pub composite_mode: CompositeMode,
    pub profile_color: Color,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            value_area_pct: 70.0,
            show_naked_poc: true,
            composite_mode: CompositeMode::default(),
            profile_color: Color::Blue,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize, Default)]
pub enum CompositeMode {
    #[default]
    TotalVolume,
    DeltaVolume,
    TpoCount,
}

impl std::fmt::Display for CompositeMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CompositeMode::TotalVolume => write!(f, "Total Volume"),
            CompositeMode::DeltaVolume => write!(f, "Delta Volume"),
            CompositeMode::TpoCount => write!(f, "TPO Count"),
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
