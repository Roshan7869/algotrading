import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "skills_registry.json"


def _load() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    try:
        return json.loads(STORE_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"skill_manager load failed: {e}")
        return []


def _save(skills: list[dict]):
    STORE_PATH.write_text(json.dumps(skills, indent=2, default=str))


def list_skills() -> list[dict]:
    return _load()


def get_skill(name: str) -> Optional[dict]:
    for s in _load():
        if s["name"] == name:
            return s
    return None


def add_skill(name: str, description: str = "", category: str = "general",
              source: str = "manual", tags: list[str] | None = None) -> dict:
    skills = _load()
    if any(s["name"] == name for s in skills):
        return {"success": False, "error": f"Skill '{name}' already exists"}
    skill = {
        "name": name,
        "description": description,
        "category": category,
        "source": source,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    skills.append(skill)
    _save(skills)
    return {"success": True, "skill": skill}


def remove_skill(name: str) -> dict:
    skills = _load()
    filtered = [s for s in skills if s["name"] != name]
    if len(filtered) == len(skills):
        return {"success": False, "error": f"Skill '{name}' not found"}
    _save(filtered)
    return {"success": True, "removed": name}


def update_skill(name: str, **kwargs) -> dict:
    skills = _load()
    for s in skills:
        if s["name"] == name:
            for k, v in kwargs.items():
                if v is not None:
                    s[k] = v
            s["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save(skills)
            return {"success": True, "skill": s}
    return {"success": False, "error": f"Skill '{name}' not found"}
