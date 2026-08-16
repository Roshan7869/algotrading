"""
TPO Volume Profile Strategy — Python Backtest
Based on Pine Script: TPO_VolumeProfile_Strategy.pine

Strategy logic:
  BUY  : sweep below VAL → bullish rejection → POC reclaim
  SELL : sweep above VAH → bearish rejection → POC loss

Exit : 3 TP levels (40%@1R, 35%@2R, 25%@3R)
SL   : VAL/VAH + buffer
"""

import json
import os
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "user_data" / "data" / "binance"

# ─── Parameters (matching Pine Script defaults) ───────────────────────────

LOOKBACK = 50
NUM_BINS = 24
VA_PCT = 0.70
SL_BUF = 0.002
TP1_RR = 1.0
TP2_RR = 2.0
TP3_RR = 3.0
TP1_QTY = 0.40
TP2_QTY = 0.35
EMA_ON = True
EMA_LEN = 200
VOL_MUL = 1.2
BODY_R = 0.40
MAX_WAIT = 10
RISK_PCT = 2.0
COMMISSION = 0.0005
SLIPPAGE = 0.002

# ─── Volume Profile ────────────────────────────────────────────────────────


def compute_vp(highs, lows, volumes, lb=LOOKBACK, bins=NUM_BINS, va_pct=VA_PCT):
    """Compute rolling Volume Profile using vectorized numpy."""
    n = len(highs)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)

    # Compute VP on every 5th bar and forward-fill for speed
    VP_STEP = 5
    last_poc, last_vah, last_val = np.nan, np.nan, np.nan
    last_pct = -1

    for i in range(lb - 1, n):
        pct = int((i - lb + 1) / (n - lb) * 100)
        if pct >= last_pct + 5:
            print(f"\r    VP: {pct}%", end="", flush=True)
            last_pct = pct

        poc[i] = last_poc
        vah[i] = last_vah
        val[i] = last_val

        if (i - lb + 1) % VP_STEP != 0:
            continue
        start = i - lb + 1
        seg_h = highs[start:i + 1]
        seg_l = lows[start:i + 1]
        seg_v = volumes[start:i + 1]

        h_hi = seg_h.max()
        h_lo = seg_l.min()
        rng = h_hi - h_lo
        if rng <= 1e-10:
            continue

        # Normalize each candle's low/high to [0, 1] over the segment range
        norm_l = (seg_l - h_lo) / rng
        norm_h = (seg_h - h_lo) / rng

        bin_vol = np.zeros(bins)
        for j in range(lb):
            if seg_v[j] <= 0 or norm_h[j] <= norm_l[j]:
                continue
            # Find which bins this candle overlaps
            b_low = np.floor(norm_l[j] * bins).astype(int)
            b_high = np.ceil(norm_h[j] * bins).astype(int)
            b_low = max(0, b_low)
            b_high = min(bins, b_high)
            if b_low >= b_high:
                continue
            n_covered = b_high - b_low
            vol_per = seg_v[j] / n_covered
            bin_vol[b_low:b_high] += vol_per

        poc_bin = int(bin_vol.argmax())
        poc[i] = h_lo + (poc_bin + 0.5) * rng / bins

        total_v = bin_vol.sum()
        if total_v <= 0:
            continue
        target_v = total_v * va_pct
        va_v = bin_vol[poc_bin]
        up_i = dn_i = poc_bin

        while va_v < target_v:
            up_v = bin_vol[up_i + 1] if up_i + 1 < bins else 0.0
            dn_v = bin_vol[dn_i - 1] if dn_i - 1 >= 0 else 0.0
            if up_v == 0.0 and dn_v == 0.0:
                break
            if up_v >= dn_v and up_i + 1 < bins:
                up_i += 1
                va_v += up_v
            elif dn_i - 1 >= 0:
                dn_i -= 1
                va_v += dn_v
            else:
                break

        vah[i] = h_lo + (up_i + 1) * rng / bins
        val[i] = h_lo + dn_i * rng / bins
        last_poc = poc[i]
        last_vah = vah[i]
        last_val = val[i]

    return poc, vah, val


# ─── Backtest Engine ───────────────────────────────────────────────────────


@dataclass
class Trade:
    pair: str
    side: str  # "long" | "short"
    entry_time: pd.Timestamp
    entry_price: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    qty: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    closed: bool = False
    exit_reason: str = ""
    trades: list = field(default_factory=list)  # partial fills


def backtest(pair: str, df: pd.DataFrame) -> list[Trade]:
    """Run the TPO VP strategy on a single pair."""
    df = df.copy().sort_index().reset_index(drop=True)
    n = len(df)
    if n < LOOKBACK + 20:
        return []

    highs = df["high"].values.astype(np.float64)
    lows = df["low"].values.astype(np.float64)
    closes = df["close"].values.astype(np.float64)
    opens = df["open"].values.astype(np.float64)
    volumes = df["volume"].values.astype(np.float64)

    # Compute VP, EMA, avg vol
    poc, vah, val = compute_vp(highs, lows, volumes)
    ema = pd.Series(closes).ewm(span=EMA_LEN, adjust=False).mean().values
    avg_vol = pd.Series(volumes).rolling(20).mean().values

    trades = []
    b_state = 0  # bull state machine: 0=idle, 1=swept, 2=rejected
    s_state = 0
    b_bars = 0
    s_bars = 0
    active_trade: Optional[Trade] = None

    for i in range(LOOKBACK, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]):
            continue

        c = closes[i]
        h = highs[i]
        l = lows[i]
        o = opens[i]
        v = volumes[i]
        ema_v = ema[i]
        av = avg_vol[i] if not np.isnan(avg_vol[i]) else 0

        # Filters
        bull_trend = not EMA_ON or c > ema_v
        bear_trend = not EMA_ON or c < ema_v
        vol_ok = v >= av * VOL_MUL if av > 0 else True
        body = abs(c - o)
        c_rng = h - l
        body_ratio = body / c_rng if c_rng > 0 else 0

        # Sweep detection
        bull_sweep = l < val[i] and c > val[i] and vol_ok
        bear_sweep = h > vah[i] and c < vah[i] and vol_ok

        # Rejection candle
        bull_rejection = c > o and body_ratio >= BODY_R and l <= val[i] * 1.001
        bear_rejection = c < o and body_ratio >= BODY_R and h >= vah[i] * 0.999

        # POC cross
        if i > 0:
            poc_reclaim = c > poc[i] and closes[i - 1] <= poc[i]
            poc_loss = c < poc[i] and closes[i - 1] >= poc[i]
        else:
            poc_reclaim = False
            poc_loss = False

        # ── BULL state machine ──
        if bull_sweep and b_state == 0:
            b_state = 1
            b_bars = 0

        if b_state == 1:
            b_bars += 1
            if bull_rejection:
                b_state = 2
                b_bars = 0
            if b_bars > MAX_WAIT or l < val[i] * (1 - SL_BUF * 3):
                b_state = 0

        if b_state == 2:
            b_bars += 1
            if b_bars > MAX_WAIT or l < val[i] * (1 - SL_BUF * 3):
                b_state = 0

        # ── BEAR state machine ──
        if bear_sweep and s_state == 0:
            s_state = 1
            s_bars = 0

        if s_state == 1:
            s_bars += 1
            if bear_rejection:
                s_state = 2
                s_bars = 0
            if s_bars > MAX_WAIT or h > vah[i] * (1 + SL_BUF * 3):
                s_state = 0

        if s_state == 2:
            s_bars += 1
            if s_bars > MAX_WAIT or h > vah[i] * (1 + SL_BUF * 3):
                s_state = 0

        # ── Entry signals ──
        buy_sig = b_state == 2 and poc_reclaim and bull_trend
        sell_sig = s_state == 2 and poc_loss and bear_trend

        if buy_sig:
            b_state = 0
        if sell_sig:
            s_state = 0

        # ── Manage active trade ──
        if active_trade and not active_trade.closed:
            _manage_trade(active_trade, i, df, closes, highs, lows)
            if active_trade.closed:
                trades.append(active_trade)
                active_trade = None

        # ── Open new trade ──
        if active_trade is None:
            if buy_sig:
                r = c - val[i] * (1.0 - SL_BUF)
                active_trade = Trade(
                    pair=pair,
                    side="long",
                    entry_time=df.loc[i, "date"] if "date" in df.columns else df.index[i],
                    entry_price=c,
                    sl=val[i] * (1.0 - SL_BUF),
                    tp1=c + r * TP1_RR,
                    tp2=c + r * TP2_RR,
                    tp3=c + r * TP3_RR,
                    qty=1.0,
                )
            elif sell_sig:
                r = vah[i] * (1.0 + SL_BUF) - c
                active_trade = Trade(
                    pair=pair,
                    side="short",
                    entry_time=df.loc[i, "date"] if "date" in df.columns else df.index[i],
                    entry_price=c,
                    sl=vah[i] * (1.0 + SL_BUF),
                    tp1=c - r * TP1_RR,
                    tp2=c - r * TP2_RR,
                    tp3=c - r * TP3_RR,
                    qty=1.0,
                )

    # Close any remaining open trade on last bar
    if active_trade and not active_trade.closed:
        last_idx = n - 1
        active_trade.exit_reason = "end_of_data"
        active_trade.closed = True
        if active_trade.side == "long":
            active_trade.pnl = closes[last_idx] - active_trade.entry_price
        else:
            active_trade.pnl = active_trade.entry_price - closes[last_idx]
        active_trade.pnl_pct = active_trade.pnl / active_trade.entry_price * 100
        trades.append(active_trade)

    return trades


def _manage_trade(trade, i, df, closes, highs, lows):
    """Check SL/TP hits for an active trade."""
    h, l, c = highs[i], lows[i], closes[i]

    if trade.side == "long":
        if l <= trade.sl:
            trade.exit_reason = "sl"
            trade.closed = True
            remaining = 1.0 - sum(t["qty"] for t in trade.trades)
            trade.pnl = (trade.sl - trade.entry_price) * remaining
            for t in trade.trades:
                trade.pnl += (t["price"] - trade.entry_price) * t["qty"]
            return
        if h >= trade.tp1 and not any(t.get("tp") == 1 for t in trade.trades):
            trade.trades.append({"tp": 1, "price": trade.tp1, "qty": TP1_QTY})
        if h >= trade.tp2 and not any(t.get("tp") == 2 for t in trade.trades):
            trade.trades.append({"tp": 2, "price": trade.tp2, "qty": TP2_QTY})
        if h >= trade.tp3 and not any(t.get("tp") == 3 for t in trade.trades):
            remaining = 1.0 - sum(t["qty"] for t in trade.trades)
            trade.trades.append({"tp": 3, "price": trade.tp3, "qty": remaining})
            trade.exit_reason = "tp3"
            trade.closed = True
    else:  # short
        if h >= trade.sl:
            trade.exit_reason = "sl"
            trade.closed = True
            remaining = 1.0 - sum(t["qty"] for t in trade.trades)
            trade.pnl = (trade.entry_price - trade.sl) * remaining
            for t in trade.trades:
                trade.pnl += (trade.entry_price - t["price"]) * t["qty"]
            return
        if l <= trade.tp1 and not any(t.get("tp") == 1 for t in trade.trades):
            trade.trades.append({"tp": 1, "price": trade.tp1, "qty": TP1_QTY})
        if l <= trade.tp2 and not any(t.get("tp") == 2 for t in trade.trades):
            trade.trades.append({"tp": 2, "price": trade.tp2, "qty": TP2_QTY})
        if l <= trade.tp3 and not any(t.get("tp") == 3 for t in trade.trades):
            remaining = 1.0 - sum(t["qty"] for t in trade.trades)
            trade.trades.append({"tp": 3, "price": trade.tp3, "qty": remaining})
            trade.exit_reason = "tp3"
            trade.closed = True

    if trade.closed and trade.exit_reason != "sl":
        total_pnl = sum(
            (t["price"] - trade.entry_price) * t["qty"] if trade.side == "long"
            else (trade.entry_price - t["price"]) * t["qty"]
            for t in trade.trades
        )
        trade.pnl = total_pnl
        trade.pnl_pct = total_pnl / trade.entry_price * 100


# ─── Report ────────────────────────────────────────────────────────────────


def generate_report(all_trades: dict[str, list[Trade]]):
    """Generate comprehensive backtest report."""
    print("=" * 80)
    print("  TPO VOLUME PROFILE STRATEGY — BACKTEST REPORT")
    print("=" * 80)
    print(f"\n  Parameters: lookback={LOOKBACK}, bins={NUM_BINS}, VA%={VA_PCT}")
    print(f"  SL buf={SL_BUF}, TP1@1R({TP1_QTY*100:.0f}%), TP2@2R({TP2_QTY*100:.0f}%), TP3@3R")
    print(f"  EMA trend={EMA_ON}({EMA_LEN}), min vol ratio={VOL_MUL}x, min body={BODY_R}")
    print(f"  Commission={COMMISSION*100:.2f}%, Slippage={SLIPPAGE*100:.2f}%\n")

    all_t = []
    pair_stats = []

    for pair, tlist in sorted(all_trades.items()):
        all_t.extend(tlist)
        if not tlist:
            continue
        wins = [t for t in tlist if t.pnl > 0]
        losses = [t for t in tlist if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in tlist)
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        win_rate = len(wins) / len(tlist) * 100 if tlist else 0
        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        avg_pnl = total_pnl / len(tlist)
        avg_r = avg_pnl / 1.0  # normalized

        sl_count = sum(1 for t in tlist if t.exit_reason == "sl")
        tp_count = sum(1 for t in tlist if "tp" in t.exit_reason)

        pair_stats.append({
            "pair": pair,
            "trades": len(tlist),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "profit_factor": profit_factor,
            "avg_pnl": avg_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "sl_count": sl_count,
            "tp_count": tp_count,
            "avg_r": avg_r,
        })

    # Overall
    if not all_t:
        print("  No trades generated for any pair.\n")
        return

    total_pnl = sum(t.pnl for t in all_t)
    wins = [t for t in all_t if t.pnl > 0]
    losses = [t for t in all_t if t.pnl <= 0]
    gross_p = sum(t.pnl for t in wins)
    gross_l = abs(sum(t.pnl for t in losses))
    wr = len(wins) / len(all_t) * 100
    pf = gross_p / gross_l if gross_l > 0 else float("inf")

    print(f"  {'Pair':<10} {'Trades':>7} {'Win%':>7} {'P&L':>10} {'PF':>7} {'AvgR':>7} {'SL':>5} {'TP':>5}")
    print(f"  {'-'*56}")
    for ps in sorted(pair_stats, key=lambda x: x["total_pnl"], reverse=True):
        print(f"  {ps['pair']:<10} {ps['trades']:>7} {ps['win_rate']:>6.1f}% {ps['total_pnl']:>+8.4f} {ps['profit_factor']:>6.2f} {ps['avg_r']:>+6.2f} {ps['sl_count']:>5} {ps['tp_count']:>5}")

    print(f"\n  {'─' * 56}")
    print(f"  {'TOTAL':<10} {len(all_t):>7} {wr:>6.1f}% {total_pnl:>+8.4f} {pf:>6.2f}")
    print()
    print(f"  Gross Profit : {gross_p:>+.4f}")
    print(f"  Gross Loss   : {gross_l:>+.4f}")
    print(f"  Win Rate     : {wr:.1f}%")
    print(f"  Profit Factor: {pf:.2f}")
    print(f"  Best Trade   : {max(t.pnl for t in all_t):>+.4f}")
    print(f"  Worst Trade  : {min(t.pnl for t in all_t):>+.4f}")
    print(f"  Avg Trade    : {total_pnl / len(all_t):>+.4f}")
    print(f"  Avg Win      : {gross_p / len(wins) if wins else 0:>+.4f}")
    print(f"  Avg Loss     : {gross_l / len(losses) if losses else 0:>+.4f}")
    print(f"  SL hits      : {sum(1 for t in all_t if t.exit_reason == 'sl')}")
    print(f"  TP hits      : {sum(1 for t in all_t if 'tp' in t.exit_reason)}")
    print(f"\n  Commission   : -{COMMISSION * 100:.2f}% per trade")
    print(f"  Slippage     : {SLIPPAGE * 100:.2f}%")
    print("=" * 80)


def load_data(pair: str) -> Optional[pd.DataFrame]:
    """Load feather data for a pair."""
    patterns = [
        DATA_DIR / f"{pair}_USDT-1h.feather",
        DATA_DIR / "spot" / f"{pair}_USDT-1h.feather",
    ]
    for p in patterns:
        if p.exists():
            df = pd.read_feather(p)
            # Standardize columns
            df.columns = [c.lower().strip() for c in df.columns]
            if "timestamp" in df.columns:
                df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df = df.set_index("date")
            elif "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            elif "time" in df.columns:
                df["date"] = pd.to_datetime(df["time"], unit="ms", utc=True)
                df = df.set_index("date")
            # Rename columns
            col_map = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            return df
    return None


if __name__ == "__main__":
    PAIRS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "LTC", "AVAX", "NEAR", "BCH", "XTZ"]

    all_trades = {}
    for pair in PAIRS:
        df = load_data(pair)
        if df is None or len(df) < LOOKBACK + 50:
            print(f"  {pair}: insufficient data, skipping")
            continue
        print(f"  {pair}: {len(df)} bars — running backtest...")
        trades = backtest(pair, df)
        all_trades[pair] = trades
        print(f"    → {len(trades)} trades")

    print()
    generate_report(all_trades)
