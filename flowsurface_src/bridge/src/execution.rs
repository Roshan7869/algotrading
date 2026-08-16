use crate::indicators::IndicatorValues;
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub enum SignalType {
    Buy,
    Sell,
    CloseLong,
    CloseShort,
}

#[derive(Debug, Clone, Serialize)]
pub struct Signal {
    pub timestamp: u64,
    pub pair: String,
    pub signal_type: SignalType,
    pub price: f64,
    pub reason: String,
    pub confidence: f32,
    pub rsi: Option<f32>,
    pub super_trend_dir: Option<i8>,
    pub macd_histogram: Option<f32>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum PositionSide {
    Flat,
    Long,
    Short,
}

#[derive(Debug, Clone)]
pub struct Position {
    pub side: PositionSide,
    pub entry_price: f64,
    pub entry_time: u64,
    pub size: f64,
    pub unrealized_pnl: f64,
}

impl Position {
    pub fn new() -> Self {
        Self {
            side: PositionSide::Flat,
            entry_price: 0.0,
            entry_time: 0,
            size: 0.0,
            unrealized_pnl: 0.0,
        }
    }
}

pub struct SignalEngine {
    pair: String,
    position: Position,
    prev_st_direction: Option<i8>,
    prev_macd_histogram: f32,
    confidence_threshold: f32,
    pub signals: Vec<Signal>,
}

impl SignalEngine {
    pub fn new(pair: &str) -> Self {
        Self {
            pair: pair.to_string(),
            position: Position::new(),
            prev_st_direction: None,
            prev_macd_histogram: 0.0,
            confidence_threshold: 0.6,
            signals: Vec::new(),
        }
    }

    pub fn evaluate(&mut self, values: &IndicatorValues, current_price: f64) -> Vec<Signal> {
        let mut new_signals: Vec<Signal> = Vec::new();
        let last = values.len().saturating_sub(1);
        if last < 30 {
            return new_signals;
        }

        let rsi = values.rsi_14[last];
        let st_dir = values.super_trend[last].map(|v| if v > 0.0 { 1i8 } else { -1i8 });
        let macd_hist = values.macd[last].as_ref().map(|m| m.histogram);

        // SuperTrend flip signal
        if let Some(dir) = st_dir {
            if let Some(prev) = self.prev_st_direction {
                if prev != dir {
                    let (stype, reason) = match dir {
                        1 => {
                            self.position = Position::new();
                            self.position.side = PositionSide::Long;
                            self.position.entry_price = current_price;
                            (SignalType::Buy, "SuperTrend flipped UP".to_string())
                        }
                        -1 => {
                            self.position = Position::new();
                            self.position.side = PositionSide::Short;
                            self.position.entry_price = current_price;
                            (SignalType::Sell, "SuperTrend flipped DOWN".to_string())
                        }
                        _ => unreachable!(),
                    };
                    let signal = Signal {
                        timestamp: std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap()
                            .as_millis() as u64,
                        pair: self.pair.clone(),
                        signal_type: stype,
                        price: current_price,
                        reason,
                        confidence: 0.8,
                        rsi,
                        super_trend_dir: st_dir,
                        macd_histogram: macd_hist,
                    };
                    new_signals.push(signal);
                }
            }
        }
        self.prev_st_direction = st_dir;

        // MACD zero-line crossover
        if let Some(hist) = macd_hist {
            if self.prev_macd_histogram < 0.0 && hist > 0.0 {
                if self.position.side != PositionSide::Long {
                    new_signals.push(Signal {
                        timestamp: std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap()
                            .as_millis() as u64,
                        pair: self.pair.clone(),
                        signal_type: SignalType::Buy,
                        price: current_price,
                        reason: "MACD histogram turned positive".to_string(),
                        confidence: 0.6,
                        rsi,
                        super_trend_dir: st_dir,
                        macd_histogram: Some(hist),
                    });
                }
            } else if self.prev_macd_histogram > 0.0 && hist < 0.0 {
                if self.position.side != PositionSide::Short {
                    new_signals.push(Signal {
                        timestamp: std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap()
                            .as_millis() as u64,
                        pair: self.pair.clone(),
                        signal_type: SignalType::Sell,
                        price: current_price,
                        reason: "MACD histogram turned negative".to_string(),
                        confidence: 0.6,
                        rsi,
                        super_trend_dir: st_dir,
                        macd_histogram: Some(hist),
                    });
                }
            }
            self.prev_macd_histogram = hist;
        }

        // Update position PnL
        if self.position.side != PositionSide::Flat {
            self.position.unrealized_pnl = match self.position.side {
                PositionSide::Long => current_price - self.position.entry_price,
                PositionSide::Short => self.position.entry_price - current_price,
                _ => 0.0,
            };
        }

        self.signals.extend(new_signals.clone());
        new_signals
    }

    pub fn position_status(&self) -> &Position {
        &self.position
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_st_values(count: usize, st_val: f32) -> IndicatorValues {
        let mut v = IndicatorValues::new(count);
        for i in 0..count {
            v.super_trend[i] = Some(st_val);
            v.rsi_14[i] = Some(50.0);
        }
        v
    }

    #[test]
    fn test_signal_engine_flat_start() {
        let engine = SignalEngine::new("BTC/USDT");
        assert_eq!(engine.position_status().side, PositionSide::Flat);
    }

    #[test]
    fn test_super_trend_flip_buy() {
        let mut engine = SignalEngine::new("BTC/USDT");
        let v = make_st_values(50, -1.0);
        assert!(engine.evaluate(&v, 50000.0).is_empty());

        let v2 = make_st_values(50, 1.0);
        let signals = engine.evaluate(&v2, 51000.0);
        assert!(!signals.is_empty());
        assert_eq!(signals[0].signal_type, SignalType::Buy);
    }

    #[test]
    fn test_super_trend_flip_sell() {
        let mut engine = SignalEngine::new("BTC/USDT");
        let v = make_st_values(50, 1.0);
        assert!(engine.evaluate(&v, 50000.0).is_empty());

        let v2 = make_st_values(50, -1.0);
        let signals = engine.evaluate(&v2, 49000.0);
        assert!(!signals.is_empty());
        assert_eq!(signals[0].signal_type, SignalType::Sell);
    }
}
