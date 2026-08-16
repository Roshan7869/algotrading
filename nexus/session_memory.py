import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "session_memory.jsonl"


def save_session(session_id: str, key: str, value: str, metadata: dict | None = None) -> dict:
    entry = {
        "session_id": session_id,
        "key": key,
        "value": value,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(STORE_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"success": True, "entry": entry}
    except OSError as e:
        return {"success": False, "error": str(e)}


def search_sessions(query: str, limit: int = 10) -> list[dict]:
    if not STORE_PATH.exists():
        return []
    results = []
    query_lower = query.lower()
    try:
        with open(STORE_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (query_lower in str(entry.get("key", "")).lower()
                        or query_lower in str(entry.get("value", "")).lower()
                        or query_lower in str(entry.get("session_id", "")).lower()):
                    results.append(entry)
                    if len(results) >= limit:
                        break
        return results
    except OSError as e:
        logger.error(f"session_memory search failed: {e}")
        return []


def get_session(session_id: str, limit: int = 50) -> list[dict]:
    if not STORE_PATH.exists():
        return []
    results = []
    try:
        with open(STORE_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("session_id") == session_id:
                    results.append(entry)
                    if len(results) >= limit:
                        break
        return results
    except OSError as e:
        logger.error(f"session_memory get_session failed: {e}")
        return []
