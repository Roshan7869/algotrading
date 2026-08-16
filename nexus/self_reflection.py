import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nexus.local_learning_store import get_outcomes

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "reflection.db"


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reflection_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT,
            resource_name TEXT,
            root_cause TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reflection_fixes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_name TEXT,
            failure_summary TEXT,
            fix_description TEXT,
            times_applied INTEGER DEFAULT 0,
            times_successful INTEGER DEFAULT 0,
            last_applied_at TIMESTAMP
        )
    """)
    conn.commit()


def classify_error(log: str) -> str:
    log_lower = log.lower()
    if any(kw in log_lower for kw in ["null", "none", "nil", "nonetype"]):
        return "null_reference"
    elif any(kw in log_lower for kw in ["import", "module", "not found", "no module named"]):
        return "missing_dependency"
    elif any(kw in log_lower for kw in ["permission", "forbidden", "auth", "access denied"]):
        return "permission_denied"
    elif any(kw in log_lower for kw in ["timeout", "timed out", "hang", "deadline"]):
        return "timeout"
    elif any(kw in log_lower for kw in ["syntax", "parse", "format"]):
        return "syntax_error"
    elif any(kw in log_lower for kw in ["type", "cast", "conversion", "typeerror"]):
        return "type_mismatch"
    elif any(kw in log_lower for kw in ["connection", "host", "port", "network", "socket"]):
        return "network_error"
    else:
        return "general_failure"


def record_failure(skill_name: str, task_summary: str = "") -> dict:
    error_type = classify_error(task_summary)
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO reflection_failures (task, resource_name, root_cause)
            VALUES (?, ?, ?)
        """, (task_summary or "unknown", skill_name, error_type))
        conn.commit()

        alternatives = find_alternatives(skill_name)

        if alternatives:
            for alt in alternatives[:3]:
                existing = conn.execute(
                    "SELECT id FROM reflection_fixes WHERE resource_name=? AND failure_summary=? AND fix_description=?",
                    (skill_name, f"Failed with {error_type}", f"Use {alt} instead")
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE reflection_fixes SET times_applied = times_applied + 1, last_applied_at = datetime('now') WHERE id=?",
                        (existing["id"],)
                    )
                else:
                    conn.execute("""
                        INSERT INTO reflection_fixes (resource_name, failure_summary, fix_description, times_applied)
                        VALUES (?, ?, ?, 1)
                    """, (skill_name, f"Failed with {error_type}", f"Use {alt} instead"))
                conn.commit()

        conn.close()
        return {
            "status": "logged",
            "error_type": error_type,
            "alternatives_found": len(alternatives),
            "alternatives": alternatives[:5],
        }
    except Exception as e:
        conn.close()
        logger.error(f"self_reflection.record_failure failed: {e}")
        return {"status": "error", "message": str(e)}


def find_alternatives(failed_skill: str) -> list[dict]:
    outcomes = get_outcomes(limit=10000)
    skill_outcomes = {}
    for o in outcomes:
        name = o.get("skill_name", "")
        if name == failed_skill or not name:
            continue
        if name not in skill_outcomes:
            skill_outcomes[name] = {"correct": 0, "wrong": 0, "total": 0}
        outcome = o.get("outcome", "")
        if outcome == "correct":
            skill_outcomes[name]["correct"] += 1
        elif outcome == "wrong":
            skill_outcomes[name]["wrong"] += 1
        skill_outcomes[name]["total"] += 1

    scored = []
    for name, stats in skill_outcomes.items():
        if stats["total"] == 0:
            continue
        win_rate = stats["correct"] / stats["total"]
        scored.append({
            "name": name,
            "win_rate": round(win_rate, 3),
            "uses": stats["total"],
            "correct": stats["correct"],
            "wrong": stats["wrong"],
        })

    scored.sort(key=lambda x: (-x["win_rate"], -x["uses"]))
    return scored


def get_failure_stats() -> dict:
    conn = _get_conn()
    try:
        failures = conn.execute("SELECT COUNT(*) FROM reflection_failures").fetchone()[0]
        fixes = conn.execute("SELECT COUNT(*) FROM reflection_fixes").fetchone()[0]

        recent = conn.execute(
            "SELECT task, resource_name, root_cause, created_at FROM reflection_failures ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

        return {
            "enabled": True,
            "total_failures": failures,
            "total_fixes": fixes,
            "recent_failures": [dict(r) for r in recent],
        }
    except Exception as e:
        return {"enabled": True, "error": str(e)}
    finally:
        conn.close()
