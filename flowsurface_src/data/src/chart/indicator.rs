use std::collections::HashMap;
use std::fmt::{self, Debug, Display};

use enum_map::Enum;
use exchange::adapter::MarketKind;
use serde::{Deserialize, Serialize};

pub trait Indicator: PartialEq + Display + 'static {
    fn for_market(market: MarketKind) -> &'static [Self]
    where
        Self: Sized;
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize, Eq, Hash, Enum)]
pub enum KlineIndicator {
    Volume,
    CumulativeDelta,
    OpenInterest,
    Vwap,
    Alma,
    Rsi,
    Macd,
    BollingerBands,
    Aroon,
    Adx,
    Fvg,
    OrderBlock,
    Candlestick,
    PerCandleDelta,
    PerCandleAbsorption,
    PerCandleZScore,
    PerCandleImbalance,
    Lvn,
    Atr,
    PivotPoints,
    Mss,
    CvdDivergence,
    Rvol,
    Sma,
    Ema,
}

impl Indicator for KlineIndicator {
    fn for_market(market: MarketKind) -> &'static [Self] {
        match market {
            MarketKind::Spot => &Self::FOR_SPOT,
            MarketKind::LinearPerps | MarketKind::InversePerps => &Self::FOR_PERPS,
        }
    }
}

impl KlineIndicator {
    // Indicator togglers on UI menus depend on these arrays.
    // Every variant needs to be in either SPOT, PERPS or both.
        /// Indicators that can be used with spot market tickers
    const FOR_SPOT: [KlineIndicator; 22] = [
        KlineIndicator::Volume,
        KlineIndicator::CumulativeDelta,
        KlineIndicator::Vwap,
        KlineIndicator::Alma,
        KlineIndicator::Rsi,
        KlineIndicator::Macd,
        KlineIndicator::BollingerBands,
        KlineIndicator::Aroon,
        KlineIndicator::Fvg,
        KlineIndicator::OrderBlock,
        KlineIndicator::Candlestick,
        KlineIndicator::PerCandleDelta,
        KlineIndicator::PerCandleAbsorption,
        KlineIndicator::PerCandleZScore,
        KlineIndicator::PerCandleImbalance,
        KlineIndicator::Lvn,
        KlineIndicator::Atr,
        KlineIndicator::PivotPoints,
        KlineIndicator::Mss,
        KlineIndicator::Rvol,
        KlineIndicator::Sma,
        KlineIndicator::Ema,
    ];
    /// Indicators that can be used with perpetual swap market tickers
    const FOR_PERPS: [KlineIndicator; 25] = [
        KlineIndicator::Volume,
        KlineIndicator::CumulativeDelta,
        KlineIndicator::OpenInterest,
        KlineIndicator::Vwap,
        KlineIndicator::Alma,
        KlineIndicator::Rsi,
        KlineIndicator::Macd,
        KlineIndicator::BollingerBands,
        KlineIndicator::Aroon,
        KlineIndicator::Adx,
        KlineIndicator::Fvg,
        KlineIndicator::OrderBlock,
        KlineIndicator::Candlestick,
        KlineIndicator::PerCandleDelta,
        KlineIndicator::PerCandleAbsorption,
        KlineIndicator::PerCandleZScore,
        KlineIndicator::PerCandleImbalance,
        KlineIndicator::Lvn,
        KlineIndicator::Atr,
        KlineIndicator::PivotPoints,
        KlineIndicator::Mss,
        KlineIndicator::CvdDivergence,
        KlineIndicator::Rvol,
        KlineIndicator::Sma,
        KlineIndicator::Ema,
    ];
}

impl Display for KlineIndicator {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            KlineIndicator::Volume => write!(f, "Volume"),
            KlineIndicator::CumulativeDelta => write!(f, "CVD"),
            KlineIndicator::OpenInterest => write!(f, "Open Interest"),
            KlineIndicator::Vwap => write!(f, "VWAP"),
            KlineIndicator::Alma => write!(f, "ALMA"),
            KlineIndicator::Rsi => write!(f, "RSI"),
            KlineIndicator::Macd => write!(f, "MACD"),
            KlineIndicator::BollingerBands => write!(f, "BB"),
            KlineIndicator::Aroon => write!(f, "Aroon"),
            KlineIndicator::Adx => write!(f, "ADX"),
            KlineIndicator::Fvg => write!(f, "FVG"),
            KlineIndicator::OrderBlock => write!(f, "OB"),
            KlineIndicator::Candlestick => write!(f, "Patterns"),
            KlineIndicator::Lvn => write!(f, "LVN/HVN"),
            KlineIndicator::PerCandleDelta => write!(f, "Delta"),
            KlineIndicator::PerCandleAbsorption => write!(f, "Absorption"),
            KlineIndicator::PerCandleZScore => write!(f, "Delta Z-Score"),
            KlineIndicator::PerCandleImbalance => write!(f, "Imbalance"),
            KlineIndicator::Atr => write!(f, "ATR"),
            KlineIndicator::PivotPoints => write!(f, "Pivots"),
            KlineIndicator::Mss => write!(f, "MSS"),
            KlineIndicator::CvdDivergence => write!(f, "CVD Div"),
            KlineIndicator::Rvol => write!(f, "RVOL"),
            KlineIndicator::Sma => write!(f, "SMA"),
            KlineIndicator::Ema => write!(f, "EMA"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize, Eq, Enum)]
pub enum HeatmapIndicator {
    Volume,
}

impl Indicator for HeatmapIndicator {
    fn for_market(market: MarketKind) -> &'static [Self] {
        match market {
            MarketKind::Spot => &Self::FOR_SPOT,
            MarketKind::LinearPerps | MarketKind::InversePerps => &Self::FOR_PERPS,
        }
    }
}

impl HeatmapIndicator {
    // Indicator togglers on UI menus depend on these arrays.
    // Every variant needs to be in either SPOT, PERPS or both.
    /// Indicators that can be used with spot market tickers
    const FOR_SPOT: [HeatmapIndicator; 1] = [HeatmapIndicator::Volume];
    /// Indicators that can be used with perpetual swap market tickers
    const FOR_PERPS: [HeatmapIndicator; 1] = [HeatmapIndicator::Volume];
}

impl Display for HeatmapIndicator {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            HeatmapIndicator::Volume => write!(f, "Volume"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize, Eq, Enum)]
pub enum OrderFlowIndicator {
    Cvd,
    Delta,
    Absorption,
    DeltaZscore,
    ImbalanceRatio,
}

impl Indicator for OrderFlowIndicator {
    fn for_market(_market: MarketKind) -> &'static [Self] {
        &Self::ALL
    }
}

impl OrderFlowIndicator {
    const ALL: [OrderFlowIndicator; 5] = [
        OrderFlowIndicator::Cvd,
        OrderFlowIndicator::Delta,
        OrderFlowIndicator::Absorption,
        OrderFlowIndicator::DeltaZscore,
        OrderFlowIndicator::ImbalanceRatio,
    ];
}

impl Display for OrderFlowIndicator {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            OrderFlowIndicator::Cvd => write!(f, "CVD"),
            OrderFlowIndicator::Delta => write!(f, "Delta"),
            OrderFlowIndicator::Absorption => write!(f, "Absorption"),
            OrderFlowIndicator::DeltaZscore => write!(f, "Delta Z-Score"),
            OrderFlowIndicator::ImbalanceRatio => write!(f, "Imbalance Ratio"),
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub enum UiIndicator {
    Heatmap(HeatmapIndicator),
    Kline(KlineIndicator),
    OrderFlow(OrderFlowIndicator),
}

impl From<KlineIndicator> for UiIndicator {
    fn from(k: KlineIndicator) -> Self {
        UiIndicator::Kline(k)
    }
}

impl From<HeatmapIndicator> for UiIndicator {
    fn from(h: HeatmapIndicator) -> Self {
        UiIndicator::Heatmap(h)
    }
}

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
pub enum IndicatorConfig {
    Rsi {
        period: usize,
        overbought: f32,
        oversold: f32,
    },
    Macd {
        fast_period: usize,
        slow_period: usize,
        signal_period: usize,
    },
    BollingerBands {
        period: usize,
        stddev: f32,
    },
    Adx {
        period: usize,
        di_threshold: f32,
    },
    Aroon {
        period: usize,
    },
    Alma {
        period: usize,
        offset: f32,
        sigma: f32,
    },
    Volume {},
    CumulativeDelta {},
    OpenInterest {},
    Vwap {},
    Fvg {},
    OrderBlock {
        body_threshold: f32,
        impulse_count: usize,
        lookback: usize,
    },
    Candlestick {
        wickless_threshold: f32,
        doji_threshold: f32,
        engulf_ratio: f32,
        hammer_lower_ratio: f32,
        star_upper_ratio: f32,
    },
    Atr {
        period: usize,
    },
    PivotPoints {
        pivot_type: String,
    },
    PerCandleDelta {
        lookback: usize,
    },
    PerCandleAbsorption {
        vol_multiplier: f32,
        range_multiplier: f32,
        warmup: usize,
    },
    PerCandleZScore {
        lookback: usize,
        stddev_threshold: f32,
    },
    PerCandleImbalance {
        lookback: usize,
        threshold: f32,
    },
    Lvn {
        lvn_threshold: f32,
        hvn_threshold: f32,
        min_bins: usize,
        value_area_pct: f32,
    },
    Mss {
        swing_lookback: usize,
        confirmation_bars: usize,
    },
    CvdDivergence {
        lookback: usize,
    },
    Rvol {
        lookback: usize,
        high_threshold: f32,
        low_threshold: f32,
    },
    Sma {
        period: usize,
        color: String,
    },
    Ema {
        period: usize,
        color: String,
    },
}

impl IndicatorConfig {
    pub fn for_kline(kind: KlineIndicator) -> Self {
        match kind {
            KlineIndicator::Rsi => Self::Rsi { period: 14, overbought: 70.0, oversold: 30.0 },
            KlineIndicator::Macd => Self::Macd { fast_period: 12, slow_period: 26, signal_period: 9 },
            KlineIndicator::BollingerBands => Self::BollingerBands { period: 20, stddev: 2.0 },
            KlineIndicator::Adx => Self::Adx { period: 14, di_threshold: 25.0 },
            KlineIndicator::Aroon => Self::Aroon { period: 25 },
            KlineIndicator::Alma => Self::Alma { period: 9, offset: 0.85, sigma: 6.0 },
            KlineIndicator::OrderBlock => Self::OrderBlock { body_threshold: 0.5, impulse_count: 2, lookback: 60 },
            KlineIndicator::Candlestick => Self::Candlestick {
                wickless_threshold: 0.05, doji_threshold: 0.1, engulf_ratio: 0.5,
                hammer_lower_ratio: 2.0, star_upper_ratio: 2.0,
            },
            KlineIndicator::Volume => Self::Volume {},
            KlineIndicator::CumulativeDelta => Self::CumulativeDelta {},
            KlineIndicator::OpenInterest => Self::OpenInterest {},
            KlineIndicator::Vwap => Self::Vwap {},
            KlineIndicator::Fvg => Self::Fvg {},
            KlineIndicator::PerCandleDelta => Self::PerCandleDelta { lookback: 20 },
            KlineIndicator::PerCandleAbsorption => Self::PerCandleAbsorption {
                vol_multiplier: 1.5, range_multiplier: 0.5, warmup: 20,
            },
            KlineIndicator::PerCandleZScore => Self::PerCandleZScore {
                lookback: 20, stddev_threshold: 2.0,
            },
            KlineIndicator::PerCandleImbalance => Self::PerCandleImbalance {
                lookback: 14, threshold: 0.6,
            },
            KlineIndicator::Lvn => Self::Lvn {
                lvn_threshold: 0.5, hvn_threshold: 1.5, min_bins: 3, value_area_pct: 0.7,
            },
            KlineIndicator::Atr => Self::Atr { period: 14 },
            KlineIndicator::PivotPoints => Self::PivotPoints { pivot_type: "classic".to_string() },
            KlineIndicator::Mss => Self::Mss {
                swing_lookback: 5,
                confirmation_bars: 1,
            },
            KlineIndicator::CvdDivergence => Self::CvdDivergence { lookback: 20 },
            KlineIndicator::Rvol => Self::Rvol {
                lookback: 20,
                high_threshold: 2.0,
                low_threshold: 0.5,
            },
            KlineIndicator::Sma => Self::Sma { period: 20, color: "#FFD700".into() },
            KlineIndicator::Ema => Self::Ema { period: 9, color: "#FF69B4".into() },
        }
    }
}

pub type IndicatorConfigs = HashMap<KlineIndicator, IndicatorConfig>;
