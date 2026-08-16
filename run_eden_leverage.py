#!/usr/bin/env python3
"""Run EDEN backtest at 6x, 12x, 18x leverage"""
import subprocess, json, os, re, shutil, tempfile
from pathlib import Path

BASE = "/home/roshan/Downloads/Algotrading"
FREQTRADE = f"{BASE}/.venv/bin/freqtrade"
CONFIG = f"{BASE}/user_data/config_dryrun.json"
TIMERANGE = "20260512-20260519"
STRAT_DIR = Path(f"{BASE}/user_data/strategies")

# Strategies that had trades in the last run
STRATEGIES = [
    "BOS_V1_ShortTop9", "BOS_V2_Short_SL4", "BOS_V2_Short_SL6",
    "BOS_V2_Short_SL8", "BOS_V3_LateTrailMerge", "BOS_V5_Hyperopt",
    "BOS_FRVP_LVN_VWAP", "BOS_FRVP_LVN_VWAP_Short",
    "Hedge01FixedFractional", "Hedge02RiskToZero", "Hedge04ConsecLossProtect",
    "Hedge05ScaleOut", "Hedge06AntiMartingale", "Hedge07WinRateAdaptive",
    "HedgeMeta7in1", "HedgeChampionP3F", "HedgeMomentumMacdRsiLong",
    "HedgeMomentumMacdRsiShort", "HedgeShortV1Baseline", "HedgeShortV1FixedTP",
    "HedgeShortV2Trail", "HedgeShortV2WideTrail", "HedgeShortV3ATRTP",
    "HedgeShortV3ATRTrail", "HedgeShortV4Cascade", "HedgeShortV4MACDExit",
    "HedgeShortV5PureTrail", "HedgeShortV5RSIExit", "HedgeShortV6Hybrid",
    "HedgeShortV6LateTrail", "HedgeMomentumMacdRsi", "HedgeMomentumMacdRsiV2",
    "BOSV4ShortStrict", "Hedge03HalfKelly",
]

def find_strat_file(strat_name):
    for f in STRAT_DIR.glob("*.py"):
        content = f.read_text()
        if f"class {strat_name}" in content:
            return f, content
    return None, None

def patch_leverage(content, leverage):
    # BOS pattern: default=10.0 in leverage_num
    content = re.sub(
        r'(leverage_num\s*=\s*DecimalParameter\([^,]+,\s*[^,]+,\s*)default=10([\d.]*)([\s,]*)',
        lambda m: f"{m.group(1)}default={leverage}{m.group(3)}",
        content
    )
    # BOS pattern: default=10
    content = re.sub(
        r'(leverage_num\s*=\s*DecimalParameter\([^,]+,\s*[^,]+,\s*)default=10(\s*[\),])',
        lambda m: f"{m.group(1)}default={leverage}{m.group(2)}",
        content
    )
    # Hedge pattern: min(10.0, max_leverage)
    content = re.sub(
        r'min\(10[\d.]*\s*,\s*max_leverage\)',
        f'min({float(leverage)}, max_leverage)',
        content
    )
    # Hedge pattern: min(10, max_leverage)
    content = re.sub(
        r'min\(10\s*,\s*max_leverage\)',
        f'min({float(leverage)}, max_leverage)',
        content
    )
    return content

def run_backtest(strat_name, strat_path, leverage):
    cmd = [
        FREQTRADE, "backtesting",
        "--strategy", strat_name,
        "--strategy-path", str(strat_path),
        "--config", CONFIG,
        "--timerange", TIMERANGE,
        "--timeframe", "1h",
        "--cache", "none",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=BASE)
    return parse_result(result.stdout + result.stderr)

def parse_result(output):
    r = {"profit_pct": None, "profit_usdt": None, "trades": None}
    for line in output.split("\n"):
        if "Total profit %" in line:
            parts = line.split("│")
            if len(parts) >= 3:
                try: r["profit_pct"] = float(parts[2].strip().replace("%","").replace(",",""))
                except: pass
        if "Absolute profit" in line:
            parts = line.split("│")
            if len(parts) >= 3:
                try: r["profit_usdt"] = float(parts[2].strip().replace("USDT","").strip())
                except: pass
        if "Total/Daily Avg Trades" in line:
            parts = line.split("│")
            if len(parts) >= 3:
                try: r["trades"] = int(parts[2].strip().split("/")[0].strip())
                except: pass
    return r

results = []
for lev in [6, 12, 18]:
    print(f"\n{'='*70}")
    print(f"  LEVERAGE: {lev}x")
    print(f"{'='*70}")
    tmpdir = Path(tempfile.mkdtemp(prefix=f"eden_{lev}x_"))
    for i, strat in enumerate(STRATEGIES, 1):
        print(f"  [{i}/{len(STRATEGIES)}] {strat}...", end=" ", flush=True)
        sf, content = find_strat_file(strat)
        if not sf:
            print("✗ NOT FOUND")
            continue
        patched = patch_leverage(content, lev)
        tmpfile = tmpdir / sf.name
        tmpfile.write_text(patched)
        try:
            stats = run_backtest(strat, tmpdir, lev)
            pct = stats.get("profit_pct", "N/A")
            trades = stats.get("trades", "N/A")
            if pct is not None:
                print(f"✓ {pct:+.2f}% | {trades} trades")
            else:
                print(f"✓ (no output)")
            results.append({"strategy": strat, "leverage": lev, **stats})
        except subprocess.TimeoutExpired:
            print(f"✗ TIMEOUT")
            results.append({"strategy": strat, "leverage": lev, "error": "timeout"})
        except Exception as e:
            print(f"✗ {e}")
            results.append({"strategy": strat, "leverage": lev, "error": str(e)})
    shutil.rmtree(tmpdir)

# Print summary
print(f"\n{'='*100}")
print(f"  EDEN 7-DAY BACKTEST — ALL LEVERAGE LEVELS")
print(f"{'='*100}")
print(f"{'Strategy':<30} {'6x%':<10} {'6x$':<12} {'6xTr':<7} {'12x%':<10} {'12x$':<12} {'12xTr':<7} {'18x%':<10} {'18x$':<12} {'18xTr':<7}")
print(f"{'-'*100}")
by_strat = {}
for r in results:
    s = r["strategy"]
    if s not in by_strat:
        by_strat[s] = {}
    by_strat[s][r["leverage"]] = r

for s in sorted(by_strat.keys()):
    row = [s]
    for lev in [6, 12, 18]:
        r = by_strat[s].get(lev, {})
        pct = r.get("profit_pct")
        pu = r.get("profit_usdt")
        tr = r.get("trades")
        row.append(f"{pct:+.2f}%" if pct is not None else "N/A")
        row.append(f"${pu:+.2f}" if pu is not None else "N/A")
        row.append(str(tr) if tr is not None else "N/A")
    print(f"{row[0]:<30} {row[1]:<10} {row[2]:<12} {row[3]:<7} {row[4]:<10} {row[5]:<12} {row[6]:<7} {row[7]:<10} {row[8]:<12} {row[9]:<7}")

results.sort(key=lambda r: r.get("profit_pct", -9999) if r.get("profit_pct") is not None else -9999, reverse=True)
print(f"\nTop 5 overall:")
for r in results[:5]:
    print(f"  {r['strategy']} @ {r['leverage']}x: {r.get('profit_pct', 0):+.2f}%")

with open(f"{BASE}/eden_leverage_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved to eden_leverage_results.json")
