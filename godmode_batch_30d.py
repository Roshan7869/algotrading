#!/usr/bin/env python3
"""GODMODE 30-day backtest — top 8 strategies, last 30 days"""
import subprocess, sys, time, json

STRATEGIES = [
    "VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL",
    "VectorStrategy_P3E_KEY_LEVEL_BOOST",
    "VectorStrategy_P3E_HYPEROPT",
    "BollingerMeanReversion",
    "VectorStrategy",
    "VectorStrategy_P3B_TIGHTER_TRAIL",
    "VectorStrategy_P3A_RSI_DIVERGENCE_EXIT",
    "AroonMomentumEngine_V2",
]

CONFIG = "user_data/config_godmode_17p.json"
TIMERANGE = "20260416-20260516"
BATCH_SIZE = 2
results = {}

def run_backtest(strategy):
    cmd = [
        ".venv/bin/freqtrade", "backtesting",
        "--strategy-path", "user_data/strategies",
        "--strategy", strategy,
        "--config", CONFIG,
        "--timerange", TIMERANGE,
        "--timeframe-detail", "5m",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.stdout + r.stderr

for i in range(0, len(STRATEGIES), BATCH_SIZE):
    batch = STRATEGIES[i:i+BATCH_SIZE]
    procs = {}
    for strat in batch:
        p = subprocess.Popen(
            f'.venv/bin/freqtrade backtesting --strategy-path user_data/strategies --strategy {strat} --config {CONFIG} --timerange {TIMERANGE} --timeframe-detail 5m',
            shell=True, cwd="/home/roshan/Downloads/Algotrading",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        procs[strat] = p

    for strat, p in procs.items():
        out, _ = p.communicate(timeout=600)
        # Parse total line
        trades = profit_pct = wr = dd = 0
        for line in out.split("\n"):
            if "TOTAL" in line and "│" in line:
                parts = [x.strip() for x in line.split("│") if x.strip()]
                if len(parts) >= 7:
                    try:
                        trades = int(parts[1])
                        profit_pct = float(parts[4].replace(",",""))
                        wr = float(parts[6].split()[0])
                    except:
                        pass
            if "Absolute drawdown" in line:
                try:
                    dd = float(line.split("(")[1].split("%")[0].strip())
                except:
                    pass
            # Strategy summary line
            if strat in line and "│" in line and "Trades" not in line:
                sparts = [x.strip() for x in line.split("│") if x.strip()]
                if len(sparts) >= 7:
                    try:
                        trades = int(sparts[1])
                        profit_pct = float(sparts[4].replace(",",""))
                        wr = float(sparts[6].split()[0])
                    except:
                        pass

        results[strat] = {
            "trades": trades, "profit_pct": profit_pct,
            "wr": wr, "dd": dd, "status": "DONE" if trades > 0 else "ZERO_TRADES"
        }
        print(f"  {strat}: {trades} trades, +{profit_pct}%, WR {wr}%, DD {dd}%", flush=True)

# Save
with open("godmode_30d_results.json", "w") as f:
    json.dump(results, f, indent=2)

# Print table
print(f"\n{'Rank':>4} {'Strategy':50s} {'Trades':>7} {'Profit%':>12} {'WR%':>7} {'DD%':>7}")
print("-" * 95)
ranked = sorted(results.items(), key=lambda x: x[1]["profit_pct"], reverse=True)
for i, (n, v) in enumerate(ranked, 1):
    print(f"{i:>4} {n:50s} {v['trades']:>7} {v['profit_pct']:>12.2f} {v['wr']:>7.1f} {v['dd']:>7.2f}")

print("\nDone!")
