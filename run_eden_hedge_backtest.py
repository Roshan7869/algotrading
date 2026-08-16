#!/usr/bin/env python3
"""Run all HEdge + BOS strategies on EDEN token, last 7 days"""
import subprocess, json, re, sys, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "/home/roshan/Downloads/Algotrading"
FREQTRADE = f"{BASE}/.venv/bin/freqtrade"
CONFIG = f"{BASE}/user_data/config_dryrun.json"
STRAT_PATH = f"{BASE}/user_data/strategies"
TIMERANGE = "20260512-20260519"
TIMEFRAME = "1h"

STRATEGIES = [
    # Hedge strategies (risk management variants)
    "Hedge01FixedFractional",
    "Hedge02RiskToZero",
    "Hedge03HalfKelly",
    "Hedge04ConsecLossProtect",
    "Hedge05ScaleOut",
    "Hedge06AntiMartingale",
    "Hedge07WinRateAdaptive",
    "HedgeMeta7in1",
    "HedgeChampionP3F",
    # Hedge momentum variants
    "HedgeMomentumMacdRsi",
    "HedgeMomentumMacdRsiLong",
    "HedgeMomentumMacdRsiShort",
    "HedgeMomentumMacdRsiV2",
    # Short exit variants
    "HedgeShortV1Baseline",
    "HedgeShortV1FixedTP",
    "HedgeShortV2Trail",
    "HedgeShortV2WideTrail",
    "HedgeShortV3ATRTP",
    "HedgeShortV3ATRTrail",
    "HedgeShortV4Cascade",
    "HedgeShortV4MACDExit",
    "HedgeShortV5PureTrail",
    "HedgeShortV5RSIExit",
    "HedgeShortV6Hybrid",
    "HedgeShortV6LateTrail",
    # BOS FRVP variants
    "BOS_FRVP_LVN_VWAP",
    "BOS_FRVP_LVN_VWAP_Short",
    "BOSV4ShortStrict",
    # BOS optimisation suite
    "BOS_V1_ShortTop9",
    "BOS_V2_Short_SL4",
    "BOS_V2_Short_SL6",
    "BOS_V2_Short_SL8",
    "BOS_V3_LateTrailMerge",
    "BOS_V5_Hyperopt",
]

def parse_result(output):
    result = {"profit_pct": None, "trades": None, "winrate": None, "dd_pct": None, "profit_usdt": None}
    lines = output.split("\n")
    for i, line in enumerate(lines):
        if "│" in line and "TOTAL" in line and i + 1 < len(lines):
            next_line = lines[i + 1]
            if "│" in next_line:
                parts = [p.strip() for p in next_line.split("│") if p.strip()]
                if len(parts) >= 5:
                    result["trades"] = parts[1] if parts[1] != "0" else parts[1]
                    try: result["profit_pct"] = float(parts[3].replace("%", "").replace(",", ""))
                    except: pass
                    if len(parts) >= 7:
                        try: result["winrate"] = float(parts[6].split()[-1].replace("%", ""))
                        except: pass
        if "Total profit %" in line:
            parts = line.split("│")
            if len(parts) >= 3:
                try: result["profit_pct"] = float(parts[2].strip().replace("%", "").replace(",", ""))
                except: pass
        if "Total/Daily Avg Trades" in line:
            parts = line.split("│")
            if len(parts) >= 3:
                try: result["trades"] = int(parts[2].strip().split("/")[0].strip())
                except: pass
        if "Absolute profit" in line:
            parts = line.split("│")
            if len(parts) >= 3:
                try: result["profit_usdt"] = float(parts[2].strip().replace("USDT", "").strip())
                except: pass
    return result

def run_backtest(strategy_name):
    cmd = [
        FREQTRADE, "backtesting",
        "--strategy", strategy_name,
        "--strategy-path", STRAT_PATH,
        "--config", CONFIG,
        "--timerange", TIMERANGE,
        "--timeframe", TIMEFRAME,
        "--cache", "none",
    ]
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=BASE)
    elapsed = time.time() - start
    output = result.stdout + result.stderr
    stats = parse_result(output)
    stats["elapsed_s"] = round(elapsed, 1)
    return stats, output

results = []
print(f"\n{'='*80}")
print(f"  EDEN Backtest — All HEdge + BOS Strategies")
print(f"  Period: {TIMERANGE} | Timeframe: {TIMEFRAME}")
print(f"  Strategies: {len(STRATEGIES)}")
print(f"{'='*80}\n")

for i, strat in enumerate(STRATEGIES, 1):
    print(f"[{i}/{len(STRATEGIES)}] {strat}...", end=" ", flush=True)
    try:
        stats, output = run_backtest(strat)
        pct = stats["profit_pct"]
        trades = stats["trades"]
        if pct is not None:
            print(f"✓ {pct:+.2f}% | {trades} trades | {stats['elapsed_s']}s")
        else:
            print(f"✓ (parsed) | {stats['elapsed_s']}s")
        results.append({"strategy": strat, **stats})
    except subprocess.TimeoutExpired:
        print(f"✗ TIMEOUT")
        results.append({"strategy": strat, "error": "timeout"})
    except Exception as e:
        print(f"✗ {e}")
        results.append({"strategy": strat, "error": str(e)})

results.sort(key=lambda r: r.get("profit_pct") if r.get("profit_pct") is not None else -9999, reverse=True)

print(f"\n{'='*80}")
print(f"  RESULTS — EDEN 7-Day Backtest")
print(f"{'='*80}")
print(f"{'Rank':<5} {'Strategy':<30} {'Profit%':<10} {'Trades':<8} {'WinRate':<8} {'DD%':<8} {'Profit$':<12}")
print(f"{'-'*80}")
for rank, r in enumerate(results, 1):
    pct = r.get("profit_pct", "N/A")
    trades = r.get("trades", "N/A")
    wr = r.get("winrate", "N/A")
    dd = r.get("dd_pct", "N/A")
    pu = r.get("profit_usdt", "N/A")
    pct_str = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else str(pct)
    trades_str = str(trades) if trades is not None else "N/A"
    wr_str = f"{wr:.1f}%" if isinstance(wr, (int, float)) else "N/A"
    dd_str = f"{dd:.1f}%" if isinstance(dd, (int, float)) else "N/A"
    pu_str = f"${pu:+.2f}" if isinstance(pu, (int, float)) else "N/A"
    print(f"{rank:<5} {r['strategy']:<30} {pct_str:<10} {trades_str:<8} {wr_str:<8} {dd_str:<8} {pu_str:<12}")

print(f"\nResults saved to: {BASE}/eden_hedge_results.json")
with open(f"{BASE}/eden_hedge_results.json", "w") as f:
    json.dump(results, f, indent=2)
