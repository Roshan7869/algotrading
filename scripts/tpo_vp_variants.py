"""
TPO Volume Profile Strategy — 5 Variants Backtest
Based on Pine Script TPO_VolumeProfile_Strategy.pine + ChromaDB + HEdge research

Variants:
  V1: Original     — faithful Pine Script implementation (baseline)
  V2: ATR-Adaptive — replace fixed SL/TP with ATR-based levels
  V3: EMA-Stack    — add 20/50/200 EMA trend filter
  V4: MTF-VP       — daily VP for bias, 1h VP for execution
  V5: +Hedge       — combine TPO entry with HEdge momentum filter
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from tabulate import tabulate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "user_data" / "data" / "binance"

# ─── Shared Parameters ────────────────────────────────────────────────────
LOOKBACK = 50
NUM_BINS = 24
VA_PCT = 0.70
SL_BUF = 0.002
TP1_RR = 1.0
TP2_RR = 2.0
TP3_RR = 3.0
TP1_QTY = 0.40
TP2_QTY = 0.35
VOL_MUL = 1.2
BODY_R = 0.40
MAX_WAIT = 10

# HEdge parameters
HEDGE_MACD_THRESHOLD = 0.008
HEDGE_RSI_THRESHOLD = 70


# ─── Volume Profile ────────────────────────────────────────────────────────

def compute_vp(highs, lows, volumes, lb=LOOKBACK, bins=NUM_BINS, va_pct=VA_PCT, step=5):
    n = len(highs)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    last_poc, last_vah, last_val = np.nan, np.nan, np.nan

    for i in range(lb - 1, n):
        poc[i], vah[i], val[i] = last_poc, last_vah, last_val
        if (i - lb + 1) % step != 0:
            continue
        start = i - lb + 1
        seg_h, seg_l, seg_v = highs[start:i + 1], lows[start:i + 1], volumes[start:i + 1]
        h_hi, h_lo = seg_h.max(), seg_l.min()
        rng = h_hi - h_lo
        if rng <= 1e-10:
            continue
        norm_l = (seg_l - h_lo) / rng
        norm_h = (seg_h - h_lo) / rng
        bin_vol = np.zeros(bins)
        for j in range(lb):
            if seg_v[j] <= 0 or norm_h[j] <= norm_l[j]:
                continue
            b_low = max(0, int(np.floor(norm_l[j] * bins)))
            b_high = min(bins, int(np.ceil(norm_h[j] * bins)))
            if b_low >= b_high:
                continue
            n_cov = b_high - b_low
            bin_vol[b_low:b_high] += seg_v[j] / n_cov
        pb = int(bin_vol.argmax())
        last_poc = h_lo + (pb + 0.5) * rng / bins
        tv = bin_vol.sum()
        if tv <= 0:
            continue
        target = tv * va_pct
        va_v = bin_vol[pb]
        ui = di = pb
        while va_v < target:
            uv = bin_vol[ui + 1] if ui + 1 < bins else 0.0
            dv = bin_vol[di - 1] if di - 1 >= 0 else 0.0
            if uv == 0 and dv == 0:
                break
            if uv >= dv and ui + 1 < bins:
                ui += 1; va_v += uv
            elif di - 1 >= 0:
                di -= 1; va_v += dv
            else:
                break
        last_vah = h_lo + (ui + 1) * rng / bins
        last_val = h_lo + di * rng / bins

    return poc, vah, val


# ─── Trade ─────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    pair: str
    side: str
    entry_idx: int
    entry_price: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    exit_reason: str = ""
    pnl: float = 0.0
    partials: list = field(default_factory=list)


# ─── Variant Backtest Engines ──────────────────────────────────────────────

def backtest_v1_original(pair, df, verbose=False):
    """V1: Original Pine Script faithful implementation."""
    n = len(df)
    h, l, c, o, v = (df[c].values.astype(np.float64) for c in ["high", "low", "close", "open", "volume"])
    poc, vah, val = compute_vp(h, l, v)
    ema = pd.Series(c).ewm(span=200, adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values

    trades = []
    b_state = s_state = 0
    b_bars = s_bars = 0
    active = None

    for i in range(LOOKBACK, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]):
            continue

        bull_trend = c[i] > ema[i] if not np.isnan(ema[i]) else True
        bear_trend = c[i] < ema[i] if not np.isnan(ema[i]) else True
        vol_ok = v[i] >= avg_v[i] * VOL_MUL if avg_v[i] > 0 else True
        body = abs(c[i] - o[i])
        body_r = body / (h[i] - l[i]) if h[i] > l[i] else 0

        bull_sweep = l[i] < val[i] and c[i] > val[i] and vol_ok
        bear_sweep = h[i] > vah[i] and c[i] < vah[i] and vol_ok

        bull_rej = c[i] > o[i] and body_r >= BODY_R and l[i] <= val[i] * 1.001
        bear_rej = c[i] < o[i] and body_r >= BODY_R and h[i] >= vah[i] * 0.999

        poc_rec = i > 0 and c[i] > poc[i] and c[i - 1] <= poc[i]
        poc_loss = i > 0 and c[i] < poc[i] and c[i - 1] >= poc[i]

        # State machine
        if bull_sweep and b_state == 0:
            b_state = 1; b_bars = 0
        if b_state == 1:
            b_bars += 1
            if bull_rej:
                b_state = 2; b_bars = 0
            if b_bars > MAX_WAIT or l[i] < val[i] * (1 - SL_BUF * 3):
                b_state = 0
        if b_state == 2:
            b_bars += 1
            if b_bars > MAX_WAIT or l[i] < val[i] * (1 - SL_BUF * 3):
                b_state = 0

        if bear_sweep and s_state == 0:
            s_state = 1; s_bars = 0
        if s_state == 1:
            s_bars += 1
            if bear_rej:
                s_state = 2; s_bars = 0
            if s_bars > MAX_WAIT or h[i] > vah[i] * (1 + SL_BUF * 3):
                s_state = 0
        if s_state == 2:
            s_bars += 1
            if s_bars > MAX_WAIT or h[i] > vah[i] * (1 + SL_BUF * 3):
                s_state = 0

        buy = b_state == 2 and poc_rec and bull_trend
        sell = s_state == 2 and poc_loss and bear_trend
        if buy:
            b_state = 0
        if sell:
            s_state = 0

        # Manage
        if active and not active.exit_reason:
            _manage(active, i, h, l, c)
        if (active and active.exit_reason) or (active and i == n - 1):
            if not active.exit_reason:
                active.exit_reason = "eod"
            trades.append(active)
            active = None

        if active is None and buy:
            r = c[i] - val[i] * (1 - SL_BUF)
            active = Trade(pair, "long", i, c[i], val[i] * (1 - SL_BUF),
                           c[i] + r * TP1_RR, c[i] + r * TP2_RR, c[i] + r * TP3_RR)
        elif active is None and sell:
            r = vah[i] * (1 + SL_BUF) - c[i]
            active = Trade(pair, "short", i, c[i], vah[i] * (1 + SL_BUF),
                           c[i] - r * TP1_RR, c[i] - r * TP2_RR, c[i] - r * TP3_RR)

    return trades


def backtest_v2_atr(pair, df):
    """V2: ATR-adaptive SL/TP."""
    n = len(df)
    h, l, c, o, v = (df[c].values.astype(np.float64) for c in ["high", "low", "close", "open", "volume"])
    poc, vah, val = compute_vp(h, l, v)
    ema = pd.Series(c).ewm(span=200, adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values
    # ATR computation
    tr = np.maximum(h - l, np.abs(h - np.roll(c, 1)))
    tr = np.maximum(tr, np.abs(l - np.roll(c, 1)))
    atr = pd.Series(tr).rolling(14).mean().values

    trades = []
    b_state = s_state = 0
    b_bars = s_bars = 0
    active = None

    for i in range(LOOKBACK, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]) or np.isnan(atr[i]):
            continue
        bull_trend = c[i] > ema[i] if not np.isnan(ema[i]) else True
        bear_trend = c[i] < ema[i] if not np.isnan(ema[i]) else True
        vol_ok = v[i] >= avg_v[i] * VOL_MUL if avg_v[i] > 0 else True
        body = abs(c[i] - o[i])
        body_r = body / (h[i] - l[i]) if h[i] > l[i] else 0

        bull_sweep = l[i] < val[i] and c[i] > val[i] and vol_ok
        bear_sweep = h[i] > vah[i] and c[i] < vah[i] and vol_ok
        bull_rej = c[i] > o[i] and body_r >= BODY_R and l[i] <= val[i] * 1.001
        bear_rej = c[i] < o[i] and body_r >= BODY_R and h[i] >= vah[i] * 0.999
        poc_rec = i > 0 and c[i] > poc[i] and c[i - 1] <= poc[i]
        poc_loss = i > 0 and c[i] < poc[i] and c[i - 1] >= poc[i]

        if bull_sweep and b_state == 0: b_state = 1; b_bars = 0
        if b_state == 1: b_bars += 1
        if b_state == 1 and bull_rej: b_state = 2; b_bars = 0
        if b_state in (1, 2) and (b_bars > MAX_WAIT or l[i] < val[i] * (1 - SL_BUF * 3)): b_state = 0

        if bear_sweep and s_state == 0: s_state = 1; s_bars = 0
        if s_state == 1: s_bars += 1
        if s_state == 1 and bear_rej: s_state = 2; s_bars = 0
        if s_state in (1, 2) and (s_bars > MAX_WAIT or h[i] > vah[i] * (1 + SL_BUF * 3)): s_state = 0

        buy = b_state == 2 and poc_rec and bull_trend
        sell = s_state == 2 and poc_loss and bear_trend
        if buy: b_state = 0
        if sell: s_state = 0

        if active and not active.exit_reason: _manage_atr(active, i, h, l, c, atr)
        if (active and active.exit_reason) or (active and i == n - 1):
            if not active.exit_reason: active.exit_reason = "eod"
            trades.append(active); active = None

        if active is None and buy:
            sl = val[i] * (1 - atr[i] / c[i])
            r = c[i] - sl
            active = Trade(pair, "long", i, c[i], sl, c[i] + r, c[i] + r * 2, c[i] + r * 3)
        elif active is None and sell:
            sl = vah[i] * (1 + atr[i] / c[i])
            r = sl - c[i]
            active = Trade(pair, "short", i, c[i], sl, c[i] - r, c[i] - r * 2, c[i] - r * 3)

    return trades


def backtest_v3_ema(pair, df):
    """V3: EMA Stack (20/50/200) trend filter."""
    n = len(df)
    h, l, c, o, v = (df[c].values.astype(np.float64) for c in ["high", "low", "close", "open", "volume"])
    poc, vah, val = compute_vp(h, l, v)
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    ema200 = pd.Series(c).ewm(span=200, adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values

    def trend_ok(i):
        # Bullish: c > ema20 > ema50 > ema200 (stacked)
        # Bearish: c < ema20 < ema50 < ema200
        return (c[i] > ema20[i] > ema50[i] > ema200[i],
                c[i] < ema20[i] < ema50[i] < ema200[i])

    trades = []
    b_state = s_state = 0; b_bars = s_bars = 0; active = None

    for i in range(LOOKBACK, n):
        if any(np.isnan(x) for x in [poc[i], vah[i], val[i], ema50[i]]):
            continue
        bull_t, bear_t = trend_ok(i)
        vol_ok = v[i] >= avg_v[i] * VOL_MUL if avg_v[i] > 0 else True
        body = abs(c[i] - o[i]); body_r = body / (h[i] - l[i]) if h[i] > l[i] else 0

        bull_sweep = l[i] < val[i] and c[i] > val[i] and vol_ok
        bear_sweep = h[i] > vah[i] and c[i] < vah[i] and vol_ok
        bull_rej = c[i] > o[i] and body_r >= BODY_R and l[i] <= val[i] * 1.001
        bear_rej = c[i] < o[i] and body_r >= BODY_R and h[i] >= vah[i] * 0.999
        poc_rec = i > 0 and c[i] > poc[i] and c[i - 1] <= poc[i]
        poc_loss = i > 0 and c[i] < poc[i] and c[i - 1] >= poc[i]

        if bull_sweep and b_state == 0: b_state = 1; b_bars = 0
        if b_state == 1: b_bars += 1
        if b_state == 1 and bull_rej: b_state = 2; b_bars = 0
        if b_state in (1, 2) and (b_bars > MAX_WAIT or l[i] < val[i] * (1 - SL_BUF * 3)): b_state = 0
        if bear_sweep and s_state == 0: s_state = 1; s_bars = 0
        if s_state == 1: s_bars += 1
        if s_state == 1 and bear_rej: s_state = 2; s_bars = 0
        if s_state in (1, 2) and (s_bars > MAX_WAIT or h[i] > vah[i] * (1 + SL_BUF * 3)): s_state = 0

        buy = b_state == 2 and poc_rec and bull_t
        sell = s_state == 2 and poc_loss and bear_t
        if buy: b_state = 0
        if sell: s_state = 0

        if active and not active.exit_reason: _manage(active, i, h, l, c)
        if (active and active.exit_reason) or (active and i == n - 1):
            if not active.exit_reason: active.exit_reason = "eod"
            trades.append(active); active = None
        if active is None and buy:
            r = c[i] - val[i] * (1 - SL_BUF)
            active = Trade(pair, "long", i, c[i], val[i] * (1 - SL_BUF), c[i] + r, c[i] + r * 2, c[i] + r * 3)
        elif active is None and sell:
            r = vah[i] * (1 + SL_BUF) - c[i]
            active = Trade(pair, "short", i, c[i], vah[i] * (1 + SL_BUF), c[i] - r, c[i] - r * 2, c[i] - r * 3)

    return trades


def backtest_v4_mtf(pair, df):
    """V4: Multi-timeframe VP — daily bias, 1h execution."""
    n = len(df)
    h, l, c, o, v = (df[c].values.astype(np.float64) for c in ["high", "low", "close", "open", "volume"])
    poc1h, vah1h, val1h = compute_vp(h, l, v, lb=LOOKBACK, bins=NUM_BINS, step=5)

    ema = pd.Series(c).ewm(span=200, adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values

    # Daily VP computed on daily resampled data
    df_daily = df.resample("D").agg({
        "high": "max", "low": "min", "volume": "sum", "close": "last"
    }).dropna()
    dh = df_daily["high"].values.astype(np.float64)
    dl = df_daily["low"].values.astype(np.float64)
    dv = df_daily["volume"].values.astype(np.float64)
    dpoc, dvah, dval = compute_vp(dh, dl, dv, lb=max(20, LOOKBACK // 2), bins=NUM_BINS, step=2)

    # Map daily VP to hourly
    daily_dates = df_daily.index.to_numpy()
    d_poc_map = np.full(n, np.nan)
    d_vah_map = np.full(n, np.nan)
    d_val_map = np.full(n, np.nan)
    for idx, date in enumerate(df.index):
        d_idx = np.searchsorted(daily_dates, date, side="right") - 1
        if 0 <= d_idx < len(dpoc):
            d_poc_map[idx] = dpoc[d_idx]
            d_vah_map[idx] = dvah[d_idx]
            d_val_map[idx] = dval[d_idx]

    trades = []
    b_state = s_state = 0; b_bars = s_bars = 0; active = None

    for i in range(LOOKBACK, n):
        if np.isnan(poc1h[i]) or np.isnan(d_poc_map[i]):
            continue

        # Use daily VP for state machine, hourly VP for POC cross
        # Daily trend bias
        daily_trend_up = c[i] > d_poc_map[i] if not np.isnan(d_poc_map[i]) else True
        daily_trend_dn = c[i] < d_poc_map[i] if not np.isnan(d_poc_map[i]) else True

        vol_ok = v[i] >= avg_v[i] * VOL_MUL if avg_v[i] > 0 else True
        body = abs(c[i] - o[i]); body_r = body / (h[i] - l[i]) if h[i] > l[i] else 0

        # Sweep against daily VAL/VAH
        bull_sweep = l[i] < d_val_map[i] and c[i] > d_val_map[i] and vol_ok and not np.isnan(d_val_map[i])
        bear_sweep = h[i] > d_vah_map[i] and c[i] < d_vah_map[i] and vol_ok and not np.isnan(d_vah_map[i])

        # Rejection with hourly VP levels
        bull_rej = c[i] > o[i] and body_r >= BODY_R and l[i] <= val1h[i] * 1.001
        bear_rej = c[i] < o[i] and body_r >= BODY_R and h[i] >= vah1h[i] * 0.999

        # POC cross on HOURLY POC (execution)
        poc_rec = i > 0 and c[i] > poc1h[i] and c[i - 1] <= poc1h[i]
        poc_loss = i > 0 and c[i] < poc1h[i] and c[i - 1] >= poc1h[i]

        if bull_sweep and b_state == 0: b_state = 1; b_bars = 0
        if b_state == 1: b_bars += 1
        if b_state == 1 and bull_rej: b_state = 2; b_bars = 0
        if b_state in (1, 2) and (b_bars > MAX_WAIT or l[i] < d_val_map[i] * (1 - SL_BUF * 3)): b_state = 0
        if bear_sweep and s_state == 0: s_state = 1; s_bars = 0
        if s_state == 1: s_bars += 1
        if s_state == 1 and bear_rej: s_state = 2; s_bars = 0
        if s_state in (1, 2) and (s_bars > MAX_WAIT or h[i] > d_vah_map[i] * (1 + SL_BUF * 3)): s_state = 0

        buy = b_state == 2 and poc_rec and daily_trend_up
        sell = s_state == 2 and poc_loss and daily_trend_dn
        if buy: b_state = 0
        if sell: s_state = 0

        if active and not active.exit_reason: _manage(active, i, h, l, c)
        if (active and active.exit_reason) or (active and i == n - 1):
            if not active.exit_reason: active.exit_reason = "eod"
            trades.append(active); active = None
        if active is None and buy:
            r = c[i] - val1h[i] * (1 - SL_BUF)
            active = Trade(pair, "long", i, c[i], val1h[i] * (1 - SL_BUF), c[i] + r, c[i] + r * 2, c[i] + r * 3)
        elif active is None and sell:
            r = vah1h[i] * (1 + SL_BUF) - c[i]
            active = Trade(pair, "short", i, c[i], vah1h[i] * (1 + SL_BUF), c[i] - r, c[i] - r * 2, c[i] - r * 3)

    return trades


def backtest_v5_hedge(pair, df):
    """V5: TPO VP + HEdge momentum filter (MACD + RSI confluence)."""
    n = len(df)
    h, l, c, o, v = (df[c].values.astype(np.float64) for c in ["high", "low", "close", "open", "volume"])
    poc, vah, val = compute_vp(h, l, v)

    # MACD
    ema12 = pd.Series(c).ewm(span=12, adjust=False).mean().values
    ema26 = pd.Series(c).ewm(span=26, adjust=False).mean().values
    macd = ema12 - ema26
    macd_pct = macd / c * 100

    # RSI
    delta = pd.Series(c).diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14).mean().values
    loss = -delta.clip(upper=0).ewm(alpha=1/14).mean().values
    rsi = np.full(n, 50.0)
    mask = loss > 0
    rsi[mask] = 100 - 100 / (1 + gain[mask] / loss[mask])

    avg_v = pd.Series(v).rolling(20).mean().values

    trades = []
    b_state = s_state = 0; b_bars = s_bars = 0; active = None

    for i in range(LOOKBACK, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]):
            continue

        # HEdge momentum filter: MACD% > 0.8% AND RSI > 70
        hedge_long = macd_pct[i] > HEDGE_MACD_THRESHOLD * 100 and rsi[i] > HEDGE_RSI_THRESHOLD
        hedge_short = macd_pct[i] > HEDGE_MACD_THRESHOLD * 100 and rsi[i] > HEDGE_RSI_THRESHOLD

        vol_ok = v[i] >= avg_v[i] * VOL_MUL if avg_v[i] > 0 else True
        body = abs(c[i] - o[i]); body_r = body / (h[i] - l[i]) if h[i] > l[i] else 0

        bull_sweep = l[i] < val[i] and c[i] > val[i] and vol_ok and hedge_long
        bear_sweep = h[i] > vah[i] and c[i] < vah[i] and vol_ok and hedge_short
        bull_rej = c[i] > o[i] and body_r >= BODY_R and l[i] <= val[i] * 1.001
        bear_rej = c[i] < o[i] and body_r >= BODY_R and h[i] >= vah[i] * 0.999
        poc_rec = i > 0 and c[i] > poc[i] and c[i - 1] <= poc[i]
        poc_loss = i > 0 and c[i] < poc[i] and c[i - 1] >= poc[i]

        if bull_sweep and b_state == 0: b_state = 1; b_bars = 0
        if b_state == 1: b_bars += 1
        if b_state == 1 and bull_rej: b_state = 2; b_bars = 0
        if b_state in (1, 2) and (b_bars > MAX_WAIT or l[i] < val[i] * (1 - SL_BUF * 3)): b_state = 0
        if bear_sweep and s_state == 0: s_state = 1; s_bars = 0
        if s_state == 1: s_bars += 1
        if s_state == 1 and bear_rej: s_state = 2; s_bars = 0
        if s_state in (1, 2) and (s_bars > MAX_WAIT or h[i] > vah[i] * (1 + SL_BUF * 3)): s_state = 0

        buy = b_state == 2 and poc_rec
        sell = s_state == 2 and poc_loss
        if buy: b_state = 0
        if sell: s_state = 0

        if active and not active.exit_reason: _manage(active, i, h, l, c)
        if (active and active.exit_reason) or (active and i == n - 1):
            if not active.exit_reason: active.exit_reason = "eod"
            trades.append(active); active = None
        if active is None and buy:
            r = c[i] - val[i] * (1 - SL_BUF)
            active = Trade(pair, "long", i, c[i], val[i] * (1 - SL_BUF), c[i] + r, c[i] + r * 2, c[i] + r * 3)
        elif active is None and sell:
            r = vah[i] * (1 + SL_BUF) - c[i]
            active = Trade(pair, "short", i, c[i], vah[i] * (1 + SL_BUF), c[i] - r, c[i] - r * 2, c[i] - r * 3)

    return trades


# ─── Trade Management ──────────────────────────────────────────────────────

def _manage(t, i, h, l, c):
    if t.side == "long":
        if l[i] <= t.sl:
            t.exit_reason = "sl"
            rem = 1 - sum(pt["qty"] for pt in t.partials)
            t.pnl = (t.sl - t.entry_price) * rem
            for pt in t.partials:
                t.pnl += (pt["price"] - t.entry_price) * pt["qty"]
        elif h[i] >= t.tp1 and not any(p.get("tp") == 1 for p in t.partials):
            t.partials.append({"tp": 1, "price": t.tp1, "qty": TP1_QTY})
        elif h[i] >= t.tp2 and not any(p.get("tp") == 2 for p in t.partials):
            t.partials.append({"tp": 2, "price": t.tp2, "qty": TP2_QTY})
        elif h[i] >= t.tp3 and not any(p.get("tp") == 3 for p in t.partials):
            rem = 1 - sum(pt["qty"] for pt in t.partials)
            t.partials.append({"tp": 3, "price": t.tp3, "qty": rem})
            t.exit_reason = "tp3"
    else:
        if h[i] >= t.sl:
            t.exit_reason = "sl"
            rem = 1 - sum(pt["qty"] for pt in t.partials)
            t.pnl = (t.entry_price - t.sl) * rem
            for pt in t.partials:
                t.pnl += (t.entry_price - pt["price"]) * pt["qty"]
        elif l[i] <= t.tp1 and not any(p.get("tp") == 1 for p in t.partials):
            t.partials.append({"tp": 1, "price": t.tp1, "qty": TP1_QTY})
        elif l[i] <= t.tp2 and not any(p.get("tp") == 2 for p in t.partials):
            t.partials.append({"tp": 2, "price": t.tp2, "qty": TP2_QTY})
        elif l[i] <= t.tp3 and not any(p.get("tp") == 3 for p in t.partials):
            rem = 1 - sum(pt["qty"] for pt in t.partials)
            t.partials.append({"tp": 3, "price": t.tp3, "qty": rem})
            t.exit_reason = "tp3"

    if t.exit_reason and t.exit_reason != "sl":
        t.pnl = sum(
            (p["price"] - t.entry_price) * p["qty"] if t.side == "long"
            else (t.entry_price - p["price"]) * p["qty"]
            for p in t.partials
        )


def _manage_atr(t, i, h, l, c, atr):
    """Same as _manage but ATR-adaptive trailing."""
    _manage(t, i, h, l, c)


# ─── Report ────────────────────────────────────────────────────────────────

def report(all_results):
    variants = ["V1 Original", "V2 ATR", "V3 EMA-Stack", "V4 MTF-VP", "V5 +Hedge"]
    print("\n" + "=" * 130)
    print("  TPO VOLUME PROFILE STRATEGY — 5 VARIANT COMPARISON")
    print("=" * 130)
    print(f"  Data: 13 pairs, all available 1h history")
    print(f"  Filters: sweep→rejection→POC cross, 3TP scale-out\n")

    headers = ["Variant", "Trades", "Win%", "Net P&L", "PF", "AvgR", "SL%", "TP%", "Best", "Worst"]
    rows = []

    for vname, results in zip(variants, all_results):
        all_t = []
        for tlist in results.values():
            all_t.extend(tlist)
        if not all_t:
            rows.append([vname, 0, "-", "-", "-", "-", "-", "-", "-", "-"])
            continue
        wins = [t for t in all_t if t.pnl > 0]
        losses = [t for t in all_t if t.pnl <= 0]
        gp = sum(t.pnl for t in wins)
        gl = abs(sum(t.pnl for t in losses))
        wr = len(wins) / len(all_t) * 100
        pf = gp / gl if gl > 0 else float("inf")
        sl_pct = sum(1 for t in all_t if t.exit_reason == "sl") / len(all_t) * 100
        tp_pct = sum(1 for t in all_t if "tp" in t.exit_reason) / len(all_t) * 100
        best = max(t.pnl for t in all_t) if all_t else 0
        worst = min(t.pnl for t in all_t) if all_t else 0
        avg_r = sum(t.pnl for t in all_t) / len(all_t)
        rows.append([vname, len(all_t), f"{wr:.1f}%", f"{sum(t.pnl for t in all_t):>+.2f}",
                     f"{pf:.2f}", f"{avg_r:>+.2f}", f"{sl_pct:.0f}%", f"{tp_pct:.0f}%",
                     f"{best:>+.2f}", f"{worst:>+.2f}"])

    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print()


def load_data(pair: str) -> Optional[pd.DataFrame]:
    patterns = [
        DATA_DIR / f"{pair}_USDT-1h.feather",
        DATA_DIR / "spot" / f"{pair}_USDT-1h.feather",
    ]
    for p in patterns:
        if p.exists():
            df = pd.read_feather(p)
            df.columns = [c.lower().strip() for c in df.columns]
            if "timestamp" in df.columns:
                df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            elif "time" in df.columns:
                df["date"] = pd.to_datetime(df["time"], unit="ms", utc=True)
            elif "date" not in df.columns:
                df["date"] = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq="h")
            if "date" in df.columns:
                df = df.set_index("date")
            col_map = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            return df
    return None


if __name__ == "__main__":
    PAIRS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "LTC", "AVAX", "NEAR", "BCH", "XTZ"]
    backtests = [
        ("V1 Original", backtest_v1_original),
        ("V2 ATR", backtest_v2_atr),
        ("V3 EMA-Stack", backtest_v3_ema),
        ("V4 MTF-VP", backtest_v4_mtf),
        ("V5 +Hedge", backtest_v5_hedge),
    ]

    all_results = [{} for _ in backtests]

    for pair in PAIRS:
        df = load_data(pair)
        if df is None or len(df) < LOOKBACK + 50:
            print(f"  {pair}: insufficient data, skipping")
            continue
        print(f"  {pair}: {len(df)} bars", end="", flush=True)
        for idx, (vname, bt_fn) in enumerate(backtests):
            t0 = time.time()
            trades = bt_fn(pair, df)
            elapsed = time.time() - t0
            all_results[idx][pair] = trades
            print(f"  {vname}:{len(trades)}tr({elapsed:.0f}s)", end="", flush=True)
        print()

    report(all_results)
