"""
Event Bridge — bridges MCP outcomes to Thompson Sampling beliefs.

This is a lightweight wrapper that feeds trade outcomes into NEXUS
Thompson Sampling via the NEXUS event_bridge module at /home/roshan/nexus/.
"""

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NEXUS_DIR = Path(os.getenv("NEXUS_HOME", Path.home() / "nexus"))
NEXUS_CLI = NEXUS_DIR / "cli.py"
NEXUS_FEEDBACK = NEXUS_DIR / "server" / "feedback.py"

_OUTCOME_MAP = {
    "correct": "task_completed",
    "wrong": "test_failed",
    "error": "error",
}


def record_outcome(skill_name: str, outcome: str, task_summary: str = "") -> dict:
    """Record a skill/tool outcome to NEXUS Thompson Sampling.
    Tries: 1) feedback.py subprocess with cwd fix, 2) CLI subprocess, 3) local JSONL fallback."""
    event = _OUTCOME_MAP.get(outcome, outcome)
    payload = json.dumps({
        "skill": skill_name,
        "outcome": outcome,
        "event": event,
        "task": task_summary,
    })

    if NEXUS_FEEDBACK.exists():
        try:
            nexus_lib = NEXUS_DIR / "lib"
            env = {
                **os.environ,
                "NEXUS_SKILL": skill_name,
                "NEXUS_TASK": task_summary,
            }
            if nexus_lib.is_dir():
                env["PYTHONPATH"] = f"{nexus_lib}:{env.get('PYTHONPATH', '')}"
            result = subprocess.run(
                [sys.executable, str(NEXUS_FEEDBACK), outcome],
                capture_output=True, text=True, timeout=15,
                cwd=str(NEXUS_DIR),
                env=env,
            )
            if result.returncode == 0:
                return {"success": True, "output": result.stdout.strip(), "via": "nexus_feedback"}
        except Exception as e:
            logger.warning(f"nexus_feedback subprocess failed: {e}")

    if NEXUS_CLI.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(NEXUS_CLI), "report-outcome", skill_name, outcome],
                capture_output=True, text=True, timeout=10,
                cwd=str(NEXUS_DIR),
            )
            if result.returncode == 0:
                return {"success": True, "output": result.stdout.strip(), "via": "nexus_cli"}
        except Exception as e:
            logger.warning(f"nexus_cli subprocess failed: {e}")

    from nexus.local_learning_store import record_outcome as local_record
    result = local_record(skill_name, outcome, task_summary)

    if outcome == "wrong":
        try:
            from nexus.self_reflection import record_failure
            reflection = record_failure(skill_name, task_summary)
            result["reflection"] = reflection
        except Exception as e:
            logger.warning(f"self_reflection failed: {e}")

    return result


def record_trade(trade_data: dict) -> dict:
    """Record a trade outcome from the Rust bridge into NEXUS Thompson Sampling.

    Expected trade_data keys: pair, signal, outcome, pnl_pct, strategy, entry_price, exit_price.
    Maps to record_outcome() via pair name and inferred outcome.
    """
    skill_name = trade_data.get("pair", "unknown")
    outcome = trade_data.get("outcome", "error")
    if outcome not in ("correct", "wrong", "error"):
        outcome = "correct" if trade_data.get("pnl_pct", 0) > 0 else "wrong"
    task_summary = json.dumps({
        "pair": trade_data.get("pair"),
        "signal": trade_data.get("signal"),
        "pnl_pct": trade_data.get("pnl_pct"),
        "strategy": trade_data.get("strategy"),
    })
    return record_outcome(skill_name, outcome, task_summary)


def subscribe_outcomes(redis_host: str = "127.0.0.1", redis_port: int = 6379) -> None:
    """Subscribe to the algotrading:outcomes Redis channel in a daemon thread.

    Each message is parsed as JSON and routed through record_trade() → record_outcome().
    """
    try:
        import redis as redis_lib
    except ImportError:
        logger.error("redis package not installed — outcome subscription disabled")
        return

    def _listen():
        try:
            r = redis_lib.Redis(host=redis_host, port=redis_port, decode_responses=True)
            pubsub = r.pubsub()
            pubsub.subscribe("algotrading:outcomes")
            logger.info("Subscribed to algotrading:outcomes")
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        trade_data = json.loads(message["data"])
                        record_trade(trade_data)
                    except Exception as e:
                        logger.error(f"Failed to process outcome message: {e}")
        except Exception as e:
            logger.error(f"Redis subscription failed: {e}")

    thread = threading.Thread(target=_listen, daemon=True)
    thread.start()
    logger.info("Outcome subscriber daemon started")
