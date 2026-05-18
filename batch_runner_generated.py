#!/usr/bin/env python3
"""
Phase 3: Batch Backtest Runner — Auto-discover generated strategies and run on futures + spot.

Usage:
  python3 batch_runner_generated.py --mode futures    # 17 pairs, 300d, shorts enabled
  python3 batch_runner_generated.py --mode spot       # 9 pairs, 8+ years, longs only
  python3 batch_runner_generated.py --mode both       # both modes (default)
"""
import subprocess
import json
import re
import time
import os
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path("/home/roshan/Downloads/Algotrading")
STRATEGY_DIR = BASE / "user_data" / "strategies"
GENERATED_DIR = STRATEGY_DIR / "generated"
VENV = str(BASE / ".venv" / "bin" / "freqtrade")
CONFIG_FUTURES = str(BASE / "user_data" / "config_godmode_17p.json")
CONFIG_SPOT = str(BASE / "user_data" / "config_spot.json")
MAX_CONCURRENT = 2

SPOT_PAIRS = [
    "BTC/USDT", "ETH/USDT", "LTC/USDT", "NEO/USDT",
    "XRP/USDT", "ADA/USDT", "XLM/USDT", "TRX/USDT", "BCH/USDT",
]

TIMERANGE_FUTURES = "20250701-20260517"
TIMERANGE_SPOT = "20180101-20260517"


def discover_strategies() -> list:
    """Discover generated strategy files."""
    files = sorted(GENERATED_DIR.glob("GenStrategy_*.py"))
    names = []
    for f in files:
        name = f.stem
        # Validate it's in manifest
        names.append(name)
    return names


def patch_for_spot(strategy_name: str) -> str | None:
    """Patch can_short=False for spot mode. Returns backup path."""
    f = STRATEGY_DIR / "generated" / f"{strategy_name}.py"
    if not f.exists():
        return None
    bak = str(f) + ".bak"
    shutil.copy2(f, bak)
    content = f.read_text()
    patched = re.sub(r'can_short\s*=\s*True', 'can_short = False', content)
    patched = re.sub(r'can_short:\s*bool\s*=\s*True', 'can_short: bool = False', patched)
    f.write_text(patched)
    return bak


def restore_from_backup(bak: str):
    """Restore original file from backup."""
    if os.path.exists(bak):
        orig = bak.replace(".bak", "")
        shutil.move(bak, orig)


def run_backtest(strategy: str, config: str, timerange: str, extra_args: list = None) -> dict:
    """Run a single backtest and parse results."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(STRATEGY_DIR) + ":" + env.get("PYTHONPATH", "")
    cmd = [
        VENV, "backtesting",
        "--strategy-path", str(STRATEGY_DIR),
        "--recursive-strategy-search",
        "--strategy", strategy,
        "--config", config,
        "--timerange", timerange,
        "--cache", "none",
    ]
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                              env=env, cwd=str(BASE))
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "trades": 0, "profit_pct": 0.0, "win_rate": 0.0, "dd_pct": 0.0}

    result = {"status": "DONE", "raw_suffix": output[-1500:]}

    # Parse STRATEGY SUMMARY table
    # Format: │ Name │ Trades │ Avg Profit % │ Tot Profit USDT │ Tot Profit % │ Duration │ Win Draw Loss Win% │ Drawdown │
    pattern = (
        r'│\s*' + re.escape(strategy) +
        r'\s*│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*(\d+:\d+:\d+)\s*│\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)\s*│\s*([-\d.]+)\s*USDT\s+([\d.]+)%'
    )
    m = re.search(pattern, output)
    if m:
        result["trades"] = int(m.group(1))
        result["avg_profit_pct"] = float(m.group(2))
        result["tot_profit_usdt"] = float(m.group(3))
        result["profit_pct"] = float(m.group(4))
        result["avg_duration"] = m.group(5)
        result["wins"] = int(m.group(6))
        result["losses"] = int(m.group(7))
        result["win_rate"] = float(m.group(8))
        result["dd_usdt"] = float(m.group(9))
        result["dd_pct"] = float(m.group(10))
    else:
        result["trades"] = 0
        result["profit_pct"] = 0.0
        result["win_rate"] = 0.0
        result["dd_pct"] = 0.0

    # Check errors
    if "Could not import" in output:
        result["status"] = "IMPORT_ERROR"
        err_m = re.search(r"due to '(.+?)'", output)
        result["error"] = err_m.group(1) if err_m else "unknown"
    elif result["trades"] == 0 and result["status"] == "DONE":
        result["status"] = "ZERO_TRADES"
    elif "No data found" in output:
        result["status"] = "NO_DATA"

    return result


def run_batch(strategies: list, mode: str, config: str, timerange: str,
              extra_args: list = None, patch_short: bool = False) -> dict:
    """Run a batch of backtests with concurrent processes."""
    print(f"\n{'=' * 80}")
    print(f"  BATCH: {mode} — {len(strategies)} strategies, {timerange}")
    print(f"  Config: {config}, max_concurrent={MAX_CONCURRENT}")
    print(f"{'=' * 80}")

    running = {}
    queue = list(strategies)
    completed = {}
    backup_files = {}

    if patch_short:
        print(f"  Patching can_short=False for spot mode...")
        for s in strategies:
            bak = patch_for_spot(s)
            if bak:
                backup_files[s] = bak

    while queue or running:
        # Fill slots
        while len(running) < MAX_CONCURRENT and queue:
            strat = queue.pop(0)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(STRATEGY_DIR) + ":" + env.get("PYTHONPATH", "")
            cmd = [
                VENV, "backtesting",
                "--strategy-path", str(STRATEGY_DIR),
                "--recursive-strategy-search",
                "--strategy", strat,
                "--config", config,
                "--timerange", timerange,
                "--cache", "none",
            ]
            if extra_args:
                cmd.extend(extra_args)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, env=env, cwd=str(BASE))
            running[strat] = {"proc": proc, "start": time.time()}
            print(f"  STARTED [{len(completed) + 1}/{len(strategies) + len(queue) + len(running)}]: {strat} (pid {proc.pid})")

        # Wait for any to finish
        if running:
            time.sleep(5)
            for strat, info in list(running.items()):
                ret = info["proc"].poll()
                if ret is not None:
                    proc = info["proc"]
                    output = proc.stdout.read() + proc.stderr.read()
                    elapsed = time.time() - info["start"]
                    running.pop(strat)

                    r = {"status": "DONE", "elapsed": round(elapsed, 1)}

                    # Parse
                    pattern = (
                        r'│\s*' + re.escape(strat) +
                        r'\s*│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*(\d+:\d+:\d+)\s*│\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)\s*│\s*([-\d.]+)\s*USDT\s+([\d.]+)%'
                    )
                    m = re.search(pattern, output)
                    if m:
                        r["trades"] = int(m.group(1))
                        r["profit_pct"] = float(m.group(4))
                        r["win_rate"] = float(m.group(8))
                        r["dd_pct"] = float(m.group(10))
                    else:
                        r["trades"] = 0
                        r["profit_pct"] = 0.0
                        r["win_rate"] = 0.0
                        r["dd_pct"] = 0.0

                    if "Could not import" in output:
                        r["status"] = "IMPORT_ERROR"
                        err_m = re.search(r"due to '(.+?)'", output)
                        r["error"] = err_m.group(1) if err_m else "unknown"
                    elif r["trades"] == 0 and r["status"] == "DONE":
                        r["status"] = "ZERO_TRADES"
                    elif "No data found" in output:
                        r["status"] = "NO_DATA"

                    completed[strat] = r
                    print(f"  DONE: {strat}  |  trades={r.get('trades',0):>4}  "
                          f"profit={r.get('profit_pct',0):>+7.2f}%  "
                          f"wr={r.get('win_rate',0):>5.1f}%  "
                          f"dd={r.get('dd_pct',0):>5.2f}%  |  {r['status']}  ({elapsed:.0f}s)")

    # Restore patched files
    if patch_short:
        print(f"  Restoring patched files...")
        for s, bak in backup_files.items():
            restore_from_backup(bak)

    return completed


def print_results_table(results: dict, title: str):
    """Print a ranked results table."""
    ranked = sorted(results.items(), key=lambda x: x[1].get("profit_pct", 0), reverse=True)

    print(f"\n{'=' * 90}")
    print(f"  RESULTS — {title}")
    print(f"{'=' * 90}")
    print(f"{'Rank':>4} {'Strategy':40s} {'Trades':>6} {'Profit%':>9} {'WR%':>6} {'DD%':>6} {'Status':15s}")
    print("-" * 90)
    for i, (strat, r) in enumerate(ranked, 1):
        print(f"{i:>4} {strat:40s} {r.get('trades',0):>6} {r.get('profit_pct',0):>+9.2f} "
              f"{r.get('win_rate',0):>6.1f} {r.get('dd_pct',0):>6.2f} {r.get('status','?'):15s}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch backtest runner for generated strategies")
    parser.add_argument("--mode", choices=["futures", "spot", "both"], default="both")
    args = parser.parse_args()

    strategies = discover_strategies()
    print(f"Discovered {len(strategies)} generated strategies in {GENERATED_DIR}")

    all_results = {}

    # ─── Futures ───
    if args.mode in ("futures", "both"):
        fut = run_batch(strategies, "futures", CONFIG_FUTURES, TIMERANGE_FUTURES)
        all_results["futures"] = fut
        print_results_table(fut, f"Futures ({TIMERANGE_FUTURES})")

    # ─── Spot ───
    if args.mode in ("spot", "both"):
        spot_extra = ["-p"] + SPOT_PAIRS + ["--datadir", str(BASE / "user_data" / "data" / "binance" / "spot")]
        spot = run_batch(strategies, "spot", CONFIG_SPOT, TIMERANGE_SPOT,
                         extra_args=spot_extra)
        all_results["spot"] = spot
        print_results_table(spot, f"Spot ({TIMERANGE_SPOT})")

    # ─── Save ───
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = BASE / f"generated_results_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")

    # Summary
    for mode_name, results in all_results.items():
        ok = [s for s, r in results.items() if r.get("trades", 0) > 0]
        zero = [s for s, r in results.items() if r.get("trades", 0) == 0 and r["status"] != "IMPORT_ERROR"]
        err = [s for s, r in results.items() if r["status"] == "IMPORT_ERROR"]
        prof = sum(r.get("profit_pct", 0) for r in results.values())
        print(f"\n{mode_name}: {len(ok)} with trades, {len(zero)} zero-trades, {len(err)} import-errors, total profit={prof:+.2f}%")


if __name__ == "__main__":
    main()
