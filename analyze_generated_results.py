#!/usr/bin/env python3
"""
Phase 4.1: Results Analyzer — Rank generated strategies and decompose component alpha.

Usage:
  python3 analyze_generated_results.py <results.json>
  python3 analyze_generated_results.py --latest
"""
import json
import sys
import os
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE = Path("/home/roshan/Downloads/Algotrading")
GENERATED_DIR = BASE / "user_data" / "strategies" / "generated"
MANIFEST_PATH = GENERATED_DIR / "manifest.json"
LAYOUT = "{rank:>4} {strategy:42s} {trades:>6} {profit:>+9.2f} {wr:>6.1f} {dd:>6.2f} {status:15s}"


def find_latest_results() -> str:
    """Find the most recent generated_results_*.json file."""
    files = sorted(BASE.glob("generated_results_*.json"), reverse=True)
    if not files:
        print("No generated_results_*.json files found.")
        sys.exit(1)
    return str(files[0])


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {}


def classify(profit_pct: float, trades: int, win_rate: float, dd_pct: float) -> str:
    """Classify strategy performance."""
    if trades < 10:
        return "insufficient_trades"
    if dd_pct > 40:
        return "high_drawdown"
    if profit_pct > 20 and win_rate > 50 and dd_pct < 25:
        return "production_ready"
    if profit_pct > 10 and win_rate > 45:
        return "needs_hyperopt"
    if profit_pct > 0:
        return "promising"
    return "underperforming"


def analyze_results(data: dict, manifest: dict):
    """Full analysis of backtest results."""
    for mode, results in data.items():
        if not isinstance(results, dict):
            continue

        print(f"\n{'=' * 90}")
        print(f"  ANALYSIS — {mode.upper()}")
        print(f"{'=' * 90}")

        # Filter valid
        valid = {s: r for s, r in results.items() if r.get("trades", 0) >= 10}
        ranked = sorted(valid.items(), key=lambda x: x[1].get("profit_pct", 0), reverse=True)

        if not ranked:
            print("  No strategies with >= 10 trades.")
            continue

        print(f"\n  Ranked by Profit % (filtered: >= 10 trades)")
        print(f"{'Rank':>4} {'Strategy':42s} {'Trades':>6} {'Profit%':>9} {'WR%':>6} {'DD%':>6} {'Verdict':18s}")
        print("-" * 90)

        verdicts = {}
        for i, (strat, r) in enumerate(ranked, 1):
            v = classify(r["profit_pct"], r["trades"], r["win_rate"], r["dd_pct"])
            verdicts[strat] = v
            print(f"{i:>4} {strat:42s} {r['trades']:>6} {r['profit_pct']:>+9.2f} "
                  f"{r['win_rate']:>6.1f} {r['dd_pct']:>6.2f} {v:18s}")

        # Summary stats
        verdict_counts = defaultdict(int)
        for v in verdicts.values():
            verdict_counts[v] += 1
        print(f"\n  Verdict distribution:")
        for v in ["production_ready", "needs_hyperopt", "promising", "high_drawdown", "underperforming", "insufficient_trades"]:
            if verdict_counts[v]:
                print(f"    {v:20s}: {verdict_counts[v]}")

        # Top performers
        winners = [s for s, v in verdicts.items() if v in ("production_ready",)]
        if winners:
            print(f"\n  Production-ready candidates:")
            for s in winners:
                r = results[s]
                print(f"    {s}: {r['profit_pct']:+.2f}% | WR={r['win_rate']:.1f}% | DD={r['dd_pct']:.2f}% | {r['trades']} trades")

    return data, verdicts


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze generated strategy backtest results")
    parser.add_argument("results_file", nargs="?", help="Path to results JSON file")
    parser.add_argument("--latest", action="store_true", help="Use latest results file")
    args = parser.parse_args()

    if args.latest:
        path = find_latest_results()
    elif args.results_file:
        path = args.results_file
    else:
        path = find_latest_results()

    print(f"Analyzing: {path}")
    with open(path) as f:
        data = json.load(f)

    manifest = load_manifest()
    analyze_results(data, manifest)


if __name__ == "__main__":
    main()
