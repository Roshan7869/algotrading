"""
TPO VP V3 EMA-Stack — Last 3 Days Backtest
Runs on 2026-05-13 to 2026-05-16 data for all 13 pairs
"""

import json
import csv
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "user_data" / "data" / "binance"

# Original V3 parameters
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
VP_STEP = 2  # faster for small dataset


def compute_vp(highs, lows, volumes, lb=LOOKBACK, bins=NUM_BINS, va_pct=VA_PCT):
    n = len(highs)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    last_poc, last_vah, last_val = np.nan, np.nan, np.nan
    for i in range(lb - 1, n):
        poc[i], vah[i], val[i] = last_poc, last_vah, last_val
        if (i - lb + 1) % VP_STEP != 0:
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


def v3_backtest_3d(pair, df):
    """V3 EMA-Stack on 3 days of data with shorter lookback."""
    n = len(df)
    dates = df.index.to_numpy()
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    c = df["close"].values.astype(np.float64)
    o = df["open"].values.astype(np.float64)
    v = df["volume"].values.astype(np.float64)

    # Use shorter lookback for 3-day window
    lb = min(LOOKBACK, n // 3)
    if lb < 10:
        return []

    poc, vah, val = compute_vp(h, l, v, lb=lb)

    # EMA20 for trend (EMA200 needs 200 bars, not available in 3 days)
    ema20_s = pd.Series(c).ewm(span=20, adjust=False).mean().values
    ema50_s = pd.Series(c).ewm(span=50, adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values

    # Try original EMA stack if enough data, else fallback to EMA20 only
    ema200_ok = n >= 200
    if n >= 200:
        ema200_s = pd.Series(c).ewm(span=200, adjust=False).mean().values
    else:
        ema200_s = np.full(n, np.nan)

    def trend_ok(i):
        if ema200_ok and not np.isnan(ema200_s[i]):
            return (c[i] > ema20_s[i] > ema50_s[i] > ema200_s[i],
                    c[i] < ema20_s[i] < ema50_s[i] < ema200_s[i])
        # Fallback: EMA20 only
        return (c[i] > ema20_s[i], c[i] < ema20_s[i])

    trades = []
    b_state = s_state = 0; b_bars = s_bars = 0
    active = None; active_partials = []

    for i in range(lb, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]):
            continue

        bull_t, bear_t = trend_ok(i)
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

        buy = b_state == 2 and poc_rec and bull_t
        sell = s_state == 2 and poc_loss and bear_t
        if buy: b_state = 0
        if sell: s_state = 0

        # Manage
        if active:
            exit_now = False
            if active["side"] == "long":
                if l[i] <= active["sl"]:
                    exit_now = True; reason = "sl"
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    pnl = (active["sl"] - active["entry_price"]) * rem
                    for pt in active_partials:
                        pnl += (pt["price"] - active["entry_price"]) * pt["qty"]
                elif h[i] >= active["tp3"] and not any(p.get("tp") == 3 for p in active_partials):
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    active_partials.append({"tp": 3, "price": active["tp3"], "qty": rem})
                    exit_now = True; reason = "tp3"
                    pnl = sum((p["price"] - active["entry_price"]) * p["qty"] for p in active_partials)
                elif h[i] >= active["tp2"] and not any(p.get("tp") == 2 for p in active_partials):
                    active_partials.append({"tp": 2, "price": active["tp2"], "qty": TP2_QTY})
                elif h[i] >= active["tp1"] and not any(p.get("tp") == 1 for p in active_partials):
                    active_partials.append({"tp": 1, "price": active["tp1"], "qty": TP1_QTY})
            else:
                if h[i] >= active["sl"]:
                    exit_now = True; reason = "sl"
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    pnl = (active["entry_price"] - active["sl"]) * rem
                    for pt in active_partials:
                        pnl += (active["entry_price"] - pt["price"]) * pt["qty"]
                elif l[i] <= active["tp3"] and not any(p.get("tp") == 3 for p in active_partials):
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    active_partials.append({"tp": 3, "price": active["tp3"], "qty": rem})
                    exit_now = True; reason = "tp3"
                    pnl = sum((active["entry_price"] - p["price"]) * p["qty"] for p in active_partials)
                elif l[i] <= active["tp2"] and not any(p.get("tp") == 2 for p in active_partials):
                    active_partials.append({"tp": 2, "price": active["tp2"], "qty": TP2_QTY})
                elif l[i] <= active["tp1"] and not any(p.get("tp") == 1 for p in active_partials):
                    active_partials.append({"tp": 1, "price": active["tp1"], "qty": TP1_QTY})

            if exit_now:
                risk = abs(active["entry_price"] - active["sl"])
                r_mult = pnl / risk if risk > 0 else 0
                trades.append({
                    "pair": pair, "entry_date": str(pd.Timestamp(active["entry_date"])),
                    "exit_date": str(pd.Timestamp(dates[i])),
                    "side": active["side"], "entry_price": round(active["entry_price"], 4),
                    "sl": round(active["sl"], 4), "tp1": round(active["tp1"], 4),
                    "tp2": round(active["tp2"], 4), "tp3": round(active["tp3"], 4),
                    "exit_reason": reason, "pnl": round(pnl, 4),
                    "r_multiple": round(r_mult, 2),
                    "exit_bar_close": round(c[i], 4),
                    "sweep_val": round(active.get("sweep_val", 0), 4),
                    "sweep_vah": round(active.get("sweep_vah", 0), 4),
                    "poc": round(active.get("poc", 0), 4),
                })
                active = None; active_partials = []

        if active is None and buy:
            risk = c[i] - val[i] * (1 - SL_BUF)
            active = {"side": "long", "entry_date": dates[i], "entry_price": c[i],
                      "sl": val[i] * (1 - SL_BUF),
                      "tp1": c[i] + risk * TP1_RR, "tp2": c[i] + risk * TP2_RR,
                      "tp3": c[i] + risk * TP3_RR,
                      "sweep_val": val[i], "sweep_vah": vah[i], "poc": poc[i]}
            active_partials = []
        elif active is None and sell:
            risk = vah[i] * (1 + SL_BUF) - c[i]
            active = {"side": "short", "entry_date": dates[i], "entry_price": c[i],
                      "sl": vah[i] * (1 + SL_BUF),
                      "tp1": c[i] - risk * TP1_RR, "tp2": c[i] - risk * TP2_RR,
                      "tp3": c[i] - risk * TP3_RR,
                      "sweep_val": val[i], "sweep_vah": vah[i], "poc": poc[i]}
            active_partials = []

    return trades


def load_data_3d(pair):
    patterns = [
        DATA_DIR / f"{pair}_USDT-1h.feather",
        DATA_DIR / "spot" / f"{pair}_USDT-1h.feather",
    ]
    for p in patterns:
        if p.exists():
            df = pd.read_feather(p)
            df.columns = [c.lower().strip() for c in df.columns]
            if "date" in df.columns:
                df["_date"] = pd.to_datetime(df["date"])
                df = df.set_index("_date")
            elif "timestamp" in df.columns:
                df["_date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df = df.set_index("_date")
            col_map = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

            # Filter last 3 days
            latest = df.index.max()
            cutoff = latest - pd.Timedelta(days=3)
            df = df[df.index >= cutoff].copy()
            return df
    return None


if __name__ == "__main__":
    PAIRS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "LTC", "AVAX", "NEAR", "BCH", "XTZ"]
    all_trades = []

    print("=" * 80)
    print("  TPO VP V3 EMA-Stack — Last 3 Days Backtest")
    print(f"  Date range: 2026-05-13 to 2026-05-16")
    print("=" * 80)

    for pair in PAIRS:
        df = load_data_3d(pair)
        if df is None or len(df) < 20:
            print(f"  {pair}: insufficient data")
            continue
        print(f"  {pair}: {len(df)} bars ({str(df.index.min())[:16]} to {str(df.index.max())[:16]})", end="", flush=True)
        trades = v3_backtest_3d(pair, df)
        all_trades.extend(trades)
        print(f" → {len(trades)} trades")

    # Summary
    print(f"\n  {'='*60}")
    print(f"  TOTAL: {len(all_trades)} trades across {len(PAIRS)} pairs")

    if all_trades:
        pnl = sum(t["pnl"] for t in all_trades)
        wins = [t for t in all_trades if t["pnl"] > 0]
        losses = [t for t in all_trades if t["pnl"] <= 0]
        wr = len(wins) / len(all_trades) * 100
        pf = sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses)) if losses else float("inf")
        avg_r = sum(t["r_multiple"] for t in all_trades) / len(all_trades)

        print(f"  Win Rate : {wr:.1f}%")
        print(f"  Net P&L  : {pnl:+.2f}")
        print(f"  PF       : {pf:.2f}")
        print(f"  Avg R    : {avg_r:+.2f}")
        print(f"  SL hits  : {sum(1 for t in all_trades if t['exit_reason']=='sl')}")
        print(f"  TP hits  : {sum(1 for t in all_trades if 'tp' in t['exit_reason'])}")

        print(f"\n  ── All Trades ──")
        for t in sorted(all_trades, key=lambda x: x["entry_date"]):
            print(f"  {t['pair']:6s} {t['side']:5s} {str(t['entry_date'])[:19]} "
                  f"entry={t['entry_price']:>10.2f} "
                  f"{'TP3 ✓' if 'tp3' in t['exit_reason'] else ('TP' if 'tp' in t['exit_reason'] else 'SL ✗')} "
                  f"R={t['r_multiple']:>+5.1f} PnL={t['pnl']:>+10.2f}")

        # Save CSV
        csv_path = PROJECT_ROOT / "scripts" / "tpo_v3_last3d.csv"
        if all_trades:
            with open(csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=all_trades[0].keys())
                w.writeheader()
                w.writerows(all_trades)
            print(f"\n  CSV saved: {csv_path}")
    else:
        print("  No trades generated — EMA200 requires 200+ bars (8+ days)")
        print("  Last 3 days = ~72 bars, insufficient for full V3 indicator stack")
    print()
