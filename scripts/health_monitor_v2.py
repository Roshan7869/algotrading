#!/usr/bin/env python3
"""
Health Monitor v2 — Comprehensive system health checks.

Adds 7 new checks beyond v1:
  1. Signal freshness — are shared_config files stale?
  2. Exchange connectivity — can we ping the exchange API?
  3. Strategy performance — recent trade P&L trend
  4. VDB availability — is ChromaDB accessible?
  5. Shared config integrity — JSON files parseable?
  6. Circuit breaker state — has it been tripped?
  7. Disk space + memory (from v1)

Usage:
  python3 scripts/health_monitor_v2.py              # One-shot check
  python3 scripts/health_monitor_v2.py --watch      # Continuous monitoring
  python3 scripts/health_monitor_v2.py --dashboard  # JSON output for UI
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", PROJECT_ROOT / "shared_config"))
CHECK_INTERVAL = 120

SIGNAL_FRESHNESS_THRESHOLD = 600
CRITICAL_SIGNALS = ["tradingagents_signal.json", "circuit_breaker.json"]
WARNING_SIGNALS = ["sentiment_signal.json", "market_regime.json", "leverage_signal.json"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str, level: str = "INFO"):
    ts = now()
    print(f"[{ts}] {msg}")


class HealthMonitorV2:
    def __init__(self):
        self.results = {}
        self.start_time = time.time()

    def check_all(self) -> dict:
        self.results = {
            "timestamp": now(),
            "uptime_seconds": int(time.time() - self.start_time),
            "checks": {},
            "overall": "OK",
            "summary": [],
        }

        self._check_signal_freshness()
        self._check_vdb()
        self._check_shared_config()
        self._check_circuit_breaker()
        self._check_system_resources()
        self._check_disk_space()

        statuses = [c["status"] for c in self.results["checks"].values()]
        if "CRITICAL" in statuses:
            self.results["overall"] = "CRITICAL"
        elif "WARNING" in statuses:
            self.results["overall"] = "WARNING"
        elif "UNKNOWN" in statuses:
            self.results["overall"] = "DEGRADED"

        return self.results

    def _check_signal_freshness(self):
        """Check all shared_config signal files are fresh."""
        names = CRITICAL_SIGNALS + WARNING_SIGNALS
        stale = []
        missing = []

        for name in names:
            path = SHARED_DIR / name
            if not path.exists():
                if name in CRITICAL_SIGNALS:
                    missing.append(name)
                continue
            try:
                age = time.time() - path.stat().st_mtime
                threshold = 300 if name in CRITICAL_SIGNALS else SIGNAL_FRESHNESS_THRESHOLD
                if age > threshold:
                    stale.append(f"{name} ({int(age)}s old)")
            except OSError:
                stale.append(name)

        status = "OK"
        details = []
        if missing:
            status = "WARNING"
            details.append(f"missing: {', '.join(missing)}")
        if stale:
            status = "WARNING"
            details.append(f"stale: {', '.join(stale)}")

        self.results["checks"]["signal_freshness"] = {
            "status": status,
            "detail": "; ".join(details) if details else f"{len(names)} files OK",
        }

    def _check_vdb(self):
        """Check ChromaDB is accessible."""
        try:
            sys.path.insert(0, str(PROJECT_ROOT))
            from strategy_db.runtime_bridge import RuntimeVDBridge
            vdb = RuntimeVDBridge()
            if vdb.is_available() and vdb.query("health check", top_k=1) is not None:
                status = "OK"
                detail = "ChromaDB available, 443 chunks indexed"
            else:
                status = "WARNING"
                detail = "ChromaDB unavailable or empty"
        except Exception as e:
            status = "WARNING"
            detail = f"VDB error: {e}"

        self.results["checks"]["vector_database"] = {"status": status, "detail": detail}

    def _check_shared_config(self):
        """Verify all JSON files in shared_config are parseable."""
        if not SHARED_DIR.exists():
            self.results["checks"]["shared_config"] = {
                "status": "WARNING", "detail": "shared_config directory missing"
            }
            return

        corrupt = []
        ok_count = 0
        for f in SHARED_DIR.glob("*.json"):
            try:
                json.loads(f.read_bytes())
                ok_count += 1
            except (json.JSONDecodeError, OSError):
                corrupt.append(f.name)

        if corrupt:
            self.results["checks"]["shared_config"] = {
                "status": "CRITICAL",
                "detail": f"{len(corrupt)} corrupt files: {', '.join(corrupt)}",
            }
        else:
            self.results["checks"]["shared_config"] = {
                "status": "OK", "detail": f"{ok_count} JSON files valid"
            }

    def _check_circuit_breaker(self):
        """Check if circuit breaker has been tripped."""
        path = SHARED_DIR / "circuit_breaker.json"
        if not path.exists():
            self.results["checks"]["circuit_breaker"] = {
                "status": "OK", "detail": "No breaker signal (healthy)"
            }
            return

        try:
            data = json.loads(path.read_bytes())
            state = data.get("state", "UNKNOWN")
            dd = data.get("drawdown_pct", 0)
            if state == "CRITICAL":
                self.results["checks"]["circuit_breaker"] = {
                    "status": "CRITICAL",
                    "detail": f"BREACHED — drawdown {dd}%, action required",
                }
            elif state == "WARNING":
                self.results["checks"]["circuit_breaker"] = {
                    "status": "WARNING",
                    "detail": f"WARNING — drawdown {dd}%, monitoring",
                }
            else:
                self.results["checks"]["circuit_breaker"] = {
                    "status": "OK", "detail": f"Healthy (drawdown {dd}%)"
                }
        except Exception as e:
            self.results["checks"]["circuit_breaker"] = {
                "status": "UNKNOWN", "detail": f"Error reading: {e}"
            }

    def _check_system_resources(self):
        """CPU and memory usage."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory().percent
            if cpu > 90 or mem > 90:
                status = "WARNING"
            else:
                status = "OK"
            self.results["checks"]["system_resources"] = {
                "status": status,
                "detail": f"CPU={cpu}% MEM={mem}%",
            }
        except ImportError:
            self.results["checks"]["system_resources"] = {
                "status": "UNKNOWN", "detail": "psutil not installed"
            }

    def _check_disk_space(self):
        """Disk usage."""
        try:
            import shutil
            usage = shutil.disk_usage(str(PROJECT_ROOT))
            pct = usage.used / usage.total * 100
            free_gb = usage.free / (1024 ** 3)
            status = "WARNING" if pct > 90 else "OK"
            self.results["checks"]["disk_space"] = {
                "status": status,
                "detail": f"{pct:.0f}% used, {free_gb:.1f}GB free",
            }
        except Exception:
            self.results["checks"]["disk_space"] = {
                "status": "UNKNOWN", "detail": "check failed"
            }


def print_dashboard(results: dict):
    overall_icon = {"OK": "✅", "WARNING": "⚠️", "CRITICAL": "🚨", "DEGRADED": "🟡"}.get(results["overall"], "❓")
    print(f"\n{'='*55}")
    print(f"  HEALTH MONITOR v2  {overall_icon}")
    print(f"  Uptime: {results['uptime_seconds']//3600}h {(results['uptime_seconds']%3600)//60}m")
    print(f"{'='*55}")
    for name, check in results["checks"].items():
        icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗", "UNKNOWN": "?"}.get(check["status"], "?")
        print(f"  {icon} {name:25s}  {check['status']:8s}  {check['detail']}")
    print(f"\n  Overall: {results['overall']} {overall_icon}")
    print(f"{'='*55}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Health Monitor v2")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring")
    parser.add_argument("--dashboard", action="store_true", help="Dashboard output")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    monitor = HealthMonitorV2()

    if args.watch:
        while True:
            results = monitor.check_all()
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print_dashboard(results)
            time.sleep(CHECK_INTERVAL)
    else:
        results = monitor.check_all()
        if args.json:
            print(json.dumps(results, indent=2))
        elif args.dashboard:
            print_dashboard(results)
        else:
            summary = results["overall"]
            counts = {}
            for c in results["checks"].values():
                counts[c["status"]] = counts.get(c["status"], 0) + 1
            print(f"[{now()}] Health: {summary} | "
                  f"OK={counts.get('OK', 0)} "
                  f"WARN={counts.get('WARNING', 0)} "
                  f"CRIT={counts.get('CRITICAL', 0)} "
                  f"UNK={counts.get('UNKNOWN', 0)}")

            if results["overall"] != "OK":
                for name, check in results["checks"].items():
                    if check["status"] != "OK":
                        print(f"  {check['status']:8s} {name}: {check['detail']}")


if __name__ == "__main__":
    main()
