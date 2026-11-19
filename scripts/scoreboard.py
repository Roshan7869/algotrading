#!/usr/bin/env python
"""Phase 1.4 scoreboard — reproducible, sealed-holdout strategy scoreboard.

WHY THIS FILE EXISTS
--------------------
Every number this project stored before 2026-11 came without a reproducibility header, and the
best-looking one (+3,632,254 %) belonged to a strategy that was reading future candles.  This
script produces the opposite kind of artifact: a scoreboard whose every metric can be re-derived
from (git SHA, data manifest, config path, fee model), whose train/validation/holdout split is
frozen in code, and whose holdout is written to a separate file that selection never reads.

THE THREE-WAY SPLIT (selection-leakage rationale)
-------------------------------------------------
* train      : data start -> 2025-12-31   -- in-sample history, used to *build* nothing here;
                                            it is reported so drift between periods is visible.
* validation : 2026-01-01 -> 2026-06-30   -- THE ONLY WINDOW SELECTION MAY USE.  Phase 2.1 picks
                                            the top-2 candidates by validation expectancy.
* holdout    : 2026-07-01 -> run date      -- never used for selection.  Written ONLY to
                                            HOLDOUT_SEALED.json; no selection file (results.json,
                                            SCOREBOARD.md, UNIVERSE.json, MANIFEST.json) may carry
                                            holdout metrics.  Opening it requires --open-holdout,
                                            and Phase 2.4 opens it exactly once.

Why a three-way split and not train/test: with a two-way split the window used to choose the
strategy is the same window used to judge it, so the reported number is a maximum over candidates,
not an estimate of future performance.  A sealed third window that nobody has looked at is the only
cheap defence — it costs one more backtest batch and it cannot be un-seen once opened.

BOUNDARY CONVENTION
-------------------
freqtrade's ``--timerange START-END`` treats END as EXCLUSIVE.  The constants below therefore hold
*inclusive* human boundaries for documentation and the equivalent exclusive freqtrade timerange for
execution, so "train ends 2025-12-31" means the last candle used is 2025-12-31 23:00 UTC.

COST MODEL
----------
freqtrade's backtester has no native slippage parameter, so the honest proxy is to fold a slippage
estimate into the fee it does model: ``--fee 0.001`` (10 bps) is charged on entry AND exit, i.e.
10 bps per side-equivalent covering exchange taker fee plus a slippage allowance.  This string is
emitted verbatim in every output: ``fee_model: 10bps all-in (fee + slippage proxy)``.

Usage
-----
  python scripts/scoreboard.py --stage all                       # full 8 x 20 x 3 matrix
  python scripts/scoreboard.py --stage train --limit 2 \
      --strategies EmaTrendFollowing --timerange 20251001-20251120
  python scripts/scoreboard.py --stage holdout --open-holdout    # Phase 2.4 only
  python scripts/scoreboard.py --verify reports/scoreboard-A reports/scoreboard-B
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------------------------------
# CONSTANTS — the parts that must never be inferred at runtime
# --------------------------------------------------------------------------------------------------

#: Emitted verbatim in MANIFEST.json / results.json / SCOREBOARD.md / HOLDOUT_SEALED.json.
FEE_MODEL = "fee_model: 10bps all-in (fee + slippage proxy)"
#: --fee value handed to freqtrade.  Charged on entry and exit => 10 bps per side-equivalent.
FEE_RATIO = 0.001

CONFIG_BACKTEST = "user_data/config_backtest.json"
DATA_SUBDIR = "user_data/data/binance/futures"
TIMEFRAME = "1h"

#: Canonical 20-pair futures universe (Phase 1.4).  The SAME list drives Phase 2's dry-run config,
#: so it is a single constant here and is emitted to UNIVERSE.json in every output directory.
CANONICAL_UNIVERSE_BASES: tuple[str, ...] = (
    "BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX", "LINK", "DOT",
    "LTC", "TRX", "ATOM", "NEAR", "APT", "ARB", "OP", "SUI", "INJ", "SEI",
)
QUOTE = "USDT"
CONTRACT_SUFFIX = ":USDT"  # binance futures pair format: BTC/USDT:USDT

#: Substitution order when a canonical pair has no usable futures 1h file.  Frozen list (not
#: "whatever is on disk") so a rerun on a refreshed data dir substitutes the same way.  Pairs
#: appearing later in the canonical list are never re-used as substitutes.
SUBSTITUTE_ORDER: tuple[str, ...] = (
    "BCH", "FIL", "HBAR", "TON", "ENA", "ONDO", "WLD", "XLM", "VET", "ALGO",
    "ZEC", "XMR", "AAVE", "KAS", "HYPE", "FARTCOIN", "RENDER", "STORJ", "BIO", "EDEN",
)

#: Minimum candles (1h) a pair must have inside a stage window to be counted as covered.
MIN_STAGE_CANDLES = 100
#: Minimum rows in the file for the pair to be considered available at all (~3 weeks of 1h).
MIN_PAIR_ROWS = 500

#: Stage boundaries.  ``*_incl`` is documentation; ``timerange`` is what freqtrade receives
#: (END exclusive).  See module docstring for the leakage rationale.
TRAIN_START = "20250101"          # data-start floor; per-pair real start recorded in the manifest
TRAIN_END_INCL = "20251231"
TRAIN_END_EXCL = "20260101"

VALIDATION_START = "20260101"
VALIDATION_END_INCL = "20260630"
VALIDATION_END_EXCL = "20260701"

HOLDOUT_START = "20260701"        # holdout end = run date (resolved per run, never hard-coded)
HOLDOUT_END_MODE = "run_date"

STAGE_ORDER: tuple[str, ...] = ("train", "validation", "holdout")
SELECTION_STAGES: tuple[str, ...] = ("train", "validation")  # never includes holdout

#: Strategy classes actually loaded by freqtrade.  NOTE: the file ensemble_strategy.py defines
#: class EnsembleStrategy — the class name, not the filename, is what --strategy accepts.
DEFAULT_STRATEGIES: tuple[str, ...] = (
    "AroonMomentumEngine_Hybrid",
    "AroonMomentumEngine_V2",
    "BollingerMeanReversion",
    "DmiAdxStrategy",
    "EmaTrendFollowing",
    "EnsembleStrategy",
    "MacdRsiStrategy",
    "SupertrendEmaStrategy",
)

METRIC_ROUND_DP = 6          # stored precision
VERIFY_ROUND_DP = 4          # contract: re-runs must match at 4 decimal places


# --------------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------------

def _f(value: Any, nd: int = METRIC_ROUND_DP) -> float | None:
    """Float-or-None with fixed rounding (keeps JSON deterministic and NaN-free)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return round(out, nd)


def _pct(value: Any, nd: int = METRIC_ROUND_DP) -> float | None:
    v = _f(value, nd + 2)
    return None if v is None else round(v * 100.0, nd)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    try:
        return dt.isoformat()
    except AttributeError:
        return str(dt)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str | None:
    """Content hash of the canonical config — a path alone cannot prove which config ran."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return "sha256:" + h.hexdigest()
    except OSError:
        return None


def git_sha() -> str:
    """Read-only git call (the only git command this script is allowed to run)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # pragma: no cover - git absent / not a repo
        pass
    return "unknown"


def freqtrade_exe() -> str:
    candidates = [
        REPO_ROOT / ".venv" / "Scripts" / "freqtrade.exe",
        REPO_ROOT / ".venv" / "bin" / "freqtrade",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    found = shutil.which("freqtrade")
    if found:
        return found
    return f"{sys.executable} -m freqtrade"


def freqtrade_version(exe: str) -> str:
    try:
        cmd = exe.split() + ["--version"]
        out = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
        for line in out.stdout.splitlines():
            if "Freqtrade Version" in line:
                return line.split(":", 1)[1].strip()
    except Exception:  # pragma: no cover
        pass
    return "unknown"


# --------------------------------------------------------------------------------------------------
# Stage / universe resolution
# --------------------------------------------------------------------------------------------------

def stage_bounds(run_date: datetime) -> dict[str, dict[str, Any]]:
    """Return per-stage boundaries, both human-inclusive and the exclusive freqtrade timerange."""
    holdout_end_excl = (run_date + timedelta(days=1)).strftime("%Y%m%d")
    return {
        "train": {
            "start": TRAIN_START,
            "end_inclusive": TRAIN_END_INCL,
            "timerange": f"{TRAIN_START}-{TRAIN_END_EXCL}",
            "note": "in-sample history; data start per pair is recorded in data_manifest",
        },
        "validation": {
            "start": VALIDATION_START,
            "end_inclusive": VALIDATION_END_INCL,
            "timerange": f"{VALIDATION_START}-{VALIDATION_END_EXCL}",
            "note": "SELECTION WINDOW — Phase 2.1 ranks candidates on this stage only",
        },
        "holdout": {
            "start": HOLDOUT_START,
            "end_inclusive": HOLDOUT_END_MODE,
            "timerange": f"{HOLDOUT_START}-{holdout_end_excl}",
            "note": "SEALED — metrics go only to HOLDOUT_SEALED.json until --open-holdout",
        },
    }


def pair_from_base(base: str) -> str:
    return f"{base}/{QUOTE}{CONTRACT_SUFFIX}"


def data_file_for_base(data_dir: Path, base: str) -> Path:
    return data_dir / f"{base}_{QUOTE}_{QUOTE}-{TIMEFRAME}-futures.feather"


def _feather_dates(path: Path):
    """Return (n_rows, first_ts, last_ts, pandas Series of dates) or None if unreadable."""
    import pyarrow.feather as feather

    try:
        table = feather.read_table(path, columns=["date"])
    except Exception:
        return None
    if table.num_rows == 0:
        return None
    series = table.column("date").to_pandas()
    return table.num_rows, _iso(series.iloc[0]), _iso(series.iloc[-1]), series


def resolve_universe(data_dir: Path) -> dict[str, Any]:
    """Check each canonical pair against the futures 1h files; substitute missing ones in order."""
    availability: dict[str, Any] = {}
    resolved: list[str] = []
    substitutions: list[dict[str, str]] = []
    used_bases: set[str] = set()

    for base in CANONICAL_UNIVERSE_BASES:
        path = data_file_for_base(data_dir, base)
        info = {"file": path.name, "exists": path.exists(), "rows": None, "first": None, "last": None}
        ok = False
        if path.exists():
            meta = _feather_dates(path)
            if meta is not None:
                rows, first, last, _ = meta
                info.update(rows=rows, first=first, last=last)
                ok = rows >= MIN_PAIR_ROWS
        info["usable"] = ok
        availability[base] = info
        if ok:
            resolved.append(pair_from_base(base))
            used_bases.add(base)
        else:
            substitutions.append({"requested": pair_from_base(base), "reason": "no usable futures 1h file"})

    # Fill substitutions from the frozen pool (canonical bases are never used twice).
    pending = [s for s in substitutions]
    for sub in pending:
        replacement = None
        for cand in SUBSTITUTE_ORDER:
            if cand in used_bases:
                continue
            path = data_file_for_base(data_dir, cand)
            if not path.exists():
                continue
            meta = _feather_dates(path)
            if meta is None or meta[0] < MIN_PAIR_ROWS:
                continue
            replacement = (cand, meta)
            break
        if replacement is None:
            continue
        cand, (rows, first, last, _) = replacement
        used_bases.add(cand)
        availability[cand] = {
            "file": data_file_for_base(data_dir, cand).name,
            "exists": True, "rows": rows, "first": first, "last": last, "usable": True,
        }
        sub["used"] = pair_from_base(cand)
        sub["rows"] = rows
        sub["first_candle"] = first
        sub["last_candle"] = last
        resolved.append(pair_from_base(cand))

    return {
        "requested": [pair_from_base(b) for b in CANONICAL_UNIVERSE_BASES],
        "resolved": resolved,
        "substitutions": [s for s in substitutions if "used" in s],
        "unresolved": [s["requested"] for s in substitutions if "used" not in s],
        "availability": availability,
    }


# --------------------------------------------------------------------------------------------------
# Data manifest
# --------------------------------------------------------------------------------------------------

def build_data_manifest(data_dir: Path, universe: dict[str, Any],
                        bounds: dict[str, dict[str, Any]], run_date: datetime) -> dict[str, Any]:
    """Per-pair row counts + candle coverage, total and per stage window.

    ``rows_total`` / ``last_candle`` describe the file on disk; the per-stage coverage is what the
    backtests actually consume and is what the manifest hash is computed over (a data download that
    only appends future candles must not invalidate a past-window run).
    """
    import pandas as pd

    pairs: dict[str, Any] = {}
    for pair in universe["resolved"]:
        base = pair.split("/")[0]
        path = data_file_for_base(data_dir, base)
        meta = _feather_dates(path)
        if meta is None:
            pairs[pair] = {"file": path.name, "readable": False}
            continue
        rows, first, last, series = meta
        per_stage: dict[str, Any] = {}
        for stage in STAGE_ORDER:
            b = bounds[stage]
            start = pd.Timestamp(datetime.strptime(b["start"], "%Y%m%d").replace(tzinfo=timezone.utc))
            end_excl = b["timerange"].split("-")[1]
            end = pd.Timestamp(datetime.strptime(end_excl, "%Y%m%d").replace(tzinfo=timezone.utc))
            mask = (series >= start) & (series < end)
            window = series[mask]
            per_stage[stage] = {
                "rows": int(window.shape[0]),
                "first_candle": _iso(window.iloc[0]) if len(window) else None,
                "last_candle": _iso(window.iloc[-1]) if len(window) else None,
                "covered": bool(window.shape[0] >= MIN_STAGE_CANDLES),
            }
        pairs[pair] = {
            "file": path.name,
            "readable": True,
            "rows_total": int(rows),
            "first_candle": first,
            "last_candle": last,
            "stages": per_stage,
        }

    totals: dict[str, Any] = {}
    for stage in STAGE_ORDER:
        covered = [p for p, d in pairs.items() if d.get("stages", {}).get(stage, {}).get("covered")]
        totals[stage] = {
            "pairs_covered": len(covered),
            "pairs_total": len(pairs),
            "rows": sum(d.get("stages", {}).get(stage, {}).get("rows", 0) for d in pairs.values()),
            "sufficient_data": len(covered) > 0,
        }
    return {"pairs": pairs, "totals": totals,
            "min_stage_candles": MIN_STAGE_CANDLES, "min_pair_rows": MIN_PAIR_ROWS}


# --------------------------------------------------------------------------------------------------
# Running freqtrade
# --------------------------------------------------------------------------------------------------

def build_command(strategies: list[str], timerange: str, pairs: list[str], export_dir: Path,
                  config: str, userdir: str, batch: bool = False) -> list[str]:
    """Flags verified against `freqtrade backtesting --help` on the installed version.

    In this version --export-filename is deprecated for backtesting; results are directed with
    --backtest-directory instead (the archive is named after that directory).

    With ``batch`` all strategies run in ONE process via --strategy-list (each still gets a fresh
    wallet); that saves ~8 s of interpreter/import startup per strategy on the full matrix.
    """
    cmd = freqtrade_exe().split()
    cmd += [
        "backtesting",
        *(["--strategy-list", *strategies] if batch else ["--strategy", strategies[0]]),
        "-c", config,
        "--userdir", userdir,
        "--timerange", timerange,
        "--fee", str(FEE_RATIO),
        "--cache", "none",
        "--export", "trades",
        "--backtest-directory", export_dir.as_posix(),
        "--timeframe", TIMEFRAME,
        "-p", *pairs,
    ]
    return cmd


def _newest_zip(directory: Path) -> Path | None:
    zips = sorted(directory.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-1] if zips else None


def parse_result_zip(path: Path) -> dict[str, Any]:
    """Return {strategy_name: payload} from a freqtrade backtest archive."""
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist()
                 if n.endswith(".json") and "_config" not in n and "_market_change" not in n]
        if not names:
            return {}
        payload = json.loads(zf.read(names[0]))
    return payload.get("strategy", {}) or {}


def run_backtest(label: str, strategies: list[str], timerange: str, pairs: list[str],
                 out_dir: Path, args: argparse.Namespace, batch: bool = False) -> dict[str, Any]:
    """Run one backtest process; returns {strategy: payload} plus bookkeeping."""
    export_dir = out_dir / "raw" / label
    export_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_command(strategies, timerange, pairs, export_dir, args.config, args.userdir, batch)
    started = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=args.max_run_seconds,
        )
        rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        rc = -1
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = f"TIMEOUT after {args.max_run_seconds}s"
    elapsed = time.time() - started

    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{label}.log"
    log_path.write_text(
        f"# cmd: {' '.join(cmd)}\n# rc={rc} elapsed={elapsed:.1f}s\n\n"
        f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n",
        encoding="utf-8", errors="replace",
    )

    results: dict[str, Any] = {}
    zip_path = _newest_zip(export_dir)
    if zip_path is not None:
        try:
            results = parse_result_zip(zip_path)
        except Exception as exc:  # pragma: no cover - corrupt archive
            stderr += f"\nPARSE_ERROR: {exc}"

    return {
        "results": results,
        "returncode": rc,
        "elapsed_s": round(elapsed, 2),
        "timed_out": timed_out,
        "log": f"logs/{label}.log",
        "stderr_tail": (stderr or "").strip().splitlines()[-6:],
        "command": " ".join(cmd),
    }


# --------------------------------------------------------------------------------------------------
# Metric extraction
# --------------------------------------------------------------------------------------------------

def extract_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    per_pair = []
    for row in payload.get("results_per_pair") or []:
        if str(row.get("key") or "").upper() == "TOTAL":
            continue  # freqtrade appends an aggregate row; only real pairs belong here
        per_pair.append({
            "pair": row.get("key"),
            "trades": int(row.get("trades") or 0),
            "profit_abs": _f(row.get("profit_total_abs")),
            "profit_pct": _pct(row.get("profit_total")),
            "winrate_pct": _pct(row.get("winrate")),
            "expectancy_abs": _f(row.get("expectancy")),
            "expectancy_pct": _pct(row.get("profit_mean")),
            "max_drawdown_pct": _pct(row.get("max_drawdown_account")),
            "profit_factor": _f(row.get("profit_factor")),
            "sharpe": _f(row.get("sharpe")),
        })
    per_pair.sort(key=lambda r: (r["pair"] or ""))
    pairs_traded = sum(1 for r in per_pair if r["trades"] > 0)

    return {
        "trades": int(payload.get("total_trades") or 0),
        "trades_long": payload.get("trade_count_long"),
        "trades_short": payload.get("trade_count_short"),
        "profit_abs": _f(payload.get("profit_total_abs")),
        "profit_pct": _pct(payload.get("profit_total")),
        "winrate_pct": _pct(payload.get("winrate")),
        "expectancy_abs": _f(payload.get("expectancy")),
        "expectancy_pct": _pct(payload.get("profit_mean")),
        "max_drawdown_pct": _pct(payload.get("max_drawdown_account")),
        "max_drawdown_abs": _f(payload.get("max_drawdown_abs")),
        "sharpe": _f(payload.get("sharpe")),
        "sortino": _f(payload.get("sortino")),
        "calmar": _f(payload.get("calmar")),
        "profit_factor": _f(payload.get("profit_factor")),
        "cagr_pct": _pct(payload.get("cagr")),
        "trades_per_day": _f(payload.get("trades_per_day")),
        "avg_duration_s": _f(payload.get("holding_avg_s")),
        "starting_balance": _f(payload.get("starting_balance"), 2),
        "final_balance": _f(payload.get("final_balance"), 2),
        "max_open_trades": payload.get("max_open_trades"),
        "stake_amount": payload.get("stake_amount"),
        "backtest_start": payload.get("backtest_start"),
        "backtest_end": payload.get("backtest_end"),
        "timerange": payload.get("timerange"),
        "timeframe": payload.get("timeframe"),
        "pairs_in_report": len(per_pair),
        "pairs_traded": pairs_traded,
        "per_pair": per_pair,
    }


#: Shape of a metrics block when no backtest result exists — keeps every consumer's key access
#: valid (a missing key would crash SCOREBOARD.md rendering instead of reporting the gap).
EMPTY_METRICS: dict[str, Any] = {
    "trades": 0,
    "trades_long": None,
    "trades_short": None,
    "profit_abs": None,
    "profit_pct": None,
    "winrate_pct": None,
    "expectancy_abs": None,
    "expectancy_pct": None,
    "max_drawdown_pct": None,
    "max_drawdown_abs": None,
    "sharpe": None,
    "sortino": None,
    "calmar": None,
    "profit_factor": None,
    "cagr_pct": None,
    "trades_per_day": None,
    "avg_duration_s": None,
    "starting_balance": None,
    "final_balance": None,
    "max_open_trades": None,
    "stake_amount": None,
    "backtest_start": None,
    "backtest_end": None,
    "timerange": None,
    "timeframe": None,
    "pairs_in_report": 0,
    "pairs_traded": 0,
    "per_pair": [],
}


# --------------------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------------------

def run_stage(stage: str, strategies: list[str], pairs: list[str], bounds: dict[str, Any],
              out_dir: Path, args: argparse.Namespace, data_totals: dict[str, Any]) -> dict[str, Any]:
    timerange = args.timerange or bounds[stage]["timerange"]
    coverage = data_totals[stage]
    entries: dict[str, Any] = {}

    if not coverage["sufficient_data"]:
        for strat in strategies:
            entries[strat] = {
                "strategy": strat, "stage": stage, "status": "insufficient_data",
                "timerange": timerange,
                "note": (f"no pair has >= {MIN_STAGE_CANDLES} candles in this window; "
                         f"backtest skipped (data refresh pending)"),
                "metrics": copy.deepcopy(EMPTY_METRICS),
            }
        return {"entries": entries, "runs": []}

    print(f"[scoreboard] stage={stage} timerange={timerange} pairs={len(pairs)} "
          f"strategies={len(strategies)} covered_pairs={coverage['pairs_covered']}", flush=True)

    payloads: dict[str, Any] = {}
    runs: list[dict[str, Any]] = []
    use_batch = len(strategies) > 1 and not getattr(args, "no_batch", False) \
        and not getattr(args, "batch_disabled", False)
    if use_batch:
        label = f"{stage}__batch"
        run = run_backtest(label, strategies, timerange, pairs, out_dir, args, batch=True)
        runs.append({"label": label, **{k: run[k] for k in ("returncode", "elapsed_s", "timed_out", "command")}})
        payloads.update(run["results"])
        if run["returncode"] != 0 and not payloads:
            # One crashing strategy kills the whole batch (e.g. EnsembleStrategy raises inside
            # populate_entry_trend at this HEAD).  Remember it so the remaining stages do not
            # pay the failed-batch cost again.
            args.batch_disabled = True
            print(f"[scoreboard] batch run failed (rc={run['returncode']}); "
                  f"falling back to per-strategy runs for the rest of this invocation", flush=True)

    missing = [s for s in strategies if s not in payloads]
    for strat in missing:
        label = f"{stage}__{strat}"
        run = run_backtest(label, [strat], timerange, pairs, out_dir, args, batch=False)
        runs.append({"label": label, **{k: run[k] for k in ("returncode", "elapsed_s", "timed_out", "command")}})
        payloads.update(run["results"])
        if strat not in payloads:
            print(f"[scoreboard] {strat} @ {stage}: no result (rc={run['returncode']}) "
                  f"{run['stderr_tail']}", flush=True)

    for strat in strategies:
        payload = payloads.get(strat)
        if payload is None:
            entries[strat] = {
                "strategy": strat, "stage": stage, "status": "no_result",
                "timerange": timerange,
                "note": "freqtrade produced no result for this strategy (see logs/)",
                "metrics": copy.deepcopy(EMPTY_METRICS),
            }
            continue
        entries[strat] = {
            "strategy": strat, "stage": stage,
            "status": "ok" if int(payload.get("total_trades") or 0) > 0 else "no_trades",
            "timerange": timerange,
            "metrics": extract_metrics(payload),
        }
    return {"entries": entries, "runs": runs}


# --------------------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------------------

def _fmt(value: Any, nd: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{nd}f}"
    except (TypeError, ValueError):
        return str(value)


def render_scoreboard(manifest: dict[str, Any], results: dict[str, Any],
                      holdout_sealed: dict[str, Any] | None, open_holdout: bool) -> str:
    lines: list[str] = []
    lines.append("# Phase 1.4 — strategy scoreboard")
    lines.append("")
    lines.append("## Reproducibility header")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| git SHA | `{manifest['git_sha']}` |")
    lines.append(f"| generated (UTC) | {manifest['generated_at_utc']} |")
    lines.append(f"| freqtrade | {manifest['freqtrade_version']} |")
    cfg_sha = manifest.get("config_sha256") or "n/a"
    lines.append(f"| config | `{manifest['config_path']}` |")
    lines.append(f"| config sha256 | `{cfg_sha}` |")
    lines.append(f"| **{FEE_MODEL.split(':')[0]}** | **{FEE_MODEL.split(':', 1)[1].strip()}** |")
    lines.append(f"| timeframe | {TIMEFRAME} |")
    lines.append(f"| manifest hash | `{manifest['manifest_hash']}` |")
    lines.append(f"| strategies | {len(manifest['strategies'])} |")
    lines.append(f"| universe | {len(manifest['universe'])} pairs |")
    lines.append("")
    lines.append("Cost model detail: `--fee 0.001` is charged on entry **and** exit, i.e. 10 bps per")
    lines.append("side-equivalent covering exchange fee plus a slippage proxy (the backtester has no")
    lines.append("native slippage model, so this is the honest proxy).")
    lines.append("")
    lines.append("## Stage boundaries")
    lines.append("")
    lines.append("| Stage | Window (inclusive) | freqtrade timerange | Role |")
    lines.append("|---|---|---|---|")
    for stage in STAGE_ORDER:
        b = manifest["stage_bounds"][stage]
        role = {"train": "in-sample history", "validation": "**SELECTION**",
                "holdout": "SEALED (Phase 2.4)"}[stage]
        lines.append(f"| {stage} | {b['start']} → {b['end']} | `{b['timerange']}` | {role} |")
    lines.append("")
    lines.append("## Universe")
    lines.append("")
    lines.append("Canonical 20-pair futures universe; same list drives Phase 2's dry-run config.")
    lines.append("")
    lines.append("`" + "`, `".join(manifest["universe"]) + "`")
    lines.append("")
    subs = manifest["substitutions"]
    if subs:
        lines.append("**Substitutions** (canonical pair had no usable futures 1h file):")
        lines.append("")
        lines.append("| requested | used | reason |")
        lines.append("|---|---|---|")
        for s in subs:
            lines.append(f"| {s['requested']} | {s['used']} | {s['reason']} |")
        lines.append("")
    if manifest["universe_unresolved"]:
        lines.append("**Unresolved (no substitute available)**: "
                     + ", ".join(manifest["universe_unresolved"]))
        lines.append("")
    lines.append("### Data coverage per stage")
    lines.append("")
    lines.append("| Pair | file rows | train | validation | holdout |")
    lines.append("|---|---|---|---|---|")
    for pair, d in manifest["data_manifest"]["pairs"].items():
        st = d.get("stages", {})
        cells = []
        for stage in STAGE_ORDER:
            info = st.get(stage, {})
            mark = "" if info.get("covered") else " *(insufficient)*"
            cells.append(f"{info.get('rows', 0)}{mark}")
        lines.append(f"| {pair} | {d.get('rows_total', 0)} | " + " | ".join(cells) + " |")
    lines.append("")

    for stage in SELECTION_STAGES:
        stage_results = [r for r in results["results"] if r["stage"] == stage]
        lines.append(f"## {stage}")
        lines.append("")
        if not stage_results:
            lines.append("_not run_")
            lines.append("")
            continue
        lines.append("| Strategy | Trades | Profit % | Profit USDT | Win % | Exp/trade USDT | "
                     "Exp/trade % | MaxDD % | Sharpe | PF | Status |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in sorted(stage_results, key=lambda x: x["strategy"]):
            m = r["metrics"]
            lines.append(
                f"| {r['strategy']} | {m['trades']} | {_fmt(m['profit_pct'])} | "
                f"{_fmt(m['profit_abs'])} | {_fmt(m['winrate_pct'], 1)} | "
                f"{_fmt(m['expectancy_abs'])} | {_fmt(m['expectancy_pct'], 3)} | "
                f"{_fmt(m['max_drawdown_pct'])} | {_fmt(m['sharpe'])} | "
                f"{_fmt(m['profit_factor'])} | {r['status']} |"
            )
        lines.append("")
        lines.append("Per-pair breakdown: see `results.json` (`per_pair` on each entry).")
        lines.append("")

    lines.append("## holdout — SEALED")
    lines.append("")
    if open_holdout and holdout_sealed and holdout_sealed.get("results"):
        lines.append("> **Holdout opened with `--open-holdout`.** Phase 2.4 opens this exactly once.")
        lines.append("")
        lines.append("| Strategy | Trades | Profit % | Profit USDT | Win % | Exp/trade USDT | "
                     "Exp/trade % | MaxDD % | Sharpe | PF | Status |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in sorted(holdout_sealed["results"], key=lambda x: x["strategy"]):
            m = r["metrics"]
            lines.append(
                f"| {r['strategy']} | {m['trades']} | {_fmt(m['profit_pct'])} | "
                f"{_fmt(m['profit_abs'])} | {_fmt(m['winrate_pct'], 1)} | "
                f"{_fmt(m['expectancy_abs'])} | {_fmt(m['expectancy_pct'], 3)} | "
                f"{_fmt(m['max_drawdown_pct'])} | {_fmt(m['sharpe'])} | "
                f"{_fmt(m['profit_factor'])} | {r['status']} |"
            )
    else:
        lines.append("Holdout metrics are **not** in this file and not in `results.json`; they live")
        lines.append("only in `HOLDOUT_SEALED.json`. Opening requires `--open-holdout` (Phase 2.4).")
        if holdout_sealed:
            lines.append("")
            lines.append(f"Sealed file: `HOLDOUT_SEALED.json` — {len(holdout_sealed.get('results', []))} "
                         f"strategy rows, hash of scope `{holdout_sealed.get('seal', {}).get('sealed_hash', 'n/a')}`.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Ranking for Phase 2.1 uses **validation** expectancy only; train is reported for drift.")
    lines.append("- A pair whose window has fewer than "
                 f"{manifest['data_manifest']['min_stage_candles']} candles is reported as insufficient.")
    lines.append("- Reproduce: `python scripts/scoreboard.py --stage all`; compare with "
                 "`--verify <dir1> <dir2>` (4 dp).")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------------------------------

def build_manifest(args, out_dir: Path, universe: dict[str, Any], data_manifest: dict[str, Any],
                   bounds: dict[str, dict[str, Any]], strategies: list[str],
                   run_date: datetime, stages_run: list[str] | None = None) -> dict[str, Any]:
    sha = git_sha()
    exe = freqtrade_exe()
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": run_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "output_dir": out_dir.name,
        "git_sha": sha,
        "git_sha_short": sha[:9] if sha != "unknown" else "unknown",
        "freqtrade_version": freqtrade_version(exe),
        "python_version": sys.version.split()[0],
        "config_path": args.config,
        "config_sha256": file_sha256(REPO_ROOT / args.config),
        "userdir": args.userdir,
        "fee_model": FEE_MODEL,
        "fee_ratio": FEE_RATIO,
        "fee_note": "--fee is charged on entry and exit; 10 bps all-in per side-equivalent "
                    "(exchange fee + slippage proxy, no native slippage in the backtester)",
        "timeframe": TIMEFRAME,
        "strategies": strategies,
        "stages_run": stages_run or list(STAGE_ORDER),
        "selection_stage": "validation",
        "universe": universe["resolved"],
        "universe_requested": universe["requested"],
        "universe_unresolved": universe["unresolved"],
        "substitutions": universe["substitutions"],
        "stage_bounds": {s: {"start": bounds[s]["start"],
                             # holdout end is the run date: kept symbolic so a daily rerun of an
                             # unchanged window does not churn the hash by itself.
                             "end": HOLDOUT_END_MODE if s == "holdout" else bounds[s]["end_inclusive"],
                             "timerange": (f"{bounds[s]['start']}-{'RUN_DATE'}"
                                           if s == "holdout" else bounds[s]["timerange"])}
                        for s in STAGE_ORDER},
        "smoke": {
            "limit": args.limit,
            "timerange_override": args.timerange,
            "pairs": args.pairs,
        },
        "data_manifest": data_manifest,
        "manifest_hash_scope": (
            "sha256 over: schema_version, git_sha, freqtrade_version, config_path, config_sha256, fee_model, "
            "fee_ratio, timeframe, strategies, stages_run, universe, substitutions, stage "
            "boundaries, and the per-stage candle coverage per pair for the stages actually run. "
            "EXCLUDED: timestamps, output paths, full-file row counts/last-candle (a data refresh "
            "that only appends candles outside the scored windows must not change the hash)."
        ),
    }
    manifest["manifest_hash"] = manifest_hash(manifest)
    return manifest


def manifest_hash(manifest: dict[str, Any]) -> str:
    data = manifest["data_manifest"]["pairs"]
    # Only the windows this run actually scored: a train-only smoke must not churn its hash
    # because a parallel data refresh is still appending 2026 candles.
    stages_hashed = manifest.get("stages_run") or list(STAGE_ORDER)
    coverage = {
        pair: {stage: {"rows": info.get("stages", {}).get(stage, {}).get("rows"),
                       "first": info.get("stages", {}).get(stage, {}).get("first_candle"),
                       "last": info.get("stages", {}).get(stage, {}).get("last_candle")}
               for stage in stages_hashed}
        for pair, info in data.items()
    }
    payload = {
        "schema_version": manifest["schema_version"],
        "git_sha": manifest["git_sha"],
        "freqtrade_version": manifest["freqtrade_version"],
        "config_path": manifest["config_path"],
        "config_sha256": manifest.get("config_sha256"),
        "fee_model": manifest["fee_model"],
        "fee_ratio": manifest["fee_ratio"],
        "timeframe": manifest["timeframe"],
        "strategies": manifest["strategies"],
        "stages_run": manifest.get("stages_run"),
        "universe": manifest["universe"],
        "substitutions": [{k: s.get(k) for k in ("requested", "used", "reason")}
                          for s in manifest["substitutions"]],
        "stage_bounds": manifest["stage_bounds"],
        "smoke": manifest["smoke"],
        "coverage": coverage,
    }
    return sha256_of(payload)


# --------------------------------------------------------------------------------------------------
# Verify
# --------------------------------------------------------------------------------------------------

def _walk_numbers(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_walk_numbers(v, f"{prefix}/{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_walk_numbers(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def verify_dirs(dir_a: Path, dir_b: Path) -> int:
    ok = True
    print(f"verify: {dir_a} vs {dir_b}")

    def load(p: Path) -> dict:
        f = p / "results.json"
        if not f.exists():
            raise SystemExit(f"FAIL: missing {f}")
        return json.loads(f.read_text(encoding="utf-8"))

    a, b = load(dir_a), load(dir_b)

    ma = json.loads((dir_a / "MANIFEST.json").read_text(encoding="utf-8"))
    mb = json.loads((dir_b / "MANIFEST.json").read_text(encoding="utf-8"))
    if ma.get("manifest_hash") == mb.get("manifest_hash"):
        print(f"  manifest_hash: MATCH ({ma.get('manifest_hash')})")
    else:
        ok = False
        print(f"  manifest_hash: MISMATCH\n    A={ma.get('manifest_hash')}\n    B={mb.get('manifest_hash')}")
        for key in ("git_sha", "fee_model", "fee_ratio", "config_path", "config_sha256",
                    "strategies",
                    "universe", "substitutions", "stage_bounds", "smoke"):
            if canonical_json(ma.get(key)) != canonical_json(mb.get(key)):
                print(f"    differing manifest field: {key}")

    na, nb = _walk_numbers(a), _walk_numbers(b)
    diffs = []
    for key in sorted(set(na) | set(nb)):
        va, vb = na.get(key), nb.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) \
                and not isinstance(va, bool) and not isinstance(vb, bool):
            if round(float(va), VERIFY_ROUND_DP) != round(float(vb), VERIFY_ROUND_DP):
                diffs.append(f"{key}: {va} != {vb}")
        elif va != vb:
            diffs.append(f"{key}: {va!r} != {vb!r}")
    if diffs:
        ok = False
        print(f"  results: MISMATCH at {VERIFY_ROUND_DP} dp ({len(diffs)} field(s))")
        for d in diffs[:40]:
            print(f"    {d}")
        if len(diffs) > 40:
            print(f"    ... {len(diffs) - 40} more")
    else:
        print(f"  results: MATCH at {VERIFY_ROUND_DP} dp ({len(na)} scalar fields)")
    n_entries = len(a.get("results", []))
    print(f"  entries compared: {n_entries}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# --------------------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase 1.4 reproducible scoreboard (sealed holdout).")
    ap.add_argument("--stage", choices=[*STAGE_ORDER, "all"], default="all")
    ap.add_argument("--open-holdout", action="store_true",
                    help="unseal holdout metrics into results.json / SCOREBOARD.md (Phase 2.4, once)")
    ap.add_argument("--strategies", nargs="+", default=list(DEFAULT_STRATEGIES))
    ap.add_argument("--pairs", nargs="+", default=None,
                    help="explicit pairs (default: canonical universe resolved against futures data)")
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke: use only the first N resolved pairs")
    ap.add_argument("--timerange", default=None,
                    help="smoke: override the stage timerange (START-END, YYYYMMDD)")
    ap.add_argument("--userdir", default="user_data")
    ap.add_argument("--config", default=CONFIG_BACKTEST)
    ap.add_argument("--data-dir", default=DATA_SUBDIR)
    ap.add_argument("--outdir", default=None, help="explicit output dir (default reports/scoreboard-<ts>)")
    ap.add_argument("--max-run-seconds", type=int, default=1800)
    ap.add_argument("--no-batch", action="store_true",
                    help="run each strategy in its own process (batch mode is faster but one "
                         "crashing strategy invalidates the whole batch)")
    ap.add_argument("--verify", nargs=2, metavar=("DIR1", "DIR2"),
                    help="compare two scoreboard output dirs (4 dp) and print PASS/FAIL")
    args = ap.parse_args(argv)

    if args.verify:
        return verify_dirs(Path(args.verify[0]), Path(args.verify[1]))

    run_date = _utc_now()
    stages = list(STAGE_ORDER) if args.stage == "all" else [args.stage]
    strategies = list(dict.fromkeys(args.strategies))  # dedupe, keep order

    out_dir = Path(args.outdir) if args.outdir else \
        REPO_ROOT / "reports" / f"scoreboard-{run_date.strftime('%Y%m%d-%H%M')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    data_dir = REPO_ROOT / args.data_dir
    bounds = stage_bounds(run_date)

    universe = resolve_universe(data_dir)
    pairs = list(universe["resolved"])
    if args.pairs:
        pairs = list(dict.fromkeys(args.pairs))
        universe["resolved"] = pairs
    if args.limit:
        pairs = pairs[: args.limit]
        universe["resolved"] = pairs

    if not pairs:
        print("ERROR: no usable pairs — nothing to score.", file=sys.stderr)
        return 2

    print(f"[scoreboard] out={out_dir}")
    print(f"[scoreboard] git={git_sha()[:9]} pairs={len(pairs)} stages={stages} "
          f"strategies={len(strategies)}")
    if universe["substitutions"]:
        for s in universe["substitutions"]:
            print(f"[scoreboard] substitution: {s['requested']} -> {s['used']} ({s['reason']})")

    data_manifest = build_data_manifest(data_dir, universe, bounds, run_date)

    results: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "fee_model": FEE_MODEL,
                               "stages": [], "results": []}
    holdout_block: dict[str, Any] | None = None
    run_log: list[dict[str, Any]] = []

    for stage in stages:
        outcome = run_stage(stage, strategies, pairs, bounds, out_dir, args, data_manifest["totals"])
        run_log.extend(outcome["runs"])
        entries = [outcome["entries"][s] for s in strategies]
        if stage == "holdout":
            holdout_block = {
                "schema_version": SCHEMA_VERSION,
                "fee_model": FEE_MODEL,
                "sealed": not args.open_holdout,
                "opened": bool(args.open_holdout),
                "stage_window": bounds["holdout"],
                "results": entries,
            }
            # Sealed by default: holdout metrics never reach results.json / SCOREBOARD.md
            # unless --open-holdout is passed explicitly.
            if args.open_holdout:
                results["stages"].append(stage)
                results["results"].extend(entries)
        else:
            results["stages"].append(stage)
            results["results"].extend(entries)

    results["results"].sort(key=lambda r: (STAGE_ORDER.index(r["stage"])
                                           if r["stage"] in STAGE_ORDER else 99, r["strategy"]))
    results["stages"] = [s for s in STAGE_ORDER if s in results["stages"]]

    manifest = build_manifest(args, out_dir, universe, data_manifest, bounds, strategies,
                              run_date, stages_run=stages)
    manifest["runs"] = run_log

    if holdout_block is not None:
        holdout_block["seal"] = {
            "note": "Holdout metrics are sealed. Selection (Phase 2.1) must not read this file. "
                    "Opening requires --open-holdout (Phase 2.4, once).",
            "sealed_hash": sha256_of(holdout_block["results"]),
            "git_sha": manifest["git_sha"],
            "fee_model": FEE_MODEL,
        }
        (out_dir / "HOLDOUT_SEALED.json").write_text(
            json.dumps(holdout_block, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    (out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "UNIVERSE.json").write_text(json.dumps({
        "canonical_constants": list(CANONICAL_UNIVERSE_BASES),
        "pair_format": f"<BASE>/{QUOTE}{CONTRACT_SUFFIX}",
        "quote": QUOTE,
        "resolved": pairs,
        "requested": universe["requested"],
        "substitutions": universe["substitutions"],
        "unresolved": universe["unresolved"],
        "purpose": "Phase 1.4 scoreboard universe; same list drives Phase 2 dry-run config",
    }, indent=2) + "\n", encoding="utf-8")
    (out_dir / "SCOREBOARD.md").write_text(
        render_scoreboard(manifest, results, holdout_block, args.open_holdout), encoding="utf-8")

    print(f"[scoreboard] wrote {out_dir / 'MANIFEST.json'}")
    print(f"[scoreboard] manifest_hash={manifest['manifest_hash']}")
    print(f"[scoreboard] entries={len(results['results'])} holdout_sealed={holdout_block is not None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
