import logging

from nexus.local_learning_store import get_outcomes
from nexus.self_reflection import find_alternatives

logger = logging.getLogger(__name__)


def auto_invoke(task: str, skill_name: str, max_retries: int = 2) -> dict:
    attempts = []
    tried = [skill_name]

    for attempt in range(max_retries):
        alternatives = find_alternatives(tried[-1])

        fresh = [a for a in alternatives if a["name"] not in tried]

        if not fresh:
            return {
                "status": "exhausted",
                "attempts": attempts,
                "tried": tried,
                "message": f"No alternatives after {attempt} retries",
            }

        from nexus.thompson_local import thompson_rank
        ranked = thompson_rank(
            [{"name": a["name"], "score": a["win_rate"]} for a in fresh]
        )

        best = ranked[0] if ranked else fresh[0]
        tried.append(best["name"] if isinstance(best, dict) else best)
        attempts.append({
            "attempt": attempt + 1,
            "recommended": best["name"] if isinstance(best, dict) else best,
            "score": best.get("combined_score", best.get("win_rate", 0)) if isinstance(best, dict) else 0,
        })

        score = best.get("combined_score", 0) if isinstance(best, dict) else 0
        if score >= 0.1:
            return {
                "status": "alternative_found",
                "attempts": attempts,
                "recommended": best["name"] if isinstance(best, dict) else best,
                "tried": tried,
                "message": f"Found alternative: {best['name'] if isinstance(best, dict) else best}",
            }

    return {
        "status": "exhausted",
        "attempts": attempts,
        "tried": tried,
        "message": "Max retries exhausted",
    }
