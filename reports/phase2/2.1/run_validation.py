"""Phase 2.1 re-measurement runner — validation window only, scoreboard-identical flags.

Builds the same command line as scripts/scoreboard.py:build_command() (read-only import at
runtime, never modified), writes the raw freqtrade output to
reports/phase2/2.1/backtest_<label>.log and the parsed metrics to
reports/phase2/2.1/metrics_<label>.json using scoreboard.extract_metrics() so the
BEFORE (SCOREBOARD.md) and AFTER numbers are computed by the same code.

Usage:  .venv/Scripts/python.exe reports/phase2/2.1/run_validation.py <StrategyClass> <label>
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TIMERANGE = "20260101-20260701"          # validation stage, END exclusive (scoreboard 1.4)
FEE = "0.001"                            # 10 bps all-in, scoreboard fee model
CONFIG = "user_data/config_backtest.json"
UNIVERSE = json.loads((REPO / "reports/scoreboard-20261119-1229/UNIVERSE.json").read_text())["resolved"]


def scoreboard_module():
    spec = importlib.util.spec_from_file_location("sb", REPO / "scripts" / "scoreboard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    strategy, label = sys.argv[1], sys.argv[2]
    sb = scoreboard_module()
    export_dir = OUT / "raw" / label
    export_dir.mkdir(parents=True, exist_ok=True)
    cmd = sb.build_command([strategy], TIMERANGE, UNIVERSE, export_dir, CONFIG, "user_data", batch=False)
    started = time.time()
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - started
    log = OUT / f"backtest_{label}.log"
    log.write_text(f"# cmd: {' '.join(cmd)}\n# rc={proc.returncode} elapsed={elapsed:.1f}s\n\n"
                   f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n",
                   encoding="utf-8", errors="replace")
    zip_path = sb._newest_zip(export_dir)
    if zip_path is None:
        print(f"{label}: NO RESULT rc={proc.returncode} — see {log.name}")
        return 1
    payload = sb.parse_result_zip(zip_path).get(strategy, {})
    metrics = sb.extract_metrics(payload)
    (OUT / f"metrics_{label}.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"{label}: trades={metrics['trades']} profit%={metrics['profit_pct']} "
          f"win%={metrics['winrate_pct']} exp%={metrics['expectancy_pct']} "
          f"maxDD%={metrics['max_drawdown_pct']} pf={metrics['profit_factor']} "
          f"sharpe={metrics['sharpe']} long/short={metrics['trades_long']}/{metrics['trades_short']} "
          f"({elapsed:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
