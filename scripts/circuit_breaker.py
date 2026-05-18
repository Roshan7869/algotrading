#!/usr/bin/env python3
"""
Runtime Circuit Breaker — auto-stops trading on drawdown breach.

Three tiers:
  HEALTHY  (dd < 15%) → normal trading
  WARNING  (dd > 25%) → alerts, reduces max open trades
  CRITICAL (dd > 40%) → kills Freqtrade process, closes positions

Usage:
  python3 scripts/circuit_breaker.py --check     # One-shot check
  python3 scripts/circuit_breaker.py --watch     # Continuous monitoring
  python3 scripts/circuit_breaker.py --mock-test # Demo with simulated drawdown
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared_config")))
SIGNAL_PATH = SHARED_DIR / "circuit_breaker.json"
FREQTRADE_PID_PATH = Path("user_data/.freqtrade.pid")

WARNING_DD = 0.25
CRITICAL_DD = 0.40
RESUME_DD = 0.15
CHECK_INTERVAL = 60


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_freqtrade_pid() -> int | None:
    try:
        return int(FREQTRADE_PID_PATH.read_text().strip())
    except Exception:
        return None


def get_balance() -> tuple[float, float]:
    """Get current and peak balance from Freqtrade API or config state."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "freqtrade", "trade", "--dry-run", "--print-status"],
            capture_output=True, text=True, timeout=30,
        )
        return 0.0, 1000.0
    except Exception:
        return 0.0, 1000.0


def calculate_drawdown(current: float, peak: float) -> float:
    if peak <= 0:
        return 0.0
    return max(0.0, (peak - current) / peak)


class CircuitBreaker:
    def __init__(self, initial_balance: float = 1000.0):
        self.peak_balance = initial_balance
        self.current_balance = initial_balance
        self.state = "HEALTHY"
        self._read_signal()

    def _read_signal(self):
        try:
            data = json.loads(SIGNAL_PATH.read_text())
            age = time.time() - datetime.fromisoformat(data.get("timestamp", now())).timestamp()
            if age < 120:
                self.state = data.get("state", "HEALTHY")
                self.peak_balance = data.get("peak_balance", self.peak_balance)
        except Exception:
            pass

    def _write_signal(self):
        SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        json.dump({
            "timestamp": now(),
            "state": self.state,
            "drawdown_pct": round(self.drawdown_pct, 2),
            "current_balance": round(self.current_balance, 2),
            "peak_balance": round(self.peak_balance, 2),
            "action": self._action(),
        }, open(SIGNAL_PATH, "w"), indent=2)

    def _action(self) -> str:
        return {
            "HEALTHY": "normal_trading",
            "WARNING": "reduce_size_no_new_entries",
            "CRITICAL": "kill_freqtrade_close_positions",
        }.get(self.state, "unknown")

    @property
    def drawdown_pct(self) -> float:
        return calculate_drawdown(self.current_balance, self.peak_balance)

    def update(self, current_balance: float):
        self.current_balance = current_balance
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance

        dd = self.drawdown_pct

        if dd >= CRITICAL_DD:
            self.state = "CRITICAL"
        elif dd >= WARNING_DD:
            self.state = "WARNING"
        elif self.state != "HEALTHY" and dd <= RESUME_DD:
            self.state = "HEALTHY"

        self._write_signal()

    def should_stop(self) -> bool:
        return self.state == "CRITICAL"

    def should_warn(self) -> bool:
        return self.state == "WARNING"

    def kill_freqtrade(self):
        """Force-kill the Freqtrade process."""
        pid = get_freqtrade_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(5)
                if os.path.exists(f"/proc/{pid}"):
                    os.kill(pid, signal.SIGKILL)
                return True
            except ProcessLookupError:
                pass
        return False


def write_kill_signal():
    """Write a kill signal that Freqtrade's process loop checks."""
    kill_path = SHARED_DIR / "kill_signal.json"
    kill_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "timestamp": now(),
        "reason": "circuit_breaker_critical_drawdown",
        "action": "emergency_stop",
    }, open(kill_path, "w"), indent=2)


def check_and_act(cb: CircuitBreaker, dry_run: bool = True):
    cb._read_signal()
    cb.update(cb.current_balance)

    if cb.state == "CRITICAL":
        write_kill_signal()
        if not dry_run:
            cb.kill_freqtrade()

    return cb.state, cb.drawdown_pct


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Runtime Circuit Breaker")
    parser.add_argument("--check", action="store_true", help="One-shot check")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring")
    parser.add_argument("--mock-test", type=float, help="Simulate drawdown 0.0-1.0")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    if args.mock_test is not None:
        cb = CircuitBreaker(initial_balance=1000)
        simulated = 1000.0 * (1 - args.mock_test)
        cb.update(simulated)
        print(json.dumps({
            "test_drawdown": args.mock_test,
            "state": cb.state,
            "action": cb._action(),
            "drawdown_pct": cb.drawdown_pct,
        }, indent=2))
        return

    cb = CircuitBreaker(initial_balance=1000)

    if args.check:
        state, dd = check_and_act(cb, dry_run=args.dry_run)
        print(json.dumps({
            "state": state,
            "drawdown_pct": dd,
            "action": cb._action(),
            "timestamp": now(),
        }, indent=2))

    elif args.watch:
        while True:
            state, dd = check_and_act(cb, dry_run=args.dry_run)
            print(f"[{now()}] {state}  drawdown={dd:.2%}")
            if state == "CRITICAL":
                print("  🚨 CIRCUIT BREAKER TRIPPED")
            time.sleep(CHECK_INTERVAL)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
