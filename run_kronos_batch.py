#!/usr/bin/env python3
"""
Batch runner for Kronos+ChromaDB enhanced strategies.

Runs all 4 strategies on 8-year spot data.
"""
import subprocess, json, re, time, os, shutil
from pathlib import Path
from datetime import datetime

BASE = Path("/home/roshan/Downloads/Algotrading")
VENV = str(BASE / ".venv" / "bin" / "freqtrade")
CONFIG = str(BASE / "user_data" / "config_spot.json")
STRATEGY_DIR = str(BASE / "user_data" / "strategies")
KRONOS_DIR = str(BASE / "user_data" / "strategies" / "kronos_chromadb")
MAX_CONCURRENT = 2
TIMERANGE = "20180101-20260517"
SPOT_PAIRS = ["BTC/USDT", "ETH/USDT", "LTC/USDT", "NEO/USDT",
              "XRP/USDT", "ADA/USDT", "XLM/USDT", "TRX/USDT", "BCH/USDT"]
SPOT_DATADIR = str(BASE / "user_data" / "data" / "binance" / "spot")

STRATEGIES = ["Kronos_CandlePattern", "Kronos_Filtered", "Kronos_RiskManaged", "Kronos_Full"]

results = {}
running = {}
queue = list(STRATEGIES)

print(f"Running {len(STRATEGIES)} Kronos+ChromaDB strategies on 8y spot...")
print(f"  Timerange: {TIMERANGE}, pairs: {len(SPOT_PAIRS)}, concurrency: {MAX_CONCURRENT}")

while queue or running:
    while len(running) < MAX_CONCURRENT and queue:
        strat = queue.pop(0)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE) + ":" + env.get("PYTHONPATH", "")
        cmd = [VENV, "backtesting", "--strategy-path", KRONOS_DIR,
               "--recursive-strategy-search",
               "--strategy", strat, "--config", CONFIG,
               "--timerange", TIMERANGE, "--cache", "none",
               "-p"] + SPOT_PAIRS + ["--datadir", SPOT_DATADIR]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, env=env, cwd=str(BASE))
        running[strat] = {"proc": proc, "start": time.time()}
        print(f"  STARTED: {strat} (pid {proc.pid}) [{len(results) + len(running)}/{len(STRATEGIES)}]")

    if running:
        time.sleep(5)
        for strat, info in list(running.items()):
            ret = info["proc"].poll()
            if ret is not None:
                output = info["proc"].stdout.read() + info["proc"].stderr.read()
                elapsed = time.time() - info["start"]
                running.pop(strat)

                r = {"status": "DONE", "elapsed": round(elapsed, 1)}
                pattern = (r'│\s*' + re.escape(strat) +
                           r'\s*│\s*(\d+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*([-\d.]+)\s*│\s*(\d+:\d+:\d+)\s*│\s*(\d+)\s+\d+\s+(\d+)\s+([\d.]+)\s*│\s*([-\d.]+)\s*USDT\s+([\d.]+)%')
                m = re.search(pattern, output)
                if m:
                    r["trades"] = int(m.group(1))
                    r["profit_pct"] = float(m.group(4))
                    r["win_rate"] = float(m.group(8))
                    r["dd_pct"] = float(m.group(10))
                else:
                    r["trades"] = 0; r["profit_pct"] = 0.0; r["win_rate"] = 0.0; r["dd_pct"] = 0.0
                if "Could not import" in output:
                    r["status"] = "IMPORT_ERROR"
                elif r["trades"] == 0:
                    r["status"] = "ZERO_TRADES"

                results[strat] = r
                arrow = "+" if r.get("profit_pct", 0) >= 0 else " "
                print(f"  DONE: {strat:30s} | {r.get('trades',0):>5} tr  profit={arrow}{r.get('profit_pct',0):>+8.2f}%  "
                      f"wr={r.get('win_rate',0):>5.1f}%  dd={r.get('dd_pct',0):>5.2f}%  ({elapsed:.0f}s)")

# Print ranked results
ranked = sorted(results.items(), key=lambda x: x[1].get("profit_pct", 0), reverse=True)
print(f"\n{'=' * 90}")
print(f"  KRONOS+CHROMADB RESULTS (compared to P3E_KEY_LEVEL_BOOST baseline: +178.91%)")
print(f"{'=' * 90}")
print(f"{'Rank':>4} {'Strategy':30s} {'Trades':>6} {'Profit%':>9} {'WR%':>6} {'DD%':>6} {'Status':15s}")
print("-" * 90)
for i, (s, r) in enumerate(ranked, 1):
    arrow = "+" if r.get("profit_pct", 0) >= 0 else " "
    print(f"{i:>4} {s:30s} {r.get('trades',0):>6} {arrow}{r.get('profit_pct',0):>+8.2f} "
          f"{r.get('win_rate',0):>6.1f} {r.get('dd_pct',0):>6.2f} {r.get('status','?'):15s}")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
outfile = BASE / f"kronos_results_{ts}.json"
with open(outfile, "w") as f:
    json.dump({"kronos_chromadb_8y_spot": results}, f, indent=2, default=str)
print(f"\nResults saved to {outfile}")
