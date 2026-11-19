"""Unit tests for Phase 2.2 `research/walkforward.py` (no freqtrade runs — pure logic only).

The backtest invocation itself is exercised by the smoke evidence in ``reports/phase2/2.2/``;
these tests pin the parts that decide whether a green run means anything: window arithmetic, the
bootstrap, the gate, and the no-result / insufficient-data paths.

Runs with the platform venv (which has no pytest installed):

    .venv/Scripts/python.exe -m unittest tests.phase2.test_walkforward -v

Plain `unittest` on purpose: a test file that cannot run is the same as no test file.
"""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (REPO_ROOT, REPO_ROOT / "research", REPO_ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import walkforward as wf  # noqa: E402
import scoreboard as sb  # noqa: E402


def _args(**over) -> SimpleNamespace:
    base = dict(bootstrap_resamples=200, seed=42, min_trades=30, batch=False)
    base.update(over)
    return SimpleNamespace(**base)


def _entry(strategy: str, window: str, ratios: list[float], status: str | None = None) -> dict:
    metrics = copy.deepcopy(sb.EMPTY_METRICS)
    metrics.update({
        "trades": len(ratios),
        "profit_pct": round(sum(ratios) * 100.0, 6) if ratios else 0.0,
        "expectancy_pct": round(sum(ratios) / len(ratios) * 100.0, 6) if ratios else None,
        "winrate_pct": None,
        "max_drawdown_pct": None,
    })
    return {
        "strategy": strategy,
        "window": window,
        "status": status or ("ok" if ratios else "no_trades"),
        "timerange": "20250101-20250201",
        "metrics": metrics,
        "trades_detail": [{"profit_ratio": r} for r in ratios],
        "elapsed_s": 1.0,
        "note": None,
    }


# --------------------------------------------------------------------------------------------------
# Window arithmetic
# --------------------------------------------------------------------------------------------------

class TestWindows(unittest.TestCase):
    def test_smoke_span_has_three_months_and_drops_short_tail(self):
        windows, dropped = wf.build_windows(date(2025, 8, 1), date(2025, 11, 1), 3, 1)
        self.assertEqual([w.label for w in windows], ["2025-08", "2025-09", "2025-10"])
        self.assertEqual(windows[0].train_timerange, "20250501-20250801")
        self.assertEqual(windows[0].test_timerange, "20250801-20250901")
        self.assertEqual(windows[1].train_timerange, "20250601-20250901")
        self.assertEqual(windows[2].test_timerange, "20251001-20251101")
        self.assertTrue(all(not w.partial for w in windows))
        # 2025-11 would be a single day (20251101-20251102): too short to measure, so dropped.
        self.assertEqual([d["label"] for d in dropped], ["2025-11"])

    def test_keeps_partial_tail_when_long_enough(self):
        windows, dropped = wf.build_windows(date(2026, 10, 1), date(2026, 11, 19), 6, 1)
        self.assertEqual([w.label for w in windows], ["2026-10", "2026-11"])
        self.assertTrue(windows[-1].partial)
        self.assertEqual(windows[-1].test_timerange, "20261101-20261120")  # END exclusive
        self.assertEqual(dropped, [])

    def test_train_window_never_overlaps_test_window(self):
        windows, _ = wf.build_windows(date(2024, 1, 1), date(2026, 11, 19), 6, 1)
        self.assertEqual(len(windows), 35)
        for w in windows:
            self.assertEqual(w.train_end, w.test_start)
            self.assertLess(w.train_start, w.train_end)
            self.assertLess(w.train_end, w.test_end)
            self.assertEqual(w.train_months, 6)

    def test_inverted_span_is_rejected(self):
        with self.assertRaises(SystemExit):
            wf.build_windows(date(2025, 2, 1), date(2025, 1, 1), 6, 1)

    def test_add_months_clamps_day(self):
        self.assertEqual(wf.add_months(date(2025, 1, 31), 1), date(2025, 2, 28))
        self.assertEqual(wf.add_months(date(2024, 3, 31), -1), date(2024, 2, 29))  # leap year


# --------------------------------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------------------------------

class TestBootstrap(unittest.TestCase):
    def test_seeded_and_brackets_the_mean(self):
        values = [0.01, 0.02, -0.01, 0.03, 0.005, -0.02, 0.015, 0.0, 0.025, -0.005] * 3
        a = wf.bootstrap_ci(values, resamples=500, seed=42)
        b = wf.bootstrap_ci(values, resamples=500, seed=42)
        self.assertEqual(a, b)
        self.assertEqual(a["n"], len(values))
        self.assertLess(a["ci_low"], a["mean"])
        self.assertLess(a["mean"], a["ci_high"])

    def test_empty_returns_none_bounds(self):
        out = wf.bootstrap_ci([])
        self.assertEqual(out["n"], 0)
        self.assertIsNone(out["ci_low"])
        self.assertIsNone(out["mean"])

    def test_all_positive_stays_positive(self):
        out = wf.bootstrap_ci([0.004] * 40 + [0.006] * 40, resamples=500, seed=42)
        self.assertGreater(out["ci_low"], 0)

    def test_window_level_needs_two_windows(self):
        one = wf.bootstrap_ci_windows([0.01])
        self.assertEqual(one["n_windows"], 1)
        self.assertIsNone(one["ci_low"])
        two = wf.bootstrap_ci_windows([0.01, 0.02], resamples=200, seed=42)
        self.assertIsNotNone(two["ci_low"])


# --------------------------------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------------------------------

class TestGate(unittest.TestCase):
    def test_passes_positive_edge_over_two_windows(self):
        entries = [
            _entry("S", "2025-01", [0.01, 0.02, 0.015, -0.005] * 5),
            _entry("S", "2025-02", [0.012, 0.018, 0.011, -0.004] * 5),
        ]
        out = wf.aggregate_strategy(entries, _args())
        self.assertEqual(out["gate"], "PASS")
        self.assertGreater(out["ci_low"], 0)
        self.assertEqual(out["n_trades"], 40)
        self.assertEqual(out["n_windows_evaluated"], 2)
        self.assertEqual(out["pct_positive_windows"], 100.0)

    def test_fails_negative_edge(self):
        entries = [
            _entry("S", "2025-01", [-0.01, -0.02, -0.015, -0.005] * 5),
            _entry("S", "2025-02", [-0.012, -0.018, -0.011, -0.004] * 5),
        ]
        out = wf.aggregate_strategy(entries, _args())
        self.assertEqual(out["gate"], "FAIL")
        self.assertTrue(any("ci_low" in r for r in out["gate_reasons"]))
        self.assertLess(out["ci_high"], 0)

    def test_insufficient_sample_fails_even_when_every_trade_wins(self):
        entries = [_entry("S", "2025-01", [0.05, 0.06]), _entry("S", "2025-02", [0.04])]
        out = wf.aggregate_strategy(entries, _args())
        self.assertEqual(out["gate"], "FAIL")
        self.assertTrue(any("min_trades" in r for r in out["gate_reasons"]))

    def test_all_no_result_fails(self):
        entries = [_entry("S", "2025-01", [], status="no_result"),
                   _entry("S", "2025-02", [], status="no_result")]
        out = wf.aggregate_strategy(entries, _args())
        self.assertEqual(out["gate"], "FAIL")
        self.assertEqual(out["n_trades"], 0)
        self.assertEqual(out["n_windows_no_result"], 2)
        self.assertTrue(any("no out-of-sample trades" in r for r in out["gate_reasons"]))

    def test_single_trading_window_fails(self):
        """One lucky month is not a walk-forward result: the gate needs >= 2 windows with trades."""
        entries = [_entry("S", "2025-01", [0.02] * 40), _entry("S", "2025-02", [])]
        out = wf.aggregate_strategy(entries, _args())
        self.assertEqual(out["gate"], "FAIL")
        self.assertTrue(any("windows_with_trades" in r for r in out["gate_reasons"]))

    def test_zero_trade_windows_count_as_non_positive(self):
        entries = [_entry("S", "2025-01", [0.02] * 40), _entry("S", "2025-02", []),
                   _entry("S", "2025-03", [0.02] * 40)]
        out = wf.aggregate_strategy(entries, _args())
        self.assertAlmostEqual(out["pct_positive_windows"], 66.67, places=2)


# --------------------------------------------------------------------------------------------------
# Fee label / scoreboard reuse
# --------------------------------------------------------------------------------------------------

class TestScoreboardReuse(unittest.TestCase):
    def test_fee_model_label_matches_scoreboard_string_at_default_fee(self):
        self.assertEqual(wf.fee_model_label(0.001), sb.FEE_MODEL)
        self.assertEqual(wf.fee_model_label(0.0005),
                         "fee_model: 5bps all-in (fee + slippage proxy)")

    def test_build_command_reads_scoreboard_fee_ratio(self):
        """build_command reads the scoreboard module global, so --fee must land there verbatim."""
        before = sb.FEE_RATIO
        try:
            sb.FEE_RATIO = 0.002
            cmd = sb.build_command(["S"], "20250101-20250201", ["BTC/USDT:USDT"], Path("."),
                                   sb.CONFIG_BACKTEST, "user_data")
            self.assertEqual(cmd[cmd.index("--fee") + 1], "0.002")
            self.assertEqual(cmd[cmd.index("--cache") + 1], "none")
        finally:
            sb.FEE_RATIO = before


# --------------------------------------------------------------------------------------------------
# Data sufficiency
# --------------------------------------------------------------------------------------------------

class _FakeIndex:
    """Maps pair -> (test_rows, train_rows); the window under test starts its test on 2025-01-01."""

    def __init__(self, rows: dict[str, tuple[int, int]]):
        self.rows = rows

    def rows_between(self, pair, start, end_excl):
        test_rows, train_rows = self.rows.get(pair, (0, 0))
        return test_rows if start == date(2025, 1, 1) else train_rows


def _jan_window() -> wf.Window:
    return wf.Window(index=1, label="2025-01", train_start=date(2024, 7, 1),
                     train_end=date(2025, 1, 1), test_start=date(2025, 1, 1),
                     test_end=date(2025, 2, 1), partial=False)


class TestDataSufficiency(unittest.TestCase):
    def test_skips_late_listed_pairs(self):
        pairs = ["BTC/USDT:USDT", "SEI/USDT:USDT"]
        index = _FakeIndex({"BTC/USDT:USDT": (700, 700), "SEI/USDT:USDT": (5, 700)})
        used, skipped = wf.window_pairs(_jan_window(), pairs, index)
        self.assertEqual(used, ["BTC/USDT:USDT"])
        self.assertEqual(skipped[0]["pair"], "SEI/USDT:USDT")
        self.assertIn("test_rows=5", skipped[0]["reason"])

    def test_skips_pairs_without_train_history(self):
        index = _FakeIndex({"BTC/USDT:USDT": (700, 10)})
        used, skipped = wf.window_pairs(_jan_window(), ["BTC/USDT:USDT"], index)
        self.assertEqual(used, [])
        self.assertIn("train_rows=10", skipped[0]["reason"])


# --------------------------------------------------------------------------------------------------
# Verify contract
# --------------------------------------------------------------------------------------------------

def _write_pair(directory: Path, ci_low: float, manifest_hash: str = "sha256:abc") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    results = {"aggregate": {"S": {"ci_low": ci_low, "n_trades": 100}},
               "gate": {"verdict": "FAIL"}, "windows_run": 3}
    (directory / "walkforward.json").write_text(json.dumps(results), encoding="utf-8")
    (directory / "MANIFEST.json").write_text(json.dumps({"manifest_hash": manifest_hash}),
                                             encoding="utf-8")


class TestVerify(unittest.TestCase):
    def test_matches_identical_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            _write_pair(a, -0.01234)
            _write_pair(b, -0.0123404)  # differs below the 4th dp only
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = wf.verify_dirs(a, b)
            self.assertEqual(rc, 0)
            self.assertIn("MATCH", buf.getvalue())

    def test_flags_metric_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            _write_pair(a, -0.01234)
            _write_pair(b, -0.01239)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(wf.verify_dirs(a, b), 1)

    def test_flags_manifest_hash_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            _write_pair(a, -0.01, manifest_hash="sha256:aaa")
            _write_pair(b, -0.01, manifest_hash="sha256:bbb")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(wf.verify_dirs(a, b), 1)


if __name__ == "__main__":
    unittest.main()
