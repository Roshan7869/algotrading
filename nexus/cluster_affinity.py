from nexus.local_learning_store import get_outcomes


CLUSTERS = [
    "analyzer_planner", "architect", "frontend_ui", "backend_api",
    "devops_infra", "quality_security", "knowledge_wiki", "general",
]


def get_cluster_affinities() -> dict:
    outcomes = get_outcomes(limit=10000)
    cluster_stats = {c: {"correct": 0, "wrong": 0, "total": 0} for c in CLUSTERS}

    for o in outcomes:
        name = o.get("skill_name", "")
        outcome = o.get("outcome", "")
        cluster = _map_skill_to_cluster(name)
        if cluster and outcome in ("correct", "wrong"):
            cluster_stats[cluster]["total"] += 1
            if outcome == "correct":
                cluster_stats[cluster]["correct"] += 1
            else:
                cluster_stats[cluster]["wrong"] += 1

    affinities = {}
    for c in CLUSTERS:
        stats = cluster_stats[c]
        if stats["total"] >= 3:
            affinities[c] = round(stats["correct"] / stats["total"], 3)
        else:
            affinities[c] = 0.5

    return affinities


def _map_skill_to_cluster(skill_name: str) -> str:
    name_lower = skill_name.lower()
    if any(kw in name_lower for kw in ["analyze", "research", "plan", "strategy"]):
        return "analyzer_planner"
    elif any(kw in name_lower for kw in ["architect", "design", "structure"]):
        return "architect"
    elif any(kw in name_lower for kw in ["ui", "frontend", "dashboard", "streamlit"]):
        return "frontend_ui"
    elif any(kw in name_lower for kw in ["api", "backend", "server", "db", "database"]):
        return "backend_api"
    elif any(kw in name_lower for kw in ["deploy", "infra", "docker", "ci", "devops"]):
        return "devops_infra"
    elif any(kw in name_lower for kw in ["test", "security", "audit", "quality"]):
        return "quality_security"
    elif any(kw in name_lower for kw in ["kb", "wiki", "knowledge", "document", "strategy"]):
        return "knowledge_wiki"
    else:
        return "general"


def get_cluster_affinity_history() -> list[dict]:
    return []
