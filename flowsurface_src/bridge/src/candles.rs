use std::collections::BTreeMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Candle {
    pub open_time: u64,
    pub close_time: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub quote_volume: f64,
    pub is_closed: bool,
    pub trades: u64,
    pub taker_buy_volume: f64,
    pub taker_buy_quote_volume: f64,
}

pub struct CandleStore {
    candles: BTreeMap<u64, Candle>,
    max: usize,
}

impl CandleStore {
    pub fn new(max: usize) -> Self {
        Self { candles: BTreeMap::new(), max }
    }

    pub fn insert(&mut self, candle: Candle) {
        self.candles.insert(candle.open_time, candle);
        self.trim();
    }

    pub fn get_all(&self) -> Vec<&Candle> {
        self.candles.values().collect()
    }

    pub fn latest(&self) -> Option<&Candle> {
        self.candles.values().last()
    }

    pub fn len(&self) -> usize {
        self.candles.len()
    }

    pub fn is_empty(&self) -> bool {
        self.candles.is_empty()
    }

    fn trim(&mut self) {
        while self.candles.len() > self.max + 100 {
            if let Some(key) = self.candles.keys().next().copied() {
                self.candles.remove(&key);
            }
        }
    }

    pub fn from_kline_stream(k: &serde_json::Value) -> Option<Candle> {
        let open_time = k["t"].as_u64()?;
        Some(Candle {
            open_time,
            close_time: k["T"].as_u64()?,
            open: k["o"].as_str()?.parse().ok()?,
            high: k["h"].as_str()?.parse().ok()?,
            low: k["l"].as_str()?.parse().ok()?,
            close: k["c"].as_str()?.parse().ok()?,
            volume: k["v"].as_str()?.parse().ok()?,
            quote_volume: k["q"].as_str()?.parse().ok()?,
            is_closed: k["x"].as_bool().unwrap_or(false),
            trades: k["n"].as_u64().unwrap_or(0),
            taker_buy_volume: k["V"].as_str().and_then(|s| s.parse().ok()).unwrap_or(0.0),
            taker_buy_quote_volume: k["Q"].as_str().and_then(|s| s.parse().ok()).unwrap_or(0.0),
        })
    }
}
