use crate::candles::CandleStore;
use futures_util::StreamExt;
use tokio::sync::Mutex;
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::Message;
use std::sync::Arc;

const FUTURES_WS: &str = "fstream.binance.com";
const SPOT_WS: &str = "stream.binance.com:9443";

pub struct BinanceWS {
    pair: String,
    timeframe: String,
    market: String,
    candles: Arc<Mutex<CandleStore>>,
    max_retries: u32,
    base_delay_ms: u64,
}

impl BinanceWS {
    pub fn new(pair: String, timeframe: String, market: String, max_candles: usize) -> Self {
        Self {
            pair,
            timeframe,
            market,
            candles: Arc::new(Mutex::new(CandleStore::new(max_candles))),
            max_retries: 5,
            base_delay_ms: 1000,
        }
    }

    pub fn candle_store(&self) -> Arc<Mutex<CandleStore>> {
        self.candles.clone()
    }

    fn stream_symbol(&self) -> String {
        self.pair.replace("/", "").replace(":USDT", "").to_lowercase()
    }

    fn stream_url(&self) -> String {
        let sym = self.stream_symbol();
        let tf = &self.timeframe;
        let host = match self.market.as_str() {
            "futures" => FUTURES_WS,
            _ => SPOT_WS,
        };
        format!("wss://{}/ws/{}@kline_{}/{}@aggTrade", host, sym, tf, sym)
    }

    pub async fn connect(&self) -> Result<(), Box<dyn std::error::Error>> {
        let url = self.stream_url();
        log::info!("Connecting to Binance WS: {}", url);

        let (ws_stream, _) = connect_async(&url).await?;
        log::info!("Binance WS connected: {} {}", self.pair, self.timeframe);

        let (_, mut read) = ws_stream.split();

        while let Some(msg) = read.next().await {
            match msg? {
                Message::Text(text) => {
                    if let Ok(data) = serde_json::from_str::<serde_json::Value>(&text) {
                        self.process_message(data).await;
                    }
                }
                Message::Binary(buf) => {
                    if let Ok(text) = String::from_utf8(buf.to_vec()) {
                        if let Ok(data) = serde_json::from_str::<serde_json::Value>(&text) {
                            self.process_message(data).await;
                        }
                    }
                }
                Message::Close(_) => {
                    log::warn!("Binance WS closed");
                    break;
                }
                Message::Ping(_) => {}
                _ => {}
            }
        }

        Ok(())
    }

    async fn process_message(&self, data: serde_json::Value) {
        if let Some(k) = data.get("k") {
            if let Some(candle) = CandleStore::from_kline_stream(k) {
                let mut store = self.candles.lock().await;
                store.insert(candle);
            }
        }
    }

    pub async fn run_with_reconnect(&self) {
        let mut attempt = 0;
        loop {
            match self.connect().await {
                Ok(()) => {
                    log::info!("Binance WS disconnected gracefully");
                    break;
                }
                Err(e) => {
                    attempt += 1;
                    log::error!("Binance WS error (attempt {}/{}): {}", attempt, self.max_retries, e);
                    if attempt >= self.max_retries {
                        log::error!("Max retries reached, giving up");
                        break;
                    }
                    let delay = self.base_delay_ms * (1u64 << (attempt - 1));
                    tokio::time::sleep(tokio::time::Duration::from_millis(delay)).await;
                }
            }
        }
    }
}
