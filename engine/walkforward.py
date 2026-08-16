"""
Walkforward Backtest Runner — split data into training/test windows,
run backtests, and report performance metrics.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class WalkforwardWindow:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_results: dict = field(default_factory=dict)
    test_results: dict = field(default_factory=dict)
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    train_sharpe: float = 0.0
    train_drawdown: float = 0.0


@dataclass
class WalkforwardReport:
    strategy: str
    timerange: str
    windows: list[WalkforwardWindow] = field(default_factory=list)
    avg_train_sharpe: float = 0.0
    avg_test_sharpe: float = 0.0
    avg_train_dd: float = 0.0
    avg_test_dd: float = 0.0
    combined_win_rate: float = 0.0
    total_trades: int = 0
    is_robust: bool = False
    generated_at: str = ""


def generate_windows(
    total_start: str,
    total_end: str,
    window_size_days: int = 90,
    test_size_days: int = 30,
    step_days: int = 30,
) -> list[WalkforwardWindow]:
    from datetime import timedelta

    start = datetime.strptime(total_start, "%Y%m%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(total_end, "%Y%m%d").replace(tzinfo=timezone.utc)
    windows = []
    cursor = start

    while cursor + timedelta(days=window_size_days + test_size_days) <= end:
        train_end = cursor + timedelta(days=window_size_days)
        test_end = train_end + timedelta(days=test_size_days)
        windows.append(WalkforwardWindow(
            train_start=cursor.strftime("%Y%m%d"),
            train_end=train_end.strftime("%Y%m%d"),
            test_start=train_end.strftime("%Y%m%d"),
            test_end=test_end.strftime("%Y%m%d"),
        ))
        cursor += timedelta(days=step_days)

    return windows


class WalkforwardRunner:
    def __init__(self, freqtrade_dir: Optional[str] = None):
        self.freqtrade_dir = freqtrade_dir or str(
            Path(__file__).parent.parent / "user_data"
        )
        self._results_cache: dict[str, WalkforwardReport] = {}

    def run(
        self,
        strategy: str,
        timerange: str,
        window_size_days: int = 90,
        test_size_days: int = 30,
        step_days: int = 30,
        config: Optional[str] = None,
    ) -> WalkforwardReport:
        total_start, total_end = timerange.split("-")
        windows = generate_windows(total_start, total_end, window_size_days, test_size_days, step_days)
        report = WalkforwardReport(
            strategy=strategy,
            timerange=timerange,
            windows=windows,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        for i, window in enumerate(windows):
            train_results = self._run_freqtrade_backtest(strategy, window.train_start, window.train_end, config)
            window.train_results = train_results
            test_results = self._run_freqtrade_backtest(strategy, window.test_start, window.test_end, config)
            window.test_results = test_results
            self._extract_metrics(window)

        self._compute_summary(report)
        self._results_cache[strategy] = report
        return report

    def _run_freqtrade_backtest(self, strategy: str, start: str, end: str,
                                config: Optional[str] = None) -> dict:
        cmd = [
            sys.executable, "-m", "freqtrade", "backtesting",
            "--strategy", strategy,
            "--timerange", f"{start}-{end}",
            "--datadir", self.freqtrade_dir,
            "--export", "none",
            "--verbosity", "0",
        ]
        if config:
            cmd.extend(["--config", config])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return {
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-1000:],
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout"}
        except FileNotFoundError:
            return {"success": False, "error": "freqtrade not found"}

    def _extract_metrics(self, window: WalkforwardWindow):
        import re
        for phase, results in [("train", window.train_results), ("test", window.test_results)]:
            if not results.get("success"):
                continue
            stdout = results.get("stdout", "")

            m = re.search(r"Sharpe:\s+([\d.]+)", stdout)
            if m:
                val = float(m.group(1))
                if phase == "train":
                    window.train_sharpe = val
                else:
                    window.sharpe = val

            m = re.search(r"Max drawdown:\s+([\d.]+)%", stdout)
            if m:
                val = float(m.group(1))
                if phase == "train":
                    window.train_drawdown = val
                else:
                    window.max_drawdown = val

            m = re.search(r"Total trades:\s+(\d+)", stdout)
            if m:
                window.num_trades = int(m.group(1))

            m = re.search(r"Win rate:\s+([\d.]+)%", stdout)
            if m:
                if phase == "test":
                    window.win_rate = float(m.group(1))

            m = re.search(r"Profit factor:\s+([\d.]+)", stdout)
            if m:
                if phase == "test":
                    window.total_pnl = float(m.group(1))

    def _compute_summary(self, report: WalkforwardReport):
        train_sharpes = [w.train_sharpe for w in report.windows if w.train_sharpe > 0]
        test_sharpes = [w.sharpe for w in report.windows if w.sharpe > 0]
        train_dds = [w.train_drawdown for w in report.windows if w.train_drawdown > 0]
        test_dds = [w.max_drawdown for w in report.windows if w.max_drawdown > 0]
        report.avg_train_sharpe = (sum(train_sharpes) / len(train_sharpes)) if train_sharpes else 0
        report.avg_test_sharpe = (sum(test_sharpes) / len(test_sharpes)) if test_sharpes else 0
        report.avg_train_dd = (sum(train_dds) / len(train_dds)) if train_dds else 0
        report.avg_test_dd = (sum(test_dds) / len(test_dds)) if test_dds else 0
        report.total_trades = sum(w.num_trades for w in report.windows)
        report.is_robust = (
            report.avg_test_sharpe > 0.5 and
            report.avg_train_sharpe > 0.5 and
            report.avg_test_dd < 20
        )


def run_backtest_window(strategy: str, start: str, end: str,
                        config: Optional[str] = None) -> dict:
    """Module-level wrapper for running a single backtest window."""
    runner = WalkforwardRunner()
    return runner._run_freqtrade_backtest(strategy, start, end, config)


def compute_report(strategy: str, windows: list[WalkforwardWindow]) -> WalkforwardReport:
    """Module-level wrapper for computing a walkforward summary report."""
    report = WalkforwardReport(strategy=strategy, timerange=f"{windows[0].train_start}-{windows[-1].test_end}" if windows else "")
    report.windows = windows
    runner = WalkforwardRunner()
    runner._compute_summary(report)
    return report
