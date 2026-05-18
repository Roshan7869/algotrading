#!/usr/bin/env python3
"""Refresh outcome feedback from Freqtrade trade history.

Reads recent trade results and writes outcome stats to Signal Bus.
Meant to run every hour via cron.
"""

import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared_config.signal_bus import get_bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [outcomes] %(message)s")
log = logging.getLogger(__name__)

OUTCOME_PATH = PROJECT_ROOT / "strategy_db" / "outcome_history.json"


def compute_outcome_stats():
    """Read outcome history and compute rolling stats."""
    if not OUTCOME_PATH.exists():
        log.warning("No outcome_history.json found")
        return {"win_rate": 0.0, "total_trades": 0, "avg_r_multiple": 0.0, "status": "no_data"}

    try:
        with open(OUTCOME_PATH) as f:
            data = json.load(f)

        trades = data.get("trades", data) if isinstance(data, dict) else data
        if isinstance(trades, dict):
            trades = list(trades.values())

        if not trades:
            return {"win_rate": 0.0, "total_trades": 0, "avg_r_multiple": 0.0, "status": "empty"}

        total = len(trades)
        wins = sum(1 for t in trades if t.get("is_win", False))
        win_rate = round(wins / total, 4) if total > 0 else 0.0

        r_multiples = [t.get("r_multiple", 0) for t in trades if "r_multiple" in t]
        avg_r = round(sum(r_multiples) / len(r_multiples), 4) if r_multiples else 0.0

        # Regime breakdown
        regime_stats = {}
        for t in trades:
            regime = t.get("regime", "unknown")
            if regime not in regime_stats:
                regime_stats[regime] = {"trades": 0, "wins": 0}
            regime_stats[regime]["trades"] += 1
            if t.get("is_win"):
                regime_stats[regime]["wins"] += 1

        for r in regime_stats:
            rt = regime_stats[r]["trades"]
            regime_stats[r]["win_rate"] = round(regime_stats[r]["wins"] / rt, 4) if rt else 0.0

        # Side breakdown
        long_trades = [t for t in trades if t.get("side") == "long"]
        short_trades = [t for t in trades if t.get("side") == "short"]
        long_wr = round(sum(1 for t in long_trades if t.get("is_win")) / len(long_trades), 4) if long_trades else 0.0
        short_wr = round(sum(1 for t in short_trades if t.get("is_win")) / len(short_trades), 4) if short_trades else 0.0

        return {
            "win_rate": win_rate,
            "total_trades": total,
            "wins": wins,
            "avg_r_multiple": avg_r,
            "long_win_rate": long_wr,
            "short_win_rate": short_wr,
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
            "regime_stats": regime_stats,
            "status": "ok",
        }

    except Exception as e:
        log.error(f"Outcome computation failed: {e}")
        return {"win_rate": 0.0, "total_trades": 0, "status": "error", "error": str(e)}


def main():
    bus = get_bus()
    log.info("Refreshing outcome feedback signal...")
    stats = compute_outcome_stats()
    bus.write("outcome_feedback.json", stats)
    log.info(f"Outcome signal written: WR={stats.get('win_rate')}, trades={stats.get('total_trades')}, avg_R={stats.get('avg_r_multiple')}")


if __name__ == "__main__":
    main()