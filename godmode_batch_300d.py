#!/usr/bin/env python3
"""GODMODE BATCH RUNNER: Backtest all strategies on 300d data, 2 at a time."""
import subprocess
import sys
import time
import re
import json
import os

STRATEGIES = [
    # Vector family (all loadable)
    "VectorStrategy",
    "VectorStrategyV2",
    "VectorStrategy_P3B_TIGHTER_TRAIL",
    "VectorStrategy_P3C_WIDER_TRAIL",
    "VectorStrategy_P3D_KILL_ZONE_FILTER",
    "VectorStrategy_P3D_KILL_ZONE_FORCED",
    "VectorStrategy_P3E_KEY_LEVEL_BOOST",
    "VectorStrategy_P3E_HYPEROPT",
    "VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL",
    "VectorStrategy_P3A_RSI_DIVERGENCE_EXIT",
    # Other strategies (some may need PYTHONPATH fix)
    "AroonMomentumEngine_Hybrid",
    "BollingerMeanReversion",
    "DmiAdxStrategy",
    "EmaTrendFollowing",
    "MacdRsiStrategy",
    "RsiDivergenceStrategy",
    "SupertrendEmaStrategy",
    "ensemble_strategy",
]

CONFIG = "user_data/config_godmode_17p.json"
TIMERANGE = "20250711-20260507"
STRATEGY_PATH = "user_data/strategies"
VENV_FREQTRADE = ".venv/bin/freqtrade"
MAX_CONCURRENT = 2
EXTRA_PYTHONPATH = "user_data/strategies"

results = {}

def run_backtest(strategy):
    """Run a single backtest and parse results."""
    env = os.environ.copy()
    # Add strategy dir to PYTHONPATH so mixins resolve
    env["PYTHONPATH"] = EXTRA_PYTHONPATH + ":" + env.get("PYTHONPATH", "")
    
    cmd = [
        VENV_FREQTRADE, "backtesting",
        "--strategy-path", STRATEGY_PATH,
        "--strategy", strategy,
        "--config", CONFIG,
        "--timerange", TIMERANGE,
        "--timeframe-detail", "5m",
    ]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                            env=env, cwd="/home/roshan/Downloads/Algotrading")
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "trades": 0, "profit_pct": 0, "win_rate": 0, "dd": 0}
    
    # Parse summary table
    result = {"status": "DONE", "raw": output[-2000:]}
    
    # Extract from STRATEGY SUMMARY table
    # Pattern: │ StrategyName │ Trades │ Avg Profit % │ Tot Profit USDT │ Tot Profit % │ Duration │ Win Draw Loss Win% │ Drawdown │
    summary_match = re.search(r'│\s*\S+\s*│\s*(\d+)\s*│\s*([\d.-]+)\s*│\s*([\d.]+)\s*│\s*([\d.]+)\s*│\s*([\d:]+)\s*│\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+\.?\d*)\s*│\s*([\d.]+)\s*USDT\s+([\d.]+)%', output)
    if summary_match:
        result["trades"] = int(summary_match.group(1))
        result["avg_profit_pct"] = float(summary_match.group(2))
        result["tot_profit_usdt"] = float(summary_match.group(3))
        result["profit_pct"] = float(summary_match.group(4))
        result["avg_duration"] = summary_match.group(5)
        result["wins"] = int(summary_match.group(6))
        result["draws"] = int(summary_match.group(7))
        result["losses"] = int(summary_match.group(8))
        result["win_rate"] = float(summary_match.group(9))
        result["dd_usdt"] = float(summary_match.group(10))
        result["dd_pct"] = float(summary_match.group(11))
    else:
        result["trades"] = 0
        result["profit_pct"] = 0
        result["win_rate"] = 0
        result["dd_pct"] = 0
    
    # Check for errors
    if "Could not import" in output:
        result["status"] = "IMPORT_ERROR"
        err_match = re.search(r"Could not import.*due to '(.+?)'", output)
        if err_match:
            result["error"] = err_match.group(1)
    
    return result

def main():
    print(f"GODMODE BATCH: {len(STRATEGIES)} strategies, timerange={TIMERANGE}")
    print(f"Config: {CONFIG}, max_concurrent={MAX_CONCURRENT}")
    print("=" * 80)
    
    running = {}
    queue = list(STRATEGIES)
    completed = {}
    
    while queue or running:
        # Fill slots
        while len(running) < MAX_CONCURRENT and queue:
            strat = queue.pop(0)
            env = os.environ.copy()
            env["PYTHONPATH"] = EXTRA_PYTHONPATH + ":" + env.get("PYTHONPATH", "")
            cmd = [
                VENV_FREQTRADE, "backtesting",
                "--strategy-path", STRATEGY_PATH,
                "--strategy", strat,
                "--config", CONFIG,
                "--timerange", TIMERANGE,
                "--timeframe-detail", "5m",
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=env, cwd="/home/roshan/Downloads/Algotrading")
            running[strat] = {"proc": proc, "start": time.time()}
            print(f"  STARTED: {strat} (pid {proc.pid})")
        
        # Wait for any to finish
        if running:
            time.sleep(5)
            done_strats = []
            for strat, info in running.items():
                ret = info["proc"].poll()
                if ret is not None:
                    done_strats.append(strat)
            
            for strat in done_strats:
                info = running.pop(strat)
                proc = info["proc"]
                output = proc.stdout.read() + proc.stderr.read()
                elapsed = time.time() - info["start"]
                
                result = {"status": "DONE", "elapsed": round(elapsed, 1)}
                
                # Parse
                summary_match = re.search(
                    r'│\s*[\w_]+\s*│\s*(\d+)\s*│\s*([\d.-]+)\s*│\s*([\d.]+)\s*│\s*([\d.]+)\s*│\s*([\d:]+)\s*│\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+\.?\d*)\s*│\s*([\d.]+)\s*USDT\s+([\d.]+)%',
                    output
                )
                if summary_match:
                    result["trades"] = int(summary_match.group(1))
                    result["profit_pct"] = float(summary_match.group(4))
                    result["win_rate"] = float(summary_match.group(9))
                    result["dd_pct"] = float(summary_match.group(11))
                else:
                    result["trades"] = 0
                    result["profit_pct"] = 0
                    result["win_rate"] = 0
                    result["dd_pct"] = 0
                
                if "Could not import" in output:
                    result["status"] = "IMPORT_ERROR"
                    err_match = re.search(r"due to '(.+?)'", output)
                    result["error"] = err_match.group(1) if err_match else "unknown"
                
                if result["trades"] == 0 and result["status"] == "DONE":
                    result["status"] = "ZERO_TRADES"
                
                completed[strat] = result
                print(f"  DONE: {strat} → trades={result['trades']}, profit={result['profit_pct']}%, "
                      f"wr={result['win_rate']}%, dd={result['dd_pct']}%, status={result['status']} "
                      f"({elapsed:.0f}s)")
    
    # Final report
    print("\n" + "=" * 80)
    print("GODMODE RESULTS — 300d, 17 pairs, 1h/5m")
    print("=" * 80)
    
    # Sort by profit
    ranked = sorted(completed.items(), key=lambda x: x[1].get("profit_pct", 0), reverse=True)
    
    print(f"\n{'Rank':>4} {'Strategy':40s} {'Trades':>6} {'Profit%':>9} {'WR%':>6} {'DD%':>6} {'Status':15s}")
    print("-" * 90)
    for i, (strat, r) in enumerate(ranked, 1):
        print(f"{i:>4} {strat:40s} {r.get('trades',0):>6} {r.get('profit_pct',0):>+9.2f} "
              f"{r.get('win_rate',0):>6.1f} {r.get('dd_pct',0):>6.2f} {r.get('status','?'):15s}")
    
    # Save JSON
    with open("/home/roshan/Downloads/Algotrading/godmode_300d_results.json", "w") as f:
        json.dump(completed, f, indent=2)
    print(f"\nResults saved to godmode_300d_results.json")

if __name__ == "__main__":
    main()