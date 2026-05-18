"""
Process Manager for Freqtrade
Ensures only one bot instance runs at a time to prevent Telegram conflicts.
"""

import os
import sys
import time
import signal
import psutil
from pathlib import Path
from datetime import datetime
from typing import Optional

# PID file location
PID_FILE = Path(__file__).parent.parent.parent / "user_data" / ".freqtrade.pid"


class ProcessManager:
    """
    Manages Freqtrade process lifecycle with single-instance enforcement.
    """

    def __init__(self, pid_file: Path = PID_FILE):
        """
        Initialize process manager.

        Args:
            pid_file: Path to PID file for tracking running instance
        """
        self.pid_file = pid_file
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)

    def is_running(self) -> bool:
        """
        Check if another instance is already running.

        Returns:
            True if another instance is running, False otherwise
        """
        if not self.pid_file.exists():
            return False

        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())

            # Check if process with this PID exists
            if psutil.pid_exists(pid):
                try:
                    proc = psutil.Process(pid)
                    # Verify it's actually a Freqtrade process
                    cmdline = " ".join(proc.cmdline()).lower()
                    if "freqtrade" in cmdline or "python" in cmdline:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # PID file exists but process is dead - clean up stale PID file
            self._cleanup_pid_file()
            return False

        except (ValueError, IOError):
            # Invalid PID file - clean up
            self._cleanup_pid_file()
            return False

    def get_running_pid(self) -> Optional[int]:
        """
        Get PID of running instance if it exists.

        Returns:
            PID of running instance or None
        """
        if not self.pid_file.exists():
            return None

        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())

            if psutil.pid_exists(pid):
                return pid
        except (ValueError, IOError):
            pass

        return None

    def acquire_lock(self) -> bool:
        """
        Acquire process lock by writing PID file.

        Returns:
            True if lock acquired, False if another instance is running
        """
        if self.is_running():
            return False

        try:
            # Write current process PID
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))
            return True
        except IOError as e:
            print(f"[ERROR] Failed to acquire lock: {e}")
            return False

    def release_lock(self):
        """Release process lock by removing PID file."""
        self._cleanup_pid_file()

    def _cleanup_pid_file(self):
        """Remove PID file if it exists."""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except IOError:
            pass

    def stop_running_instance(self, timeout: int = 30) -> bool:
        """
        Stop currently running instance gracefully.

        Args:
            timeout: Maximum time to wait for process to stop (seconds)

        Returns:
            True if stopped successfully, False otherwise
        """
        pid = self.get_running_pid()
        if not pid:
            return True

        try:
            proc = psutil.Process(pid)

            # Send SIGTERM for graceful shutdown
            print(f"[STOP] Stopping running instance (PID: {pid})...")
            proc.terminate()

            # Wait for process to exit
            start_time = time.time()
            while proc.is_running() and (time.time() - start_time) < timeout:
                time.sleep(0.5)

            if proc.is_running():
                # Force kill if still running
                print(f"[WARN] Process didn't stop gracefully, forcing kill...")
                proc.kill()
                time.sleep(1)

            self._cleanup_pid_file()
            print(f"[OK] Instance stopped successfully")
            return True

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"[WARN] Error stopping process: {e}")
            self._cleanup_pid_file()
            return True

    def register_cleanup_handlers(self):
        """Register signal handlers for graceful shutdown."""

        def cleanup_handler(signum, frame):
            print(f"\n[STOP] Received signal {signum}, cleaning up...")
            self.release_lock()
            sys.exit(0)

        signal.signal(signal.SIGTERM, cleanup_handler)
        signal.signal(signal.SIGINT, cleanup_handler)


def check_single_instance(force_stop: bool = False) -> bool:
    """
    Ensure only one instance is running.

    Args:
        force_stop: If True, stop any running instance

    Returns:
        True if ready to run (no other instance), False otherwise
    """
    manager = ProcessManager()

    if manager.is_running():
        pid = manager.get_running_pid()

        if force_stop:
            print(f"[WARN] Another instance is running (PID: {pid})")
            return manager.stop_running_instance()
        else:
            print(f"[ERROR] Another Freqtrade instance is already running (PID: {pid})")
            print(f"   PID file: {PID_FILE}")
            print(f"\nOptions:")
            print(f"  1. Stop the running instance first")
            print(f"  2. Use --force-stop flag to automatically stop it")
            return False

    return True


def main():
    """Test the process manager."""
    import argparse

    parser = argparse.ArgumentParser(description="Freqtrade Process Manager")
    parser.add_argument(
        "--check", action="store_true", help="Check if instance is running"
    )
    parser.add_argument("--stop", action="store_true", help="Stop running instance")
    parser.add_argument("--test-lock", action="store_true", help="Test acquiring lock")

    args = parser.parse_args()

    manager = ProcessManager()

    if args.check:
        if manager.is_running():
            pid = manager.get_running_pid()
            print(f"[OK] Instance is running (PID: {pid})")
        else:
            print(f"[INFO] No instance is running")

    elif args.stop:
        if manager.stop_running_instance():
            print(f"[OK] Instance stopped")
        else:
            print(f"[ERROR] Failed to stop instance")

    elif args.test_lock:
        if manager.acquire_lock():
            print(f"[OK] Lock acquired (PID: {os.getpid()})")
            print(f"   Press Ctrl+C to release lock...")
            manager.register_cleanup_handlers()
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                manager.release_lock()
                print(f"\n[OK] Lock released")
        else:
            print(f"[ERROR] Failed to acquire lock (another instance is running)")


if __name__ == "__main__":
    main()
