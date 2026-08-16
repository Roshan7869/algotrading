import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "user_preferences.json"


def _load() -> dict:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"user_preferences load failed: {e}")
        return {}


def _save(data: dict):
    STORE_PATH.write_text(json.dumps(data, indent=2, default=str))


def get_all() -> dict:
    return _load()


def get(key: str, default: Any = None) -> Any:
    return _load().get(key, default)


def set(key: str, value: Any) -> dict:
    data = _load()
    data[key] = value
    data["_updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(data)
    return {"success": True, "key": key, "value": value}


def delete(key: str) -> dict:
    data = _load()
    if key in data:
        del data[key]
        data["_updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(data)
        return {"success": True, "removed": key}
    return {"success": False, "error": f"Key '{key}' not found"}


def list_keys() -> list[str]:
    data = _load()
    return [k for k in data if not k.startswith("_")]
