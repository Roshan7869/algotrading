use crate::candles::CandleStore;
use data::chart::ta;
use serde::Serialize;

#[derive(Debug, Clone)]
pub struct IndicatorValues {
    pub sma_20: Vec<Option<f32>>,
    pub sma_50: Vec<Option<f32>>,
    pub sma_200: Vec<Option<f32>>,
    pub ema_12: Vec<Option<f32>>,
    pub ema_26: Vec<Option<f32>>,
    pub rsi_14: Vec<Option<f32>>,
    pub macd: Vec<Option<ta::MacdResult>>,
    pub bollinger: Vec<Option<ta::BollingerBands>>,
    pub atr_14: Vec<Option<f32>>,
    pub vwap: Vec<Option<f32>>,
    pub volume_delta: Vec<f64>,
    pub buy_vol: Vec<f64>,
    pub sell_vol: Vec<f64>,
    pub cvd: Vec<f64>,
    pub delta_zscore: Vec<Option<f64>>,
    pub super_trend: Vec<Option<f32>>,
}

impl IndicatorValues {
    pub fn len(&self) -> usize {
        self.sma_20.len()
    }

    pub fn new(count: usize) -> Self {
        Self {
            sma_20: vec![None; count],
            sma_50: vec![None; count],
            sma_200: vec![None; count],
            ema_12: vec![None; count],
            ema_26: vec![None; count],
            rsi_14: vec![None; count],
            macd: vec![None; count],
            bollinger: vec![None; count],
            atr_14: vec![None; count],
            vwap: vec![None; count],
            volume_delta: vec![0.0; count],
            buy_vol: vec![0.0; count],
            sell_vol: vec![0.0; count],
            cvd: vec![0.0; count],
            delta_zscore: vec![None; count],
            super_trend: vec![None; count],
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct IndicatorOutput {
    pub sma_20: Vec<Option<f32>>,
    pub sma_50: Vec<Option<f32>>,
    pub sma_200: Vec<Option<f32>>,
    pub ema_12: Vec<Option<f32>>,
    pub ema_26: Vec<Option<f32>>,
    pub rsi_14: Vec<Option<f32>>,
    pub macd_line: Vec<Option<f32>>,
    pub macd_signal: Vec<Option<f32>>,
    pub macd_histogram: Vec<Option<f32>>,
    pub bb_upper: Vec<Option<f32>>,
    pub bb_middle: Vec<Option<f32>>,
    pub bb_lower: Vec<Option<f32>>,
    pub atr_14: Vec<Option<f32>>,
    pub vwap: Vec<Option<f32>>,
    pub volume_delta: Vec<f64>,
    pub buy_vol: Vec<f64>,
    pub sell_vol: Vec<f64>,
    pub cvd: Vec<f64>,
    pub delta_zscore: Vec<Option<f64>>,
    pub super_trend: Vec<Option<f32>>,
}

impl IndicatorOutput {
    pub fn from_values(v: &IndicatorValues) -> Self {
        let count = v.len();
        let mut out = Self {
            sma_20: v.sma_20.clone(),
            sma_50: v.sma_50.clone(),
            sma_200: v.sma_200.clone(),
            ema_12: v.ema_12.clone(),
            ema_26: v.ema_26.clone(),
            rsi_14: v.rsi_14.clone(),
            macd_line: vec![None; count],
            macd_signal: vec![None; count],
            macd_histogram: vec![None; count],
            bb_upper: vec![None; count],
            bb_middle: vec![None; count],
            bb_lower: vec![None; count],
            atr_14: v.atr_14.clone(),
            vwap: v.vwap.clone(),
            volume_delta: v.volume_delta.clone(),
            buy_vol: v.buy_vol.clone(),
            sell_vol: v.sell_vol.clone(),
            cvd: v.cvd.clone(),
            delta_zscore: v.delta_zscore.clone(),
            super_trend: v.super_trend.clone(),
        };
        for i in 0..count {
            if let Some(m) = &v.macd[i] {
                out.macd_line[i] = Some(m.macd_line);
                out.macd_signal[i] = Some(m.signal);
                out.macd_histogram[i] = Some(m.histogram);
            }
            if let Some(b) = &v.bollinger[i] {
                out.bb_upper[i] = Some(b.upper);
                out.bb_middle[i] = Some(b.middle);
                out.bb_lower[i] = Some(b.lower);
            }
        }
        out
    }
}

pub struct IndicatorsEngine;

impl IndicatorsEngine {
    pub fn compute(store: &CandleStore) -> IndicatorValues {
        let candles = store.get_all();
        let count = candles.len();
        if count == 0 {
            return IndicatorValues::new(0);
        }

        let _opens: Vec<f32> = candles.iter().map(|c| c.open as f32).collect();
        let highs: Vec<f32> = candles.iter().map(|c| c.high as f32).collect();
        let lows: Vec<f32> = candles.iter().map(|c| c.low as f32).collect();
        let closes: Vec<f32> = candles.iter().map(|c| c.close as f32).collect();
        let volumes: Vec<f32> = candles.iter().map(|c| c.volume as f32).collect();
        let taker_buy: Vec<f64> = candles.iter().map(|c| c.taker_buy_volume).collect();

        let mut values = IndicatorValues::new(count);

        values.sma_20 = ta::sma_series(&closes, 20);
        values.sma_50 = ta::sma_series(&closes, 50);
        values.sma_200 = ta::sma_series(&closes, 200);
        values.ema_12 = ta::ema_series(&closes, 12);
        values.ema_26 = ta::ema_series(&closes, 26);
        values.rsi_14 = ta::rsi_series(&closes, 14);
        values.macd = ta::macd(&closes, 12, 26, 9);
        values.bollinger = ta::bollinger_series(&closes, 20, 2.0);
        values.atr_14 = ta::atr_series(&highs, &lows, &closes, 14);
        values.vwap = ta::vwap_series(&highs, &lows, &closes, &volumes, None);

        let atr_clone = values.atr_14.clone();
        Self::compute_volume_delta(&taker_buy, &volumes, &mut values);
        Self::compute_super_trend(&highs, &lows, &closes, &atr_clone, 10, 3.0, &mut values);

        values
    }

    fn compute_volume_delta(taker_buy: &[f64], volumes: &[f32], values: &mut IndicatorValues) {
        let n = taker_buy.len();
        let mut cumsum: f64 = 0.0;
        for i in 0..n {
            let vol = volumes[i] as f64;
            values.buy_vol[i] = taker_buy[i].max(0.0);
            values.sell_vol[i] = (vol - taker_buy[i]).max(0.0);
            let delta = 2.0 * taker_buy[i] - vol;
            values.volume_delta[i] = delta;
            cumsum += delta;
            values.cvd[i] = cumsum;
        }
        if n >= 20 {
            for i in 19..n {
                let start = i - 19;
                let slice: Vec<f64> = values.volume_delta[start..=i].iter().copied().collect();
                let mean: f64 = slice.iter().sum::<f64>() / slice.len() as f64;
                let variance: f64 = slice.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / slice.len() as f64;
                let std = variance.sqrt();
                values.delta_zscore[i] = Some(if std > 1e-10 { (values.volume_delta[i] - mean) / std } else { 0.0 });
            }
        }
    }

    fn compute_super_trend(
        highs: &[f32],
        lows: &[f32],
        closes: &[f32],
        atr_series_: &[Option<f32>],
        period: usize,
        multiplier: f32,
        values: &mut IndicatorValues,
    ) {
        let n = closes.len();
        if n < period + 1 {
            return;
        }

        let mut prev_upper: f32 = 0.0;
        let mut prev_lower: f32 = 0.0;
        let mut prev_trend: f32 = 1.0;
        let mut prev_close: f32 = 0.0;
        let mut initialized = false;

        for i in period..n {
            let atr_val = match atr_series_[i] {
                Some(v) => v,
                None => continue,
            };

            let hl2 = (highs[i] + lows[i]) / 2.0;

            let mut upper = hl2 + multiplier * atr_val;
            let mut lower = hl2 - multiplier * atr_val;

            if initialized {
                upper = if prev_close <= prev_upper {
                    prev_upper.min(upper)
                } else {
                    upper
                };
                lower = if prev_close >= prev_lower {
                    prev_lower.max(lower)
                } else {
                    lower
                };
            }

            let (trend_dir, super_trend_val) = if initialized && prev_trend < 0.0 && closes[i] > upper {
                (1.0, lower)
            } else if initialized && prev_trend > 0.0 && closes[i] < lower {
                (-1.0, upper)
            } else if initialized {
                (prev_trend, if prev_trend > 0.0 { lower } else { upper })
            } else {
                (1.0, lower)
            };

            prev_upper = upper;
            prev_lower = lower;
            prev_trend = trend_dir;
            prev_close = closes[i];
            initialized = true;

            values.super_trend[i] = Some(if trend_dir > 0.0 { super_trend_val } else { -super_trend_val });
        }
    }
}
