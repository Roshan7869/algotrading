#!/usr/bin/env python3
"""Refresh TradingAgents signal — placeholder for TradingAgents bridge.

Currently writes a default neutral signal. When TradingAgents is connected,
this will query the agents and write their consensus.
Meant to run every 15 minutes via cron.
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared_config.signal_bus import get_bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [agents] %(message)s")
log = logging.getLogger(__name__)


def main():
    bus = get_bus()
    log.info("Refreshing TradingAgents signal...")

    # Placeholder: read existing signal or write neutral
    existing = bus.read("tradingagents_signal.json")
    if existing and existing.get("rating"):
        log.info(f"TradingAgents signal exists: {existing.get('rating')}, keeping")
    else:
        bus.write("tradingagents_signal.json", {
            "rating": "Neutral",
            "confidence": 0.5,
            "risk_assessment": {"approval": True},
        })
        log.info("Wrote neutral TradingAgents signal (placeholder)")


if __name__ == "__main__":
    main()