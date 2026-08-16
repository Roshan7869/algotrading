"""
TPO VP Short-Term Strategy (ST-V1) — 5m Timeframe
Designed for 1-3 day holding period with faster signals

Key differences from V3 (1h):
  - Timeframe: 5m (864 bars in 3 days)
  - VP lookback: 20 bars (~100 min window)
  - Trend: EMA8/21 (fast shortest-term EMAs)
  - Tighter SL: 0.15% buffer
  - Simpler exit: TP1@1.5R(50%), TP2@2.5R(50%)
  - More permissive filters for more signals
"""

import csv
import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FUTURES_DIR = PROJECT_ROOT / "user_data" / "data" / "binance" / "futures"

# ST-V2 Parameters (refined)
LOOKBACK = 30       # 2.5 hours of 5m data
NUM_BINS = 20
VA_PCT = 0.70
SL_BUF = 0.0025     # Wider for 5m noise
TP1_RR = 1.2        # First target at 1.2R
TP2_RR = 2.0        # Second target at 2.0R
TP1_QTY = 0.50
VOL_MUL = 1.2       # Require volume above average
BODY_R = 0.30
MAX_WAIT = 8
VP_STEP = 2


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


def backtest_st_v1(pair: str, df: pd.DataFrame) -> list[dict]:
    """ST-V1: Short-term TPO VP on 5m data."""
    n = len(df)
    dates = df.index.to_numpy()
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    c = df["close"].values.astype(np.float64)
    o = df["open"].values.astype(np.float64)
    v = df["volume"].values.astype(np.float64)
    poc, vah, val = compute_vp(h, l, v)

    # EMA21/55 for short-term trend (more stable than EMA8/21)
    ema21 = pd.Series(c).ewm(span=21, adjust=False).mean().values
    ema55 = pd.Series(c).ewm(span=55, adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values

    def trend_ok(i):
        return (c[i] > ema21[i] > ema55[i], c[i] < ema21[i] < ema55[i])

    trades = []
    b_state = s_state = 0; b_bars = s_bars = 0
    active = None; active_partials = []

    for i in range(LOOKBACK, n):
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
        if b_state in (1, 2) and (b_bars > MAX_WAIT or l[i] < val[i] * (1 - SL_BUF * 3)):
            b_state = 0
        if bear_sweep and s_state == 0: s_state = 1; s_bars = 0
        if s_state == 1: s_bars += 1
        if s_state == 1 and bear_rej: s_state = 2; s_bars = 0
        if s_state in (1, 2) and (s_bars > MAX_WAIT or h[i] > vah[i] * (1 + SL_BUF * 3)):
            s_state = 0

        buy = b_state == 2 and poc_rec and bull_t
        sell = s_state == 2 and poc_loss and bear_t
        if buy: b_state = 0
        if sell: s_state = 0

        # Manage active trade — 2 TP levels (1.5R and 2.5R)
        if active:
            exit_now = False
            if active["side"] == "long":
                if l[i] <= active["sl"]:
                    exit_now = True; reason = "sl"
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    pnl = (active["sl"] - active["entry_price"]) * rem
                    for pt in active_partials:
                        pnl += (pt["price"] - active["entry_price"]) * pt["qty"]
                elif h[i] >= active["tp2"] and not any(p.get("tp") == 2 for p in active_partials):
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    active_partials.append({"tp": 2, "price": active["tp2"], "qty": rem})
                    exit_now = True; reason = "tp2"
                    pnl = sum((p["price"] - active["entry_price"]) * p["qty"] for p in active_partials)
                elif h[i] >= active["tp1"] and not any(p.get("tp") == 1 for p in active_partials):
                    active_partials.append({"tp": 1, "price": active["tp1"], "qty": TP1_QTY})
            else:
                if h[i] >= active["sl"]:
                    exit_now = True; reason = "sl"
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    pnl = (active["entry_price"] - active["sl"]) * rem
                    for pt in active_partials:
                        pnl += (active["entry_price"] - pt["price"]) * pt["qty"]
                elif l[i] <= active["tp2"] and not any(p.get("tp") == 2 for p in active_partials):
                    rem = 1 - sum(pt["qty"] for pt in active_partials)
                    active_partials.append({"tp": 2, "price": active["tp2"], "qty": rem})
                    exit_now = True; reason = "tp2"
                    pnl = sum((active["entry_price"] - p["price"]) * p["qty"] for p in active_partials)
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
                    "tp2": round(active["tp2"], 4),
                    "exit_reason": reason, "pnl": round(pnl, 4),
                    "r_multiple": round(r_mult, 2),
                    "sweep_val": round(val[i], 4), "sweep_vah": round(vah[i], 4),
                    "poc": round(poc[i], 4), "ema21": round(ema21[i], 4),
                    "ema55": round(ema55[i], 4), "body_ratio": round(body_r, 2),
                    "volume_ratio": round(v[i] / avg_v[i], 2) if avg_v[i] > 0 else 0,
                })
                active = None; active_partials = []

        if active is None and buy:
            risk = c[i] - val[i] * (1 - SL_BUF)
            active = {"side": "long", "entry_date": dates[i], "entry_price": c[i],
                      "sl": val[i] * (1 - SL_BUF),
                      "tp1": c[i] + risk * TP1_RR, "tp2": c[i] + risk * TP2_RR}
            active_partials = []
        elif active is None and sell:
            risk = vah[i] * (1 + SL_BUF) - c[i]
            active = {"side": "short", "entry_date": dates[i], "entry_price": c[i],
                      "sl": vah[i] * (1 + SL_BUF),
                      "tp1": c[i] - risk * TP1_RR, "tp2": c[i] - risk * TP2_RR}
            active_partials = []

    return trades


def load_data_5m(pair: str) -> Optional[pd.DataFrame]:
    f = FUTURES_DIR / f"{pair}_USDT_USDT-5m-futures.feather"
    if not f.exists():
        return None
    df = pd.read_feather(f)
    df.columns = [c.lower().strip() for c in df.columns]
    df["_date"] = pd.to_datetime(df["date"])
    df = df.set_index("_date")
    col_map = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    # Filter last 3 days
    latest = df.index.max()
    cutoff = latest - pd.Timedelta(days=3)
    df = df[df.index >= cutoff].copy()
    return df


if __name__ == "__main__":
    # Use pairs that have 5m futures data
    PAIRS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "LTC",
             "AVAX", "NEAR", "BCH", "ATOM", "ARB", "APT"]

    all_trades = []
    print("=" * 90)
    print("  TPO VP SHORT-TERM ST-V1 — 5m Timeframe, Last 3 Days")
    print("=" * 90)
    print(f"  VP lookback={LOOKBACK}, EMA8/21 trend, SL={SL_BUF}")
    print(f"  TP1@{TP1_RR}R(50%), TP2@{TP2_RR}R(50%), body_ratio>={BODY_R}, vol>={VOL_MUL}x\n")

    for pair in PAIRS:
        df = load_data_5m(pair)
        if df is None or len(df) < 50:
            continue
        print(f"  {pair}: {len(df)} 5m bars ({str(df.index.min())[:16]} → {str(df.index.max())[:16]})",
              end="", flush=True)
        trades = backtest_st_v1(pair, df)
        all_trades.extend(trades)
        print(f" → {len(trades)} trades")

    print(f"\n  {'='*70}")
    print(f"  TOTAL: {len(all_trades)} trades")

    if all_trades:
        pnl = sum(t["pnl"] for t in all_trades)
        wins = [t for t in all_trades if t["pnl"] > 0]
        losses = [t for t in all_trades if t["pnl"] <= 0]
        wr = len(wins) / len(all_trades) * 100
        pf = sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses)) if losses else float("inf")
        avg_r = sum(t["r_multiple"] for t in all_trades) / len(all_trades)
        sl_hits = sum(1 for t in all_trades if t["exit_reason"] == "sl")
        tp_hits = sum(1 for t in all_trades if "tp" in t["exit_reason"])

        print(f"  Win Rate : {wr:.1f}%")
        print(f"  Net P&L  : {pnl:+.2f}")
        print(f"  PF       : {pf:.2f}")
        print(f"  Avg R    : {avg_r:+.2f}")
        print(f"  SL/TP    : {sl_hits}/{tp_hits} ({sl_hits/len(all_trades)*100:.0f}%/{tp_hits/len(all_trades)*100:.0f}%)")

        # Per-pair breakdown
        from collections import defaultdict
        pair_data = defaultdict(lambda: {"trades": 0, "pnl": 0, "wins": 0})
        for t in all_trades:
            p = t["pair"]
            pair_data[p]["trades"] += 1
            pair_data[p]["pnl"] += t["pnl"]
            if t["pnl"] > 0:
                pair_data[p]["wins"] += 1

        print(f"\n  {'Pair':<8} {'Trades':>7} {'Win%':>7} {'Net P&L':>12}")
        print(f"  {'-'*36}")
        for pair, pd_ in sorted(pair_data.items(), key=lambda x: x[1]["pnl"], reverse=True):
            wr_p = pd_["wins"] / pd_["trades"] * 100
            print(f"  {pair:<8} {pd_['trades']:>7} {wr_p:>6.1f}% {pd_['pnl']:>+10.2f}")
        print(f"  {'-'*36}")
        print(f"  {'TOTAL':<8} {len(all_trades):>7} {wr:>6.1f}% {pnl:>+10.2f}")

        # Top/Bottom trades
        print(f"\n  ── Best 5 Trades ──")
        for t in sorted(all_trades, key=lambda x: x["pnl"], reverse=True)[:5]:
            print(f"  {t['pair']:6s} {t['side']:5s} {t['entry_date'][:19]} "
                  f"entry={t['entry_price']:>10.2f} PnL={t['pnl']:>+8.2f} R={t['r_multiple']:>+4.1f} {t['exit_reason']}")

        print(f"  ── Worst 5 Trades ──")
        for t in sorted(all_trades, key=lambda x: x["pnl"])[:5]:
            print(f"  {t['pair']:6s} {t['side']:5s} {t['entry_date'][:19]} "
                  f"entry={t['entry_price']:>10.2f} PnL={t['pnl']:>+8.2f} R={t['r_multiple']:>+4.1f} {t['exit_reason']}")

        # Save CSV
        csv_path = PROJECT_ROOT / "scripts" / "tpo_st_v1_trades.csv"
        with open(csv_path, "w", newline="") as f:
            if all_trades:
                w = csv.DictWriter(f, fieldnames=all_trades[0].keys())
                w.writeheader()
                w.writerows(all_trades)
        print(f"\n  CSV: {csv_path}")
    else:
        print("  No trades generated")
    print()
