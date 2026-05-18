#!/usr/bin/env python3
"""
Trading System Orchestrator - Fault-Tolerant Entry Point
Manages all subsystems with error isolation.
"""

import os
import sys
import time
import signal
import logging
import subprocess
import multiprocessing as mp
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.resilient_telegram import TelegramCircuitBreaker
from scripts.health_monitor import HealthMonitor
from scripts.process_manager import ProcessManager
from scripts.logging_config import setup_logging


class TradingOrchestrator:
    """Main orchestrator that manages all system components."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.logger = logging.getLogger("orchestrator")
        self.process_manager = ProcessManager()
        self.health_monitor = None
        self.telegram_cb = None
        self.trading_process = None
        self.running = False

    def start(self):
        """Start all components with fault isolation."""
        self.logger.info("=" * 60)
        self.logger.info("TRADING SYSTEM ORCHESTRATOR STARTING")
        self.logger.info("=" * 60)

        # Step 1: Ensure single instance
        try:
            self.process_manager.ensure_single_instance()
        except RuntimeError as e:
            self.logger.critical(f"Cannot start: {e}")
            return False

        # Step 2: Start Trading Engine (CRITICAL)
        if not self._start_trading_engine():
            self.logger.critical("Failed to start Trading Engine")
            return False

        # Step 3: Start Telegram (NON-CRITICAL)
        self._start_telegram_module()

        # Step 4: Start Health Monitor
        self._start_health_monitor()

        # Step 5: Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.running = True
        self.logger.info("✅ All components started - System OPERATIONAL")

        # Main loop
        self._run_main_loop()

    def _start_trading_engine(self) -> bool:
        """Start Freqtrade in subprocess."""
        self.logger.info("Starting Trading Engine...")

        try:
            cmd = [
                "freqtrade",
                "trade",
                "-c",
                self.config_path,
                "--logfile",
                "logs/trading_engine.log",
            ]

            self.trading_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            # Wait a few seconds to check if it crashes immediately
            time.sleep(3)
            if self.trading_process.poll() is not None:
                self.logger.error("Trading Engine crashed on startup")
                return False

            self.process_manager.write_pidfile(self.trading_process.pid)
            self.logger.info(
                f"✅ Trading Engine started (PID: {self.trading_process.pid})"
            )
            return True

        except Exception as e:
            self.logger.exception(f"Failed to start Trading Engine: {e}")
            return False

    def _start_telegram_module(self):
        """Start Telegram with Circuit Breaker (non-critical)."""
        self.logger.info("Starting Telegram Module...")

        try:
            self.telegram_cb = TelegramCircuitBreaker()

            # Test connection
            if self.telegram_cb.test_connection():
                self.logger.info("✅ Telegram Module initialized")
            else:
                self.logger.warning(
                    "⚠️  Telegram Module DEGRADED (will continue without it)"
                )

        except Exception as e:
            self.logger.error(f"Telegram initialization failed: {e}")
            self.logger.info("System will continue without Telegram")

    def _start_health_monitor(self):
        """Start health monitoring."""
        self.logger.info("Starting Health Monitor...")

        try:
            self.health_monitor = HealthMonitor(
                trading_pid=self.trading_process.pid if self.trading_process else None,
                telegram_cb=self.telegram_cb,
            )
            self.health_monitor.start()
            self.logger.info("✅ Health Monitor started")

        except Exception as e:
            self.logger.error(f"Health Monitor failed: {e}")
            # Non-critical, continue

    def _run_main_loop(self):
        """Main monitoring loop."""
        self.logger.info("Entering main loop - Press Ctrl+C to stop")

        while self.running:
            try:
                # Check if Trading Engine is still alive
                if self.trading_process and self.trading_process.poll() is not None:
                    self.logger.critical("⚠️  Trading Engine has stopped!")
                    self._attempt_recovery()

                time.sleep(10)  # Check every 10 seconds

            except KeyboardInterrupt:
                self.logger.info("Shutdown requested by user")
                break
            except Exception as e:
                self.logger.exception(f"Error in main loop: {e}")

        self.shutdown()

    def _attempt_recovery(self):
        """Attempt to restart Trading Engine."""
        self.logger.warning("Attempting to restart Trading Engine...")

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            self.logger.info(f"Recovery attempt {attempt}/{max_retries}")

            if self._start_trading_engine():
                self.logger.info("✅ Trading Engine recovered")
                return True

            time.sleep(30)  # Wait before retry

        self.logger.critical("❌ Recovery failed - shutting down")
        self.running = False
        return False

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}")
        self.running = False

    def shutdown(self):
        """Graceful shutdown of all components."""
        self.logger.info("=" * 60)
        self.logger.info("SHUTTING DOWN SYSTEM")
        self.logger.info("=" * 60)

        # Stop health monitor
        if self.health_monitor:
            self.health_monitor.stop()

        # Stop Trading Engine
        if self.trading_process:
            self.logger.info("Stopping Trading Engine...")
            self.trading_process.terminate()
            try:
                self.trading_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.logger.warning("Force killing Trading Engine")
                self.trading_process.kill()

        # Cleanup
        self.process_manager.cleanup()
        self.logger.info("✅ Shutdown complete")


def main():
    # Setup logging
    setup_logging()

    # Get config path from args
    if len(sys.argv) < 2:
        config_path = "user_data/config_live_trading_6x.json"
        print(f"No config specified, using default: {config_path}")
    else:
        config_path = sys.argv[1]

    # Verify config exists
    if not Path(config_path).exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    orchestrator = TradingOrchestrator(config_path)
    orchestrator.start()


if __name__ == "__main__":
    main()
