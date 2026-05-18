#!/usr/bin/env python3
"""
GODMODE Batch Backtest Runner — All Strategies on 2018+ Data

Two modes:
  1. FUTURES: BTC+ETH+XRP from 2020-01 (longest futures data with shorts)
  2. SPOT: BTC+ETH+LTC+NEO from 2018-01 (8+ years, longs only)

For spot mode, temporarily patches can_short=False in each strategy.
"""
import subprocess
import json
import re
import sys
import os
import shutil
import time
from pathlib import Path
from datetime import datetime

BASE = Path("/home/roshan/Downloads/Algotrading")
STRAT_DIR = BASE / "user_data" / "strategies"
VENV = str(BASE / ".venv" / "bin" / "freqtrade")

# All strategies to test
ALL_STRATEGIES = [
    "VectorStrategy",
    "VectorStrategy_P3E_KEY_LEVEL_BOOST",
    "VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL",
    "VectorStrategy_P3E_HYPEROPT",
    "VectorStrategy_P3A_RSI_DIVERGENCE_EXIT",
    "VectorStrategy_P3B_TIGHTER_TRAIL",
    "VectorStrategy_P3C_WIDER_TRAIL",
    "VectorStrategy_P3D_KILL_ZONE_FILTER",
    "BollingerMeanReversion",
    "MacdRsiStrategy",
    "AroonMomentumEngine_V2",
    "EmaTrendFollowing",
    "DmiAdxStrategy",
    "RsiDivergenceStrategy",
    "SupertrendEmaStrategy",
    "ensemble_strategy",
    "VectorStrategyV2",
]

# Pairs for each mode
SPOT_PAIRS = ["BTC/USDT", "ETH/USDT", "LTC/USDT", "NEO/USDT", "XRP/USDT", "ADA/USDT", "XLM/USDT", "TRX/USDT"]
FUTURES_PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "XRP/USDT:USDT"]

def patch_can_short(strategy_file, value=False):
    """Temporarily patch can_short in a strategy file."""
    with open(strategy_file, 'r') as f:
        content = f.read()
    # Backup
    shutil.copy2(strategy_file, str(strategy_file) + '.bak')
    # Patch can_short
    patched = re.sub(r'can_short\s*[:=]\s*bool\s*=\s*True', f'can_short: bool = {value}', content)
    patched = re.sub(r'can_short\s*=\s*True', f'can_short = {value}', patched)
    with open(strategy_file, 'w') as f:
        f.write(patched)
    return str(strategy_file) + '.bak'

def restore_strategy(bak_file):
    """Restore from backup."""
    orig = bak_file.replace('.bak', '')
    shutil.move(bak_file, orig)

def run_backtest(strategy, pairs, timerange, datadir=None, config=None):
    """Run a single backtest and parse results."""
    cmd = [VENV, "backtesting", "--strategy", strategy, "--timerange", timerange,
           "--stake-amount", "50", "--max-open-trades", "3", "-p"] + pairs
    if datadir:
        cmd.extend(["--datadir", datadir])
    if config:
        cmd.extend(["--config", config])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(BASE))
        output = result.stdout + result.stderr
        
        # Parse strategy summary table
        pattern = r'\|\s*(' + re.escape(strategy) + r')\s*\|\s*(\d+)\s*\|\s*([-\d.]+)\s*\|\s*([-\d.]+)\s*\|\s*([-\d.]+)\s*\|\s*(\d+:\d+:\d+)\s*\|\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)\s*\|\s*([\d.]+)\s*USDT\s+([\d.]+)%'
        match = re.search(pattern, output)
        
        if match:
            return {
                "strategy": strategy,
                "trades": int(match.group(2)),
                "avg_profit_pct": float(match.group(3)),
                "total_profit_usdt": float(match.group(4)),
                "total_profit_pct": float(match.group(5)),
                "avg_duration": match.group(6),
                "wins": int(match.group(7)),
                "losses": int(match.group(8)),
                "win_rate": float(match.group(9)),
                "drawdown_usdt": float(match.group(10)),
                "drawdown_pct": float(match.group(11)),
                "ok": True,
            }
        
        # Check for errors
        if "No pair in whitelist" in output:
            return {"strategy": strategy, "ok": False, "error": "No pairs found"}
        if "cannot run in spot" in output:
            return {"strategy": strategy, "ok": False, "error": "can_short=True on spot"}
        if "Error" in output:
            err_lines = [l for l in output.split('\n') if 'Error' in l]
            return {"strategy": strategy, "ok": False, "error": '; '.join(err_lines[:3])}
        
        return {"strategy": strategy, "ok": False, "error": "Could not parse results", "raw": output[-500:]}
    
    except subprocess.TimeoutExpired:
        return {"strategy": strategy, "ok": False, "error": "timeout"}
    except Exception as e:
        return {"strategy": strategy, "ok": False, "error": str(e)}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["spot_2018", "futures_2020", "both"], default="both")
    args = parser.parse_args()
    
    all_results = {}
    
    # ─── MODE 1: SPOT from 2018 (longs only) ───
    if args.mode in ("spot_2018", "both"):
        print("\n" + "="*80)
        print("  SPOT BACKTEST — 2018-01 to 2026-05 (8+ years, longs only)")
        print("="*80)
        
        # Patch can_short=False for spot mode
        bak_files = []
        for s in ALL_STRATEGIES:
            f = STRAT_DIR / f"{s}.py"
            if f.exists():
                bak = patch_can_short(f, value=False)
                bak_files.append(bak)
        
        spot_results = []
        for i, s in enumerate(ALL_STRATEGIES):
            print(f"\n[{i+1}/{len(ALL_STRATEGIES)}] {s} (SPOT 2018-2026)...")
            r = run_backtest(
                s, SPOT_PAIRS, "20180101-20260516",
                datadir=str(BASE / "user_data" / "data" / "binance" / "spot"),
            )
            spot_results.append(r)
            if r.get("ok"):
                print(f"  ✅ {r['trades']} trades, {r['total_profit_pct']:+.2f}%, WR={r['win_rate']}%, DD={r['drawdown_pct']}%")
            else:
                print(f"  ❌ {r.get('error', 'unknown')}")
            time.sleep(1)
        
        all_results["spot_2018"] = spot_results
        
        # Restore
        for bak in bak_files:
            restore_strategy(bak)
    
    # ─── MODE 2: FUTURES from 2020 (with shorts) ───
    if args.mode in ("futures_2020", "both"):
        print("\n" + "="*80)
        print("  FUTURES BACKTEST — 2020-01 to 2026-05 (6+ years, longs + shorts)")
        print("="*80)
        
        futures_results = []
        for i, s in enumerate(ALL_STRATEGIES):
            print(f"\n[{i+1}/{len(ALL_STRATEGIES)}] {s} (FUTURES 2020-2026)...")
            r = run_backtest(s, FUTURES_PAIRS, "20200101-20260516")
            futures_results.append(r)
            if r.get("ok"):
                print(f"  ✅ {r['trades']} trades, {r['total_profit_pct']:+.2f}%, WR={r['win_rate']}%, DD={r['drawdown_pct']}%")
            else:
                print(f"  ❌ {r.get('error', 'unknown')}")
            time.sleep(1)
        
        all_results["futures_2020"] = futures_results
    
    # ─── SAVE RESULTS ───
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = BASE / f"batch_results_{ts}.json"
    with open(outfile, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")
    
    # ─── PRINT SUMMARY ───
    for mode_name, results in all_results.items():
        ok_results = [r for r in results if r.get("ok")]
        ok_results.sort(key=lambda x: x.get("total_profit_pct", -999), reverse=True)
        
        print(f"\n{'='*100}")
        print(f"  RESULTS — {mode_name}")
        print(f"{'='*100}")
        print(f"{'Strategy':<45} {'Trades':>6} {'Profit%':>8} {'WR%':>6} {'DD%':>6} {'Duration':>10}")
        print("-"*100)
        for r in ok_results:
            print(f"{r['strategy']:<45} {r['trades']:>6} {r['total_profit_pct']:>+8.2f} {r['win_rate']:>6.1f} {r['drawdown_pct']:>6.2f} {r['avg_duration']:>10}")
        
        fail_results = [r for r in results if not r.get("ok")]
        if fail_results:
            print(f"\nFailed strategies:")
            for r in fail_results:
                print(f"  {r['strategy']}: {r.get('error', 'unknown')}")

if __name__ == "__main__":
    main()