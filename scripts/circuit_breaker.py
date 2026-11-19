#!/usr/bin/env python3
"""
Runtime Circuit Breaker — auto-stops trading on drawdown breach.

Three tiers:
  HEALTHY  (dd < 15%) → normal trading
  WARNING  (dd > 25%) → alerts, reduces max open trades
  CRITICAL (dd > 40%) → kills Freqtrade process, closes positions

Fail-closed: if the account balance cannot be read from the local freqtrade
REST API, no drawdown is invented. The breaker writes state "UNKNOWN" and the
one-shot check exits with code 2 so the orchestrator does not proceed.

Usage:
  python3 scripts/circuit_breaker.py --check     # One-shot check
  python3 scripts/circuit_breaker.py --watch     # Continuous monitoring
  python3 scripts/circuit_breaker.py --mock-test # Demo with simulated drawdown
"""

import base64
import json
import math
import os
import signal
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared_config")))
SIGNAL_PATH = SHARED_DIR / "circuit_breaker.json"
FREQTRADE_PID_PATH = Path("user_data/.freqtrade.pid")

REPO_ROOT = Path(__file__).resolve().parent.parent
API_TIMEOUT = 5.0
API_PASSWORD_FILE = Path.home() / ".config" / "freqtrade" / "api_password"
API_CONFIG_CANDIDATES = (
    REPO_ROOT / "user_data" / "config.json",
    REPO_ROOT / "user_data" / "config_live_real.json",
    REPO_ROOT / "user_data" / "config_api.json",
)

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


def _as_float(value) -> float | None:
    """Coerce an API value to a finite float, or None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _load_api_server_config() -> dict:
    """Return the api_server block of the bot config (localhost REST API)."""
    candidates = []
    env_config = os.getenv("FREQTRADE_CONFIG")
    if env_config:
        candidates.append(Path(env_config))
    candidates.extend(API_CONFIG_CANDIDATES)

    for path in candidates:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        api_server = config.get("api_server") if isinstance(config, dict) else None
        if isinstance(api_server, dict):
            return api_server
    return {}


def _resolve_api_credentials(api_server: dict) -> tuple[str, str, int] | None:
    """Resolve (username, password, port); password from env, then the 600 file."""
    try:
        port = int(os.getenv("FREQTRADE_API_PORT") or api_server.get("listen_port") or 8080)
    except (TypeError, ValueError):
        port = 8080
    username = os.getenv("FREQTRADE_API_USERNAME") or api_server.get("username") or "freqtrader"

    password = os.getenv("FREQTRADE_API_PASSWORD") or ""
    if not password:
        try:
            password = API_PASSWORD_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            password = ""
    if not password:
        # Last resort: the password declared next to the configured api_server.
        password = str(api_server.get("password") or "")

    if not password:
        return None
    return username, password, port


def _api_get(path: str, port: int, username: str, password: str):
    """GET a freqtrade REST endpoint with HTTP Basic auth (urllib only)."""
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def get_balance() -> tuple[float | None, float | None]:
    """Return (current_balance, starting_balance) from the freqtrade REST API.

    Fail-CLOSED: returns (None, None) when the API is unreachable, rejects the
    credentials, or answers without a parseable balance. Numbers are never
    invented — an unknown balance must not look like a healthy one.
    """
    credentials = _resolve_api_credentials(_load_api_server_config())
    if credentials is None:
        return None, None
    username, password, port = credentials

    # /api/v1/profit carries both the live equity and the account's start value.
    try:
        profit = _api_get("/api/v1/profit", port, username, password)
        current = _as_float(profit.get("current_balance"))
        starting = _as_float(profit.get("starting_balance"))
        if current is not None:
            return current, starting
    except Exception:
        pass

    # /api/v1/balance carries the wallet total; show_config supplies dry_run_wallet.
    try:
        balance = _api_get("/api/v1/balance", port, username, password)
        current = _as_float(balance.get("total"))
        if current is not None:
            starting = None
            try:
                config = _api_get("/api/v1/show_config", port, username, password)
                starting = _as_float(config.get("dry_run_wallet"))
            except Exception:
                starting = None
            return current, starting
    except Exception:
        pass

    return None, None


def calculate_drawdown(current: float | None, peak: float | None) -> float | None:
    """Drawdown fraction, or None when either balance is unknown.

    Returning 0.0 for missing data is what made the old stub unable to trip.
    """
    if current is None or peak is None or peak <= 0:
        return None
    return max(0.0, (peak - current) / peak)


class CircuitBreaker:
    def __init__(self, initial_balance: float | None = None):
        self.peak_balance = initial_balance
        self.current_balance = None
        self.state = "HEALTHY"
        self._read_signal()

    def _read_signal(self):
        try:
            data = json.loads(SIGNAL_PATH.read_text())
            age = time.time() - datetime.fromisoformat(data.get("timestamp", now())).timestamp()
            if age < 120:
                self.state = data.get("state", "HEALTHY")
                peak = _as_float(data.get("peak_balance"))
                if peak is not None:
                    self.peak_balance = peak
        except Exception:
            pass

    def _write_signal(self):
        SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        drawdown = self.drawdown_pct
        json.dump({
            "timestamp": now(),
            "state": self.state,
            "drawdown_pct": round(drawdown, 2) if drawdown is not None else None,
            "current_balance": round(self.current_balance, 2) if self.current_balance is not None else None,
            "peak_balance": round(self.peak_balance, 2) if self.peak_balance is not None else None,
            "action": self._action(),
        }, open(SIGNAL_PATH, "w"), indent=2)

    def _action(self) -> str:
        return {
            "HEALTHY": "normal_trading",
            "WARNING": "reduce_size_no_new_entries",
            "CRITICAL": "kill_freqtrade_close_positions",
            "UNKNOWN": "fail_closed_do_not_trade",
        }.get(self.state, "unknown")

    @property
    def drawdown_pct(self) -> float | None:
        return calculate_drawdown(self.current_balance, self.peak_balance)

    def update(self, current_balance: float | None = None) -> str:
        if current_balance is None:
            self.current_balance = None
            self.state = "UNKNOWN"
            self._write_signal()
            return self.state

        self.current_balance = current_balance
        if self.peak_balance is None or current_balance > self.peak_balance:
            self.peak_balance = current_balance

        dd = self.drawdown_pct

        if dd is None:
            self.state = "UNKNOWN"
        elif dd >= CRITICAL_DD:
            self.state = "CRITICAL"
        elif dd >= WARNING_DD:
            self.state = "WARNING"
        elif self.state != "HEALTHY" and dd <= RESUME_DD:
            self.state = "HEALTHY"

        self._write_signal()
        return self.state

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
    """Fetch the balance and update the breaker. Returns (state, drawdown|None)."""
    cb._read_signal()

    current, starting = get_balance()
    if current is None:
        # Fail-closed: unknown equity must never be reported as healthy.
        cb.current_balance = None
        cb.state = "UNKNOWN"
        cb._write_signal()
        return cb.state, None

    # Peak = highest of persisted peak, account starting balance and current equity.
    for candidate in (starting, current):
        if candidate is not None and (cb.peak_balance is None or candidate > cb.peak_balance):
            cb.peak_balance = candidate

    cb.update(current)

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

    cb = CircuitBreaker()

    if args.check:
        state, dd = check_and_act(cb, dry_run=args.dry_run)
        print(json.dumps({
            "state": state,
            "drawdown_pct": dd,
            "action": cb._action(),
            "timestamp": now(),
        }, indent=2))
        if state == "UNKNOWN":
            print(
                "circuit_breaker: balance unavailable via freqtrade API — failing closed (exit 2)",
                file=sys.stderr,
            )
            sys.exit(2)

    elif args.watch:
        while True:
            state, dd = check_and_act(cb, dry_run=args.dry_run)
            drawdown_text = "unknown" if dd is None else f"{dd:.2%}"
            print(f"[{now()}] {state}  drawdown={drawdown_text}")
            if state == "CRITICAL":
                print("  🚨 CIRCUIT BREAKER TRIPPED")
            elif state == "UNKNOWN":
                print("  ⚠️  balance unavailable — state file says UNKNOWN (fail-closed)")
            time.sleep(CHECK_INTERVAL)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
