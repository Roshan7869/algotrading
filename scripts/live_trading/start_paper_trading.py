"""
Paper Trading Launcher
Start paper trading with full monitoring and alerts.
"""

import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import process manager
from scripts.live_trading.process_manager import ProcessManager, check_single_instance


def print_header(text):
    """Print formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def run_preflight_check(config_path):
    """Run pre-flight validation."""
    print_header("STEP 1: PRE-FLIGHT VALIDATION")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/live_trading/preflight_check.py",
            "--config",
            config_path,
        ],
        cwd=project_root,
    )

    if result.returncode != 0:
        print("\nPre-flight check FAILED. Fix errors before proceeding.")
        return False

    print("\nPre-flight check PASSED")
    return True


def start_freqtrade(config_path, dry_run=True):
    """Start Freqtrade in paper trading mode."""
    print_header("STEP 2: STARTING FREQTRADE")

    mode = "DRY RUN (Paper Trading)" if dry_run else "LIVE TRADING"
    print(f"Mode: {mode}")
    print(f"Config: {config_path}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Build docker command
    cmd = [
        "docker",
        "exec",
        "freqtrade",
        "freqtrade",
        "trade",
        "--config",
        f"/freqtrade/{config_path}",
        "--strategy",
        "AroonMomentumEngine_Hybrid",
    ]

    if dry_run:
        cmd.append("--dry-run")

    print(f"Command: {' '.join(cmd)}\n")
    print("Freqtrade is starting...")
    print("Telegram alerts will be sent for all signals")
    print("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, cwd=project_root)
    except KeyboardInterrupt:
        print("\n\nStopping Freqtrade...")
        print("Paper trading session ended")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Paper Trading Launcher")
    parser.add_argument(
        "--config",
        default="user_data/config_live_trading_10x.json",
        help="Config file path",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Start LIVE trading (default: paper trading)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip pre-flight validation (not recommended)",
    )
    parser.add_argument(
        "--force-stop",
        action="store_true",
        help="Stop any running instance before starting",
    )

    args = parser.parse_args()

    print_header("PAPER TRADING LAUNCHER")

    # Check for existing instances
    if not check_single_instance(force_stop=args.force_stop):
        print("\n❌ Cannot start: Another instance is already running")
        print("   Use --force-stop to automatically stop the running instance")
        return

    # Initialize process manager
    manager = ProcessManager()

    # Acquire lock
    if not manager.acquire_lock():
        print("\n❌ Failed to acquire process lock")
        return

    # Register cleanup handlers
    manager.register_cleanup_handlers()

    try:
        # Warning for live trading
        if args.live:
            print("WARNING: You are about to start LIVE TRADING")
            print("Real money will be at risk!")
            response = input("\nType 'YES' to confirm: ")
            if response != "YES":
                print("Cancelled")
                return

        # Run pre-flight check
        if not args.skip_validation:
            if not run_preflight_check(args.config):
                return
        else:
            print("Skipping pre-flight validation (not recommended)")

        # Start Freqtrade
        start_freqtrade(args.config, dry_run=not args.live)

    finally:
        # Always release lock on exit
        manager.release_lock()
        print("\n✅ Process lock released")


if __name__ == "__main__":
    main()
