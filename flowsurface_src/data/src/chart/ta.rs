//! Pure Rust f32 technical indicator math.
//!
//! Zero dependencies beyond std. All computations are rolling-window f32
//! arithmetic suitable for real-time streaming on a single core.
//! Designed to be called from indicator render modules in flowsurface.

// ---------------------------------------------------------------------------
// Moving Averages
// ---------------------------------------------------------------------------

/// Simple Moving Average over the last `period` values.
/// Returns `None` if `closes` has fewer than `period` elements.
pub fn sma(closes: &[f32], period: usize) -> Option<f32> {
    if closes.len() < period || period == 0 {
        return None;
    }
    let sum: f32 = closes[closes.len() - period..].iter().copied().sum();
    Some(sum / period as f32)
}

/// Full SMA series (one value per input close, `None` until `period` available).
pub fn sma_series(closes: &[f32], period: usize) -> Vec<Option<f32>> {
    closes
        .iter()
        .enumerate()
        .map(|(i, _)| {
            if i + 1 >= period {
                sma(&closes[..=i], period)
            } else {
                None
            }
        })
        .collect()
}

/// Exponential Moving Average. `prev_ema` is the seed (typically SMA of first `period` closes).
/// `multiplier = 2 / (period + 1)`.
pub fn ema_next(prev_ema: f32, close: f32, period: usize) -> f32 {
    let k = 2.0 / (period as f32 + 1.0);
    close * k + prev_ema * (1.0 - k)
}

/// Full EMA series. Seeds with SMA of first `period` closes.
pub fn ema_series(closes: &[f32], period: usize) -> Vec<Option<f32>> {
    if closes.len() < period || period == 0 {
        return vec![None; closes.len()];
    }
    let mut out = Vec::with_capacity(closes.len());
    for i in 0..period - 1 {
        out.push(None);
    }
    // Seed: SMA of first `period` closes
    let seed = sma(&closes[..period], period).unwrap();
    out.push(Some(seed));
    let mut prev = seed;
    for i in period..closes.len() {
        let val = ema_next(prev, closes[i], period);
        out.push(Some(val));
        prev = val;
    }
    out
}

/// ALMA (Arnaud Legoux Moving Average).
/// `offset` controls smoothness (0.85 default), `sigma` controls filter width (6.0 default).
/// Uses Gaussian weighting with offset shift.
pub fn alma(closes: &[f32], period: usize, offset: f32, sigma: f32) -> Option<f32> {
    if closes.len() < period || period == 0 {
        return None;
    }
    let m = offset * (period as f32 - 1.0);
    let s = period as f32 / sigma;
    let mut weight_sum = 0.0_f32;
    let mut norm = 0.0_f32;
    for i in 0..period {
        let idx = closes.len() - period + i;
        let w = (-(i as f32 - m) * (i as f32 - m) / (2.0 * s * s)).exp();
        weight_sum += closes[idx] * w;
        norm += w;
    }
    if norm == 0.0 {
        None
    } else {
        Some(weight_sum / norm)
    }
}

/// Full ALMA series.
pub fn alma_series(closes: &[f32], period: usize, offset: f32, sigma: f32) -> Vec<Option<f32>> {
    closes
        .iter()
        .enumerate()
        .map(|(i, _)| {
            if i + 1 >= period {
                alma(&closes[..=i], period, offset, sigma)
            } else {
                None
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Volatility
// ---------------------------------------------------------------------------

/// Average True Range over `period` bars.
/// `highs`, `lows`, `closes` must be same length. Needs `period` closes.
pub fn atr(highs: &[f32], lows: &[f32], closes: &[f32], period: usize) -> Option<f32> {
    if highs.len() < period + 1 || lows.len() < period + 1 || closes.len() < period + 1 {
        return None;
    }
    let n = highs.len();
    let mut tr_sum = 0.0_f32;
    for i in (n - period)..n {
        let hl = highs[i] - lows[i];
        let hc = (highs[i] - closes[i - 1]).abs();
        let lc = (lows[i] - closes[i - 1]).abs();
        tr_sum += hl.max(hc).max(lc);
    }
    Some(tr_sum / period as f32)
}

/// Full ATR series (first `period` values are `None`).
pub fn atr_series(highs: &[f32], lows: &[f32], closes: &[f32], period: usize) -> Vec<Option<f32>> {
    let n = closes.len();
    if n < 2 {
        return vec![None; n];
    }
    let mut out = Vec::with_capacity(n);
    out.push(None); // no TR for first bar
    let mut tr_vals = Vec::with_capacity(n - 1);
    for i in 1..n {
        let hl = highs[i] - lows[i];
        let hc = (highs[i] - closes[i - 1]).abs();
        let lc = (lows[i] - closes[i - 1]).abs();
        tr_vals.push(hl.max(hc).max(lc));
    }
    // Use SMA for initial, then Wilder's smoothing
    for i in 0..tr_vals.len() {
        if i + 1 < period {
            out.push(None);
        } else if i + 1 == period {
            let sum: f32 = tr_vals[..period].iter().sum();
            out.push(Some(sum / period as f32));
        } else {
            // Wilder's smoothing: ATR = (prev_atr * (period-1) + current_tr) / period
            let prev = out.last().and_then(|v| *v).unwrap_or(0.0);
            let val = (prev * (period - 1) as f32 + tr_vals[i]) / period as f32;
            out.push(Some(val));
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Bollinger Bands
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, Default)]
pub struct BollingerBands {
    pub middle: f32,
    pub upper: f32,
    pub lower: f32,
    pub bandwidth: f32,
    pub percent_b: f32,
}

/// Bollinger Bands: middle = SMA(period), upper/lower = middle ± k * stdev.
/// `k` is typically 2.0. Returns `None` if insufficient data.
pub fn bollinger(closes: &[f32], period: usize, k: f32) -> Option<BollingerBands> {
    if closes.len() < period || period == 0 {
        return None;
    }
    let mid = sma(closes, period)?;
    let slice = &closes[closes.len() - period..];
    let variance: f32 = slice.iter().map(|&v| (v - mid) * (v - mid)).sum::<f32>() / period as f32;
    let stdev = variance.sqrt();
    let upper = mid + k * stdev;
    let lower = mid - k * stdev;
    let current = *closes.last()?;
    let bandwidth = if mid != 0.0 { (upper - lower) / mid } else { 0.0 };
    let percent_b = if upper != lower {
        (current - lower) / (upper - lower)
    } else {
        0.5
    };
    Some(BollingerBands {
        middle: mid,
        upper,
        lower,
        bandwidth,
        percent_b,
    })
}

/// Full Bollinger Bands series.
pub fn bollinger_series(closes: &[f32], period: usize, k: f32) -> Vec<Option<BollingerBands>> {
    closes
        .iter()
        .enumerate()
        .map(|(i, _)| {
            if i + 1 >= period {
                bollinger(&closes[..=i], period, k)
            } else {
                None
            }
        })
        .collect()
}

/// Result struct for the `bollinger_bands()` convenience function.
/// Uses `mid` (matching indicator caller field name) instead of `middle`.
#[derive(Debug, Clone, Copy, Default)]
pub struct BollingerBandsResult {
    pub upper: f32,
    pub mid: f32,
    pub lower: f32,
    pub bandwidth: f32,
    pub percent_b: f32,
}

/// Full Bollinger Bands series (convenience wrapper called by indicator render modules).
/// Returns one `Option<BollingerBandsResult>` per input close — `None` until `period` bars available.
pub fn bollinger_bands(closes: &[f32], period: usize, k: f32) -> Vec<Option<BollingerBandsResult>> {
    bollinger_series(closes, period, k)
        .iter()
        .map(|v| {
            v.map(|bb| BollingerBandsResult {
                upper: bb.upper,
                mid: bb.middle,
                lower: bb.lower,
                bandwidth: bb.bandwidth,
                percent_b: bb.percent_b,
            })
        })
        .collect()
}

// ---------------------------------------------------------------------------
// RSI (Wilder's smoothing)
// ---------------------------------------------------------------------------

/// RSI of the *last* value using Wilder's exponential smoothing over `period` bars.
pub fn rsi_last(closes: &[f32], period: usize) -> Option<f32> {
    if closes.len() < period + 1 {
        return None;
    }
    // Initial average gain/loss from first `period` deltas
    let mut avg_gain = 0.0_f32;
    let mut avg_loss = 0.0_f32;
    for i in 1..=period {
        let delta = closes[i] - closes[i - 1];
        if delta > 0.0 {
            avg_gain += delta;
        } else {
            avg_loss += delta.abs();
        }
    }
    avg_gain /= period as f32;
    avg_loss /= period as f32;

    // Wilder's smoothing for remaining bars
    for i in (period + 1)..closes.len() {
        let delta = closes[i] - closes[i - 1];
        let gain = if delta > 0.0 { delta } else { 0.0 };
        let loss = if delta < 0.0 { delta.abs() } else { 0.0 };
        avg_gain = (avg_gain * (period - 1) as f32 + gain) / period as f32;
        avg_loss = (avg_loss * (period - 1) as f32 + loss) / period as f32;
    }

    if avg_loss == 0.0 {
        return Some(100.0);
    }
    let rs = avg_gain / avg_loss;
    Some(100.0 - 100.0 / (1.0 + rs))
}

/// Full RSI series.
pub fn rsi_series(closes: &[f32], period: usize) -> Vec<Option<f32>> {
    if closes.len() < period + 1 {
        return vec![None; closes.len()];
    }
    let mut out = Vec::with_capacity(closes.len());
    for _ in 0..period {
        out.push(None);
    }

    // Seed
    let mut avg_gain = 0.0_f32;
    let mut avg_loss = 0.0_f32;
    for i in 1..=period {
        let delta = closes[i] - closes[i - 1];
        if delta > 0.0 {
            avg_gain += delta;
        } else {
            avg_loss += delta.abs();
        }
    }
    avg_gain /= period as f32;
    avg_loss /= period as f32;

    let rsi_val = if avg_loss == 0.0 {
        100.0
    } else {
        100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    };
    out.push(Some(rsi_val));

    for i in (period + 1)..closes.len() {
        let delta = closes[i] - closes[i - 1];
        let gain = if delta > 0.0 { delta } else { 0.0 };
        let loss = if delta < 0.0 { delta.abs() } else { 0.0 };
        avg_gain = (avg_gain * (period - 1) as f32 + gain) / period as f32;
        avg_loss = (avg_loss * (period - 1) as f32 + loss) / period as f32;
        let rsi_val = if avg_loss == 0.0 {
            100.0
        } else {
            100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
        };
        out.push(Some(rsi_val));
    }
    out
}

/// Full RSI series (convenience wrapper).
/// Returns one `Option<f32>` per input close — `None` until `period` bars available.
/// This is the primary API called by indicator render modules.
pub fn rsi(closes: &[f32], period: usize) -> Vec<Option<f32>> {
    rsi_series(closes, period)
}

// ---------------------------------------------------------------------------
// MACD
// ---------------------------------------------------------------------------

/// Result struct for the MACD convenience function.
#[derive(Debug, Clone, Copy, Default)]
pub struct MacdResult {
    pub macd_line: f32,
    pub signal: f32,
    pub histogram: f32,
}

/// MACD convenience function that takes raw closes and periods.
/// Returns a `Vec<Option<MacdResult>>` — one per input close.
/// Internally computes fast EMA, slow EMA, then signal line.
pub fn macd(closes: &[f32], fast_period: usize, slow_period: usize, signal_period: usize) -> Vec<Option<MacdResult>> {
    let fast_ema = ema_series(closes, fast_period);
    let slow_ema = ema_series(closes, slow_period);
    let raw = macd_series(&fast_ema, &slow_ema, signal_period);
    // Convert MacdValue → MacdResult (same fields, different struct name for API clarity)
    raw.iter().map(|v| v.map(|mv| MacdResult {
        macd_line: mv.macd_line,
        signal: mv.signal,
        histogram: mv.histogram,
    })).collect()
}

#[derive(Debug, Clone, Copy, Default)]
pub struct MacdValue {
    pub macd_line: f32,
    pub signal: f32,
    pub histogram: f32,
}

/// MACD from pre-computed EMA series.
/// `fast_ema`, `slow_ema`, `signal_ema` are aligned (same length, `None` where insufficient).
pub fn macd_series(
    fast_ema: &[Option<f32>],
    slow_ema: &[Option<f32>],
    signal_period: usize,
) -> Vec<Option<MacdValue>> {
    let n = fast_ema.len();
    let mut out = Vec::with_capacity(n);
    // Collect MACD line values where both EMAs are available
    let mut macd_vals: Vec<f32> = Vec::new();
    for i in 0..n {
        match (fast_ema[i], slow_ema[i]) {
            (Some(f), Some(s)) => {
                macd_vals.push(f - s);
            }
            _ => {
                out.push(None);
            }
        }
    }
    // Now compute signal line (EMA of macd_vals) and histogram
    let macd_start = out.len(); // index where macd_vals begins
    if macd_vals.is_empty() {
        return vec![None; n];
    }
    // Signal: EMA of MACD line
    let k = 2.0 / (signal_period as f32 + 1.0);
    // Seed signal as SMA of first `signal_period` MACD values
    if macd_vals.len() < signal_period {
        // Not enough for signal — output MACD line only
        let offset = out.len();
        for _ in 0..macd_vals.len() {
            out.push(None);
        }
        // pad to length n
        while out.len() < n {
            out.push(None);
        }
        return out;
    }
    let seed_signal: f32 = macd_vals[..signal_period].iter().sum::<f32>() / signal_period as f32;
    // First signal_period MACD values → output None (not enough for signal)
    for _ in 0..signal_period - 1 {
        // We already have the macd_vals from 0..signal_period-1 but no signal yet
        // Actually we need to emit from the start. Let me redo this properly.
    }
    // Reset and redo properly
    out.clear();
    let mut macd_line_vals: Vec<Option<f32>> = Vec::with_capacity(n);
    for i in 0..n {
        match (fast_ema.get(i).copied().flatten(), slow_ema.get(i).copied().flatten()) {
            (Some(f), Some(s)) => macd_line_vals.push(Some(f - s)),
            _ => macd_line_vals.push(None),
        }
    }
    // Signal: EMA of non-None MACD values
    let mut sig = 0.0_f32;
    let mut sig_initialized = false;
    let mut valid_count = 0usize;
    for i in 0..n {
        if let Some(mv) = macd_line_vals[i] {
            valid_count += 1;
            if !sig_initialized {
                if valid_count >= signal_period {
                    // Compute seed SMA from the last signal_period valid MACD values
                    let mut vals_for_seed: Vec<f32> = Vec::new();
                    for j in 0..=i {
                        if let Some(v) = macd_line_vals[j] {
                            vals_for_seed.push(v);
                        }
                    }
                    sig = vals_for_seed.iter().sum::<f32>() / vals_for_seed.len() as f32;
                    sig_initialized = true;
                }
            }
            if sig_initialized {
                sig = mv * k + sig * (1.0 - k);
            }
            let hist = mv - sig;
            out.push(Some(MacdValue { macd_line: mv, signal: sig, histogram: hist }));
        } else {
            out.push(None);
        }
    }
    out
}

#[derive(Debug, Clone, Copy, Default)]
pub struct PivotPoint {
    pub pivot: f32,
    pub r1: f32,
    pub r2: f32,
    pub r3: f32,
    pub s1: f32,
    pub s2: f32,
    pub s3: f32,
}

/// Classic pivot point calculation from prior candle H/L/C.
pub fn pivot_points_series(
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
) -> Vec<Option<PivotPoint>> {
    let n = closes.len();
    if n < 2 {
        return vec![None; n];
    }
    let mut out = Vec::with_capacity(n);
    out.push(None);
    for i in 1..n {
        let h = highs[i - 1];
        let l = lows[i - 1];
        let c = closes[i - 1];
        let pp = (h + l + c) / 3.0;
        let range = h - l;
        out.push(Some(PivotPoint {
            pivot: pp,
            r1: 2.0 * pp - l,
            r2: pp + range,
            r3: h + 2.0 * (pp - l),
            s1: 2.0 * pp - h,
            s2: pp - range,
            s3: l - 2.0 * (h - pp),
        }));
    }
    out
}

// ---------------------------------------------------------------------------
// LVN / HVN (Low/High Volume Node) Detection
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy)]
pub struct LvnZone {
    pub price_low: f32,
    pub price_high: f32,
    pub is_lvn: bool,
}

/// Detect LVN (Low Volume Node) and HVN (High Volume Node) zones from OHLCV data.
///
/// Algorithm: bin volume by price level, classify bins below `lvn_threshold × mean`
/// as LVN and above `hvn_threshold × mean` as HVN, cluster contiguous bins,
/// filter by `min_bins`.
pub fn detect_lvn_hvn(
    highs: &[f32],
    lows: &[f32],
    volumes: &[f32],
    num_bins: usize,
    lvn_threshold: f32,
    hvn_threshold: f32,
    min_bins: usize,
) -> Vec<LvnZone> {
    if highs.is_empty() || num_bins < 2 {
        return vec![];
    }
    let min_price = lows.iter().copied().fold(f32::INFINITY, f32::min);
    let max_price = highs.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let range = max_price - min_price;
    if range <= 0.0 {
        return vec![];
    }
    let bin_size = range / num_bins as f32;
    let mut bin_volumes = vec![0.0_f32; num_bins];

    for i in 0..highs.len() {
        let low_bin = ((lows[i] - min_price) / bin_size).floor() as usize;
        let high_bin = ((highs[i] - min_price) / bin_size).ceil() as usize;
        let span = (high_bin - low_bin).max(1);
        for b in low_bin.min(num_bins - 1)..=high_bin.min(num_bins - 1) {
            bin_volumes[b] += volumes[i] / span as f32;
        }
    }

    let mean_vol: f32 = bin_volumes.iter().sum::<f32>() / num_bins as f32;
    if mean_vol <= 0.0 {
        return vec![];
    }

    let mut zones: Vec<LvnZone> = Vec::new();
    let mut current: Option<(usize, usize, bool)> = None;

    for b in 0..num_bins {
        let is_lvn = bin_volumes[b] < mean_vol * lvn_threshold;
        let is_hvn = bin_volumes[b] > mean_vol * hvn_threshold;

        match current {
            Some((start, _, lvn)) if (lvn && is_lvn) || (!lvn && is_hvn) => {
                current = Some((start, b, lvn));
            }
            Some((start, end, lvn)) => {
                if end - start + 1 >= min_bins {
                    zones.push(LvnZone {
                        price_low: min_price + start as f32 * bin_size,
                        price_high: min_price + (end + 1) as f32 * bin_size,
                        is_lvn: lvn,
                    });
                }
                current = if is_lvn {
                    Some((b, b, true))
                } else if is_hvn {
                    Some((b, b, false))
                } else {
                    None
                };
            }
            None => {
                if is_lvn {
                    current = Some((b, b, true));
                } else if is_hvn {
                    current = Some((b, b, false));
                }
            }
        }
    }

    if let Some((start, end, lvn)) = current {
        if end - start + 1 >= min_bins {
            zones.push(LvnZone {
                price_low: min_price + start as f32 * bin_size,
                price_high: min_price + (end + 1) as f32 * bin_size,
                is_lvn: lvn,
            });
        }
    }

    zones
}

// ---------------------------------------------------------------------------
// Aroon
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, Default)]
pub struct AroonValue {
    pub up: f32,   // 0-100
    pub down: f32, // 0-100
    pub oscillator: f32, // up - down
}

/// Aroon of the *last* value. Period = lookback for highest high / lowest low.
pub fn aroon_last(highs: &[f32], lows: &[f32], period: usize) -> Option<AroonValue> {
    if highs.len() < period + 1 || lows.len() < period + 1 {
        return None;
    }
    let n = highs.len();
    let slice_highs = &highs[n - period - 1..];
    let slice_lows = &lows[n - period - 1..];
    let mut high_idx = 0usize;
    let mut low_idx = 0usize;
    for (i, &h) in slice_highs.iter().enumerate() {
        if h >= slice_highs[high_idx] {
            high_idx = i;
        }
    }
    for (i, &l) in slice_lows.iter().enumerate() {
        if l <= slice_lows[low_idx] {
            low_idx = i;
        }
    }
    let bars_since_high = period - high_idx;
    let bars_since_low = period - low_idx;
    let up = ((period - bars_since_high) as f32 / period as f32) * 100.0;
    let down = ((period - bars_since_low) as f32 / period as f32) * 100.0;
    Some(AroonValue {
        up,
        down,
        oscillator: up - down,
    })
}

/// Full Aroon series.
pub fn aroon_series(highs: &[f32], lows: &[f32], period: usize) -> Vec<Option<AroonValue>> {
    if highs.len() < period + 1 {
        return vec![None; highs.len()];
    }
    let mut out = vec![None; period];
    for i in period..highs.len() {
        out.push(aroon_last(&highs[..=i], &lows[..=i], period));
    }
    out
}

/// Full Aroon series (convenience wrapper called by indicator render modules).
pub fn aroon(highs: &[f32], lows: &[f32], period: usize) -> Vec<Option<AroonValue>> {
    aroon_series(highs, lows, period)
}

// ---------------------------------------------------------------------------
// ADX (Average Directional Index)
// ---------------------------------------------------------------------------

/// ADX using Wilder's smoothing. Returns (adx, plus_di, minus_di).
/// Needs at least `period * 2 + 1` bars for initial seeding.
pub fn adx_last(highs: &[f32], lows: &[f32], closes: &[f32], period: usize) -> Option<(f32, f32, f32)> {
    let n = highs.len();
    if n < period * 2 + 1 {
        return None;
    }
    // Compute +DM, -DM, TR for all bars
    let mut plus_dm: Vec<f32> = Vec::with_capacity(n - 1);
    let mut minus_dm: Vec<f32> = Vec::with_capacity(n - 1);
    let mut tr: Vec<f32> = Vec::with_capacity(n - 1);
    for i in 1..n {
        let up_move = highs[i] - highs[i - 1];
        let down_move = lows[i - 1] - lows[i];
        plus_dm.push(if up_move > down_move && up_move > 0.0 { up_move } else { 0.0 });
        minus_dm.push(if down_move > up_move && down_move > 0.0 { down_move } else { 0.0 });
        let hl = highs[i] - lows[i];
        let hc = (highs[i] - closes[i - 1]).abs();
        let lc = (lows[i] - closes[i - 1]).abs();
        tr.push(hl.max(hc).max(lc));
    }
    if tr.len() < period {
        return None;
    }
    // Wilder smooth +DM, -DM, TR
    let smooth = |vals: &[f32], period: usize| -> Vec<f32> {
        let mut out = Vec::with_capacity(vals.len());
        let seed: f32 = vals[..period].iter().sum();
        out.push(seed);
        let mut prev = seed;
        for i in period..vals.len() {
            let val = prev - prev / period as f32 + vals[i];
            out.push(val);
            prev = val;
        }
        out
    };
    let s_plus = smooth(&plus_dm, period);
    let s_minus = smooth(&minus_dm, period);
    let s_tr = smooth(&tr, period);
    // +DI, -DI
    let min_len = s_plus.len().min(s_minus.len()).min(s_tr.len());
    let mut dx_vals: Vec<f32> = Vec::with_capacity(min_len);
    for i in 0..min_len {
        let plus_di = if s_tr[i] != 0.0 {
            100.0 * s_plus[i] / s_tr[i]
        } else {
            0.0
        };
        let minus_di = if s_tr[i] != 0.0 {
            100.0 * s_minus[i] / s_tr[i]
        } else {
            0.0
        };
        let diff = (plus_di - minus_di).abs();
        let sum = plus_di + minus_di;
        let dx = if sum != 0.0 { 100.0 * diff / sum } else { 0.0 };
        dx_vals.push(dx);
    }
    if dx_vals.len() < period {
        return None;
    }
    // ADX = Wilder smooth of DX
    let adx_seed: f32 = dx_vals[..period].iter().sum::<f32>() / period as f32;
    let mut adx_val = adx_seed;
    for i in period..dx_vals.len() {
        adx_val = (adx_val * (period - 1) as f32 + dx_vals[i]) / period as f32;
    }
    // Final +DI / -DI
    let final_plus_di = if s_tr.last().copied().unwrap_or(0.0) != 0.0 {
        100.0 * s_plus.last().copied().unwrap_or(0.0) / s_tr.last().copied().unwrap_or(1.0)
    } else {
        0.0
    };
    let final_minus_di = if s_tr.last().copied().unwrap_or(0.0) != 0.0 {
        100.0 * s_minus.last().copied().unwrap_or(0.0) / s_tr.last().copied().unwrap_or(1.0)
    } else {
        0.0
    };
    Some((adx_val, final_plus_di, final_minus_di))
}

/// Struct result for ADX series, with named fields matching indicator caller expectations.
#[derive(Debug, Clone, Copy, Default)]
pub struct AdxValue {
    pub adx: f32,
    pub plus_di: f32,
    pub minus_di: f32,
}

/// ADX of the *last* value — returns struct with named fields.
pub fn adx_last_struct(highs: &[f32], lows: &[f32], closes: &[f32], period: usize) -> Option<AdxValue> {
    adx_last(highs, lows, closes, period).map(|(a, p, m)| AdxValue { adx: a, plus_di: p, minus_di: m })
}

/// Full ADX series (convenience wrapper called by indicator render modules).
/// Returns one `Option<AdxValue>` per input bar — `None` until enough bars.
pub fn adx(highs: &[f32], lows: &[f32], closes: &[f32], period: usize) -> Vec<Option<AdxValue>> {
    let n = highs.len();
    let min_bars = period * 2 + 1;
    if n < min_bars {
        return vec![None; n];
    }
    let mut out = vec![None; min_bars - 1];
    for i in min_bars..=n {
        out.push(adx_last_struct(&highs[..i], &lows[..i], &closes[..i], period));
    }
    out
}

// ---------------------------------------------------------------------------
// VWAP (Volume-Weighted Average Price)
// ---------------------------------------------------------------------------

/// VWAP from OHLCV arrays. Accumulates typical price * volume, divides by cumulative volume.
/// Intraday reset should be handled by the caller (pass only today's bars).
pub fn vwap(
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    volumes: &[f32],
) -> Option<f32> {
    let n = closes.len();
    if n == 0 || highs.len() != n || lows.len() != n || volumes.len() != n {
        return None;
    }
    let mut cum_tp_vol = 0.0_f32;
    let mut cum_vol = 0.0_f32;
    for i in 0..n {
        let typical = (highs[i] + lows[i] + closes[i]) / 3.0;
        cum_tp_vol += typical * volumes[i];
        cum_vol += volumes[i];
    }
    if cum_vol == 0.0 {
        None
    } else {
        Some(cum_tp_vol / cum_vol)
    }
}

/// Rolling VWAP series. Each point[i] = VWAP from max(0, i-window+1)..=i.
/// `window = None` means cumulative (typical intraday VWAP).
pub fn vwap_series(
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    volumes: &[f32],
    window: Option<usize>,
) -> Vec<Option<f32>> {
    let n = closes.len();
    let mut out = Vec::with_capacity(n);
    let mut cum_tp_vol = 0.0_f32;
    let mut cum_vol = 0.0_f32;
    // Rolling window ring buffer for partial reset
    match window {
        None => {
            // Cumulative VWAP (intraday style)
            for i in 0..n {
                let typical = (highs[i] + lows[i] + closes[i]) / 3.0;
                cum_tp_vol += typical * volumes[i];
                cum_vol += volumes[i];
                if cum_vol == 0.0 {
                    out.push(None);
                } else {
                    out.push(Some(cum_tp_vol / cum_vol));
                }
            }
        }
        Some(w) => {
            // Rolling window VWAP
            let mut ring_tp_vol = Vec::with_capacity(w);
            let mut ring_vol = Vec::with_capacity(w);
            for i in 0..n {
                let typical = (highs[i] + lows[i] + closes[i]) / 3.0;
                if ring_tp_vol.len() == w {
                    cum_tp_vol -= ring_tp_vol.remove(0);
                    cum_vol -= ring_vol.remove(0);
                }
                ring_tp_vol.push(typical * volumes[i]);
                ring_vol.push(volumes[i]);
                cum_tp_vol += typical * volumes[i];
                cum_vol += volumes[i];
                if cum_vol == 0.0 {
                    out.push(None);
                } else {
                    out.push(Some(cum_tp_vol / cum_vol));
                }
            }
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Order Flow Extensions
// ---------------------------------------------------------------------------

/// Delta Z-Score: (current_delta - mean_delta) / stdev_delta over `lookback` bars.
/// Used to detect unusual aggressive flow (|z| > 2 = significant).
pub fn delta_zscore(deltas: &[f32], lookback: usize) -> Option<f32> {
    if deltas.len() < lookback || lookback < 2 {
        return None;
    }
    let slice = &deltas[deltas.len() - lookback..];
    let mean: f32 = slice.iter().sum::<f32>() / lookback as f32;
    let variance: f32 = slice.iter().map(|&d| (d - mean) * (d - mean)).sum::<f32>() / (lookback - 1) as f32;
    let stdev = variance.sqrt();
    if stdev == 0.0 {
        return Some(0.0);
    }
    let current = *slice.last()?;
    Some((current - mean) / stdev)
}

/// Full delta z-score series.
pub fn delta_zscore_series(deltas: &[f32], lookback: usize) -> Vec<Option<f32>> {
    deltas
        .iter()
        .enumerate()
        .map(|(i, _)| {
            if i + 1 >= lookback {
                delta_zscore(&deltas[..=i], lookback)
            } else {
                None
            }
        })
        .collect()
}

/// Imbalance Ratio: buy_volume / sell_volume per bar.
/// Values > 1 = buying dominance, < 1 = selling dominance.
pub fn imbalance_ratio(buy_volumes: &[f32], sell_volumes: &[f32]) -> Option<f32> {
    if buy_volumes.is_empty() || sell_volumes.is_empty() || buy_volumes.len() != sell_volumes.len() {
        return None;
    }
    let buy: f32 = buy_volumes.iter().sum();
    let sell: f32 = sell_volumes.iter().sum();
    if sell == 0.0 {
        return if buy > 0.0 { Some(f32::MAX) } else { Some(1.0) };
    }
    Some(buy / sell)
}

/// Imbalance ratio series (rolling per-bar).
pub fn imbalance_ratio_series(
    buy_volumes: &[f32],
    sell_volumes: &[f32],
    lookback: usize,
) -> Vec<Option<f32>> {
    let n = buy_volumes.len();
    if n != sell_volumes.len() {
        return vec![None; n];
    }
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        if i + 1 < lookback {
            out.push(None);
        } else {
            let start = i + 1 - lookback;
            out.push(imbalance_ratio(&buy_volumes[start..=i], &sell_volumes[start..=i]));
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Support / Resistance Detection
// ---------------------------------------------------------------------------

/// Swing point detected from N-bar fractals.
#[derive(Debug, Clone, Copy)]
pub struct SwingPoint {
    pub index: usize,
    pub price: f32,
    pub is_high: bool, // true = swing high (resistance), false = swing low (support)
}

/// Detect swing highs and lows using N-bar fractal pattern.
/// A swing high: high[i] > all highs in [i-n..i-1] AND high[i] > all highs in [i+1..i+n]
pub fn swing_points(highs: &[f32], lows: &[f32], n: usize) -> Vec<SwingPoint> {
    let len = highs.len();
    if len < 2 * n + 1 {
        return vec![];
    }
    let mut points = Vec::new();
    for i in n..len - n {
        // Check swing high
        let mut is_high = true;
        for j in (i - n)..i {
            if highs[j] >= highs[i] {
                is_high = false;
                break;
            }
        }
        if is_high {
            for j in (i + 1)..=i + n {
                if highs[j] >= highs[i] {
                    is_high = false;
                    break;
                }
            }
        }
        if is_high {
            points.push(SwingPoint {
                index: i,
                price: highs[i],
                is_high: true,
            });
            continue;
        }
        // Check swing low
        let mut is_low = true;
        for j in (i - n)..i {
            if lows[j] <= lows[i] {
                is_low = false;
                break;
            }
        }
        if is_low {
            for j in (i + 1)..=i + n {
                if lows[j] <= lows[i] {
                    is_low = false;
                    break;
                }
            }
        }
        if is_low {
            points.push(SwingPoint {
                index: i,
                price: lows[i],
                is_high: false,
            });
        }
    }
    points
}

/// Pivot Points (Classic). `high`, `low`, `close` = previous period values.
#[derive(Debug, Clone, Copy)]
pub struct PivotPoints {
    pub pp: f32,     // Pivot Point = (H + L + C) / 3
    pub r1: f32,    // R1 = 2*PP - L
    pub r2: f32,    // R2 = PP + (H - L)
    pub r3: f32,    // R3 = H + 2*(PP - L)
    pub s1: f32,    // S1 = 2*PP - H
    pub s2: f32,    // S2 = PP - (H - L)
    pub s3: f32,    // S3 = L - 2*(H - PP)
}

impl PivotPoints {
    pub fn classic(high: f32, low: f32, close: f32) -> Self {
        let pp = (high + low + close) / 3.0;
        PivotPoints {
            pp,
            r1: 2.0 * pp - low,
            r2: pp + (high - low),
            r3: high + 2.0 * (pp - low),
            s1: 2.0 * pp - high,
            s2: pp - (high - low),
            s3: low - 2.0 * (high - pp),
        }
    }

    pub fn fibonacci(high: f32, low: f32, close: f32) -> Self {
        let pp = (high + low + close) / 3.0;
        let range = high - low;
        PivotPoints {
            pp,
            r1: pp + 0.382 * range,
            r2: pp + 0.618 * range,
            r3: pp + 1.0 * range,
            s1: pp - 0.382 * range,
            s2: pp - 0.618 * range,
            s3: pp - 1.0 * range,
        }
    }

    pub fn camarilla(high: f32, low: f32, close: f32) -> Self {
        let pp = (high + low + close) / 3.0;
        let range = high - low;
        PivotPoints {
            pp,
            r1: close + range * 1.1 / 12.0,
            r2: close + range * 1.1 / 6.0,
            r3: close + range * 1.1 / 4.0,
            s1: close - range * 1.1 / 12.0,
            s2: close - range * 1.1 / 6.0,
            s3: close - range * 1.1 / 4.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Candle Pattern Detection
// ---------------------------------------------------------------------------

/// Fair Value Gap (FVG) — a 3-candle pattern where candle[1]'s wick doesn't
/// overlap with candle[0] or candle[2].
///
/// Bullish FVG: candle[2].low > candle[0].high  (gap up)
/// Bearish FVG: candle[0].low > candle[2].high   (gap down)
///
/// The "gap zone" is the price range between candle[0] and candle[2] wicks
/// that candle[1] never touched — a magnetic price area.
#[derive(Debug, Clone, Copy)]
pub struct FairValueGap {
    /// Index of the middle candle (candle[1]) in the input arrays.
    pub index: usize,
    /// Upper bound of the gap zone.
    pub gap_top: f32,
    /// Lower bound of the gap zone.
    pub gap_bottom: f32,
    /// true = bullish FVG (gap up), false = bearish FVG (gap down).
    pub is_bullish: bool,
}

/// Detect all Fair Value Gaps across the given OHLC series.
/// Returns FVGs sorted by index.
pub fn fair_value_gaps(
    highs: &[f32],
    lows: &[f32],
) -> Vec<FairValueGap> {
    let len = highs.len();
    if len < 3 {
        return vec![];
    }
    let mut gaps = Vec::new();
    for i in 1..len - 1 {
        // Bullish FVG: gap up — candle[i+1].low > candle[i-1].high
        if lows[i + 1] > highs[i - 1] {
            gaps.push(FairValueGap {
                index: i,
                gap_bottom: highs[i - 1],
                gap_top: lows[i + 1],
                is_bullish: true,
            });
        }
        // Bearish FVG: gap down — candle[i-1].low > candle[i+1].high
        if lows[i - 1] > highs[i + 1] {
            gaps.push(FairValueGap {
                index: i,
                gap_top: lows[i - 1],
                gap_bottom: highs[i + 1],
                is_bullish: false,
            });
        }
    }
    gaps
}

/// Order Block — the last opposing candle before a strong impulsive move.
///
/// A bullish OB: last bearish candle before a series of strong bullish candles.
/// A bearish OB: last bullish candle before a series of strong bearish candles.
///
/// "Strong" means the candle body is at least `body_threshold` fraction of the
/// total range, and the move span exceeds `impulse_min_range` (ATR-like).
#[derive(Debug, Clone, Copy)]
pub struct OrderBlock {
    /// Index of the order block candle in the input arrays.
    pub index: usize,
    /// Top of the OB zone (max of high).
    pub ob_top: f32,
    /// Bottom of the OB zone (min of low).
    pub ob_bottom: f32,
    /// true = bullish OB (last bearish before bullish impulse).
    pub is_bullish: bool,
}

/// Detect Order Blocks using a simple impulse-following rule.
///
/// - `body_threshold`: minimum body/range ratio for impulse candles (0.5 = 50%).
/// - `impulse_count`: minimum consecutive impulse candles to qualify (2).
/// - `lookback`: max candles to scan backward from current bar (30 typical).
pub fn order_blocks(
    opens: &[f32],
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    body_threshold: f32,
    impulse_count: usize,
    lookback: usize,
) -> Vec<OrderBlock> {
    let len = closes.len();
    if len < impulse_count + 1 {
        return vec![];
    }
    let mut blocks = Vec::new();
    let start = if len > lookback { len - lookback } else { 0 };

    for i in start..len.saturating_sub(impulse_count) {
        // Check if candles [i+1..i+1+impulse_count] are a strong impulsive move
        let first_close = closes[i];
        let last_close = closes[i + impulse_count];
        let is_bullish_impulse = last_close > first_close;
        let is_bearish_impulse = last_close < first_close;

        if !is_bullish_impulse && !is_bearish_impulse {
            continue;
        }

        // Verify all impulse candles have strong bodies
        let mut impulse_confirmed = true;
        for j in (i + 1)..=i + impulse_count {
            if j >= len {
                impulse_confirmed = false;
                break;
            }
            let range = highs[j] - lows[j];
            if range <= 0.0 {
                impulse_confirmed = false;
                break;
            }
            let body = (closes[j] - opens[j]).abs();
            if body / range < body_threshold {
                impulse_confirmed = false;
                break;
            }
            // Verify directional consistency
            if is_bullish_impulse && closes[j] <= opens[j] {
                impulse_confirmed = false;
                break;
            }
            if is_bearish_impulse && closes[j] >= opens[j] {
                impulse_confirmed = false;
                break;
            }
        }

        if !impulse_confirmed {
            continue;
        }

        // The OB is candle[i] — the last *opposing* candle before the impulse
        let ob_range = highs[i] - lows[i];
        if ob_range <= 0.0 {
            continue;
        }

        if is_bullish_impulse {
            // Bullish OB: candle[i] should be bearish (close < open)
            if closes[i] < opens[i] {
                blocks.push(OrderBlock {
                    index: i,
                    ob_top: highs[i],
                    ob_bottom: lows[i],
                    is_bullish: true,
                });
            }
        } else {
            // Bearish OB: candle[i] should be bullish (close > open)
            if closes[i] > opens[i] {
                blocks.push(OrderBlock {
                    index: i,
                    ob_top: highs[i],
                    ob_bottom: lows[i],
                    is_bullish: false,
                });
            }
        }
    }
    blocks
}

/// Candle shape classification for pattern matching.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CandleShape {
    /// No wicks on either side — body fills entire range.
    Wickless,
    /// Upper wick only, no lower wick.
    UpperWickOnly,
    /// Lower wick only, no upper wick.
    LowerWickOnly,
    /// Both wicks present, body dominates (>70% of range).
    BigBody,
    /// Both wicks present, body small (<30% of range).
    Doji,
    /// Normal candle — none of the above.
    Normal,
}

/// Classify a single candle's shape from OHLC values.
/// `wick_threshold` is the minimum wick size as fraction of range (default 0.02 = 2%).
pub fn classify_candle(
    open: f32,
    high: f32,
    low: f32,
    close: f32,
    wick_threshold: f32,
) -> CandleShape {
    let range = high - low;
    if range <= 0.0 {
        return CandleShape::Doji;
    }
    let body = (close - open).abs();
    let upper_wick = high - close.max(open);
    let lower_wick = open.min(close) - low;
    let body_ratio = body / range;
    let has_upper = upper_wick / range > wick_threshold;
    let has_lower = lower_wick / range > wick_threshold;

    if !has_upper && !has_lower && body_ratio > 0.8 {
        CandleShape::Wickless
    } else if has_upper && !has_lower {
        CandleShape::UpperWickOnly
    } else if !has_upper && has_lower {
        CandleShape::LowerWickOnly
    } else if body_ratio < 0.1 {
        CandleShape::Doji
    } else if body_ratio > 0.7 {
        CandleShape::BigBody
    } else {
        CandleShape::Normal
    }
}

/// Wickless/Repair candle result.
/// A Repair candle has no wicks → pure directional conviction.
/// After a Repair candle, its body becomes a key support/resistance level.
#[derive(Debug, Clone, Copy)]
pub struct WicklessCandle {
    /// Index in the input arrays.
    pub index: usize,
    /// Top of the body (max of open, close).
    pub body_top: f32,
    /// Bottom of the body (min of open, close).
    pub body_bottom: f32,
    /// true = bullish (close > open), false = bearish.
    pub is_bullish: bool,
}

/// Detect all wickless/repair candles in the OHLC series.
/// `wick_threshold` is the minimum wick fraction of range to count as "present"
/// (default 0.02 = 2% of range — essentially wickless).
pub fn wickless_candles(
    opens: &[f32],
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    wick_threshold: f32,
) -> Vec<WicklessCandle> {
    let len = closes.len();
    let mut result = Vec::new();
    for i in 0..len {
        let shape = classify_candle(opens[i], highs[i], lows[i], closes[i], wick_threshold);
        if shape == CandleShape::Wickless {
            result.push(WicklessCandle {
                index: i,
                body_top: closes[i].max(opens[i]),
                body_bottom: closes[i].min(opens[i]),
                is_bullish: closes[i] > opens[i],
            });
        }
    }
    result
}

/// Multi-candle pattern detection based on swing structure.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MultiCandlePattern {
    /// Fork: price breaks below a swing low, then immediately recovers back above it.
    /// Bearish trap — failed breakdown.
    Fork,
    /// H-pattern: lower-low + lower-close sequence where a recovery candle
    /// fails to break above the prior swing high. Weak downtrend continuation.
    HPattern,
    /// Cross Section: two bearish breakdown candles overlap in price range.
    /// The overlap zone is a re-entry area.
    CrossSection,
    /// Initiation: a candle with a long wick (capitulation) followed by
    /// a strong body candle in the opposite direction.
    Initiation,
}

/// Result of a multi-candle pattern detection.
#[derive(Debug, Clone, Copy)]
pub struct MultiCandleMatch {
    /// Index where the pattern completes (last candle of the pattern).
    pub index: usize,
    /// Pattern type detected.
    pub pattern: MultiCandlePattern,
    /// Key price level associated with the pattern (swing level, overlap zone, etc.).
    pub key_level: f32,
    /// Directional bias: true = bullish, false = bearish.
    pub is_bullish: bool,
}

/// Detect multi-candle patterns using swing points as anchors.
///
/// - `swings`: pre-computed swing points from `swing_points()`.
/// - `n_fractal`: the fractal window used to compute swings (for context).
/// - `wick_cap_ratio`: minimum wick/range ratio for a "capitulation wick" (0.5 = 50%).
/// - `min_body_ratio`: minimum body/range ratio for impulse candles (0.5).
pub fn detect_multi_candle_patterns(
    opens: &[f32],
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    swings: &[SwingPoint],
    wick_cap_ratio: f32,
    min_body_ratio: f32,
) -> Vec<MultiCandleMatch> {
    let len = closes.len();
    if len < 5 || swings.len() < 2 {
        return vec![];
    }
    let mut matches = Vec::new();

    // Separate swing highs and lows
    let swing_highs: Vec<&SwingPoint> = swings.iter().filter(|s| s.is_high).collect();
    let swing_lows: Vec<&SwingPoint> = swings.iter().filter(|s| !s.is_high).collect();

    // --- Fork detection: price breaks below a swing low, then recovers above it ---
    for sl in &swing_lows {
        let idx = sl.index;
        if idx + 2 >= len {
            continue;
        }
        // Check if candle after swing low breaks below it
        // Then the candle after that recovers back above
        for offset in 1..3 {
            let break_idx = idx + offset;
            if break_idx >= len {
                continue;
            }
            if lows[break_idx] < sl.price {
                // Price broke below swing low
                // Check if it recovers in the next candle
                if break_idx + 1 < len && closes[break_idx + 1] > sl.price {
                    matches.push(MultiCandleMatch {
                        index: break_idx + 1,
                        pattern: MultiCandlePattern::Fork,
                        key_level: sl.price,
                        is_bullish: true,
                    });
                }
            }
        }
    }

    // --- H-pattern: lower-low + failed recovery ---
    if swing_highs.len() >= 1 && swing_lows.len() >= 2 {
        for window in swing_lows.windows(2) {
            let (sl1, sl2) = (&window[0], &window[1]);
            // Lower low: sl2.price < sl1.price
            if sl2.price >= sl1.price {
                continue;
            }
            // Check if any swing high between these lows failed to break a prior resistance
            // Simplified: if the close at sl2 is below the most recent swing high
            if let Some(last_high) = swing_highs.iter().find(|sh| sh.index > sl1.index && sh.index < sl2.index) {
                if sl2.index + 1 < len && closes[sl2.index + 1] < last_high.price {
                    matches.push(MultiCandleMatch {
                        index: sl2.index + 1,
                        pattern: MultiCandlePattern::HPattern,
                        key_level: last_high.price,
                        is_bullish: false,
                    });
                }
            }
        }
    }

    // --- Cross Section: overlapping breakdown candles ---
    if swing_lows.len() >= 2 {
        for window in swing_lows.windows(2) {
            let (sl1, sl2) = (&window[0], &window[1]);
            if sl1.index + 1 >= len || sl2.index + 1 >= len {
                continue;
            }
            // Both are bearish breakdowns: closes below opens for candles at these indices
            let sl1_bearish = closes[sl1.index] < opens[sl1.index];
            let sl2_bearish = closes[sl2.index] < opens[sl2.index];
            if !sl1_bearish || !sl2_bearish {
                continue;
            }
            // Check overlap: the price ranges of the two candles overlap
            let top1 = highs[sl1.index];
            let bot1 = lows[sl1.index];
            let top2 = highs[sl2.index];
            let bot2 = lows[sl2.index];
            let overlap_top = top1.min(top2);
            let overlap_bot = bot1.max(bot2);
            if overlap_top > overlap_bot {
                let mid = (overlap_top + overlap_bot) / 2.0;
                matches.push(MultiCandleMatch {
                    index: sl2.index,
                    pattern: MultiCandlePattern::CrossSection,
                    key_level: mid,
                    is_bullish: false,
                });
            }
        }
    }

    // --- Initiation: capitulation wick + directional impulse ---
    for i in 1..len {
        let range = highs[i] - lows[i];
        if range <= 0.0 {
            continue;
        }
        let body = (closes[i] - opens[i]).abs();
        let upper_wick = highs[i] - closes[i].max(opens[i]);
        let lower_wick = opens[i].min(closes[i]) - lows[i];
        let max_wick = upper_wick.max(lower_wick);

        // Capitulation wick: a wick that's >= wick_cap_ratio of range
        if max_wick / range < wick_cap_ratio {
            continue;
        }
        // Body is on the opposite side of the wick
        // Upper wick (bearish rejection): open/close near the low → bearish
        // Lower wick (bullish rejection): open/close near the high → bullish
        let is_lower_wick_cap = lower_wick > upper_wick && lower_wick / range >= wick_cap_ratio;
        let is_upper_wick_cap = upper_wick > lower_wick && upper_wick / range >= wick_cap_ratio;

        if !is_lower_wick_cap && !is_upper_wick_cap {
            continue;
        }

        // Check next candle for directional impulse
        if i + 1 >= len {
            continue;
        }
        let next_body = (closes[i + 1] - opens[i + 1]).abs();
        let next_range = highs[i + 1] - lows[i + 1];
        if next_range <= 0.0 {
            continue;
        }
        let next_body_ratio = next_body / next_range;
        if next_body_ratio < min_body_ratio {
            continue;
        }

        // Directional: next candle should follow the cap direction
        let next_bullish = closes[i + 1] > opens[i + 1];
        if is_lower_wick_cap && next_bullish {
            matches.push(MultiCandleMatch {
                index: i,
                pattern: MultiCandlePattern::Initiation,
                key_level: lows[i],
                is_bullish: true,
            });
        } else if is_upper_wick_cap && !next_bullish {
            matches.push(MultiCandleMatch {
                index: i,
                pattern: MultiCandlePattern::Initiation,
                key_level: highs[i],
                is_bullish: false,
            });
        }
    }

    matches
}

// ---------------------------------------------------------------------------
// Absorption Detection (configurable thresholds)
// ---------------------------------------------------------------------------

/// An absorption bar: high volume but small range — big money absorbing orders.
#[derive(Debug, Clone, Copy)]
pub struct AbsorptionBar {
    /// Index into the input arrays.
    pub index: usize,
    /// true = close > open (bullish absorption).
    pub is_bullish: bool,
}

/// Detect absorption bars in an OHLCV series using configurable thresholds.
///
/// A bar is classified as absorption when:
/// - `volume > avg_volume * vol_multiplier` (high relative volume)
/// - `range < avg_range * range_multiplier` (compressed candle body)
///
/// The `warmup` bars at the start are excluded from both the average computation
/// and the detection scan (default 20).
pub fn detect_absorption(
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    opens: &[f32],
    volumes: &[f32],
    vol_multiplier: f32,
    range_multiplier: f32,
    warmup: usize,
) -> Vec<AbsorptionBar> {
    let len = closes.len();
    if len < warmup + 1 {
        return Vec::new();
    }

    // Compute averages over the full series
    let avg_vol: f32 = volumes.iter().sum::<f32>() / len as f32;
    let avg_range: f32 = highs
        .iter()
        .zip(lows.iter())
        .map(|(h, l)| h - l)
        .sum::<f32>()
        / len as f32;

    if avg_vol < 1e-6 || avg_range < 1e-6 {
        return Vec::new();
    }

    let mut results = Vec::new();
    for i in warmup..len {
        let range = highs[i] - lows[i];
        let vol = volumes[i];
        if vol > avg_vol * vol_multiplier && range < avg_range * range_multiplier {
            results.push(AbsorptionBar {
                index: i,
                is_bullish: closes[i] > opens[i],
            });
        }
    }
    results
}

// ---------------------------------------------------------------------------
// Candlestick Pattern Detection (composite)
// ---------------------------------------------------------------------------

/// Result of a single-candle or two-candle pattern detection.
/// Maps to `CandlePatternPoint` in the indicator layer.
#[derive(Debug, Clone, Copy)]
pub struct CandlePatternResult {
    /// Index into the OHLC arrays where the pattern completes.
    pub index: usize,
    /// Pattern code: 1=WicklessBull, 2=WicklessBear, 3=Doji,
    /// 4=BullEngulf, 5=BearEngulf, 6=Hammer, 7=ShootingStar.
    pub pattern_code: u8,
    /// Magnitude: body size / ATR (14) for this candle.
    pub magnitude: f32,
}

/// Detect all single-candle and two-candle classic patterns in an OHLC series.
///
/// Returns a `Vec<CandlePatternResult>` with one entry per detected pattern.
/// Patterns are assigned numeric codes matching `CandlePatternPoint::pattern_code`
/// in the indicator layer.
///
/// Parameters:
/// - `wickless_threshold`: max wick fraction of range to count as "wickless" (default 0.05)
/// - `doji_threshold`: max body fraction of range for doji (default 0.1)
/// - `engulf_ratio`: prior body must be < this fraction of engulfing body (default 0.5)
/// - `hammer_lower_ratio`: lower wick >= this * body for hammer (default 2.0)
/// - `hammer_upper_max`: upper wick <= this * total range for hammer (default 0.3)
/// - `star_upper_ratio`: upper wick >= this * body for shooting star (default 2.0)
/// - `star_lower_max`: lower wick <= this * total range for shooting star (default 0.3)
pub fn detect_candlestick_patterns(
    opens: &[f32],
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    wickless_threshold: f32,
    doji_threshold: f32,
    engulf_ratio: f32,
    hammer_lower_ratio: f32,
    hammer_upper_max: f32,
    star_upper_ratio: f32,
    star_lower_max: f32,
) -> Vec<CandlePatternResult> {
    let len = closes.len();
    if len < 3 {
        return Vec::new();
    }

    // Compute ATR(14) for magnitude scaling
    let atr_period = 14.min(len);
    let atr: f32 = if len > atr_period {
        (1..len)
            .rev()
            .take(atr_period)
            .map(|i| highs[i].max(highs[i - 1]) - lows[i].min(lows[i - 1]))
            .sum::<f32>()
            / atr_period as f32
    } else {
        1.0 // fallback for very short series
    };
    let atr = atr.max(1e-6);

    let mut results = Vec::new();

    for i in 0..len {
        let o = opens[i];
        let h = highs[i];
        let l = lows[i];
        let c = closes[i];
        let range = h - l;
        if range < 1e-6 {
            continue;
        }
        let body = (c - o).abs();
        let body_top = c.max(o);
        let body_bottom = c.min(o);
        let upper_wick = h - body_top;
        let lower_wick = body_bottom - l;
        let is_bullish = c > o;
        let magnitude = body / atr;

        // 1/2: Wickless (using classify_candle)
        let shape = classify_candle(o, h, l, c, wickless_threshold);
        if shape == CandleShape::Wickless {
            results.push(CandlePatternResult {
                index: i,
                pattern_code: if is_bullish { 1 } else { 2 },
                magnitude,
            });
            continue; // wickless takes priority
        }

        // 4/5: Engulfing (two-candle pattern, check i-1)
        if i > 0 {
            let prev_o = opens[i - 1];
            let prev_c = closes[i - 1];
            let prev_body = (prev_c - prev_o).abs();
            let prev_bullish = prev_c > prev_o;
            if prev_body > 1e-6 && body > prev_body / engulf_ratio {
                // Bullish engulfing: prev bearish, current bullish, current engulfs prev
                if !prev_bullish && is_bullish && c > prev_o && o < prev_c {
                    results.push(CandlePatternResult {
                        index: i,
                        pattern_code: 4,
                        magnitude,
                    });
                    continue;
                }
                // Bearish engulfing: prev bullish, current bearish, current engulfs prev
                if prev_bullish && !is_bullish && c < prev_o && o > prev_c {
                    results.push(CandlePatternResult {
                        index: i,
                        pattern_code: 5,
                        magnitude,
                    });
                    continue;
                }
            }
        }

        // 6: Hammer (bullish reversal): lower wick >= 2x body, upper wick small
        if lower_wick >= hammer_lower_ratio * body && upper_wick <= hammer_upper_max * range {
            results.push(CandlePatternResult {
                index: i,
                pattern_code: 6,
                magnitude,
            });
            continue;
        }

        // 7: Shooting Star (bearish reversal): upper wick >= 2x body, lower wick small
        if upper_wick >= star_upper_ratio * body && lower_wick <= star_lower_max * range {
            results.push(CandlePatternResult {
                index: i,
                pattern_code: 7,
                magnitude,
            });
            continue;
        }

        // 3: Doji (catch-all — checked last so specific patterns take priority)
        if body < doji_threshold * range {
            results.push(CandlePatternResult {
                index: i,
                pattern_code: 3,
                magnitude,
            });
        }
    }

    results
}

// ---------------------------------------------------------------------------
// Market Structure Shift (MSS) Detection
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MssSignal {
    /// Index where the MSS occurs.
    pub index: usize,
    /// 1 = bullish MSS (price broke above recent swing high),
    /// -1 = bearish MSS (price broke below recent swing low).
    pub direction: i8,
    /// Price level of the broken swing point.
    pub break_level: f32,
}

/// Detect Market Structure Shift — a close that breaks a recent swing high/low.
///
/// A bullish MSS occurs when close > most recent swing high (uptrend confirmation).
/// A bearish MSS occurs when close < most recent swing low (downtrend confirmation).
///
/// - `swing_lookback`: fractal window for swing detection (default 5).
/// - `confirmation_bars`: number of consecutive closes beyond the level to confirm (default 1).
pub fn detect_mss(
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    swing_lookback: usize,
    confirmation_bars: usize,
) -> Vec<MssSignal> {
    let len = closes.len();
    if len < swing_lookback * 2 + 2 {
        return vec![];
    }
    let swings = swing_points(highs, lows, swing_lookback);
    if swings.len() < 2 {
        return vec![];
    }

    let mut signals = Vec::new();
    // Track the most recent swing high/low before each bar
    let mut last_swing_high: Option<(usize, f32)> = None;
    let mut last_swing_low: Option<(usize, f32)> = None;

    // Pre-fill from initial swings
    for sp in &swings {
        if sp.is_high {
            last_swing_high = Some((sp.index, sp.price));
        } else {
            last_swing_low = Some((sp.index, sp.price));
        }
    }

    // Walk forward: detect breaks of established swings
    let mut bull_confirmation = 0usize;
    let mut bear_confirmation = 0usize;
    for i in 0..len {
        // Update last swing levels as we pass them
        for sp in &swings {
            if sp.index == i {
                if sp.is_high {
                    last_swing_high = Some((sp.index, sp.price));
                } else {
                    last_swing_low = Some((sp.index, sp.price));
                }
            }
        }

        if let Some((_, high_level)) = last_swing_high {
            if closes[i] > high_level {
                bull_confirmation += 1;
                if bull_confirmation >= confirmation_bars {
                    signals.push(MssSignal {
                        index: i,
                        direction: 1,
                        break_level: high_level,
                    });
                    bull_confirmation = 0;
                }
            } else {
                bull_confirmation = 0;
            }
        }

        if let Some((_, low_level)) = last_swing_low {
            if closes[i] < low_level {
                bear_confirmation += 1;
                if bear_confirmation >= confirmation_bars {
                    signals.push(MssSignal {
                        index: i,
                        direction: -1,
                        break_level: low_level,
                    });
                    bear_confirmation = 0;
                }
            } else {
                bear_confirmation = 0;
            }
        }
    }

    signals
}

/// Per-candle MSS signal (0=none, 1=bullish, -1=bearish).
pub fn mss_series(
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    swing_lookback: usize,
    confirmation_bars: usize,
) -> Vec<i8> {
    let signals = detect_mss(highs, lows, closes, swing_lookback, confirmation_bars);
    let len = closes.len();
    let mut out = vec![0i8; len];
    for s in &signals {
        if s.index < len {
            out[s.index] = s.direction;
        }
    }
    out
}

// ---------------------------------------------------------------------------
// CVD Divergence Detection
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CvdDivergence {
    /// Index where divergence is detected.
    pub index: usize,
    /// 1 = bullish divergence (price lower low, CVD higher low),
    /// -1 = bearish divergence (price higher high, CVD lower high).
    pub direction: i8,
}

/// Detect CVD divergence — price vs CVD swing comparison.
///
/// Bullish divergence: price makes a lower low while CVD makes a higher low.
/// Bearish divergence: price makes a higher high while CVD makes a lower high.
///
/// - `lookback`: window to search for swing pivots (default 20).
pub fn detect_cvd_divergence(
    highs: &[f32],
    lows: &[f32],
    closes: &[f32],
    cvd: &[f32],
    lookback: usize,
) -> Vec<CvdDivergence> {
    let len = closes.len();
    if len < lookback * 2 || highs.len() != len || lows.len() != len || cvd.len() != len {
        return vec![];
    }

    // Use existing swing points on price and CVD
    let _price_swings = swing_points(highs, lows, 5);
    let _cvd_highs: Vec<f32> = cvd.iter().map(|&v| v).collect();
    let _cvd_lows: Vec<f32> = cvd.iter().map(|&v| v).collect();

    let mut divergences = Vec::new();

    // For each price swing low, check if CVD made a higher low
    for i in (lookback..len).rev() {
        // Find recent price swing low
        let mut price_low_idx = i;
        let mut price_low_val = lows[i];
        // Scan back for the actual valley
        for j in (i.saturating_sub(5)..=i).rev() {
            if lows[j] < price_low_val {
                price_low_val = lows[j];
                price_low_idx = j;
            }
        }

        // Find corresponding CVD low around same area
        let cvd_window_start = price_low_idx.saturating_sub(3);
        let cvd_window_end = (price_low_idx + 3).min(len);
        let mut cvd_low_val = f32::MAX;
        let mut _cvd_low_idx = price_low_idx;
        for j in cvd_window_start..cvd_window_end {
            if cvd[j] < cvd_low_val {
                cvd_low_val = cvd[j];
                _cvd_low_idx = j;
            }
        }

        // Find previous price swing low within lookback
        let mut prev_price_low_val = price_low_val;
        let mut prev_cvd_low_val = cvd_low_val;
        let mut found_prev = false;
        for j in (price_low_idx.saturating_sub(lookback)..price_low_idx).rev() {
            if lows[j] < prev_price_low_val {
                prev_price_low_val = lows[j];
                // Corresponding CVD
                let pcvd_start = j.saturating_sub(2);
                let pcvd_end = (j + 2).min(len);
                for k in pcvd_start..pcvd_end {
                    if cvd[k] < prev_cvd_low_val {
                        prev_cvd_low_val = cvd[k];
                    }
                }
                found_prev = true;
                break;
            }
        }

        // Bullish divergence: price lower low, CVD higher low
        if found_prev && price_low_val < prev_price_low_val && cvd_low_val > prev_cvd_low_val {
            divergences.push(CvdDivergence {
                index: price_low_idx,
                direction: 1,
            });
        }
    }

    // For each price swing high, check if CVD made a lower high
    for i in (lookback..len).rev() {
        let mut price_high_idx = i;
        let mut price_high_val = highs[i];
        for j in (i.saturating_sub(5)..=i).rev() {
            if highs[j] > price_high_val {
                price_high_val = highs[j];
                price_high_idx = j;
            }
        }

        let cvd_window_start = price_high_idx.saturating_sub(3);
        let cvd_window_end = (price_high_idx + 3).min(len);
        let mut cvd_high_val = f32::MIN;
        let mut _cvd_high_idx = price_high_idx;
        for j in cvd_window_start..cvd_window_end {
            if cvd[j] > cvd_high_val {
                cvd_high_val = cvd[j];
                _cvd_high_idx = j;
            }
        }

        let mut prev_price_high_val = price_high_val;
        let mut prev_cvd_high_val = cvd_high_val;
        let mut found_prev = false;
        for j in (price_high_idx.saturating_sub(lookback)..price_high_idx).rev() {
            if highs[j] > prev_price_high_val {
                prev_price_high_val = highs[j];
                let pcvd_start = j.saturating_sub(2);
                let pcvd_end = (j + 2).min(len);
                for k in pcvd_start..pcvd_end {
                    if cvd[k] > prev_cvd_high_val {
                        prev_cvd_high_val = cvd[k];
                    }
                }
                found_prev = true;
                break;
            }
        }

        if found_prev && price_high_val > prev_price_high_val && cvd_high_val < prev_cvd_high_val {
            divergences.push(CvdDivergence {
                index: price_high_idx,
                direction: -1,
            });
        }
    }

    divergences
}

// ---------------------------------------------------------------------------
// Relative Volume (RVOL)
// ---------------------------------------------------------------------------

/// Full RVOL series: current_volume / SMA of volume over lookback period.
/// Values > 1.0 = above-average volume, > 2.0 = high RVOL, < 0.5 = low RVOL.
pub fn rvol_series(volumes: &[f32], lookback: usize) -> Vec<Option<f32>> {
    let n = volumes.len();
    if n < lookback || lookback == 0 {
        return vec![None; n];
    }
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        if i + 1 < lookback {
            out.push(None);
        } else {
            let sum: f32 = volumes[i + 1 - lookback..=i].iter().sum();
            let avg = sum / lookback as f32;
            let rvol = if avg > 0.0 { volumes[i] / avg } else { 1.0 };
            out.push(Some(rvol));
        }
    }
    out
}

/// Volume Profile result for a single session.
pub struct VolumeProfile {
    /// Total volume in the session.
    pub total_volume: f64,
    /// Price bins (low to high).
    pub bin_prices: Vec<f32>,
    /// Volume at each price bin.
    pub bin_volumes: Vec<f64>,
    /// Point of Control — price level with highest volume.
    pub poc_price: f32,
    /// POC volume.
    pub poc_volume: f64,
    /// Value Area High — upper bound containing value_area_pct of volume around POC.
    pub vah: f32,
    /// Value Area Low — lower bound.
    pub val: f32,
}

/// Compute a session-based Volume Profile from OHLCV data.
///
/// Splits the price range into `num_bins` equally-sized buckets, assigns each bar's
/// volume proportionally across its candle range, then finds the POC and Value Area
/// (default 70% of total volume centered on POC).
///
/// - `num_bins`: number of price buckets (default 24 for a session).
/// - `value_area_pct`: fraction of total volume to include in the value area (default 0.7).
pub fn volume_profile(
    highs: &[f32],
    lows: &[f32],
    volumes: &[f32],
    num_bins: usize,
    value_area_pct: f32,
) -> VolumeProfile {
    let n = highs.len().min(lows.len()).min(volumes.len());
    if n == 0 || num_bins < 2 {
        return VolumeProfile {
            total_volume: 0.0,
            bin_prices: vec![],
            bin_volumes: vec![],
            poc_price: 0.0,
            poc_volume: 0.0,
            vah: 0.0,
            val: 0.0,
        };
    }

    let overall_high = highs.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let overall_low = lows.iter().copied().fold(f32::INFINITY, f32::min);
    let bin_width = (overall_high - overall_low) / num_bins as f32;
    if bin_width <= 0.0 {
        return VolumeProfile {
            total_volume: 0.0, bin_prices: vec![], bin_volumes: vec![],
            poc_price: 0.0, poc_volume: 0.0, vah: 0.0, val: 0.0,
        };
    }

    let mut bin_volumes = vec![0.0_f64; num_bins];
    let mut bin_prices: Vec<f32> = (0..num_bins)
        .map(|i| overall_low + bin_width * (i as f32 + 0.5))
        .collect();

    for i in 0..n {
        let h = highs[i];
        let l = lows[i];
        let v = volumes[i] as f64;
        if h <= l || v <= 0.0 {
            continue;
        }
        // Distribute volume proportionally across bins the candle spans
        let first_bin = ((l - overall_low) / bin_width).max(0.0).floor() as usize;
        let last_bin = ((h - overall_low) / bin_width).min((num_bins - 1) as f32).floor() as usize;
        if first_bin > last_bin {
            continue;
        }
        let num_bins_covered = (last_bin - first_bin + 1) as f64;
        let vol_per_bin = v / num_bins_covered;
        for b in first_bin..=last_bin {
            bin_volumes[b] += vol_per_bin;
        }
    }

    let total_volume: f64 = bin_volumes.iter().sum();

    // Find POC
    let poc_idx = bin_volumes
        .iter()
        .enumerate()
        .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
        .map(|(i, _)| i)
        .unwrap_or(0);

    let poc_price = bin_prices[poc_idx];
    let poc_volume = bin_volumes[poc_idx];

    // Compute Value Area: expand outward from POC until we accumulate value_area_pct of volume
    let target_vol = total_volume * value_area_pct as f64;
    let mut accumulated = bin_volumes[poc_idx];
    let mut vah_idx = poc_idx;
    let mut val_idx = poc_idx;

    loop {
        let expand_up = if vah_idx + 1 < num_bins { Some(vah_idx + 1) } else { None };
        let expand_down = if val_idx > 0 { Some(val_idx - 1) } else { None };

        if accumulated >= target_vol {
            break;
        }

        match (expand_up, expand_down) {
            (Some(up), Some(down)) => {
                if bin_volumes[up] >= bin_volumes[down] {
                    accumulated += bin_volumes[up];
                    vah_idx = up;
                } else {
                    accumulated += bin_volumes[down];
                    val_idx = down;
                }
            }
            (Some(up), None) => {
                accumulated += bin_volumes[up];
                vah_idx = up;
            }
            (None, Some(down)) => {
                accumulated += bin_volumes[down];
                val_idx = down;
            }
            (None, None) => break,
        }
    }

    let vah = bin_prices[vah_idx] + bin_width / 2.0;
    let val = bin_prices[val_idx] - bin_width / 2.0;

    VolumeProfile {
        total_volume,
        bin_prices,
        bin_volumes,
        poc_price,
        poc_volume,
        vah,
        val,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sma() {
        let closes = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        assert_eq!(sma(&closes, 3), Some(4.0)); // last 3: 3+4+5 / 3
    }

    #[test]
    fn test_ema() {
        let closes = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let series = ema_series(&closes, 3);
        assert!(series[0].is_none());
        assert!(series[1].is_none());
        assert!(series[2].is_some()); // seed
        // EMA should be between min and max
        if let Some(v) = series[9] {
            assert!(v > 0.0 && v < 12.0);
        }
    }

    #[test]
    fn test_rsi_extreme() {
        // All rising → RSI = 100
        let closes: Vec<f32> = (1..=20).map(|x| x as f32).collect();
        let r = rsi(&closes, 14);
        let last = r.last().copied().flatten();
        assert!(last.is_some());
        assert!((last.unwrap() - 100.0).abs() < 1.0);
    }

    #[test]
    fn test_bollinger() {
        let closes = vec![10.0; 20]; // constant price
        let bb = bollinger(&closes, 20, 2.0).unwrap();
        assert!((bb.middle - 10.0).abs() < 0.01);
        assert!((bb.upper - 10.0).abs() < 0.01);
        assert!((bb.lower - 10.0).abs() < 0.01);
    }

    #[test]
    fn test_delta_zscore_constant() {
        let deltas = vec![100.0; 20];
        let z = delta_zscore(&deltas, 20);
        assert!(z.is_some());
        // Constant delta → stdev = 0 → z = 0
        assert!((z.unwrap() - 0.0).abs() < 0.01);
    }

    #[test]
    fn test_vwap() {
        let highs = vec![105.0, 110.0];
        let lows = vec![95.0, 100.0];
        let closes = vec![100.0, 105.0];
        let volumes = vec![1000.0, 2000.0];
        let v = vwap(&highs, &lows, &closes, &volumes).unwrap();
        // Bar 0: typical = (105+95+100)/3 = 100, Bar 1: typical = (110+100+105)/3 = 105
        let expected = (100.0 * 1000.0 + 105.0 * 2000.0) / 3000.0;
        assert!((v - expected).abs() < 0.01);
    }

    #[test]
    fn test_swing_points() {
        let highs = vec![1.0, 2.0, 3.0, 2.5, 2.0, 1.5, 1.0, 2.0, 3.0];
        let lows = highs.clone(); // simplify: lows = highs
        let points = swing_points(&highs, &lows, 2);
        assert!(!points.is_empty());
        // Index 2 should be a swing high (3.0 > neighbors)
        assert!(points.iter().any(|p| p.index == 2 && p.is_high));
    }

    #[test]
    fn test_pivot_points_classic() {
        let pp = PivotPoints::classic(110.0, 100.0, 105.0);
        assert!((pp.pp - 105.0).abs() < 0.01);
        assert!((pp.r1 - 110.0).abs() < 0.01); // 2*105 - 100 = 110
        assert!((pp.s1 - 100.0).abs() < 0.01); // 2*105 - 110 = 100
    }

    #[test]
    fn test_alma() {
        let closes = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let val = alma(&closes, 10, 0.85, 6.0);
        assert!(val.is_some());
        // ALMA should be weighted toward recent values (close to 10)
        let v = val.unwrap();
        assert!(v > 7.0 && v < 11.0);
    }

    #[test]
    fn test_aroon() {
        let highs = vec![1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0, 2.0, 3.0];
        let lows = highs.clone();
        let a = aroon(&highs, &lows, 5);
        // aroon() now returns Vec<Option<AroonValue>>; check last value
        let last = a.last().unwrap().unwrap();
        assert!(last.up >= 0.0 && last.up <= 100.0);
        assert!(last.down >= 0.0 && last.down <= 100.0);
    }

    // -----------------------------------------------------------------------
    // Candle pattern tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_fair_value_gap_bullish() {
        // Bullish FVG: candle[0].high < candle[2].low  (gap up)
        let highs = vec![100.0, 102.0, 108.0];
        let lows = vec![98.0, 99.0, 106.0];
        let fvgs = fair_value_gaps(&highs, &lows);
        assert_eq!(fvgs.len(), 1);
        assert!((fvgs[0].gap_top - 106.0).abs() < 0.01);
        assert!((fvgs[0].gap_bottom - 100.0).abs() < 0.01);
        assert_eq!(fvgs[0].index, 1); // middle candle
        assert!(fvgs[0].is_bullish);
    }

    #[test]
    fn test_fair_value_gap_bearish() {
        // Bearish FVG: candle[0].low > candle[2].high  (gap down)
        let highs = vec![110.0, 108.0, 100.0];
        let lows = vec![106.0, 105.0, 98.0];
        let fvgs = fair_value_gaps(&highs, &lows);
        assert_eq!(fvgs.len(), 1);
        assert!(!fvgs[0].is_bullish);
    }

    #[test]
    fn test_fair_value_gap_none() {
        // No gap — overlapping ranges
        let highs = vec![100.0, 102.0, 103.0];
        let lows = vec![98.0, 99.0, 100.0];
        let fvgs = fair_value_gaps(&highs, &lows);
        assert!(fvgs.is_empty());
    }

    #[test]
    fn test_fair_value_gap_too_short() {
        let highs = vec![100.0, 101.0];
        let lows = vec![99.0, 100.0];
        let fvgs = fair_value_gaps(&highs, &lows);
        assert!(fvgs.is_empty());
    }

    #[test]
    fn test_order_block_bullish() {
        // Bullish OB: bearish candle at i, then 2 bullish impulse candles
        let opens = vec![100.0, 102.0, 104.0, 106.0, 108.0];
        let closes = vec![101.0, 100.0, 107.0, 110.0, 112.0];
        let highs = vec![102.0, 103.0, 108.0, 111.0, 113.0];
        let lows = vec![99.0, 99.0, 103.0, 105.0, 107.0];
        let obs = order_blocks(&opens, &highs, &lows, &closes, 0.5, 2, 10);
        // Should find a bullish OB at index 1 (last bearish before bullish impulse)
        assert!(!obs.is_empty());
        assert!(obs.iter().any(|ob| ob.is_bullish));
    }

    #[test]
    fn test_order_block_bearish() {
        // Bearish OB: bullish candle at i, then 2 bearish impulse candles
        let opens = vec![100.0, 102.0, 100.0, 96.0, 94.0];
        let closes = vec![101.0, 103.0, 96.0, 94.0, 92.0];
        let highs = vec![102.0, 104.0, 101.0, 97.0, 95.0];
        let lows = vec![99.0, 101.0, 95.0, 93.0, 91.0];
        let obs = order_blocks(&opens, &highs, &lows, &closes, 0.5, 2, 10);
        assert!(!obs.is_empty());
        assert!(obs.iter().any(|ob| !ob.is_bullish));
    }

    #[test]
    fn test_order_block_too_short() {
        let opens = vec![100.0];
        let closes = vec![101.0];
        let highs = vec![102.0];
        let lows = vec![99.0];
        let obs = order_blocks(&opens, &highs, &lows, &closes, 0.5, 2, 10);
        assert!(obs.is_empty());
    }

    #[test]
    fn test_classify_candle_wickless_bull() {
        // Bullish wickless: open=low, close=high, range=10, body=10
        let shape = classify_candle(100.0, 110.0, 100.0, 110.0, 0.05);
        assert_eq!(shape, CandleShape::Wickless);
    }

    #[test]
    fn test_classify_candle_wickless_bear() {
        // Bearish wickless: open=high, close=low
        let shape = classify_candle(110.0, 110.0, 100.0, 100.0, 0.05);
        assert_eq!(shape, CandleShape::Wickless);
    }

    #[test]
    fn test_classify_candle_normal() {
        // Normal candle with both wicks
        let shape = classify_candle(105.0, 110.0, 100.0, 108.0, 0.05);
        assert_eq!(shape, CandleShape::Normal);
    }

    #[test]
    fn test_wickless_candles() {
        // Series with one wickless bull and one normal
        let opens = vec![100.0, 105.0];
        let highs = vec![110.0, 110.0];
        let lows = vec![100.0, 100.0];
        let closes = vec![110.0, 108.0];
        let wl = wickless_candles(&opens, &highs, &lows, &closes, 0.05);
        assert_eq!(wl.len(), 1);
        assert_eq!(wl[0].index, 0);
        assert!(wl[0].is_bullish);
    }

    #[test]
    fn test_detect_candlestick_patterns_wickless_bull() {
        // 30 candles, one wickless bull in the middle
        let n = 30;
        let mut opens = vec![105.0; n];
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        // Candle 15: wickless bull (open=low, close=high)
        opens[15] = 100.0;
        highs[15] = 110.0;
        lows[15] = 100.0;
        closes[15] = 110.0;
        let patterns = detect_candlestick_patterns(
            &opens, &highs, &lows, &closes,
            0.05, 0.1, 0.5, 2.0, 0.3, 2.0, 0.3,
        );
        assert!(patterns.iter().any(|p| p.index == 15 && p.pattern_code == 1));
    }

    #[test]
    fn test_detect_candlestick_patterns_doji() {
        // Doji: very small body relative to range
        let n = 30;
        let opens = vec![105.0; n];
        let highs = vec![110.0; n];
        let lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        // Candle 10: doji (body < 10% of range)
        closes[10] = 105.1;
        let patterns = detect_candlestick_patterns(
            &opens, &highs, &lows, &closes,
            0.05, 0.1, 0.5, 2.0, 0.3, 2.0, 0.3,
        );
        assert!(patterns.iter().any(|p| p.index == 10 && p.pattern_code == 3));
    }

    #[test]
    fn test_detect_candlestick_patterns_bull_engulf() {
        // Bullish engulfing: prev bearish, current bullish engulfs prev
        let n = 30;
        let mut opens = vec![105.0; n];
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        // Candle 19: small bearish
        opens[19] = 106.0;
        closes[19] = 104.0;
        highs[19] = 107.0;
        lows[19] = 103.0;
        // Candle 20: large bullish engulfing
        opens[20] = 103.5;
        closes[20] = 109.0;
        highs[20] = 110.0;
        lows[20] = 103.0;
        let patterns = detect_candlestick_patterns(
            &opens, &highs, &lows, &closes,
            0.05, 0.1, 0.5, 2.0, 0.3, 2.0, 0.3,
        );
        assert!(patterns.iter().any(|p| p.index == 20 && p.pattern_code == 4));
    }

    #[test]
    fn test_detect_candlestick_patterns_hammer() {
        // Hammer: long lower wick, small upper wick, small body at top
        let n = 30;
        let mut opens = vec![105.0; n];
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        // Candle 12: hammer body at top, long lower wick
        opens[12] = 107.0;
        closes[12] = 108.0;
        highs[12] = 108.5;
        lows[12] = 100.0;
        let patterns = detect_candlestick_patterns(
            &opens, &highs, &lows, &closes,
            0.05, 0.1, 0.5, 2.0, 0.3, 2.0, 0.3,
        );
        assert!(patterns.iter().any(|p| p.index == 12 && p.pattern_code == 6));
    }

    #[test]
    fn test_detect_candlestick_patterns_shooting_star() {
        // Shooting star: long upper wick, small lower wick, body at bottom
        let n = 30;
        let mut opens = vec![105.0; n];
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        // Candle 12: shooting star body at bottom, long upper wick
        opens[12] = 105.0;
        closes[12] = 104.0;
        highs[12] = 115.0;
        lows[12] = 103.5;
        let patterns = detect_candlestick_patterns(
            &opens, &highs, &lows, &closes,
            0.05, 0.1, 0.5, 2.0, 0.3, 2.0, 0.3,
        );
        assert!(patterns.iter().any(|p| p.index == 12 && p.pattern_code == 7));
    }

    #[test]
    fn test_detect_candlestick_patterns_empty() {
        let patterns = detect_candlestick_patterns(
            &[100.0], &[110.0], &[100.0], &[105.0],
            0.05, 0.1, 0.5, 2.0, 0.3, 2.0, 0.3,
        );
        assert!(patterns.is_empty());
    }

    // -----------------------------------------------------------------------
    // Absorption detection tests (configurable thresholds)
    // -----------------------------------------------------------------------

    #[test]
    fn test_detect_absorption_default_thresholds() {
        // 25 candles. Candle 22: high vol (2x avg), small range (0.3x avg) → absorption
        let n = 25;
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        let mut opens = vec![105.0; n];
        let mut volumes = vec![1000.0; n];
        // Candle 22: absorption candle (compressed range, high volume)
        highs[22] = 103.0;
        lows[22] = 101.0; // range=2 (vs avg range ~10)
        volumes[22] = 5000.0; // 5x avg vol
        closes[22] = 102.5; // bullish
        opens[22] = 101.5;
        let bars = detect_absorption(
            &highs, &lows, &closes, &opens, &volumes,
            1.5, 0.5, 20,
        );
        assert!(!bars.is_empty());
        assert!(bars.iter().any(|b| b.index == 22 && b.is_bullish));
    }

    #[test]
    fn test_detect_absorption_no_signal() {
        // Normal candles, no absorption
        let n = 25;
        let highs = vec![110.0; n];
        let lows = vec![100.0; n];
        let closes = vec![108.0; n];
        let opens = vec![105.0; n];
        let volumes = vec![1000.0; n];
        let bars = detect_absorption(
            &highs, &lows, &closes, &opens, &volumes,
            1.5, 0.5, 20,
        );
        assert!(bars.is_empty());
    }

    #[test]
    fn test_detect_absorption_strict_thresholds() {
        // Very strict thresholds (3x vol, 0.2x range) — should filter out mild signals
        let n = 25;
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        let mut opens = vec![105.0; n];
        let mut volumes = vec![1000.0; n];
        // Candle 22: moderate absorption (1.8x vol, 0.4x range)
        highs[22] = 104.0;
        lows[22] = 100.0;
        volumes[22] = 1800.0;
        // With strict thresholds (3x/0.2x), this should NOT trigger
        let bars = detect_absorption(
            &highs, &lows, &closes, &opens, &volumes,
            3.0, 0.2, 20,
        );
        assert!(bars.is_empty());
    }

    #[test]
    fn test_detect_absorption_lenient_thresholds() {
        // Lenient thresholds (1.0x vol, 0.8x range) — should catch more
        let n = 25;
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        let mut opens = vec![105.0; n];
        let mut volumes = vec![1000.0; n];
        // Candle 22: mild compression
        highs[22] = 107.0;
        lows[22] = 100.0; // range 7 (slightly below avg 10)
        volumes[22] = 1100.0; // slightly above avg
        let bars = detect_absorption(
            &highs, &lows, &closes, &opens, &volumes,
            1.0, 0.8, 20,
        );
        assert!(!bars.is_empty());
    }

    #[test]
    fn test_detect_absorption_too_few_candles() {
        let highs = vec![110.0; 10];
        let lows = vec![100.0; 10];
        let closes = vec![108.0; 10];
        let opens = vec![105.0; 10];
        let volumes = vec![1000.0; 10];
        let bars = detect_absorption(
            &highs, &lows, &closes, &opens, &volumes,
            1.5, 0.5, 20,
        );
        assert!(bars.is_empty());
    }

    #[test]
    fn test_detect_absorption_bearish() {
        let n = 25;
        let mut highs = vec![110.0; n];
        let mut lows = vec![100.0; n];
        let mut closes = vec![108.0; n];
        let mut opens = vec![105.0; n];
        let mut volumes = vec![1000.0; n];
        // Candle 22: bearish absorption
        highs[22] = 103.0;
        lows[22] = 101.0;
        volumes[22] = 5000.0;
        closes[22] = 101.5; // bearish
        opens[22] = 102.5;
        let bars = detect_absorption(
            &highs, &lows, &closes, &opens, &volumes,
            1.5, 0.5, 20,
        );
        assert!(!bars.is_empty());
        assert!(bars.iter().any(|b| b.index == 22 && !b.is_bullish));
    }
}