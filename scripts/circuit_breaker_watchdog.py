#!/usr/bin/env python3
"""
Circuit Breaker Watchdog — runs alongside Freqtrade.
Checks kill signal every N seconds. If triggered, kills Freqtrade.

Usage:
  python3 scripts/circuit_breaker_watchdog.py            # Auto-detect PID
  python3 scripts/circuit_breaker_watchdog.py --pid 1234 # Explicit PID
  python3 scripts/circuit_breaker_watchdog.py --dry-run  # Print only, no kill
"""

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared_config")))
KILL_SIGNAL_PATH = SHARED_DIR / "kill_signal.json"
BREAKER_PATH = SHARED_DIR / "circuit_breaker.json"
PID_FILE = Path("user_data/.freqtrade.pid")
POLL_INTERVAL = 30


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def read_kill_signal() -> dict | None:
    try:
        data = json.loads(KILL_SIGNAL_PATH.read_text())
        age = time.time() - datetime.fromisoformat(data["timestamp"]).timestamp()
        if age < 300:
            return data
    except Exception:
        return None
    return None


def clear_kill_signal():
    try:
        KILL_SIGNAL_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def kill_freqtrade(pid: int, force: bool = False) -> bool:
    try:
        print(f"[{now()}] Sending SIGTERM to Freqtrade (pid={pid})")
        os.kill(pid, signal.SIGTERM)
        time.sleep(5)
        if os.path.exists(f"/proc/{pid}"):
            print(f"[{now()}] Process still alive, sending SIGKILL")
            os.kill(pid, signal.SIGKILL)
        clear_kill_signal()
        print(f"[{now()}] Freqtrade terminated")
        return True
    except ProcessLookupError:
        print(f"[{now()}] Process {pid} already dead")
        clear_kill_signal()
        return True
    except Exception as e:
        print(f"[{now()}] Error killing process: {e}")
        return False


def read_breaker_state() -> str:
    try:
        return json.loads(BREAKER_PATH.read_text()).get("state", "HEALTHY")
    except Exception:
        return "HEALTHY"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Circuit Breaker Watchdog")
    parser.add_argument("--pid", type=int, help="Freqtrade PID")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no kill")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL)
    args = parser.parse_args()

    pid = args.pid or read_pid()
    if not pid:
        print(f"[{now()}] No Freqtrade PID found. Is it running?")
        sys.exit(1)

    print(f"[{now()}] Watchdog active — monitoring Freqtrade (pid={pid})")
    print(f"[{now()}] Poll interval: {args.interval}s")

    while True:
        state = read_breaker_state()
        kill_sig = read_kill_signal()

        if kill_sig or state == "CRITICAL":
            action = kill_sig.get("action", "emergency_stop") if kill_sig else "circuit_breaker"
            reason = kill_sig.get("reason", "drawdown_limit_breached") if kill_sig else state
            print(f"[{now()}] 🚨 KILL SIGNAL: {action} ({reason})")

            if args.dry_run:
                print(f"[{now()}] DRY RUN — would kill pid={pid}")
            else:
                kill_freqtrade(pid)
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
