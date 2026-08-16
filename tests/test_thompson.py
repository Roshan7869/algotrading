import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def clean_outcomes():
    path = Path(__file__).parent.parent / "nexus" / "outcomes.jsonl"
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()


@pytest.fixture(autouse=True)
def seed_outcomes():
    from nexus.local_learning_store import record_outcome
    for i in range(10):
        skill = "alpha_skill" if i < 7 else "beta_skill"
        outcome = "correct" if (i < 7 or i >= 8) else "wrong"
        record_outcome(skill, outcome, f"seed_{i}")


def test_thompson_score_returns_float():
    from nexus.thompson_local import thompson_score
    score = thompson_score("alpha_skill")
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_thompson_score_unknown_skill():
    from nexus.thompson_local import thompson_score
    score = thompson_score("nonexistent_skill")
    assert 0.0 <= score <= 1.0


def test_thompson_rank():
    from nexus.thompson_local import thompson_rank
    candidates = [
        {"name": "alpha_skill", "score": 0.9},
        {"name": "beta_skill", "score": 0.5},
        {"name": "unknown_skill", "score": 0.3},
    ]
    ranked = thompson_rank(candidates)
    assert len(ranked) == 3
    for r in ranked:
        assert "thompson_score" in r
        assert "combined_score" in r

    assert ranked[0]["combined_score"] >= ranked[-1]["combined_score"]


def test_thompson_stats():
    from nexus.thompson_local import get_thompson_stats
    stats = get_thompson_stats()
    assert stats["enabled"] is True
    assert stats["skills_tracked"] >= 2
    assert "alpha_skill" in stats["skill_scores"]
    assert "beta_skill" in stats["skill_scores"]
    assert stats["skill_scores"]["alpha_skill"]["correct"] == 7
    assert stats["skill_scores"]["beta_skill"]["correct"] == 2


def test_bridge_thompson_score():
    from nexus.bridge import get_bridge
    bridge = get_bridge()
    score = bridge._thompson_score("alpha_skill")
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_query_strategies_with_thompson():
    import os
    with patch.dict(os.environ, {"NEXUS_THOMPSON_ROUTING": "true"}):
        from nexus.bridge import get_bridge
        bridge = get_bridge()
        from nexus.local_learning_store import record_outcome
        record_outcome("strategy_1", "correct", "strat test")
        results = bridge.query_strategies("breakout", top_k=5)
        assert isinstance(results, list)
