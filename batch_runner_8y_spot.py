#!/usr/bin/env python3
"""
Comprehensive 8-Year Spot Backtest Runner — All 72 strategies (20 existing + 52 generated).

Usage:
  python3 batch_runner_8y_spot.py --mode existing    # 20 existing strategies
  python3 batch_runner_8y_spot.py --mode generated   # 52 generated strategies
  python3 batch_runner_8y_spot.py --mode all         # both (default)
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
CONFIG_SPOT = str(BASE / "user_data" / "config_spot.json")
MAX_CONCURRENT = 3

SPOT_PAIRS = [
    "BTC/USDT", "ETH/USDT", "LTC/USDT", "NEO/USDT",
    "XRP/USDT", "ADA/USDT", "XLM/USDT", "TRX/USDT", "BCH/USDT",
]
SPOT_DATADIR = str(BASE / "user_data" / "data" / "binance" / "spot")
TIMERANGE = "20180101-20260517"

EXISTING_STRATEGIES = [
    "AroonMomentumEngine_Hybrid", "AroonMomentumEngine_V2",
    "BollingerMeanReversion", "DmiAdxStrategy", "EmaTrendFollowing",
    "MacdRsiStrategy", "RsiDivergenceStrategy", "SupertrendEmaStrategy",
    "VectorStrategy", "VectorStrategyV2", "VectorStrategy_GODMODE_BROKEN",
    "VectorStrategy_P3A_RSI_DIVERGENCE_EXIT", "VectorStrategy_P3B_TIGHTER_TRAIL",
    "VectorStrategy_P3C_WIDER_TRAIL", "VectorStrategy_P3D_KILL_ZONE_FILTER",
    "VectorStrategy_P3D_KILL_ZONE_FORCED", "VectorStrategy_P3E_HYPEROPT",
    "VectorStrategy_P3E_KEY_LEVEL_BOOST", "VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL",
    "ensemble_strategy",
]


def discover_generated() -> list:
    files = sorted(GENERATED_DIR.glob("GenStrategy_*.py"))
    return [f.stem for f in files]


def patch_can_short(strategy_name: str, strategy_dir: Path) -> str | None:
    """Patch can_short=False for spot mode. Returns backup path."""
    f = strategy_dir / f"{strategy_name}.py"
    if not f.exists():
        return None
    bak = str(f) + ".bak"
    shutil.copy2(f, bak)
    content = f.read_text()
    patched = re.sub(r'can_short\s*=\s*True', 'can_short = False', content)
    patched = re.sub(r'can_short:\s*bool\s*=\s*True', 'can_short: bool = False', patched)
    if patched != content:
        f.write_text(patched)
        return bak
    os.remove(bak)
    return None


def restore_from_backup(bak: str):
    if os.path.exists(bak):
        orig = bak.replace(".bak", "")
        shutil.move(bak, orig)


def run_batch(strategies: list, label: str, strategy_dir: Path) -> dict:
    """Run a batch of backtests with concurrent processes on 8y spot data."""
    print(f"\n{'=' * 80}")
    print(f"  8Y SPOT BACKTEST: {label} — {len(strategies)} strategies")
    print(f"  Timerange: {TIMERANGE}, {len(SPOT_PAIRS)} pairs, max_concurrent={MAX_CONCURRENT}")
    print(f"{'=' * 80}")

    running = {}
    queue = list(strategies)
    completed = {}
    backup_files = {}

    # Patch all strategies for spot mode
    print("  Patching can_short=False...")
    for s in strategies:
        bak = patch_can_short(s, strategy_dir)
        if bak:
            backup_files[s] = bak

    while queue or running:
        while len(running) < MAX_CONCURRENT and queue:
            strat = queue.pop(0)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(STRATEGY_DIR) + ":" + env.get("PYTHONPATH", "")
            cmd = [
                VENV, "backtesting",
                "--strategy-path", str(STRATEGY_DIR),
                "--recursive-strategy-search",
                "--strategy", strat,
                "--config", CONFIG_SPOT,
                "--timerange", TIMERANGE,
                "--cache", "none",
                "-p"] + SPOT_PAIRS + ["--datadir", SPOT_DATADIR,
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, env=env, cwd=str(BASE))
            running[strat] = {"proc": proc, "start": time.time()}
            done_count = len(completed)
            queue_count = len(queue) + len(running)
            print(f"  STARTED [{done_count + 1}/{len(strategies)}] ({queue_count} left): {strat} (pid {proc.pid})")

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

                    # Parse STRATEGY SUMMARY
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
                    elif r["trades"] == 0 and "No data found" in output:
                        r["status"] = "NO_DATA"
                    elif r["trades"] == 0:
                        r["status"] = "ZERO_TRADES"

                    completed[strat] = r
                    arrow = "+" if r.get("profit_pct", 0) >= 0 else " "
                    print(f"  DONE: {strat:45s} | {r.get('trades',0):>5} trades  "
                          f"profit={arrow}{r.get('profit_pct',0):>+7.2f}%  "
                          f"wr={r.get('win_rate',0):>5.1f}%  "
                          f"dd={r.get('dd_pct',0):>5.2f}%  |  {r['status']}  ({elapsed:.0f}s)")

    # Restore patched files
    print("  Restoring patched files...")
    for s, bak in backup_files.items():
        restore_from_backup(bak)

    return completed


def print_results(results: dict, title: str):
    ranked = sorted(results.items(), key=lambda x: x[1].get("profit_pct", 0), reverse=True)
    print(f"\n{'=' * 100}")
    print(f"  RESULTS — {title}")
    print(f"{'=' * 100}")
    print(f"{'Rank':>4} {'Strategy':45s} {'Trades':>6} {'Profit%':>9} {'WR%':>6} {'DD%':>6} {'Status':15s}")
    print("-" * 100)
    for i, (s, r) in enumerate(ranked, 1):
        arrow = "+" if r.get("profit_pct", 0) >= 0 else " "
        print(f"{i:>4} {s:45s} {r.get('trades',0):>6} {arrow}{r.get('profit_pct',0):>+8.2f} "
              f"{r.get('win_rate',0):>6.1f} {r.get('dd_pct',0):>6.2f} {r.get('status','?'):15s}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="8-Year Spot Backtest for ALL strategies")
    parser.add_argument("--mode", choices=["existing", "generated", "all"], default="all")
    args = parser.parse_args()

    all_results = {}

    if args.mode in ("existing", "all"):
        results = run_batch(EXISTING_STRATEGIES, "Existing (20)", STRATEGY_DIR)
        all_results["existing_spot_8y"] = results
        print_results(results, "Existing Strategies — 8Y Spot")

    if args.mode in ("generated", "all"):
        gen_strats = discover_generated()
        results = run_batch(gen_strats, "Generated (52)", GENERATED_DIR)
        all_results["generated_spot_8y"] = results
        print_results(results, "Generated Strategies — 8Y Spot")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = BASE / f"all_results_8y_spot_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")


if __name__ == "__main__":
    main()
