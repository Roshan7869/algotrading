#!/usr/bin/env python3
"""
walk_forward.py — Walk-forward edge decay analysis.

Runs a strategy on N rolling windows and detects performance degradation
via linear regression on profit trajectory.

Usage:
  python3 scripts/analytics/walk_forward.py --strategy AroonMomentum --windows 12 --period 30d
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


def parse_period(period: str) -> int:
    """Convert '30d' to 30 days."""
    if period.endswith("d"):
        return int(period[:-1])
    elif period.endswith("w"):
        return int(period[:-1]) * 7
    raise ValueError(f"Invalid period: {period}")


def run_backtest(strategy: str, start: str, end: str, config: str = "user_data/config_base.json") -> dict:
    """Run a single Freqtrade backtest and extract metrics."""
    cmd = [
        sys.executable, "-m", "freqtrade", "backtesting",
        "--strategy", strategy,
        "--timerange", f"{start}-{end}",
        "--config", config,
        "--export", "none",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout + result.stderr
        pf, wr, dd, trades = 0.0, 0.0, 0.0, 0
        for line in output.split("\n"):
            if "Profit factor:" in line:
                try:
                    pf = float(line.split(":")[1].strip())
                except ValueError:
                    pass
            if "Win rate:" in line or "Wins:" in line:
                try:
                    parts = line.split(":")
                    val = parts[1].strip().replace("%", "")
                    wr = float(val) / 100
                except ValueError:
                    pass
            if "Max drawdown:" in line:
                try:
                    parts = line.split(":")
                    val = parts[1].strip().replace("%", "")
                    dd = float(val) / 100
                except ValueError:
                    pass
            if "Total trades:" in line:
                try:
                    trades = int(line.split(":")[1].strip())
                except ValueError:
                    pass
        return {"pf": pf, "wr": wr, "dd": dd, "trades": trades}
    except subprocess.TimeoutExpired:
        return {"pf": 0.0, "wr": 0.0, "dd": 1.0, "trades": 0}


def main():
    parser = argparse.ArgumentParser(description="Walk-forward edge decay analysis")
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument("--windows", type=int, default=12, help="Number of rolling windows")
    parser.add_argument("--period", default="30d", help="Window period (e.g., 30d)")
    parser.add_argument("--end", default=None, help="End date (default: today)")
    args = parser.parse_args()

    end_date = datetime.strptime(args.end, "%Y%m%d") if args.end else datetime.now()
    period_days = parse_period(args.period)
    total_days = period_days * args.windows
    start_date = end_date - timedelta(days=total_days)

    print(f"\n  Walk-Forward: {args.strategy}")
    print(f"  Windows: {args.windows} x {args.period} = {total_days}d total")
    print(f"  Range: {start_date.strftime('%Y%m%d')} → {end_date.strftime('%Y%m%d')}\n")

    print(f"{'Window':>8s} {'Start':>10s} {'PF':>6s} {'WR':>5s} {'DD':>6s} {'Trades':>7s}")
    print("-" * 50)

    results = []
    for i in range(args.windows):
        w_start = start_date + timedelta(days=i * period_days)
        w_end = w_start + timedelta(days=period_days)
        s = w_start.strftime("%Y%m%d")
        e = w_end.strftime("%Y%m%d")

        r = run_backtest(args.strategy, s, e)
        results.append(r)
        print(f"  {i + 1:>3d}/{args.windows:>3d}  {s:>10s}  {r['pf']:>6.2f}  {r['wr']:>5.1%}  {r['dd']:>6.1%}  {r['trades']:>7d}")

    profits = np.array([r["pf"] for r in results])
    x = np.arange(len(profits))
    slope = np.polyfit(x, profits, 1)[0] if len(profits) > 1 else 0

    n_fail = sum(1 for r in results if r["pf"] < 0.9 or r["dd"] > 0.20)
    n_profitable = sum(1 for r in results if r["pf"] >= 1.0)

    print(f"\n  Summary:")
    print(f"  Windows with PF ≥ 1.0: {n_profitable}/{args.windows}")
    print(f"  Windows with PF < 0.9 or DD > 20%: {n_fail}/{args.windows}")
    print(f"  Edge erosion slope: {slope:.4f} {'<< DETECTED' if slope < -0.5 else ''}")
    print(f"  Avg PF: {profits.mean():.2f} | Min PF: {profits.min():.2f} | Max PF: {profits.max():.2f}")

    if n_fail > 0:
        print(f"  ⚠️  {n_fail} window(s) FAIL gate requirements")
    if slope < -0.5:
        print(f"  ⚠️  Edge erosion detected (slope < -0.5)")
    if n_profitable >= args.windows * 0.67:
        print(f"  ✅ Gate PASSED: ≥ 2/3 windows profitable")


if __name__ == "__main__":
    main()
