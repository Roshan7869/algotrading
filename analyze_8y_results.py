#!/usr/bin/env python3
"""
Market Dynamics Analyzer — 8-Year Spot Backtest Results.

Processes all_results_8y_spot_*.json from batch_runner_8y_spot.py.
Ranks strategies, classifies verdicts, compares existing vs generated,
and identifies top candidates for hyperopt + Kronos strategy design.
"""
import json
import os
import sys
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE = Path("/home/roshan/Downloads/Algotrading")
BLUEPRINTS_PATH = BASE / "strategy_db" / "strategy_blueprints.json"
INVENTORY_PATH = BASE / "strategy_db" / "vector_inventory.json"
RANKINGS_PATH = BASE / "strategy_rankings.json"


def find_latest_results(pattern: str = "all_results_8y_spot_*.json") -> str:
    files = sorted(BASE.glob(pattern), reverse=True)
    if not files:
        print(f"No files matching {pattern}")
        sys.exit(1)
    return str(files[0])


def classify(profit_pct: float, trades: int, win_rate: float, dd_pct: float) -> str:
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


def load_json(path) -> dict:
    with open(path) as f:
        return json.load(f)


def print_table(ranked: list, title: str):
    print(f"\n{'=' * 100}")
    print(f"  {title}")
    print(f"{'=' * 100}")
    print(f"{'Rank':>4} {'Strategy':45s} {'Trades':>6} {'Profit%':>9} {'WR%':>6} {'DD%':>6} {'Verdict':18s}")
    print("-" * 100)
    for i, (s, r, v) in enumerate(ranked, 1):
        arrow = "+" if r.get("profit_pct", 0) >= 0 else " "
        print(f"{i:>4} {s:45s} {r.get('trades',0):>6} {arrow}{r.get('profit_pct',0):>+8.2f} "
              f"{r.get('win_rate',0):>6.1f} {r.get('dd_pct',0):>6.2f} {v:18s}")


def analyze_market_dynamics(results: dict, label: str, blueprints: dict = None):
    """Deep analysis of backtest results with market dynamics context."""
    valid = {s: r for s, r in results.items()
             if isinstance(r, dict) and r.get("trades", 0) >= 10}

    if not valid:
        print(f"\n  [{label}] No strategies with >= 10 trades.")
        return {}, []

    # Rank by profit
    ranked = sorted(valid.items(), key=lambda x: x[1].get("profit_pct", 0), reverse=True)

    verdicts = {}
    table_rows = []
    for s, r in ranked:
        v = classify(r["profit_pct"], r["trades"], r["win_rate"], r["dd_pct"])
        verdicts[s] = v
        table_rows.append((s, r, v))

    print_table(table_rows, f"{label} — Ranked by Profit% (>=10 trades)")

    # Verdict distribution
    vc = defaultdict(int)
    for v in verdicts.values():
        vc[v] += 1
    print(f"\n  Verdict distribution:")
    for v in ["production_ready", "needs_hyperopt", "promising",
              "high_drawdown", "underperforming", "insufficient_trades"]:
        if vc[v]:
            print(f"    {v:20s}: {vc[v]}")

    # Best risk-adjusted
    by_risk_adj = sorted(
        [(s, r) for s, r in valid.items() if r.get("win_rate", 0) > 0 and r.get("dd_pct", 0) > 0],
        key=lambda x: x[1]["win_rate"] / max(x[1]["dd_pct"], 0.01),
        reverse=True
    )
    if by_risk_adj:
        print(f"\n  Best risk-adjusted (WR/DD ratio):")
        for s, r in by_risk_adj[:5]:
            ratio = r["win_rate"] / max(r["dd_pct"], 0.01)
            print(f"    {s:45s} WR={r['win_rate']:5.1f}%  DD={r['dd_pct']:5.2f}%  "
                  f"ratio={ratio:.2f}  profit={r['profit_pct']:+7.2f}%  trades={r['trades']}")

    # Low drawdown candidates
    safe = [(s, r) for s, r in valid.items() if r.get("dd_pct", 100) < 15]
    if safe:
        safe.sort(key=lambda x: x[1]["profit_pct"], reverse=True)
        print(f"\n  Low drawdown candidates (DD < 15%):")
        for s, r in safe[:5]:
            print(f"    {s:45s} profit={r['profit_pct']:+7.2f}%  DD={r['dd_pct']:5.2f}%  "
                  f"WR={r['win_rate']:5.1f}%  trades={r['trades']}")

    # Profit distribution
    profits = [r["profit_pct"] for r in valid.values()]
    if profits:
        print(f"\n  Profit distribution:")
        print(f"    Mean:   {sum(profits)/len(profits):+.2f}%")
        print(f"    Median: {sorted(profits)[len(profits)//2]:+.2f}%")
        print(f"    Best:   {max(profits):+.2f}%")
        print(f"    Worst:  {min(profits):+.2f}%")
        print(f"    Positive: {sum(1 for p in profits if p > 0)}/{len(profits)}")

    # Blueprint source analysis (if available)
    if blueprints and "generated" in label.lower():
        print(f"\n  Blueprint source analysis:")
        bp_map = {}
        for bp in blueprints.get("blueprints", []):
            sid = bp["strategy_id"]
            bp_map[f"GenStrategy_{sid}"] = bp

        by_source = defaultdict(list)
        for s, r in valid.items():
            if s in bp_map:
                src = bp_map[s].get("source", "unknown")
                by_source[src].append((s, r["profit_pct"], r["dd_pct"]))

        for src, items in sorted(by_source.items()):
            if items:
                avg_profit = sum(x[1] for x in items) / len(items)
                print(f"    {src:15s}: {len(items):>3} strategies, avg profit={avg_profit:+7.2f}%")

    return verdicts, table_rows


def compare_existing_vs_generated(existing_verdicts: dict, gen_verdicts: dict,
                                  existing_results: dict, gen_results: dict):
    """Compare performance between existing and generated strategy groups."""
    print(f"\n{'=' * 100}")
    print(f"  EXISTING vs GENERATED — Head-to-Head")
    print(f"{'=' * 100}")

    # Count positive profit strategies
    for label, results in [("Existing", existing_results), ("Generated", gen_results)]:
        valid = {s: r for s, r in results.items()
                 if isinstance(r, dict) and r.get("trades", 0) >= 10}
        positive = sum(1 for r in valid.values() if r.get("profit_pct", 0) > 0)
        avg_profit = sum(r.get("profit_pct", 0) for r in valid.values()) / max(len(valid), 1)
        avg_dd = sum(r.get("dd_pct", 0) for r in valid.values()) / max(len(valid), 1)
        avg_wr = sum(r.get("win_rate", 0) for r in valid.values()) / max(len(valid), 1)
        print(f"\n  {label:10s}: {len(valid):>3} valid strategies, {positive} profitable")
        print(f"    Avg profit: {avg_profit:+7.2f}% | Avg WR: {avg_wr:5.1f}% | Avg DD: {avg_dd:5.2f}%")


def generate_recommendations(verdicts: dict, results: dict, mode: str) -> list:
    """Generate actionable recommendations."""
    recs = []
    for s, v in sorted(verdicts.items()):
        r = results.get(s, {})
        if v == "production_ready":
            recs.append(f"PRODUCTION: {s} — {r.get('profit_pct',0):+.2f}% | WR={r.get('win_rate',0):.1f}% | DD={r.get('dd_pct',0):.2f}%")
        elif v == "needs_hyperopt":
            recs.append(f"HYPEROPT: {s} — {r.get('profit_pct',0):+.2f}% | WR={r.get('win_rate',0):.1f}% | DD={r.get('dd_pct',0):.2f}%")
        elif v == "promising":
            recs.append(f"PROMISING: {s} — {r.get('profit_pct',0):+.2f}% | WR={r.get('win_rate',0):.1f}% | DD={r.get('dd_pct',0):.2f}%")
    return recs


def main():
    parser = argparse.ArgumentParser(description="8-Year Spot Backtest Results Analyzer")
    parser.add_argument("results_file", nargs="?", help="Path to all_results_8y_spot_*.json")
    parser.add_argument("--latest", action="store_true", help="Use latest results file")
    args = parser.parse_args()

    if args.latest or not args.results_file:
        path = find_latest_results()
    else:
        path = args.results_file

    print(f"Analyzing: {path}")
    data = load_json(path)

    blueprints = load_json(BLUEPRINTS_PATH) if BLUEPRINTS_PATH.exists() else None
    inventory = load_json(INVENTORY_PATH) if INVENTORY_PATH.exists() else None

    all_recs = {}
    combined_verdicts = {}
    combined_results = {}

    for mode_key, mode_label in [("existing_spot_8y", "Existing"), ("generated_spot_8y", "Generated")]:
        results = data.get(mode_key, {})
        if not results:
            print(f"\n  No results for {mode_key}")
            continue
        verdicts, _ = analyze_market_dynamics(results, mode_label, blueprints)
        combined_verdicts[mode_label] = verdicts
        combined_results[mode_label] = results
        recs = generate_recommendations(verdicts, results, mode_label)
        all_recs[mode_label] = recs

    if "Existing" in combined_results and "Generated" in combined_results:
        compare_existing_vs_generated(
            combined_verdicts.get("Existing", {}),
            combined_verdicts.get("Generated", {}),
            combined_results["Existing"],
            combined_results["Generated"]
        )

    # Print recommendations
    print(f"\n{'=' * 100}")
    print(f"  RECOMMENDATIONS")
    print(f"{'=' * 100}")
    for mode_label, recs in all_recs.items():
        if recs:
            print(f"\n  {mode_label}:")
            for r in recs:
                print(f"    {r}")

    # Save analysis
    analysis = {
        "analyzed_at": datetime.now().isoformat(),
        "source_file": path,
        "summary": {},
        "recommendations": {k: v for k, v in all_recs.items()},
    }

    for mode_label, verdicts in combined_verdicts.items():
        vc = defaultdict(int)
        for v in verdicts.values():
            vc[v] += 1
        analysis["summary"][mode_label] = dict(vc)

    outpath = BASE / "analysis_8y_spot.json"
    with open(outpath, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"\nAnalysis saved to {outpath}")


if __name__ == "__main__":
    import argparse
    main()
