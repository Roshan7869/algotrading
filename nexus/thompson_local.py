import math
import random
from typing import Any

from nexus.local_learning_store import get_outcomes


def thompson_score(skill_name: str, alpha_prior: float = 1.0, beta_prior: float = 1.0) -> float:
    outcomes = get_outcomes(limit=10000)
    skill_outcomes = [o for o in outcomes if o.get("skill_name") == skill_name]
    correct = sum(1 for o in skill_outcomes if o.get("outcome") == "correct")
    wrong = sum(1 for o in skill_outcomes if o.get("outcome") == "wrong")
    alpha = alpha_prior + correct
    beta = beta_prior + wrong
    return float(random.betavariate(max(alpha, 0.01), max(beta, 0.01)))


def thompson_rank(candidates: list[dict], score_key: str = "score") -> list[dict]:
    scored = []
    for cand in candidates:
        name = cand.get("setup_name", cand.get("name", "unknown"))
        ts = thompson_score(name)
        keyword_score = cand.get(score_key, 0.5)
        combined = ts * 0.7 + keyword_score * 0.3
        cand_copy = dict(cand)
        cand_copy["thompson_score"] = round(ts, 4)
        cand_copy["combined_score"] = round(combined, 4)
        scored.append(cand_copy)
    scored.sort(key=lambda x: -x["combined_score"])
    return scored


def get_thompson_stats() -> dict:
    outcomes = get_outcomes(limit=10000)
    skill_names = set(o.get("skill_name", "") for o in outcomes)
    skill_scores = {}
    for name in sorted(skill_names):
        if not name:
            continue
        skill_outcomes = [o for o in outcomes if o.get("skill_name") == name]
        correct = sum(1 for o in skill_outcomes if o.get("outcome") == "correct")
        wrong = sum(1 for o in skill_outcomes if o.get("outcome") == "wrong")
        total = correct + wrong
        skill_scores[name] = {
            "total": total,
            "correct": correct,
            "wrong": wrong,
            "win_rate": round(correct / total, 4) if total > 0 else 0,
        }
    return {
        "enabled": True,
        "skills_tracked": len(skill_scores),
        "skill_scores": skill_scores,
    }
