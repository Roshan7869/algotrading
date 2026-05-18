"""Process Manager - Ensure single Freqtrade instance"""

import os
import psutil
import logging
from pathlib import Path


class ProcessManager:
    """Manages process lifecycle and ensures single instance."""

    PIDFILE = Path("/tmp/freqtrade_orchestrator.pid")

    def __init__(self):
        self.logger = logging.getLogger("process_manager")

    def ensure_single_instance(self):
        """Kill zombie processes and ensure clean start."""
        if self.PIDFILE.exists():
            self.logger.warning(f"PID file exists: {self.PIDFILE}")

            try:
                with open(self.PIDFILE) as f:
                    old_pid = int(f.read().strip())

                if psutil.pid_exists(old_pid):
                    self.logger.warning(f"Process {old_pid} still running")

                    # Check if it's actually freqtrade
                    proc = psutil.Process(old_pid)
                    if "freqtrade" in " ".join(proc.cmdline()).lower():
                        self.logger.warning(
                            f"Terminating old Freqtrade process {old_pid}"
                        )
                        proc.terminate()
                        proc.wait(timeout=10)
                        self.logger.info("Old process terminated")
                    else:
                        self.logger.warning(
                            f"PID {old_pid} is not Freqtrade - ignoring"
                        )

                # Remove stale PID file
                self.PIDFILE.unlink()
                self.logger.info("Removed stale PID file")

            except Exception as e:
                self.logger.error(f"Error cleaning up old process: {e}")
                raise RuntimeError("Cannot ensure single instance")

        # Additional check: kill any freqtrade processes
        self._kill_freqtrade_zombies()

    def _kill_freqtrade_zombies(self):
        """Find and kill zombie Freqtrade processes."""
        killed = 0

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "freqtrade" in cmdline.lower() and "trade" in cmdline.lower():
                    self.logger.warning(f"Found zombie Freqtrade: PID {proc.pid}")
                    proc.terminate()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if killed:
            self.logger.info(f"Terminated {killed} zombie process(es)")

    def write_pidfile(self, pid: int):
        """Write current PID to file."""
        self.PIDFILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.PIDFILE, "w") as f:
            f.write(str(pid))
        self.logger.info(f"Wrote PID {pid} to {self.PIDFILE}")

    def cleanup(self):
        """Remove PID file on shutdown."""
        if self.PIDFILE.exists():
            self.PIDFILE.unlink()
            self.logger.info("Removed PID file")
