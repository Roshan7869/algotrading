#!/usr/bin/env python3
"""
Comprehensive Backtest: ALL strategies on 8-year spot data + 6-year futures.
3 concurrent processes, saves results incrementally.
"""
import subprocess
import json
import re
import os
import shutil
import time
import sys
from pathlib import Path
from datetime import datetime

BASE = Path("/home/roshan/Downloads/Algotrading")
STRAT_DIR = BASE / "user_data" / "strategies"
GEN_DIR = STRAT_DIR / "generated"
VENV = str(BASE / ".venv" / "bin" / "freqtrade")
RESULTS_DIR = BASE / "user_data" / "backtest_results_8yr"
MAX_CONCURRENT = 3

SPOT_PAIRS = ["BTC/USDT", "ETH/USDT", "LTC/USDT", "NEO/USDT", "XRP/USDT", "ADA/USDT", "XLM/USDT", "TRX/USDT"]
SPOT_DATADIR = str(BASE / "user_data" / "data" / "binance" / "spot")
FUTURES_PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "XRP/USDT:USDT"]

TIMERANGE_SPOT = "20180101-20260517"
TIMERANGE_FUTURES = "20200101-20260517"

MANUAL_STRATEGIES = [
    "VectorStrategy", "VectorStrategyV2",
    "VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL", "VectorStrategy_P3E_KEY_LEVEL_BOOST",
    "VectorStrategy_P3E_HYPEROPT", "VectorStrategy_P3A_RSI_DIVERGENCE_EXIT",
    "VectorStrategy_P3B_TIGHTER_TRAIL", "VectorStrategy_P3C_WIDER_TRAIL",
    "VectorStrategy_P3D_KILL_ZONE_FILTER", "VectorStrategy_P3D_KILL_ZONE_FORCED",
    "BollingerMeanReversion", "MacdRsiStrategy",
    "AroonMomentumEngine_Hybrid", "AroonMomentumEngine_V2",
    "EmaTrendFollowing", "DmiAdxStrategy",
    "RsiDivergenceStrategy", "SupertrendEmaStrategy",
    "ensemble_strategy",
]

def discover_generated():
    files = sorted(GEN_DIR.glob("GenStrategy_*.py"))
    return [f.stem for f in files]

def patch_can_short(filepath, value=False):
    bak = str(filepath) + ".bak"
    shutil.copy2(filepath, bak)
    content = filepath.read_text()
    patched = re.sub(r'can_short\s*[:=]\s*bool\s*=\s*True', f'can_short: bool = {value}', content)
    patched = re.sub(r'can_short\s*=\s*True', f'can_short = {value}', patched)
    filepath.write_text(patched)
    return bak

def restore(bak):
    if os.path.exists(bak):
        os.rename(bak, bak.replace(".bak", ""))

def parse_summary(output, name):
    pattern = (
        r'│\s*' + re.escape(name) +
        r'\s*│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*(\d+:\d+:\d+)\s*│\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)\s*│\s*([-\d.]+)\s*USDT\s+([\d.]+)%'
    )
    m = re.search(pattern, output)
    if m:
        return {
            "trades": int(m.group(1)), "avg_profit_pct": float(m.group(2)),
            "tot_profit_usdt": float(m.group(3)), "profit_pct": float(m.group(4)),
            "avg_duration": m.group(5), "wins": int(m.group(6)),
            "losses": int(m.group(7)), "win_rate": float(m.group(8)),
            "dd_usdt": float(m.group(9)), "dd_pct": float(m.group(10)),
        }
    return None

def run_batch(strategies, mode_label, pairs, timerange, datadir=None, config=None):
    Results_file = RESULTS_DIR / f"results_{mode_label}.json"
    already = {}
    if Results_file.exists():
        already = json.loads(Results_file.read_text())

    todo = [s for s in strategies if s not in already]
    if not todo:
        print(f"\n  [{mode_label}] All {len(strategies)} already done, skipping.")
        return already

    print(f"\n{'='*80}")
    print(f"  BATCH: {mode_label} — {len(todo)} remaining of {len(strategies)} strategies")
    print(f"  Timerange: {timerange}, Pairs: {len(pairs)}, Concurrent: {MAX_CONCURRENT}")
    print(f"  Progress: {len(already)}/{len(strategies)} done")
    print(f"{'='*80}")

    running = {}
    queue = list(todo)
    results = dict(already)
    start_time = time.time()

    while queue or running:
        while len(running) < MAX_CONCURRENT and queue:
            s = queue.pop(0)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(STRAT_DIR) + ":" + env.get("PYTHONPATH", "")
            cmd = [VENV, "backtesting", "--strategy", s, "--timerange", timerange,
                   "--stake-amount", "50", "--max-open-trades", "3", "-p"] + pairs
            if datadir:
                cmd.extend(["--datadir", datadir])
            if config:
                cmd.extend(["--config", config])
            cmd.extend(["--cache", "none"])
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, env=env, cwd=str(BASE))
                running[s] = {"proc": proc, "start": time.time()}
                total = len(already) + len(todo)
                remaining = total - len(results)
                print(f"  [{remaining} left] STARTED: {s} (pid {proc.pid})")
            except Exception as e:
                results[s] = {"status": "LAUNCH_ERROR", "error": str(e), "trades": 0, "profit_pct": 0, "win_rate": 0, "dd_pct": 0}
                Results_file.write_text(json.dumps(results, indent=2, default=str))

        if running:
            time.sleep(3)
            for s, info in list(running.items()):
                ret = info["proc"].poll()
                if ret is not None:
                    proc = info["proc"]
                    out = proc.stdout.read() + proc.stderr.read()
                    elapsed = time.time() - info["start"]
                    running.pop(s)

                    r = {"status": "DONE", "elapsed_s": round(elapsed, 1)}

                    # Try to re-run if output empty (freak crash)
                    if len(out.strip()) < 50 and elapsed < 10:
                        r["status"] = "EMPTY_OUTPUT"
                        r["trades"] = 0; r["profit_pct"] = 0; r["win_rate"] = 0; r["dd_pct"] = 0
                    else:
                        parsed = parse_summary(out, s)
                        if parsed:
                            r.update(parsed)
                        else:
                            r["trades"] = 0; r["profit_pct"] = 0; r["win_rate"] = 0; r["dd_pct"] = 0
                            if "Could not import" in out:
                                r["status"] = "IMPORT_ERROR"
                                em = re.search(r"due to '(.+?)'", out)
                                r["error"] = em.group(1) if em else "unknown"
                            elif "No data found" in out:
                                r["status"] = "NO_DATA"
                            elif "Error" in out:
                                r["status"] = "ERROR"
                                err_lines = [l.strip() for l in out.split('\n') if 'Error' in l or 'error' in l.lower()]
                                r["error"] = "; ".join(err_lines[:3])
                            elif r["trades"] == 0:
                                r["status"] = "ZERO_TRADES"

                    results[s] = r
                    remaining = len(strategies) - len(results)
                    tr = r.get("trades", 0)
                    pf = r.get("profit_pct", 0)
                    wr = r.get("win_rate", 0)
                    dd = r.get("dd_pct", 0)
                    print(f"  [{remaining} left] DONE: {s:50s} trades={tr:>4}  profit={pf:>+8.2f}%  wr={wr:>5.1f}%  dd={dd:>5.2f}%  {r['status']}  ({elapsed:.0f}s)")

                    # Save incrementally
                    Results_file.write_text(json.dumps(results, indent=2, default=str))

    elapsed_total = time.time() - start_time
    print(f"\n  [{mode_label}] COMPLETE in {elapsed_total/60:.1f} min.  {len(results)} strategies tested.")
    return results


def print_table(results, title):
    ranked = sorted(results.items(), key=lambda x: x[1].get("profit_pct", -999), reverse=True)
    print(f"\n{'='*100}")
    print(f"  RESULTS — {title}")
    print(f"{'='*100}")
    print(f"{'Rank':>4} {'Strategy':50s} {'Trades':>6} {'Profit%':>9} {'WR%':>7} {'DD%':>7} {'Status':>12}")
    print("-"*100)
    for i, (s, r) in enumerate(ranked, 1):
        print(f"{i:>4} {s:50s} {r.get('trades',0):>6} {r.get('profit_pct',0):>+9.2f} "
              f"{r.get('win_rate',0):>7.1f} {r.get('dd_pct',0):>7.2f} {r.get('status','?'):>12}")

    # Stats
    ok = sum(1 for r in results.values() if r.get("trades", 0) > 0)
    pos = sum(1 for r in results.values() if r.get("profit_pct", 0) > 0)
    zero = sum(1 for r in results.values() if r.get("trades", 0) == 0 and r.get("status") not in ("IMPORT_ERROR",))
    errs = sum(1 for r in results.values() if r.get("status") == "IMPORT_ERROR")
    print(f"\n  Summary: {ok} with trades, {pos} profitable, {zero} zero-trades, {errs} import errors")
    return ranked


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    manual = [s for s in MANUAL_STRATEGIES if (STRAT_DIR / f"{s}.py").exists()]
    generated = discover_generated()
    all_strategies = manual + generated
    print(f"Strategies: {len(manual)} manual + {len(generated)} generated = {len(all_strategies)} total")
    print(f"Results directory: {RESULTS_DIR}")

    # ─── SPOT: 8+ years (longs only) ───
    if mode in ("spot", "both"):
        # Patch can_short=False for spot
        print("\nPatching can_short=False for spot mode...")
        bak_files = []
        for s in all_strategies:
            sp = STRAT_DIR / f"{s}.py"
            if not sp.exists():
                sp = GEN_DIR / f"{s}.py"
            if sp.exists():
                bak_files.append(patch_can_short(sp, value=False))

        results_sp = run_batch(all_strategies, "spot_8yr", SPOT_PAIRS, TIMERANGE_SPOT,
                               datadir=SPOT_DATADIR, config=str(BASE / "user_data" / "config_spot.json"))
        print_table(results_sp, f"SPOT 8-year ({TIMERANGE_SPOT})")

        for bak in bak_files:
            restore(bak)
        print("Restored all strategy files.")

    # ─── FUTURES: 6+ years (longs + shorts) ───
    if mode in ("futures", "both"):
        all_futures_strats = manual  # generated may not have futures data
        results_ft = run_batch(all_futures_strats, "futures_6yr", FUTURES_PAIRS, TIMERANGE_FUTURES)
        print_table(results_ft, f"FUTURES 6-year ({TIMERANGE_FUTURES})")

    # ─── Final summary ───
    print(f"\n{'='*80}")
    print(f"  ALL BACKTESTS COMPLETE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Results saved to: {RESULTS_DIR}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
