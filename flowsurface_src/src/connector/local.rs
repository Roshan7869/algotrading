use std::collections::VecDeque;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use exchange::adapter::{Event, StreamKind};
use exchange::{Kline, Timeframe, Trade, UnixMs, Volume};
use log;

struct FileStream {
    path: PathBuf,
    stream_kind: StreamKind,
    reader: Option<BufReader<fs::File>>,
    exhausted: bool,
}

pub struct LocalConnector {
    data_dir: PathBuf,
    streams: Vec<FileStream>,
    poll_interval: Duration,
    last_poll: Instant,
    event_batch: VecDeque<Event>,
    running: bool,
}

impl LocalConnector {
    pub fn new(data_dir: PathBuf, poll_interval_ms: u64) -> Self {
        LocalConnector {
            data_dir,
            streams: Vec::new(),
            poll_interval: Duration::from_millis(poll_interval_ms),
            last_poll: Instant::now(),
            event_batch: VecDeque::new(),
            running: false,
        }
    }

    pub fn register_stream(&mut self, kind: StreamKind) {
        let filename = match &kind {
            StreamKind::Kline {
                ticker_info,
                timeframe,
            } => {
                let ticker_str = ticker_info.ticker.to_string();
                format!("{}_{}_kline.jsonl", ticker_str, timeframe)
            }
            StreamKind::Trades { ticker_info } => {
                let ticker_str = ticker_info.ticker.to_string();
                format!("{}_trades.jsonl", ticker_str)
            }
            StreamKind::Depth { ticker_info, .. } => {
                let ticker_str = ticker_info.ticker.to_string();
                format!("{}_depth.jsonl", ticker_str)
            }
        };

        let path = self.data_dir.join(&filename);

        let fr = if path.exists() {
            let file = fs::File::open(&path).ok();
            Some(BufReader::new(file.unwrap()))
        } else {
            log::info!(
                "Local data file not found: {} (will skip)",
                path.display()
            );
            None
        };

        self.streams.push(FileStream {
            path,
            stream_kind: kind,
            reader: fr,
            exhausted: false,
        });
    }

    pub fn start(&mut self) {
        self.running = true;
        self.last_poll = Instant::now();
        log::info!(
            "LocalConnector started with {} streams from {}",
            self.streams.len(),
            self.data_dir.display()
        );
    }

    pub fn stop(&mut self) {
        self.running = false;
        log::info!("LocalConnector stopped");
    }

    pub fn tick(&mut self) -> Vec<Event> {
        if !self.running {
            return Vec::new();
        }

        let now = Instant::now();
        if now.duration_since(self.last_poll) < self.poll_interval {
            return Vec::new();
        }
        self.last_poll = now;

        let mut events = Vec::new();

        for stream in &mut self.streams {
            if stream.exhausted {
                continue;
            }

            let reader = match &mut stream.reader {
                Some(r) => r,
                None => continue,
            };

            let mut line = String::new();
            loop {
                line.clear();
                match reader.read_line(&mut line) {
                    Ok(0) => {
                        stream.exhausted = true;
                        log::info!(
                            "Local data file exhausted: {}",
                            stream.path.display()
                        );
                        break;
                    }
                    Ok(_) => {
                        let line = line.trim();
                        if line.is_empty() {
                            continue;
                        }

                        match parse_event_line(line, &stream.stream_kind) {
                            Ok(event) => events.push(event),
                            Err(e) => {
                                log::warn!(
                                    "Failed to parse line in {}: {}",
                                    stream.path.display(),
                                    e
                                );
                            }
                        }

                        if events.len() >= 100 {
                            return events;
                        }
                    }
                    Err(e) => {
                        log::error!(
                            "Error reading {}: {}",
                            stream.path.display(),
                            e
                        );
                        stream.exhausted = true;
                        break;
                    }
                }
            }
        }

        events
    }
}

fn parse_event_line(line: &str, stream_kind: &StreamKind) -> Result<Event, String> {
    let value: serde_json::Value =
        serde_json::from_str(line).map_err(|e| format!("JSON parse error: {}", e))?;

    match stream_kind {
        StreamKind::Kline {
            ticker_info,
            timeframe,
        } => {
            let ts = value["timestamp_ms"]
                .as_u64()
                .ok_or("missing timestamp_ms")?;
            let open = value["open"]
                .as_f64()
                .ok_or("missing open")? as f32;
            let high = value["high"]
                .as_f64()
                .ok_or("missing high")? as f32;
            let low = value["low"].as_f64().ok_or("missing low")? as f32;
            let close = value["close"]
                .as_f64()
                .ok_or("missing close")? as f32;
            let vol = value["volume"]
                .as_f64()
                .unwrap_or(0.0) as f32;

            let kline = Kline::new(
                UnixMs::new(ts),
                open,
                high,
                low,
                close,
                Volume::TotalOnly(exchange::unit::Qty::from_f32(vol)),
                ticker_info.min_ticksize,
            );

            Ok(Event::KlineReceived(*stream_kind, kline))
        }
        StreamKind::Trades { ticker_info } => {
            let ts = value["timestamp_ms"]
                .as_u64()
                .ok_or("missing timestamp_ms")?;
            let price = value["price"]
                .as_f64()
                .ok_or("missing price")? as f32;
            let qty = value["qty"].as_f64().ok_or("missing qty")? as f32;
            let is_sell = value["is_sell"].as_bool().unwrap_or(false);

            let trade = Trade {
                time: UnixMs::new(ts),
                is_sell,
                price: exchange::unit::price::Price::from_f32(price),
                qty: exchange::unit::Qty::from_f32(qty),
            };

            let trades: Box<[Trade]> = Box::new([trade]);

            let now = UnixMs::new(
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_millis() as u64,
            );

            Ok(Event::TradesReceived(*stream_kind, now, trades))
        }
        StreamKind::Depth { .. } => Err("Depth events not supported in local mode".to_string()),
    }
}
