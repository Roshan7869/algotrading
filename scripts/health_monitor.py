"""Health Monitor - Continuous system health checks"""

import os
import time
import psutil
import logging
import threading
from pathlib import Path
from typing import Optional


class HealthMonitor:
    """Monitors health of all system components."""

    def __init__(self, trading_pid: Optional[int], telegram_cb):
        self.logger = logging.getLogger("health_monitor")
        self.trading_pid = trading_pid
        self.telegram_cb = telegram_cb
        self.running = False
        self.monitor_thread = None
        self.check_interval = 60  # seconds

    def start(self):
        """Start monitoring in background thread."""
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """Stop monitoring."""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                status = self.check_all()
                self._log_status(status)

                # Alert on critical issues
                if status["overall"] == "CRITICAL":
                    self.logger.error(
                        "⚠️  SYSTEM CRITICAL - Immediate attention required"
                    )

            except Exception as e:
                self.logger.exception(f"Error in health check: {e}")

            time.sleep(self.check_interval)

    def check_all(self) -> dict:
        """Perform all health checks."""
        trading_status = self.check_trading_engine()
        telegram_status = self.check_telegram()
        system_status = self.check_system_resources()

        # Determine overall status
        overall = "OK"
        if trading_status == "CRITICAL":
            overall = "CRITICAL"
        elif telegram_status == "CRITICAL" or system_status == "WARNING":
            overall = "DEGRADED"

        return {
            "trading_engine": trading_status,
            "telegram": telegram_status,
            "system": system_status,
            "overall": overall,
            "timestamp": time.time(),
        }

    def check_trading_engine(self) -> str:
        """Check if Trading Engine is alive."""
        if not self.trading_pid:
            return "UNKNOWN"

        try:
            if psutil.pid_exists(self.trading_pid):
                proc = psutil.Process(self.trading_pid)
                if proc.is_running():
                    return "OK"
            return "CRITICAL"
        except Exception:
            return "CRITICAL"

    def check_telegram(self) -> str:
        """Check Telegram circuit breaker status."""
        if not self.telegram_cb:
            return "DISABLED"

        status = self.telegram_cb.get_status()
        state = status["state"]

        if state == "closed":
            return "OK"
        elif state == "disabled":
            return "DISABLED"
        else:
            return "DEGRADED"

    def check_system_resources(self) -> str:
        """Check CPU, memory, disk usage."""
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent

            if cpu > 90 or memory > 90 or disk > 90:
                self.logger.warning(
                    f"High resource usage: CPU={cpu}% MEM={memory}% DISK={disk}%"
                )
                return "WARNING"

            return "OK"
        except Exception:
            return "UNKNOWN"

    def _log_status(self, status: dict):
        """Log health status."""
        self.logger.info(
            f"Health Check: Trading={status['trading_engine']} "
            f"Telegram={status['telegram']} "
            f"System={status['system']} "
            f"Overall={status['overall']}"
        )
