#!/usr/bin/env python3
"""
Walk-Forward Validation — detect overfitting by testing across independent time windows.

Splits data into 3 non-overlapping periods:
  TRAIN:    2019-09 — 2022-06 (bull → crash → recovery)
  VALIDATE: 2022-06 — 2024-06 (bear → accumulation)
  TEST:     2024-06 — 2026-05 (recovery → range)

Flags a strategy as OVERFIT if:
  - Profit on TEST < 50% of profit on TRAIN (profit collapse)
  - Win rate drops > 15pp between any two windows
  - Trade count < 10 across all windows (insufficient sample)
"""
import subprocess
import json
import re
import os
import sys
import time
from pathlib import Path
from datetime import datetime

BASE = Path("/home/roshan/Downloads/Algotrading")
VENV = str(BASE / ".venv" / "bin" / "freqtrade")

PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT"]

WINDOWS = {
    "train":    {"timerange": "20190917-20220601", "label": "2019-2022 (Bull→Crash)"},
    "validate": {"timerange": "20220601-20240601", "label": "2022-2024 (Bear→Accum)"},
    "test":     {"timerange": "20240601-20260517", "label": "2024-2026 (Recovery→Range)"},
}

STRATEGIES = [
    "VectorStrategy", "VectorStrategyV2",
    "VectorStrategy_P3A_RSI_DIVERGENCE_EXIT",
    "VectorStrategy_P3B_TIGHTER_TRAIL",
    "VectorStrategy_P3C_WIDER_TRAIL",
    "VectorStrategy_P3D_KILL_ZONE_FILTER",
    "VectorStrategy_P3D_KILL_ZONE_FORCED",
    "VectorStrategy_P3E_KEY_LEVEL_BOOST",
    "VectorStrategy_P3E_HYPEROPT",
    "VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL",
]

def parse_backtest(output: str, name: str) -> dict | None:
    pattern = (
        r'│\s*' + re.escape(name) +
        r'\s*│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*(\d+:\d+:\d+)\s*│\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)\s*│\s*([-\d.]+)\s*USDT\s+([\d.]+)%'
    )
    m = re.search(pattern, output)
    if m:
        return {
            "trades": int(m.group(1)),
            "avg_profit_pct": float(m.group(2)),
            "profit_pct": float(m.group(4)),
            "avg_duration": m.group(5),
            "wins": int(m.group(6)),
            "losses": int(m.group(8)),
            "win_rate": float(m.group(8)),
            "dd_pct": float(m.group(10)),
        }
    return None


def run_one(name: str, timerange: str) -> dict:
    cmd = [
        VENV, "backtesting", "--strategy", name,
        "--timerange", timerange,
        "--max-open-trades", "5",
        "-p"] + PAIRS + ["--cache", "none", "--export", "none"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(BASE))
        output = result.stdout + result.stderr

        if "Error" in output or "Traceback" in output:
            err_lines = [l.strip() for l in output.split('\n') if 'Error' in l or 'Traceback' in l]
            return {"status": "ERROR", "error": "; ".join(err_lines[:3])}

        parsed = parse_backtest(output, name)
        if parsed:
            return {"status": "OK", **parsed}
        return {"status": "NO_DATA", "trades": 0, "profit_pct": 0, "win_rate": 0, "dd_pct": 0}
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": ">600s"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def main():
    results = {}
    total = len(STRATEGIES) * len(WINDOWS)
    done = 0

    print(f"Walk-Forward Validation: {len(STRATEGIES)} strategies × {len(WINDOWS)} windows = {total} runs")
    print(f"{'='*80}")

    for s in STRATEGIES:
        results[s] = {"windows": {}}
        for wkey, winfo in WINDOWS.items():
            print(f"  [{done+1}/{total}] {s} — {winfo['label']} ...", end=" ", flush=True)
            r = run_one(s, winfo["timerange"])
            results[s]["windows"][wkey] = r
            status = r.get("status", "?")
            pf = r.get("profit_pct", 0)
            tr = r.get("trades", 0)
            wr = r.get("win_rate", 0)
            print(f"{status}  profit={pf:+.2f}%  trades={tr}  wr={wr}%")
            done += 1
            time.sleep(0.5)

    # Compute overfit flags
    print(f"\n{'='*80}")
    print(f"  OVERFITTING REPORT")
    print(f"{'='*80}")
    flagged = 0
    for s, data in results.items():
        wins = data["windows"]
        profits = {k: v.get("profit_pct", 0) for k, v in wins.items()}
        trades = {k: v.get("trades", 0) for k, v in wins.items()}
        wrs = {k: v.get("win_rate", 0) for k, v in wins.items()}
        dds = {k: v.get("dd_pct", 0) for k, v in wins.items()}

        flags = []

        # Profit collapse: test < 50% of train
        if profits.get("test", 0) < profits.get("train", 1) * 0.5 and profits.get("train", 0) > 0:
            flags.append("PROFIT_COLLAPSE")

        # Win rate instability: >15pp drop
        if wrs and max(wrs.values()) - min(wrs.values()) > 15:
            flags.append("WR_INSTABLE")

        # Insufficient data
        if sum(trades.values()) < 10:
            flags.append("LOW_SAMPLE")

        # Zero trades in test
        if trades.get("test", 0) == 0 and sum(trades.values()) > 0:
            flags.append("ZERO_TEST")

        # Extremely low DD relative to profit (classic overfit)
        total_profit = sum(profits.values())
        max_dd = max(dds.values()) if dds else 0
        if total_profit > 50 and max_dd < 2.0:
            flags.append("SUSPECT_DD")

        data["flags"] = flags
        if flags:
            flagged += 1
            print(f"\n  ⚠ {s}")

            for wk in WINDOWS:
                w = wins[wk]
                print(f"    {WINDOWS[wk]['label']:30s}  profit={w.get('profit_pct',0):>+8.2f}%  trades={w.get('trades',0):>4}  wr={w.get('win_rate',0):>5.1f}%  dd={w.get('dd_pct',0):>5.2f}%")
            print(f"    FLAGS: {', '.join(flags)}")

    if not flagged:
        print("  ✅ No overfitting detected across all strategies.")

    print(f"\n{'='*80}")
    print(f"  Total: {len(STRATEGIES)} strategies, {flagged} flagged as overfit")

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = BASE / f"walk_forward_report_{ts}.json"
    with open(outfile, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full report: {outfile}")


if __name__ == "__main__":
    main()
