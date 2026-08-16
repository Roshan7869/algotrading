use crate::candles::{Candle, CandleStore};
use crate::execution::Signal;
use crate::indicators::IndicatorValues;
use redis::AsyncCommands;
use serde::Serialize;
use std::sync::Arc;
use tokio::sync::Mutex;

#[derive(Debug, Clone, Serialize)]
pub struct CandleJson {
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

impl From<&Candle> for CandleJson {
    fn from(c: &Candle) -> Self {
        Self {
            open_time: c.open_time,
            close_time: c.close_time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume,
            quote_volume: c.quote_volume,
            is_closed: c.is_closed,
            trades: c.trades,
            taker_buy_volume: c.taker_buy_volume,
            taker_buy_quote_volume: c.taker_buy_quote_volume,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct SuperTrendJson {
    pub value: f32,
    pub direction: i8,
}

#[derive(Debug, Clone, Serialize)]
pub struct IndicatorUpdate {
    pub pair: String,
    pub timeframe: String,
    pub timestamp: u64,
    pub close: f64,
    pub sma_20: Option<f32>,
    pub sma_50: Option<f32>,
    pub sma_200: Option<f32>,
    pub ema_12: Option<f32>,
    pub ema_26: Option<f32>,
    pub rsi_14: Option<f32>,
    pub macd_line: Option<f32>,
    pub macd_signal: Option<f32>,
    pub macd_histogram: Option<f32>,
    pub bb_upper: Option<f32>,
    pub bb_middle: Option<f32>,
    pub bb_lower: Option<f32>,
    pub atr_14: Option<f32>,
    pub vwap: Option<f32>,
    pub volume_delta: f64,
    pub buy_vol: f64,
    pub sell_vol: f64,
    pub cvd: f64,
    pub delta_zscore: Option<f64>,
    pub super_trend: Option<SuperTrendJson>,
}

impl IndicatorUpdate {
    fn from_values(
        pair: &str,
        timeframe: &str,
        values: &IndicatorValues,
        latest_candle: &Candle,
    ) -> Self {
        let last = values.len().saturating_sub(1);

        let st = values.super_trend[last].map(|v| SuperTrendJson {
            value: v.abs(),
            direction: if v > 0.0 { 1 } else { -1 },
        });

        let (macd_line, macd_signal, macd_histogram) = match &values.macd[last] {
            Some(m) => (Some(m.macd_line), Some(m.signal), Some(m.histogram)),
            None => (None, None, None),
        };

        let (bb_upper, bb_middle, bb_lower) = match &values.bollinger[last] {
            Some(b) => (Some(b.upper), Some(b.middle), Some(b.lower)),
            None => (None, None, None),
        };

        Self {
            pair: pair.to_string(),
            timeframe: timeframe.to_string(),
            timestamp: latest_candle.close_time,
            close: latest_candle.close,
            sma_20: values.sma_20[last],
            sma_50: values.sma_50[last],
            sma_200: values.sma_200[last],
            ema_12: values.ema_12[last],
            ema_26: values.ema_26[last],
            rsi_14: values.rsi_14[last],
            macd_line,
            macd_signal,
            macd_histogram,
            bb_upper,
            bb_middle,
            bb_lower,
            atr_14: values.atr_14[last],
            vwap: values.vwap[last],
            volume_delta: values.volume_delta[last],
            buy_vol: values.buy_vol[last],
            sell_vol: values.sell_vol[last],
            cvd: values.cvd[last],
            delta_zscore: values.delta_zscore[last],
            super_trend: st,
        }
    }
}

pub struct RedisPublisher {
    redis_url: String,
    pair: String,
    timeframe: String,
    pub candles: Arc<Mutex<CandleStore>>,
}

impl RedisPublisher {
    pub fn new(
        redis_url: String,
        pair: String,
        timeframe: String,
        candles: Arc<Mutex<CandleStore>>,
    ) -> Self {
        Self { redis_url, pair, timeframe, candles }
    }

    pub async fn publish_candle(&self, candle: &Candle) -> Result<(), Box<dyn std::error::Error>> {
        let mut conn = redis::Client::open(self.redis_url.as_str())?
            .get_multiplexed_async_connection()
            .await?;

        let stream_key = format!("candles:{}:{}", self.pair.replace("/", "").to_lowercase(), self.timeframe);
        let json = serde_json::to_string(&CandleJson::from(candle))?;
        let _: () = conn.xadd(&stream_key, "*", &[("data", &json)]).await?;

        log::debug!("Published candle to {}", stream_key);
        Ok(())
    }

    pub async fn publish_indicators(&self) -> Result<(), Box<dyn std::error::Error>> {
        let store = self.candles.lock().await;
        let latest = match store.latest() {
            Some(c) => c.clone(),
            None => return Ok(()),
        };
        let values = crate::indicators::IndicatorsEngine::compute(&store);
        drop(store);

        let update = IndicatorUpdate::from_values(&self.pair, &self.timeframe, &values, &latest);

        let mut conn = redis::Client::open(self.redis_url.as_str())?
            .get_multiplexed_async_connection()
            .await?;

        let stream_key = format!("indicators:{}:{}", self.pair.replace("/", "").to_lowercase(), self.timeframe);
        let json = serde_json::to_string(&update)?;
        let _: () = conn.xadd(&stream_key, "*", &[("data", &json)]).await?;

        log::debug!("Published indicators to {}", stream_key);
        Ok(())
    }

    pub async fn publish_indicators_from_values(
        &self, values: &IndicatorValues, latest: &Candle,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let update = IndicatorUpdate::from_values(&self.pair, &self.timeframe, values, latest);

        let mut conn = redis::Client::open(self.redis_url.as_str())?
            .get_multiplexed_async_connection()
            .await?;

        let stream_key = format!("indicators:{}:{}", self.pair.replace("/", "").to_lowercase(), self.timeframe);
        let json = serde_json::to_string(&update)?;
        let _: () = conn.xadd(&stream_key, "*", &[("data", &json)]).await?;

        log::debug!("Published indicators to {}", stream_key);
        Ok(())
    }

    pub async fn publish_signal(&self, signal: &Signal) -> Result<(), Box<dyn std::error::Error>> {
        let mut conn = redis::Client::open(self.redis_url.as_str())?
            .get_multiplexed_async_connection()
            .await?;

        let stream_key = format!("signals:{}:{}", self.pair.replace("/", "").to_lowercase(), self.timeframe);
        let json = serde_json::to_string(&signal)?;
        let _: () = conn.xadd(&stream_key, "*", &[("data", &json)]).await?;

        log::info!("Published signal: {:?} at {}", signal.signal_type, signal.price);
        Ok(())
    }
}
