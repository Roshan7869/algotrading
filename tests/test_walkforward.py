"""
Tests for Walkforward Backtest Runner
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.walkforward import generate_windows, WalkforwardWindow, WalkforwardReport, WalkforwardRunner


def test_generate_windows_basic():
    windows = generate_windows("20250101", "20250701", window_size_days=60, test_size_days=20, step_days=30)
    assert len(windows) >= 2


def test_generate_windows_single():
    windows = generate_windows("20250101", "20250301", window_size_days=30, test_size_days=10, step_days=30)
    assert len(windows) >= 1
    assert windows[0].train_start == "20250101"


def test_window_dates():
    windows = generate_windows("20250101", "20250701", window_size_days=60, test_size_days=20, step_days=30)
    w = windows[0]
    assert int(w.test_start) >= int(w.train_end)
    assert int(w.test_end) > int(w.test_start)


def test_no_windows_if_too_short():
    windows = generate_windows("20250101", "20250115", window_size_days=30, test_size_days=10)
    assert len(windows) == 0


def test_walkforward_window_dataclass():
    w = WalkforwardWindow(
        train_start="20250101",
        train_end="20250301",
        test_start="20250301",
        test_end="20250401",
    )
    assert w.train_start == "20250101"
    assert w.sharpe == 0.0
    assert w.num_trades == 0


def test_walkforward_report_dataclass():
    r = WalkforwardReport(strategy="Test", timerange="20250101-20250701")
    assert r.strategy == "Test"
    assert r.is_robust is False


def test_walkforward_runner_init():
    runner = WalkforwardRunner()
    assert runner.freqtrade_dir is not None
    assert "user_data" in runner.freqtrade_dir


def test_run_freqtrade_backtest_handles_error():
    runner = WalkforwardRunner(freqtrade_dir="/tmp")
    result = runner._run_freqtrade_backtest("NonExistent", "20250101", "20250201")
    assert "success" in result


def test_compute_summary_empty():
    report = WalkforwardReport(strategy="Test", timerange="20250101-20250701")
    runner = WalkforwardRunner()
    runner._compute_summary(report)
    assert report.avg_train_sharpe == 0.0
    assert report.avg_test_sharpe == 0.0


def test_extract_metrics_no_results():
    window = WalkforwardWindow(train_start="20250101", train_end="20250301",
                                test_start="20250301", test_end="20250401")
    window.train_results = {"success": False}
    runner = WalkforwardRunner()
    runner._extract_metrics(window)
    assert window.num_trades == 0
