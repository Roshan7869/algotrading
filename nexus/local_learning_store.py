import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "outcomes.jsonl"


def record_outcome(skill_name: str, outcome: str, task_summary: str = "") -> dict:
    entry = {
        "skill_name": skill_name,
        "outcome": outcome,
        "task_summary": task_summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(STORE_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"success": True, "via": "local_store", "entry": entry}
    except OSError as e:
        logger.error(f"local_learning_store write failed: {e}")
        return {"success": False, "error": str(e), "via": "local_store"}


def get_outcomes(limit: int = 100) -> list[dict]:
    if not STORE_PATH.exists():
        return []
    outcomes = []
    try:
        with open(STORE_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    outcomes.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"local_learning_store read failed: {e}")
        return []
    return outcomes[-limit:]


def get_stats() -> dict:
    outcomes = get_outcomes(limit=10000)
    if not outcomes:
        return {"total": 0, "correct": 0, "wrong": 0, "win_rate": 0.0}
    total = len(outcomes)
    correct = sum(1 for o in outcomes if o.get("outcome") == "correct")
    wrong = sum(1 for o in outcomes if o.get("outcome") == "wrong")
    return {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "win_rate": round(correct / total, 4) if total > 0 else 0.0,
    }
