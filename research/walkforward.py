#!/usr/bin/env python
"""Phase 2.2 — rolling walk-forward validation with a bootstrap gate.

WHY THIS FILE EXISTS
--------------------
The scoreboard (Phase 1.4) answers "which strategy looked best on the selection window?".
That question is one number per strategy and it cannot distinguish an edge from a lucky month.
This script answers the question Phase 2 actually needs: *does the strategy make money, net of
costs, in months it was not fitted to, often enough that the aggregate expectancy is unlikely to
be zero?*

Mechanism: for every test month in the evaluation span, run freqtrade on that month alone, using a
train window that rolls immediately before it.  Concatenate the resulting per-trade returns and put
a bootstrap 95% confidence interval around the mean.  PASS requires the *lower bound* of that
interval to be above zero — a sign test would pass a strategy whose edge is one good week.

WHY `--start` BOUNDS THE TEST SPAN (not the train span)
-------------------------------------------------------
The plan text says "for each test month from start+train to end".  Implemented literally, the
prescribed smoke (`--start 20250801 --end 20251101 --train-months 3`) has zero windows, because the
first test month would start exactly where the span ends.  A zero-window smoke proves nothing, so
the CLI here treats `--start`/`--end` as the span of *tests* and rolls the train window backwards
from `--start`.  This is the stricter reading too: every month in the requested span is scored
out-of-sample, and the train data must already exist before it.

WINDOW / BOUNDARY CONVENTION
----------------------------
freqtrade's `--timerange START-END` treats END as EXCLUSIVE.  A window therefore stores inclusive
human dates plus the exclusive timerange it hands to freqtrade:
    train: [train_start, test_start)      test: [test_start, test_end)   -- in UTC candles.
A final, clipped test window (run date mid-month) is kept and flagged `partial: true`; it is real
out-of-sample data and dropping it would silently throw away the most recent month.

COST MODEL
----------
Identical to the scoreboard: the backtester models fees but has no slippage parameter, so `--fee
0.001` (10 bps, charged on entry AND exit) stands in for exchange fee + slippage.  The label is
emitted verbatim: ``fee_model: 10bps all-in (fee + slippage proxy)``.

REUSE, NOT REINVENTION
----------------------
Freqtrade invocation, result-archive parsing, metric extraction, hashing and the 4 dp comparison
rules are imported from ``scripts/scoreboard.py`` (the same code path the scoreboard uses), so a
walk-forward number and a scoreboard number are produced by the same machinery.  Only the window
loop, the aggregation and the bootstrap are new here.

WHY EVERY STRATEGY RUNS IN ITS OWN PROCESS (batch mode is opt-in)
------------------------------------------------------------------
freqtrade's ``--strategy-list`` shares the loaded data pipeline across strategies, and the shared
startup-candle window changes each strategy's warm-up.  Measured on this machine, 2025-10 window,
20 pairs: BollingerMeanReversion produced 13 trades / -1.2501 % expectancy per trade alone, and 15
trades / +0.5664 % inside a 7-strategy batch — the sign of the month flipped.  A validation run
whose numbers depend on which other strategies happened to share the batch is not a measurement, so
the default here is one process per (strategy, window).  ``--batch`` is available for speed when
the strategy set is fixed and only relative ranking inside that set matters.

GATE
----
PASS = bootstrap 95% CI lower bound of aggregate out-of-sample expectancy per trade > 0
       AND at least ``--min-trades`` trades (default 30) across at least 2 windows.
FAIL prints ``WALKFORWARD FAIL: no OOS edge at 10bps`` and exits 1.  ``--allow-fail`` always
exits 0 (CI-style use) while still printing the FAIL banner.

Usage
-----
  python research/walkforward.py                                   # 8 strategies, full span
  python research/walkforward.py --strategy EmaTrendFollowing \
      --train-months 3 --test-months 1 --start 20250801 --end 20251101
  python research/walkforward.py --limit 10 --allow-fail
  python research/walkforward.py --verify reports/walkforward-A reports/walkforward-B
"""

from __future__ import annotations

import argparse
import calendar
import copy
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import scoreboard as sb  # noqa: E402  — the Phase 1.4 runner/parser/hash scheme, reused verbatim

SCHEMA_VERSION = 1

DEFAULT_TRAIN_MONTHS = 6
DEFAULT_TEST_MONTHS = 1
DEFAULT_START = "20240101"
DEFAULT_END_MODE = "run_date"

#: Minimum 1h candles a pair needs inside a window for freqtrade to produce a meaningful backtest.
#: Same value the scoreboard uses for a "covered" stage (`MIN_STAGE_CANDLES`).
MIN_WINDOW_CANDLES = sb.MIN_STAGE_CANDLES
MIN_TRAIN_CANDLES = sb.MIN_STAGE_CANDLES

#: A clipped tail window shorter than this is dropped instead of run: one or two days of candles
#: cannot produce a month-level statistic, and a 24-candle "month" would be a fake data point.
MIN_PARTIAL_WINDOW_DAYS = 7

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 42
BOOTSTRAP_ALPHA = 0.05

#: A run slower than this triggers the runtime guardrail: subsequent windows are capped to
#: DEGRADED_PAIR_CAP pairs and the degradation is recorded in the manifest/report (never silent).
SLOW_RUN_THRESHOLD_S = 120.0
DEGRADED_PAIR_CAP = 10

#: A strategy whose backtest process dies twice is not retried every window (EnsembleStrategy is
#: known to raise inside populate_entry_trend at this HEAD); its windows are reported as no_result.
MAX_PROCESS_FAILURES = 2

#: Gate: a CI over a handful of trades is not evidence.  30 is well below the plan's ~50-trade
#: noise floor, so it filters only degenerate samples.
MIN_TRADES_FOR_GATE = 30
MIN_WINDOWS_FOR_GATE = 2

FAIL_BANNER = "WALKFORWARD FAIL: no OOS edge at 10bps"
PASS_BANNER = "WALKFORWARD PASS: OOS expectancy bootstrap CI lower bound > 0"

UNIVERSE_JSON_DEFAULT = "reports/scoreboard-20261119-1229/UNIVERSE.json"

GATE_RULE = (
    f"PASS iff bootstrap {int((1 - BOOTSTRAP_ALPHA) * 100)}% CI lower bound of the aggregate "
    f"out-of-sample expectancy per trade is > 0 AND n_trades >= {MIN_TRADES_FOR_GATE} "
    f"AND n_windows_with_trades >= {MIN_WINDOWS_FOR_GATE}"
)


# --------------------------------------------------------------------------------------------------
# Dates and windows
# --------------------------------------------------------------------------------------------------

def parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def add_months(d: date, months: int) -> date:
    """Calendar-month arithmetic without dateutil; clamps the day to the target month's length."""
    total = (d.year * 12 + (d.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


@dataclass(frozen=True)
class Window:
    index: int
    label: str
    train_start: date
    train_end: date      # exclusive; == test_start
    test_start: date
    test_end: date       # exclusive
    partial: bool

    @property
    def train_timerange(self) -> str:
        return f"{ymd(self.train_start)}-{ymd(self.train_end)}"

    @property
    def test_timerange(self) -> str:
        return f"{ymd(self.test_start)}-{ymd(self.test_end)}"

    @property
    def train_months(self) -> int:
        return (self.test_start.year - self.train_start.year) * 12 \
            + (self.test_start.month - self.train_start.month)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "train": {"start": ymd(self.train_start), "end_inclusive": ymd(self.train_end - timedelta(days=1)),
                      "timerange": self.train_timerange},
            "test": {"start": ymd(self.test_start), "end_inclusive": ymd(self.test_end - timedelta(days=1)),
                     "timerange": self.test_timerange},
            "train_months": self.train_months,
            "partial": self.partial,
        }


def build_windows(start: date, end_inclusive: date, train_months: int, test_months: int,
                  min_partial_days: int = MIN_PARTIAL_WINDOW_DAYS
                  ) -> tuple[list[Window], list[dict[str, Any]]]:
    """Roll test windows of ``test_months`` from ``start`` to ``end_inclusive``.

    Each window carries the train window that ends the day before its test window starts.
    Returns ``(windows, dropped)``; ``dropped`` lists clipped tail windows too short to measure.
    """
    if end_inclusive < start:
        raise SystemExit(f"ERROR: --end {ymd(end_inclusive)} is before --start {ymd(start)}")
    if train_months < 1 or test_months < 1:
        raise SystemExit("ERROR: --train-months and --test-months must be >= 1")

    end_excl = end_inclusive + timedelta(days=1)
    windows: list[Window] = []
    dropped: list[dict[str, Any]] = []
    cursor = month_start(start)
    index = 1
    while cursor < end_excl:
        natural_end = add_months(cursor, test_months)
        test_end = min(natural_end, end_excl)
        if test_end <= cursor:
            break
        partial = test_end != natural_end
        if partial and (test_end - cursor).days < min_partial_days:
            dropped.append({"label": f"{cursor.year:04d}-{cursor.month:02d}",
                            "timerange": f"{ymd(cursor)}-{ymd(test_end)}",
                            "reason": f"clipped tail window shorter than {min_partial_days} days"})
            cursor = natural_end
            index += 1
            continue
        windows.append(Window(
            index=index,
            label=f"{cursor.year:04d}-{cursor.month:02d}",
            train_start=add_months(cursor, -train_months),
            train_end=cursor,
            test_start=cursor,
            test_end=test_end,
            partial=partial,
        ))
        cursor = natural_end
        index += 1
    return windows, dropped


# --------------------------------------------------------------------------------------------------
# Per-pair candle availability (pairs listed late must be skipped per window, never crash a run)
# --------------------------------------------------------------------------------------------------

class DataIndex:
    """Caches each pair's 1h candle timestamps and answers 'how many candles in [a, b)'."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._cache: dict[str, Any] = {}

    def rows_total(self, pair: str) -> int | None:
        series = self._series(pair)
        return None if series is None else int(series.shape[0])

    def _series(self, pair: str):
        if pair in self._cache:
            return self._cache[pair]
        base = pair.split("/")[0]
        path = sb.data_file_for_base(self.data_dir, base)
        series = None
        if path.exists():
            meta = sb._feather_dates(path)
            if meta is not None and meta[0] > 0:
                series = meta[3]
        self._cache[pair] = series
        return series

    def rows_between(self, pair: str, start: date, end_excl: date) -> int:
        series = self._series(pair)
        if series is None:
            return 0
        lo_ts = _utc_ts(start)
        hi_ts = _utc_ts(end_excl)
        lo = int(series.searchsorted(lo_ts, side="left"))
        hi = int(series.searchsorted(hi_ts, side="left"))
        return max(0, hi - lo)

    def bounds(self, pair: str) -> tuple[str | None, str | None]:
        series = self._series(pair)
        if series is None or series.shape[0] == 0:
            return None, None
        return _iso(series.iloc[0]), _iso(series.iloc[-1])


def _utc_ts(d: date):
    """tz-aware pandas Timestamp for a UTC date — must match the feather columns' tz (UTC)."""
    import pandas as pd

    return pd.Timestamp(datetime.combine(d, dtime.min).replace(tzinfo=timezone.utc))


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def window_pairs(window: Window, pairs: list[str], index: DataIndex) -> tuple[list[str], list[dict[str, Any]]]:
    used: list[str] = []
    skipped: list[dict[str, Any]] = []
    for pair in pairs:
        n_test = index.rows_between(pair, window.test_start, window.test_end)
        n_train = index.rows_between(pair, window.train_start, window.train_end)
        if n_test >= MIN_WINDOW_CANDLES and n_train >= MIN_TRAIN_CANDLES:
            used.append(pair)
            continue
        reasons = []
        if n_test < MIN_WINDOW_CANDLES:
            reasons.append(f"test_rows={n_test} < {MIN_WINDOW_CANDLES}")
        if n_train < MIN_TRAIN_CANDLES:
            reasons.append(f"train_rows={n_train} < {MIN_TRAIN_CANDLES}")
        skipped.append({
            "pair": pair,
            "test_rows": n_test,
            "train_rows": n_train,
            "reason": "insufficient data in window (" + ", ".join(reasons) + ")",
        })
    return used, skipped


# --------------------------------------------------------------------------------------------------
# freqtrade runs (delegated to scoreboard.run_backtest so flags/fee/parsing are identical)
# --------------------------------------------------------------------------------------------------

def _run_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        config=args.config,
        userdir=args.userdir,
        max_run_seconds=args.max_run_seconds,
    )


def run_window(window: Window, strategies: list[str], pairs: list[str], out_dir: Path,
               args: argparse.Namespace, known_failures: dict[str, int],
               skip: set[str]) -> dict[str, Any]:
    """Run one window; batch first, then per-strategy for whatever the batch did not return."""
    ns = _run_args(args)
    payloads: dict[str, Any] = {}
    runs: list[dict[str, Any]] = []
    slowest = 0.0

    active = [s for s in strategies if s not in skip]
    if not active:
        return {"payloads": {}, "runs": [], "slowest_s": 0.0}

    use_batch = len(active) > 1 and args.batch
    if use_batch:
        label = f"{window.label}__batch"
        run = sb.run_backtest(label, active, window.test_timerange, pairs, out_dir, ns, batch=True)
        slowest = max(slowest, float(run["elapsed_s"]))
        runs.append({"label": label, "returncode": run["returncode"], "elapsed_s": run["elapsed_s"],
                     "timed_out": run["timed_out"], "command": run["command"]})
        payloads.update(run["results"])
        if not payloads:
            print(f"[walkforward]   batch failed (rc={run['returncode']}) — falling back to "
                  f"per-strategy runs for {window.label}", flush=True)

    for strat in [s for s in active if s not in payloads]:
        label = f"{window.label}__{strat}"
        run = sb.run_backtest(label, [strat], window.test_timerange, pairs, out_dir, ns, batch=False)
        slowest = max(slowest, float(run["elapsed_s"]))
        runs.append({"label": label, "returncode": run["returncode"], "elapsed_s": run["elapsed_s"],
                     "timed_out": run["timed_out"], "command": run["command"]})
        payloads.update(run["results"])
        if strat not in payloads:
            if run["returncode"] != 0:
                known_failures[strat] = known_failures.get(strat, 0) + 1
                print(f"[walkforward]   {strat} @ {window.label}: no result (rc={run['returncode']}) "
                      f"{run['stderr_tail']}", flush=True)
                if known_failures[strat] >= MAX_PROCESS_FAILURES:
                    skip.add(strat)
                    print(f"[walkforward]   {strat}: skipping remaining windows after "
                          f"{known_failures[strat]} process failures", flush=True)
    return {"payloads": payloads, "runs": runs, "slowest_s": slowest}


TRADE_FIELDS = ("pair", "open_date", "close_date", "profit_ratio", "profit_abs", "is_short",
                "leverage", "exit_reason", "enter_tag", "funding_fees", "stake_amount")


def extract_window_entry(strategy: str, window: Window, payload: dict[str, Any] | None,
                         elapsed_s: float) -> dict[str, Any]:
    if payload is None:
        return {
            "strategy": strategy, "window": window.label, "status": "no_result",
            "timerange": window.test_timerange,
            "metrics": copy.deepcopy(sb.EMPTY_METRICS), "trades_detail": [],
            "elapsed_s": round(elapsed_s, 2),
            "note": "freqtrade produced no result for this strategy/window (see raw logs)",
        }
    metrics = sb.extract_metrics(payload)
    trades = []
    for t in payload.get("trades") or []:
        trades.append({
            "pair": t.get("pair"),
            "open_date": t.get("open_date"),
            "close_date": t.get("close_date"),
            "profit_ratio": sb._f(t.get("profit_ratio")),
            "profit_abs": sb._f(t.get("profit_abs")),
            "is_short": t.get("is_short"),
            "leverage": t.get("leverage"),
            "exit_reason": t.get("exit_reason"),
            "enter_tag": t.get("enter_tag"),
            "funding_fees": sb._f(t.get("funding_fees")),
            "stake_amount": sb._f(t.get("stake_amount"), 2),
        })
    return {
        "strategy": strategy, "window": window.label,
        "status": "ok" if metrics["trades"] > 0 else "no_trades",
        "timerange": window.test_timerange,
        "metrics": metrics, "trades_detail": trades,
        "elapsed_s": round(elapsed_s, 2), "note": None,
    }


# --------------------------------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------------------------------

def bootstrap_ci(values: list[float], resamples: int = BOOTSTRAP_RESAMPLES,
                 seed: int = BOOTSTRAP_SEED, alpha: float = BOOTSTRAP_ALPHA) -> dict[str, Any]:
    """Percentile bootstrap of the mean, seeded and chunked (memory-safe for 10k+ trades).

    Chunking is deterministic: the generator draws in a fixed order regardless of chunk size, and
    the chunk size is a pure function of n, so a rerun over the same trades yields the same CI.
    """
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    n = int(arr.size)
    if n == 0:
        return {"mean": None, "ci_low": None, "ci_high": None, "n": 0,
                "resamples": resamples, "seed": seed, "alpha": alpha}
    rng = np.random.default_rng(seed)
    chunk = max(1, min(1000, 20_000_000 // max(n, 1)))
    means = np.empty(resamples, dtype=float)
    done = 0
    while done < resamples:
        take = min(chunk, resamples - done)
        idx = rng.integers(0, n, size=(take, n))
        means[done:done + take] = arr[idx].mean(axis=1)
        done += take
    lo = float(np.percentile(means, 100.0 * alpha / 2.0))
    hi = float(np.percentile(means, 100.0 * (1.0 - alpha / 2.0)))
    return {
        "mean": round(float(arr.mean()), 8),
        "median": round(float(np.median(arr)), 8),
        "std": round(float(arr.std(ddof=1)), 8) if n > 1 else None,
        "ci_low": round(lo, 8),
        "ci_high": round(hi, 8),
        "n": n,
        "resamples": resamples,
        "seed": seed,
        "alpha": alpha,
    }


def bootstrap_ci_windows(window_means: list[float], resamples: int = BOOTSTRAP_RESAMPLES,
                         seed: int = BOOTSTRAP_SEED, alpha: float = BOOTSTRAP_ALPHA) -> dict[str, Any]:
    """Secondary, cluster-style CI: resample *windows*, not trades.

    Trades inside one month share a regime, so the trade-level bootstrap is optimistic when a
    strategy trades in bursts. This window-level interval is the pessimistic companion; the gate
    deliberately uses the trade-level one (it is the contract), but both are reported so nobody has
    to take the friendlier number on faith.
    """
    arr = np.asarray(window_means, dtype=float)
    if arr.size == 0:
        return {"mean": None, "ci_low": None, "ci_high": None, "n_windows": 0}
    if arr.size == 1:
        return {"mean": round(float(arr[0]), 8), "ci_low": None, "ci_high": None, "n_windows": 1}
    rng = np.random.default_rng(seed + 1)
    idx = rng.integers(0, arr.size, size=(resamples, arr.size))
    means = arr[idx].mean(axis=1)
    return {
        "mean": round(float(arr.mean()), 8),
        "ci_low": round(float(np.percentile(means, 100.0 * alpha / 2.0)), 8),
        "ci_high": round(float(np.percentile(means, 100.0 * (1.0 - alpha / 2.0))), 8),
        "n_windows": int(arr.size),
        "resamples": resamples,
        "seed": seed + 1,
    }


def aggregate_strategy(entries: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    """Concatenate per-window trades and gate the aggregate expectancy."""
    profits: list[float] = []
    window_means: list[float] = []
    positive = 0
    evaluated = 0
    with_trades = 0
    no_result = 0
    window_rows: list[dict[str, Any]] = []

    for e in entries:
        if e["status"] == "no_result":
            no_result += 1
            window_rows.append({"window": e["window"], "status": e["status"], "trades": 0,
                                "profit_pct": None, "expectancy_pct": None, "winrate_pct": None,
                                "max_drawdown_pct": None})
            continue
        evaluated += 1
        m = e["metrics"]
        ratios = [t["profit_ratio"] for t in e["trades_detail"] if t["profit_ratio"] is not None]
        profits.extend(ratios)
        if ratios:
            with_trades += 1
            window_mean = float(np.mean(ratios))
            window_means.append(window_mean)
        else:
            window_mean = 0.0
        if (m["profit_pct"] or 0.0) > 0:
            positive += 1
        window_rows.append({
            "window": e["window"], "status": e["status"], "trades": m["trades"],
            "profit_pct": m["profit_pct"], "expectancy_pct": m["expectancy_pct"],
            "winrate_pct": m["winrate_pct"], "max_drawdown_pct": m["max_drawdown_pct"],
            "window_expectancy_pct": round(window_mean * 100.0, 6) if ratios else None,
        })

    stats = bootstrap_ci(profits, resamples=args.bootstrap_resamples, seed=args.seed)
    win_stats = bootstrap_ci_windows(window_means, resamples=args.bootstrap_resamples, seed=args.seed)

    reasons: list[str] = []
    if stats["n"] == 0:
        reasons.append("no out-of-sample trades")
    if stats["n"] < args.min_trades:
        reasons.append(f"n_trades={stats['n']} < min_trades={args.min_trades}")
    if with_trades < MIN_WINDOWS_FOR_GATE:
        reasons.append(f"windows_with_trades={with_trades} < {MIN_WINDOWS_FOR_GATE}")
    if stats["ci_low"] is not None and stats["ci_low"] <= 0:
        reasons.append(f"ci_low={stats['ci_low']:.6f} <= 0")

    passed = not reasons
    return {
        "strategy": entries[0]["strategy"] if entries else "unknown",
        "gate": "PASS" if passed else "FAIL",
        "gate_reasons": reasons,
        "n_trades": stats["n"],
        "n_windows_run": len(entries),
        "n_windows_evaluated": evaluated,
        "n_windows_with_trades": with_trades,
        "n_windows_no_result": no_result,
        "pct_positive_windows": round(100.0 * positive / evaluated, 2) if evaluated else None,
        "pct_positive_windows_basis": "windows where a backtest result existed (0-trade windows count as non-positive)",
        "expectancy_per_trade": stats["mean"],
        "expectancy_per_trade_pct": None if stats["mean"] is None else round(stats["mean"] * 100.0, 6),
        "median_trade": stats.get("median"),
        "std_trade": stats.get("std"),
        "ci_low": stats["ci_low"],
        "ci_high": stats["ci_high"],
        "ci_low_pct": None if stats["ci_low"] is None else round(stats["ci_low"] * 100.0, 6),
        "ci_high_pct": None if stats["ci_high"] is None else round(stats["ci_high"] * 100.0, 6),
        "bootstrap": {"resamples": args.bootstrap_resamples, "seed": args.seed,
                      "alpha": BOOTSTRAP_ALPHA, "unit": "trade"},
        "window_bootstrap": win_stats,
        "mean_window_profit_pct": round(float(np.mean([r["profit_pct"] or 0.0 for r in window_rows
                                                       if r["status"] != "no_result"])), 6)
        if evaluated else None,
        "windows": window_rows,
    }


# --------------------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------------------

def _print_aggregate_table(aggregates: list[dict[str, Any]]) -> None:
    print("")
    print(f"{'strategy':28s} {'trades':>7s} {'windows':>8s} {'exp/trade%':>11s} "
          f"{'ci_low%':>9s} {'ci_high%':>9s} {'pos%':>6s}  gate")
    for a in aggregates:
        print(f"{a['strategy']:28s} {a['n_trades']:7d} {a['n_windows_evaluated']:8d} "
              f"{_num(a['expectancy_per_trade_pct'], 4):>11s} {_num(a['ci_low_pct'], 4):>9s} "
              f"{_num(a['ci_high_pct'], 4):>9s} {_num(a['pct_positive_windows'], 1):>6s}  {a['gate']}")
    print("")


def _num(value: Any, nd: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{nd}f}"
    except (TypeError, ValueError):
        return str(value)


def render_markdown(manifest: dict[str, Any], aggregates: list[dict[str, Any]],
                    window_records: list[dict[str, Any]], gate: dict[str, Any]) -> str:
    lines: list[str] = []
    strategies = manifest["strategies"]
    lines.append("# Phase 2.2 — walk-forward validation")
    lines.append("")
    lines.append(f"## {gate['verdict']}")
    lines.append("")
    if gate["passed"]:
        lines.append(f"**{PASS_BANNER}**")
    else:
        lines.append(f"### {FAIL_BANNER}")
        lines.append("")
        lines.append("Failing strategies: " + (", ".join(gate["failed_strategies"]) or "—"))
    lines.append("")
    lines.append(f"Gate rule: {GATE_RULE}")
    lines.append("")

    lines.append("## Reproducibility header")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| git SHA | `{manifest['git_sha']}` |")
    lines.append(f"| generated (UTC) | {manifest['generated_at_utc']} |")
    lines.append(f"| freqtrade | {manifest['freqtrade_version']} |")
    lines.append(f"| config | `{manifest['config_path']}` |")
    lines.append(f"| config sha256 | `{manifest.get('config_sha256') or 'n/a'}` |")
    lines.append(f"| **{manifest['fee_model'].split(':')[0]}** | "
                 f"**{manifest['fee_model'].split(':', 1)[1].strip()}** |")
    lines.append(f"| timeframe | {manifest['timeframe']} |")
    lines.append(f"| run mode | {manifest['run_mode']} "
                 f"({'one freqtrade process per window' if manifest['run_mode'] == 'batch' else 'one freqtrade process per strategy+window'}) |")
    lines.append(f"| manifest hash | `{manifest['manifest_hash']}` |")
    lines.append(f"| strategies | {len(strategies)} — " + ", ".join(f"`{s}`" for s in strategies) + " |")
    lines.append(f"| universe | {len(manifest['universe'])} pairs |")
    lines.append(f"| bootstrap | {manifest['bootstrap']['resamples']} resamples, "
                 f"seed {manifest['bootstrap']['seed']}, unit={manifest['bootstrap']['unit']} |")
    lines.append("")

    spec = manifest["windows_spec"]
    lines.append("## Windows")
    lines.append("")
    lines.append(f"- span (tests): `{spec['start']}` → `{spec['end_inclusive']}` "
                 f"(`--end` mode: {spec['end_mode']})")
    lines.append(f"- train {spec['train_months']} month(s) rolling immediately before each test window")
    lines.append(f"- test {spec['test_months']} month(s); END exclusive in freqtrade timeranges")
    lines.append(f"- windows run: **{manifest['windows_run']}**; "
                 f"insufficient-data windows: **{manifest['windows_insufficient']}**")
    if spec["partial_windows"]:
        lines.append(f"- partial (clipped at run date): {', '.join(spec['partial_windows'])}")
    if spec.get("dropped_windows"):
        lines.append("- dropped tail window(s) (too short to measure): "
                     + ", ".join(f"`{d['label']}` {d['reason']}" for d in spec["dropped_windows"]))
    if manifest.get("degraded"):
        lines.append("")
        lines.append(f"> **Runtime guardrail applied**: {manifest['degraded']['reason']} — "
                     f"subsequent windows were capped to {DEGRADED_PAIR_CAP} pairs.")
    lines.append("")

    lines.append("## Aggregate out-of-sample results")
    lines.append("")
    lines.append("| Strategy | Trades | Windows | Exp/trade % | CI low % | CI high % | Positive win % | "
                 "Mean window profit % | Gate |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for a in aggregates:
        lines.append(
            f"| {a['strategy']} | {a['n_trades']} | {a['n_windows_evaluated']} | "
            f"{_num(a['expectancy_per_trade_pct'], 4)} | {_num(a['ci_low_pct'], 4)} | "
            f"{_num(a['ci_high_pct'], 4)} | {_num(a['pct_positive_windows'], 1)} | "
            f"{_num(a['mean_window_profit_pct'], 3)} | {a['gate']} |")
    lines.append("")
    lines.append("`Exp/trade %` is the mean per-trade return (leverage-adjusted, net of the 10 bps "
                 "all-in fee) over every concatenated test-window trade; `CI low/high` is the "
                 "percentile bootstrap of that mean.")
    lines.append("")

    lines.append("## Per-window detail")
    lines.append("")
    header = "| Window | Test timerange | Pairs | " + " | ".join(strategies) + " |"
    lines.append(header)
    lines.append("|---|---|---:|" + "---:|" * len(strategies))
    for rec in window_records:
        cells = []
        for strat in strategies:
            entry = rec["results"].get(strat)
            if entry is None or entry["status"] == "no_result":
                cells.append("—")
            elif entry["status"] == "no_trades":
                cells.append("0")
            else:
                cells.append(f"{_num(entry['metrics']['profit_pct'], 2)} ({entry['metrics']['trades']})")
        lines.append(f"| {rec['window']} | `{rec['test_timerange']}` | {rec['pairs_used']} | "
                     + " | ".join(cells) + " |")
    lines.append("")
    lines.append("Cells are `profit % (trades)` for the test month. `0` = backtest ran, no trades. "
                 "`—` = no result (process failure). Full metrics per window: `windows.json`; "
                 "per-trade records: `trades/<strategy>.csv`.")
    lines.append("")

    insufficient = [r for r in window_records if r["status"] == "insufficient_data"]
    skipped_any = [r for r in window_records if r.get("skipped_pairs")]
    lines.append("## Data sufficiency")
    lines.append("")
    lines.append(f"- windows skipped for insufficient data: **{len(insufficient)}**"
                 + (" (" + ", ".join(r["window"] for r in insufficient) + ")" if insufficient else ""))
    if skipped_any:
        total_skips = sum(len(r["skipped_pairs"]) for r in skipped_any)
        lines.append(f"- pair-window skips (listed late / no candles in window): **{total_skips}** "
                     f"across {len(skipped_any)} windows — the window still ran with the remaining pairs.")
        for r in skipped_any[:12]:
            names = ", ".join(s["pair"].split("/")[0] for s in r["skipped_pairs"])
            lines.append(f"  - {r['window']}: {names}")
        if len(skipped_any) > 12:
            lines.append(f"  - … {len(skipped_any) - 12} more (see `windows.json`)")
    else:
        lines.append("- pair-window skips: 0")
    lines.append("")

    lines.append("## Known limits")
    lines.append("")
    lines.append("- The trade-level bootstrap assumes trades are independent. They are not: trades "
                 "inside one month share a regime. `window_bootstrap` in `walkforward.json` "
                 "resamples windows instead and is the pessimistic companion number.")
    lines.append("- Each window starts from a fresh 10,000 USDT wallet with `max_open_trades: 4`, so "
                 "per-window profit % is not a compounded portfolio return; the gate is on "
                 "expectancy per trade, which is the scale-free quantity.")
    lines.append("- The train window is only reported, never fitted: these strategies have no "
                 "hyperopt step, so 'train' here means 'the history that preceded the test month', "
                 "and it is useful mainly to see whether the pair list was tradable at the time.")
    lines.append("- Backtests fill at candle prices with a 10 bps all-in proxy; slippage is not "
                 "modelled beyond that proxy, and no funding cost beyond freqtrade's funding_fees "
                 "column is charged in this run.")
    lines.append("- Each strategy runs in its own process. freqtrade's `--strategy-list` shares "
                 "startup candles across strategies and changes results (measured: 13 vs 15 trades, "
                 "expectancy sign flip, same window), so `--batch` numbers are only comparable "
                 "against the same batch.")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```")
    lines.append("python research/walkforward.py --strategy " + strategies[0]
                 + f" --start {spec['start']} --end {spec['end_inclusive']} "
                 f"--train-months {spec['train_months']} --test-months {spec['test_months']}")
    lines.append("python research/walkforward.py --verify <dirA> <dirB>   # 4 dp + manifest hash")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------
# Manifest / hashing
# --------------------------------------------------------------------------------------------------

def fee_model_label(fee: float) -> str:
    if abs(fee - sb.FEE_RATIO) < 1e-12:
        return sb.FEE_MODEL
    bps = round(fee * 10_000.0, 4)
    return f"fee_model: {bps:g}bps all-in (fee + slippage proxy)"


def build_manifest(args: argparse.Namespace, out_dir: Path, run_date: datetime,
                   strategies: list[str], universe: list[str], windows: list[Window],
                   window_records: list[dict[str, Any]], data_index: DataIndex,
                   windows_run: int, windows_insufficient: int, degraded: dict | None) -> dict[str, Any]:
    sha = sb.git_sha()
    coverage: dict[str, Any] = {}
    for pair in universe:
        first, last = data_index.bounds(pair)
        per_window = {}
        for w in windows:
            per_window[w.label] = data_index.rows_between(pair, w.test_start, w.test_end)
        coverage[pair] = {
            "rows_total": data_index.rows_total(pair),
            "first_candle": first,
            "last_candle": last,
            "test_rows_per_window": per_window,
        }

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact": "walkforward",
        "phase": "2.2",
        "generated_at_utc": run_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "output_dir": out_dir.name,
        "git_sha": sha,
        "git_sha_short": sha[:9] if sha != "unknown" else "unknown",
        "freqtrade_version": sb.freqtrade_version(sb.freqtrade_exe()),
        "python_version": sys.version.split()[0],
        "config_path": args.config,
        "config_sha256": sb.file_sha256(REPO_ROOT / args.config),
        "userdir": args.userdir,
        "fee_model": fee_model_label(args.fee),
        "fee_ratio": args.fee,
        "fee_note": "--fee is charged on entry and exit; 10 bps all-in per side-equivalent "
                    "(exchange fee + slippage proxy, no native slippage in the backtester)",
        "timeframe": sb.TIMEFRAME,
        "run_mode": "batch" if args.batch else "per-strategy",
        "strategies": strategies,
        "universe": universe,
        "universe_source": args.universe_json,
        "windows_spec": {
            "start": ymd(args.start_date),
            "end_inclusive": ymd(args.end_date),
            "end_mode": args.end_mode,
            "train_months": args.train_months,
            "test_months": args.test_months,
            "count": len(windows),
            "partial_windows": [w.label for w in windows if w.partial],
            "dropped_windows": getattr(args, "dropped_windows", []),
        },
        "windows": [w.as_dict() for w in windows],
        "windows_run": windows_run,
        "windows_insufficient": windows_insufficient,
        "bootstrap": {"resamples": args.bootstrap_resamples, "seed": args.seed,
                      "alpha": BOOTSTRAP_ALPHA, "unit": "trade",
                      "method": "percentile bootstrap of the mean over concatenated OOS trades"},
        "gate_rule": GATE_RULE,
        "min_trades": args.min_trades,
        "data_manifest": {"pairs": coverage, "min_window_candles": MIN_WINDOW_CANDLES,
                          "min_train_candles": MIN_TRAIN_CANDLES},
        "manifest_hash_scope": (
            "sha256 over: schema_version, artifact, git_sha, freqtrade_version, config_path, "
            "config_sha256, fee_model, fee_ratio, timeframe, strategies, universe, window list "
            "(train/test timeranges), bootstrap config, gate rule, and per-pair test-window row "
            "counts for every window. EXCLUDED: timestamps, output paths, full-file row counts, "
            "runtime, metrics."
        ),
    }
    if degraded:
        manifest["degraded"] = degraded
    manifest["manifest_hash"] = manifest_hash(manifest)
    return manifest


def manifest_hash(manifest: dict[str, Any]) -> str:
    coverage = manifest["data_manifest"]["pairs"]
    payload = {
        "schema_version": manifest["schema_version"],
        "artifact": manifest["artifact"],
        "git_sha": manifest["git_sha"],
        "freqtrade_version": manifest["freqtrade_version"],
        "config_path": manifest["config_path"],
        "config_sha256": manifest.get("config_sha256"),
        "fee_model": manifest["fee_model"],
        "fee_ratio": manifest["fee_ratio"],
        "timeframe": manifest["timeframe"],
        "run_mode": manifest["run_mode"],
        "strategies": manifest["strategies"],
        "universe": manifest["universe"],
        "windows": [{k: w[k] for k in ("index", "label", "train", "test", "partial")}
                    for w in manifest["windows"]],
        "bootstrap": manifest["bootstrap"],
        "gate_rule": manifest["gate_rule"],
        "min_trades": manifest["min_trades"],
        "coverage": {pair: {"rows_total": info["rows_total"],
                            "test_rows_per_window": info["test_rows_per_window"]}
                     for pair, info in coverage.items()},
    }
    return sb.sha256_of(payload)


# --------------------------------------------------------------------------------------------------
# Verify (same 4 dp contract as `scoreboard.py --verify`)
# --------------------------------------------------------------------------------------------------

def verify_dirs(dir_a: Path, dir_b: Path) -> int:
    ok = True
    print(f"verify: {dir_a} vs {dir_b}")

    def load_results(p: Path) -> dict:
        f = p / "walkforward.json"
        if not f.exists():
            raise SystemExit(f"FAIL: missing {f}")
        return json.loads(f.read_text(encoding="utf-8"))

    a, b = load_results(dir_a), load_results(dir_b)
    ma = json.loads((dir_a / "MANIFEST.json").read_text(encoding="utf-8"))
    mb = json.loads((dir_b / "MANIFEST.json").read_text(encoding="utf-8"))
    if ma.get("manifest_hash") == mb.get("manifest_hash"):
        print(f"  manifest_hash: MATCH ({ma.get('manifest_hash')})")
    else:
        ok = False
        print(f"  manifest_hash: MISMATCH\n    A={ma.get('manifest_hash')}\n    B={mb.get('manifest_hash')}")
        for key in ("git_sha", "fee_model", "fee_ratio", "config_path", "config_sha256",
                    "strategies", "universe", "windows", "bootstrap", "gate_rule"):
            if sb.canonical_json(ma.get(key)) != sb.canonical_json(mb.get(key)):
                print(f"    differing manifest field: {key}")

    na, nb = sb._walk_numbers(a), sb._walk_numbers(b)
    diffs = []
    for key in sorted(set(na) | set(nb)):
        va, vb = na.get(key), nb.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) \
                and not isinstance(va, bool) and not isinstance(vb, bool):
            if round(float(va), sb.VERIFY_ROUND_DP) != round(float(vb), sb.VERIFY_ROUND_DP):
                diffs.append(f"{key}: {va} != {vb}")
        elif va != vb:
            diffs.append(f"{key}: {va!r} != {vb!r}")
    if diffs:
        ok = False
        print(f"  results: MISMATCH at {sb.VERIFY_ROUND_DP} dp ({len(diffs)} field(s))")
        for d in diffs[:40]:
            print(f"    {d}")
        if len(diffs) > 40:
            print(f"    ... {len(diffs) - 40} more")
    else:
        print(f"  results: MATCH at {sb.VERIFY_ROUND_DP} dp ({len(na)} scalar fields)")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# --------------------------------------------------------------------------------------------------
# Universe / CLI
# --------------------------------------------------------------------------------------------------

def load_universe(args: argparse.Namespace, data_dir: Path) -> tuple[list[str], str]:
    if args.pairs:
        return list(dict.fromkeys(args.pairs)), "cli"
    if args.universe_json:
        path = Path(args.universe_json)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            pairs = payload.get("resolved") or payload.get("universe") or []
            if pairs:
                return list(dict.fromkeys(pairs)), str(args.universe_json)
        print(f"[walkforward] WARNING: universe file {path} not found/unusable — "
              f"resolving from canonical constants", flush=True)
    resolved = sb.resolve_universe(data_dir)
    return list(resolved["resolved"]), "scoreboard.resolve_universe()"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Phase 2.2 walk-forward validation (rolling train/test, bootstrap CI gate).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--strategy", action="append", default=None, metavar="CLASS",
                    help="strategy class (repeatable)")
    ap.add_argument("--strategies", nargs="+", default=None, metavar="CLASS",
                    help="alias for repeated --strategy")
    ap.add_argument("--pairs", nargs="+", default=None,
                    help="explicit pair list (default: resolved universe)")
    ap.add_argument("--universe-json", default=UNIVERSE_JSON_DEFAULT,
                    help="universe file whose `resolved` list is used as the pair list")
    ap.add_argument("--train-months", type=int, default=DEFAULT_TRAIN_MONTHS)
    ap.add_argument("--test-months", type=int, default=DEFAULT_TEST_MONTHS)
    ap.add_argument("--start", default=DEFAULT_START, help="first day of the first TEST window")
    ap.add_argument("--end", default=None, help="last day of the last TEST window (default: run date)")
    ap.add_argument("--userdir", default="user_data")
    ap.add_argument("--config", default=sb.CONFIG_BACKTEST)
    ap.add_argument("--data-dir", default=sb.DATA_SUBDIR)
    ap.add_argument("--fee", type=float, default=sb.FEE_RATIO,
                    help="all-in fee per side (0.001 = 10 bps fee + slippage proxy)")
    ap.add_argument("--limit", type=int, default=None, help="use only the first N universe pairs")
    ap.add_argument("--outdir", default=None, help="output dir (default reports/walkforward-<ts>)")
    ap.add_argument("--max-run-seconds", type=int, default=600, help="per-backtest hard timeout")
    ap.add_argument("--bootstrap-resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    ap.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    ap.add_argument("--min-trades", type=int, default=MIN_TRADES_FOR_GATE)
    ap.add_argument("--batch", action="store_true",
                    help="run all strategies of a window in one freqtrade process (faster, but "
                         "freqtrade shares startup candles across --strategy-list, so per-strategy "
                         "results then depend on batch membership; default is isolated runs)")
    ap.add_argument("--allow-fail", action="store_true",
                    help="always exit 0 (CI-style use); the FAIL banner is still printed")
    ap.add_argument("--verify", nargs=2, metavar=("DIR1", "DIR2"),
                    help="compare two walkforward output dirs (4 dp + manifest hash)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.verify:
        return verify_dirs(Path(args.verify[0]), Path(args.verify[1]))

    run_date = datetime.now(timezone.utc)
    args.start_date = parse_yyyymmdd(args.start)
    if args.end:
        args.end_date = parse_yyyymmdd(args.end)
        args.end_mode = "explicit"
    else:
        args.end_date = run_date.date()
        args.end_mode = DEFAULT_END_MODE

    explicit = list(args.strategy or []) + list(args.strategies or [])
    strategies = list(dict.fromkeys(explicit)) if explicit else list(sb.DEFAULT_STRATEGIES)

    if not (0 < args.fee < 0.1):
        raise SystemExit(f"ERROR: --fee {args.fee} is not a sane per-side fee ratio")
    sb.FEE_RATIO = args.fee  # build_command() reads this module global at call time

    out_dir = Path(args.outdir) if args.outdir else \
        REPO_ROOT / "reports" / f"walkforward-{run_date.strftime('%Y%m%d-%H%M')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(exist_ok=True)

    data_dir = REPO_ROOT / args.data_dir
    pairs, universe_source = load_universe(args, data_dir)
    if args.limit:
        pairs = pairs[: args.limit]
    if not pairs:
        print("ERROR: no usable pairs — nothing to validate.", file=sys.stderr)
        return 2

    windows, dropped_windows = build_windows(args.start_date, args.end_date, args.train_months,
                                             args.test_months)
    args.dropped_windows = dropped_windows
    if not windows:
        print("ERROR: the requested span produced zero test windows.", file=sys.stderr)
        return 2

    print(f"[walkforward] out={out_dir}")
    print(f"[walkforward] git={sb.git_sha()[:9]} strategies={len(strategies)} pairs={len(pairs)} "
          f"universe_source={universe_source}")
    print(f"[walkforward] windows={len(windows)} span={ymd(args.start_date)}..{ymd(args.end_date)} "
          f"train={args.train_months}mo test={args.test_months}mo fee={args.fee} "
          f"mode={'batch' if args.batch else 'per-strategy'} "
          f"bootstrap={args.bootstrap_resamples}x seed={args.seed}")

    data_index = DataIndex(data_dir)
    known_failures: dict[str, int] = {}
    skip: set[str] = set()
    degraded: dict[str, Any] | None = None
    pair_cap: int | None = None

    window_records: list[dict[str, Any]] = []
    entries_by_strategy: dict[str, list[dict[str, Any]]] = {s: [] for s in strategies}
    windows_run = 0
    windows_insufficient = 0
    started_all = time.time()

    for window in windows:
        w_pairs, skipped = window_pairs(window, pairs, data_index)
        if pair_cap:
            w_pairs = w_pairs[:pair_cap]
        record: dict[str, Any] = {
            "window": window.label,
            "index": window.index,
            "train_timerange": window.train_timerange,
            "test_timerange": window.test_timerange,
            "partial": window.partial,
            "pairs_used": len(w_pairs),
            "pairs": w_pairs,
            "skipped_pairs": skipped,
            "status": "ok",
            "results": {},
            "elapsed_s": 0.0,
        }
        if not w_pairs:
            record["status"] = "insufficient_data"
            windows_insufficient += 1
            print(f"[walkforward] window {window.index}/{len(windows)} {window.label}: "
                  f"INSUFFICIENT DATA (no pair has {MIN_WINDOW_CANDLES} test candles + "
                  f"{MIN_TRAIN_CANDLES} train candles) — skipped", flush=True)
            for strat in strategies:
                entries_by_strategy[strat].append(extract_window_entry(strat, window, None, 0.0))
            window_records.append(record)
            continue

        windows_run += 1
        t0 = time.time()
        outcome = run_window(window, strategies, w_pairs, out_dir, args, known_failures, skip)
        elapsed = time.time() - t0
        record["elapsed_s"] = round(elapsed, 2)
        record["runs"] = outcome["runs"]

        for strat in strategies:
            entry = extract_window_entry(strat, window, outcome["payloads"].get(strat), elapsed)
            if strat in skip and strat not in outcome["payloads"]:
                entry["note"] = ("skipped after repeated process failure — see logs of earlier "
                                 "windows")
            record["results"][strat] = entry
            entries_by_strategy[strat].append(entry)

        traded = {s: e["metrics"]["trades"] for s, e in record["results"].items()
                  if e["status"] != "no_result"}
        print(f"[walkforward] window {window.index}/{len(windows)} {window.label} "
              f"test={window.test_timerange} pairs={len(w_pairs)} "
              f"trades={{{', '.join(f'{k}:{v}' for k, v in sorted(traded.items()))}}} "
              f"elapsed={elapsed:.1f}s", flush=True)

        if elapsed > SLOW_RUN_THRESHOLD_S and pair_cap is None:
            pair_cap = DEGRADED_PAIR_CAP
            degraded = {
                "reason": f"window {window.label} took {elapsed:.1f}s > {SLOW_RUN_THRESHOLD_S:.0f}s",
                "pairs_cap_applied_from": window.label,
                "pairs_cap": DEGRADED_PAIR_CAP,
                "note": "subsequent windows run with the first N pairs only; comparability across "
                        "windows is reduced and stated in WALKFORWARD.md",
            }
            print(f"[walkforward] WARNING: {degraded['reason']} — capping subsequent windows to "
                  f"{DEGRADED_PAIR_CAP} pairs", flush=True)

        window_records.append(record)

    total_elapsed = time.time() - started_all

    aggregates = [aggregate_strategy(entries_by_strategy[s], args) for s in sorted(strategies)]
    failed = [a["strategy"] for a in aggregates if a["gate"] != "PASS"]
    passed = not failed
    gate = {
        "verdict": "PASS" if passed else "FAIL",
        "passed": passed,
        "rule": GATE_RULE,
        "failed_strategies": failed,
        "banner": PASS_BANNER if passed else FAIL_BANNER,
    }

    manifest = build_manifest(args, out_dir, run_date, strategies, pairs, windows, window_records,
                              data_index, windows_run, windows_insufficient, degraded)
    manifest["runs"] = [
        {"window": r["window"], **run}
        for r in window_records for run in r.get("runs", [])
    ]
    manifest["runtime"] = {"total_elapsed_s": round(total_elapsed, 1),
                           "windows_run": windows_run,
                           "windows_insufficient": windows_insufficient}

    results = {
        "schema_version": SCHEMA_VERSION,
        "artifact": "walkforward",
        "phase": "2.2",
        "git_sha": manifest["git_sha"],
        "fee_model": manifest["fee_model"],
        "fee_ratio": manifest["fee_ratio"],
        "timeframe": manifest["timeframe"],
        "bootstrap": manifest["bootstrap"],
        "gate_rule": GATE_RULE,
        "gate": gate,
        "windows_run": windows_run,
        "windows_insufficient": windows_insufficient,
        "strategies": [a["strategy"] for a in aggregates],
        "aggregate": {a["strategy"]: a for a in aggregates},
    }

    windows_json = {
        "schema_version": SCHEMA_VERSION,
        "fee_model": manifest["fee_model"],
        "windows": [
            {
                "window": r["window"], "index": r["index"], "status": r["status"],
                "train_timerange": r["train_timerange"], "test_timerange": r["test_timerange"],
                "partial": r["partial"], "pairs_used": r["pairs_used"], "pairs": r["pairs"],
                "skipped_pairs": r["skipped_pairs"], "elapsed_s": r["elapsed_s"],
                "results": {s: {"status": e["status"], "metrics": e["metrics"],
                                "note": e["note"]}
                            for s, e in sorted(r["results"].items())},
            }
            for r in window_records
        ],
    }

    trades_dir = out_dir / "trades"
    trades_dir.mkdir(exist_ok=True)
    for strat in strategies:
        rows = []
        for entry in entries_by_strategy[strat]:
            for t in entry["trades_detail"]:
                rows.append({"window": entry["window"], "strategy": strat, **t})
        with (trades_dir / f"{strat}.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["window", "strategy", *TRADE_FIELDS])
            writer.writeheader()
            writer.writerows(rows)

    (out_dir / "walkforward.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (out_dir / "windows.json").write_text(json.dumps(windows_json, indent=2) + "\n", encoding="utf-8")
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "WALKFORWARD.md").write_text(
        render_markdown(manifest, aggregates, window_records, gate), encoding="utf-8")

    _print_aggregate_table(aggregates)
    print(f"[walkforward] windows_run={windows_run} insufficient={windows_insufficient} "
          f"elapsed={total_elapsed:.1f}s")
    print(f"[walkforward] manifest_hash={manifest['manifest_hash']}")
    print(f"[walkforward] wrote {out_dir / 'WALKFORWARD.md'}")

    if passed:
        print(f"\n{PASS_BANNER}\n", flush=True)
        return 0
    print(f"\n{'=' * 78}\n{FAIL_BANNER}\n{'=' * 78}\n", flush=True)
    for a in aggregates:
        if a["gate"] != "PASS":
            print(f"  - {a['strategy']}: " + "; ".join(a["gate_reasons"]))
    print("", flush=True)
    return 0 if args.allow_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
