#!/usr/bin/env python3
"""
Auto-Optimize Pipeline — Walk-Forward Optimization Engine

Runs hyperopt on in-sample data → backtests on out-of-sample data →
promotes params only if OoS performance passes gates.

Usage:
  python3 scripts/auto_optimize.py --strategy DmiAdxStrategy --dry-run
  python3 scripts/auto_optimize.py --strategy EnsembleStrategy --epochs 300 --timerange 20250501-20260501
  python3 scripts/auto_optimize.py --all --dry-run
  python3 scripts/auto_optimize.py --history     # Show optimization history
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
STRATEGIES_DIR = PROJECT_ROOT / "user_data" / "strategies"
HISTORY_DIR = PROJECT_ROOT / "user_data" / "optimization_history"
CONFIG_PATH = PROJECT_ROOT / "user_data" / "config_multi_backtest_365d.json"

HYPEROPT_RESULTS_DIR = PROJECT_ROOT / "user_data" / "hyperopt_results"
BACKTEST_RESULTS_DIR = PROJECT_ROOT / "user_data" / "backtest_results"

PROMOTION_GATES = {
    "min_sharpe": 0.5,
    "min_profit_pct": -5.0,
    "max_drawdown_pct": 15.0,
    "min_trades": 5,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str, level: str = "INFO"):
    icon = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERROR": "❌", "STEP": "▶️"}.get(level, "•")
    print(f"[{now()}] {icon} {msg}")


def run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    log(f"Running: {' '.join(str(c) for c in cmd)}")
    return subprocess.run(
        cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout
    )


def get_available_strategies() -> list[str]:
    candidates = [
        "MacdRsiStrategy", "DmiAdxStrategy", "BollingerMeanReversion",
        "EmaTrendFollowing", "SupertrendEmaStrategy", "RsiDivergenceStrategy",
    ]
    return [s for s in candidates if (STRATEGIES_DIR / f"{s}.py").exists()]


def parse_hyperopt_output(output: str) -> dict:
    lines = output.split("\n")
    params = {}
    current_section = None

    for line in lines:
        stripped = line.strip()

        if '"buy_params"' in line or "# Buy parameters:" in line:
            current_section = "buy"
            params[current_section] = {}
        elif '"sell_params"' in line or "# Sell parameters:" in line:
            current_section = "sell"
            params[current_section] = {}
        elif '"roi"' in line or "# ROI" in line:
            current_section = None
        elif '"stoploss"' in line or "# Stoploss" in line:
            current_section = None
        elif '"trailing"' in line or "# Trailing stop" in line:
            current_section = None
        elif current_section and ":" in stripped and stripped.endswith(","):
            key_val = stripped.rstrip(",")
            if ":" in key_val:
                key, val = key_val.split(":", 1)
                key = key.strip().strip('"')
                val = val.strip().strip('"').strip("'")
                try:
                    val = int(val) if "." not in val else float(val)
                except ValueError:
                    pass
                params[current_section][key] = val

    return params


def parse_backtest_summary(output: str) -> dict:
    result = {"trades": 0, "profit_pct": 0.0, "profit_usdt": 0.0, "win_pct": 0.0, "drawdown_pct": 0.0, "sharpe": 0.0}

    patterns = {
        "trades": r"│\s+TOTAL\s+│\s+(\d+)",
        "profit_pct": r"Tot Profit %\s+│\s+([-\d.]+)%",
        "profit_usdt": r"Tot Profit USDT\s+│\s+([-\d.]+)\s+USDT",
        "drawdown_pct": r"Absolute drawdown.*?([\d.]+)\s+USDT\s+\(([\d.]+)%\)",
        "sharpe": r"Sharpe.*?│\s+([-\d.]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            groups = match.groups()
            if key == "drawdown_pct":
                result[key] = float(groups[1]) if len(groups) > 1 else float(groups[0])
            else:
                result[key] = float(groups[0]) if "." in groups[0] else int(groups[0])

    win_match = re.search(r"Win\s+Draw\s+Loss\s+Win%\s+│\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)", output)
    if win_match:
        result["wins"] = int(win_match.group(1))
        result["losses"] = int(win_match.group(3))
        result["win_pct"] = float(win_match.group(4))

    return result


def check_promotion_gates(metrics: dict) -> tuple[bool, list[str]]:
    gates = []
    passed = True

    if metrics["trades"] < PROMOTION_GATES["min_trades"]:
        gates.append(f"trades {metrics['trades']} < {PROMOTION_GATES['min_trades']}")
        passed = False
    if metrics["profit_pct"] < PROMOTION_GATES["min_profit_pct"]:
        gates.append(f"profit {metrics['profit_pct']}% < {PROMOTION_GATES['min_profit_pct']}%")
        passed = False
    if metrics["drawdown_pct"] > PROMOTION_GATES["max_drawdown_pct"]:
        gates.append(f"drawdown {metrics['drawdown_pct']}% > {PROMOTION_GATES['max_drawdown_pct']}%")
        passed = False
    if metrics["sharpe"] > 0 and metrics["sharpe"] < PROMOTION_GATES["min_sharpe"]:
        gates.append(f"sharpe {metrics['sharpe']} < {PROMOTION_GATES['min_sharpe']}")
        passed = False

    return passed, gates


def save_history(strategy: str, entry: dict):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_file = HISTORY_DIR / f"{strategy}.jsonl"
    entry["timestamp"] = now()
    with open(history_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    log(f"History saved to {history_file}", "OK")


def load_history(strategy: str, limit: int = 10) -> list[dict]:
    history_file = HISTORY_DIR / f"{strategy}.jsonl"
    if not history_file.exists():
        return []
    entries = []
    with open(history_file) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[-limit:]


def show_history(strategy: Optional[str] = None):
    if strategy:
        strategies = [strategy]
    else:
        strategies = get_available_strategies()

    for s in strategies:
        entries = load_history(s, limit=5)
        if not entries:
            print(f"  {s}: no history")
            continue
        print(f"\n  {s}:")
        for e in entries:
            status = "✅" if e.get("promoted") else "❌"
            oos = e.get("oos", {})
            print(f"    {status} {e['timestamp'][:19]}  "
                  f"trades={oos.get('trades', '?')}  "
                  f"profit={oos.get('profit_pct', '?')}%  "
                  f"sharpe={oos.get('sharpe', '?')}  "
                  f"dd={oos.get('drawdown_pct', '?')}%")


def auto_optimize(
    strategy: str,
    total_timerange: str = "20250501-20260501",
    epochs: int = 200,
    dry_run: bool = True,
) -> dict:
    log(f"=== Auto-Optimize: {strategy} ===", "STEP")

    in_sample_end = "20260101"
    out_sample_start = "20260101"

    existing_params = {}
    param_file = STRATEGIES_DIR / f"{strategy}.json"
    if param_file.exists():
        existing_params = json.loads(param_file.read_text())
        log(f"Existing params found: {param_file.name}", "INFO")

    log(f"Phase 1: Hyperopt on in-sample data ({in_sample_end})", "STEP")
    hyperopt_result = run([
        sys.executable, "-m", "freqtrade", "hyperopt",
        "--config", str(CONFIG_PATH),
        "--strategy", strategy,
        "--hyperopt-loss", "DrawdownAwareLoss",
        "--timerange", f"{total_timerange.split('-')[0]}-{in_sample_end}",
        "--timeframe", "1h",
        "--spaces", "buy", "sell",
        "-e", str(epochs),
        "-j", "1",
    ])

    if hyperopt_result.returncode != 0:
        log(f"Hyperopt failed: {hyperopt_result.stderr[:500]}", "ERROR")
        return {"status": "failed", "strategy": strategy, "error": "hyperopt_failed"}

    new_params = parse_hyperopt_output(hyperopt_result.stdout)
    log(f"New params discovered: {json.dumps(new_params, indent=2)}", "OK")

    if not new_params:
        log("No new params found, keeping existing", "WARN")
        return {"status": "skipped", "strategy": strategy, "reason": "no_new_params"}

    log(f"Phase 2: Backtest on out-of-sample data ({out_sample_start}-)", "STEP")
    bt_result = run([
        sys.executable, "-m", "freqtrade", "backtesting",
        "--config", str(CONFIG_PATH),
        "--strategy", strategy,
        "--timerange", f"{out_sample_start}-{total_timerange.split('-')[1]}",
        "--timeframe", "1h",
    ])

    if bt_result.returncode != 0:
        log(f"Backtest failed: {bt_result.stderr[:500]}", "ERROR")
        return {"status": "failed", "strategy": strategy, "error": "backtest_failed"}

    oos_metrics = parse_backtest_summary(bt_result.stdout)
    log(f"OoS Results: trades={oos_metrics['trades']} profit={oos_metrics['profit_pct']}% sharpe={oos_metrics['sharpe']}", "OK")

    log(f"Phase 3: Gate check", "STEP")
    promoted, failed_gates = check_promotion_gates(oos_metrics)

    if promoted:
        log(f"✅ PROMOTED — all gates passed", "OK")
        if not dry_run:
            param_file.write_text(json.dumps({
                "strategy_name": strategy,
                "params": new_params,
                "ft_stratparam_v": 1,
                "export_time": now(),
            }, indent=2))
            log(f"Params written to {param_file}", "OK")
    else:
        log(f"❌ REJECTED — gates failed: {', '.join(failed_gates)}", "WARN")
        if existing_params:
            log(f"Keeping existing params from {param_file.name}", "INFO")

    result_entry = {
        "strategy": strategy,
        "promoted": promoted,
        "new_params": new_params,
        "has_existing_params": bool(existing_params),
        "oos": oos_metrics,
        "failed_gates": failed_gates if not promoted else [],
        "epochs": epochs,
        "timerange": total_timerange,
        "dry_run": dry_run,
    }
    save_history(strategy, result_entry)
    return result_entry


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-Optimize Pipeline")
    parser.add_argument("--strategy", help="Strategy to optimize (omit for --all)")
    parser.add_argument("--all", action="store_true", help="Optimize all strategies")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--timerange", default="20250501-20260501")
    parser.add_argument("--dry-run", action="store_true", help="Run without promoting params")
    parser.add_argument("--history", action="store_true", help="Show optimization history")
    args = parser.parse_args()

    if args.history:
        show_history(args.strategy)
        return

    strategies = []
    if args.all:
        strategies = get_available_strategies()
    elif args.strategy:
        strategies = [args.strategy]
    else:
        parser.print_help()
        return

    for s in strategies:
        try:
            result = auto_optimize(
                strategy=s,
                total_timerange=args.timerange,
                epochs=args.epochs,
                dry_run=args.dry_run,
            )
            status_icon = "✅" if result.get("promoted") else "❌" if result.get("status") == "failed" else "⏭️"
            log(f"{status_icon} {s}: {result.get('status', 'done')}", "INFO")
        except Exception as e:
            log(f"❌ {s}: error — {e}", "ERROR")


if __name__ == "__main__":
    main()
