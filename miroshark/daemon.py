"""
MiroShark Daemon — Continuous decision loop with configurable interval.

Runs the Brain every N seconds, writes composite signal to the bus,
and logs decisions for audit trail.
"""

import json
import signal
import sys
import time
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from miroshark.brain import MiroSharkBrain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mirosharkd] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "logs" / "miroshark_daemon.log"),
    ],
)
log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 60  # seconds between decisions
running = True


def handle_signal(signum, frame):
    global running
    log.info(f"Received signal {signum}, shutting down...")
    running = False


def main_loop(interval: int = DEFAULT_INTERVAL):
    """Main daemon loop."""
    brain = MiroSharkBrain()
    log.info(f"MiroShark daemon starting (interval={interval}s)")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    cycle = 0
    while running:
        try:
            sig = brain.run_once()
            cycle += 1
            if cycle % 10 == 0:
                log.info(f"[cycle {cycle}] {sig.action} {sig.direction} "
                         f"conf={sig.confidence:.3f} lev={sig.suggested_leverage}")
        except Exception as e:
            log.error(f"Brain cycle failed: {e}")

        # Sleep in small increments for responsive shutdown
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    log.info(f"MiroShark daemon stopped after {cycle} cycles")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MiroShark Decision Daemon")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Decision interval in seconds (default: {DEFAULT_INTERVAL})")
    args = parser.parse_args()
    main_loop(interval=args.interval)