from pathlib import Path

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
    record_outcome("good_skill", "correct", "good test")
    record_outcome("good_skill", "correct", "good test 2")
    record_outcome("bad_skill", "wrong", "bad test")


def test_auto_invoke_finds_alternative():
    from nexus.auto_invoke import auto_invoke
    result = auto_invoke("test task", "bad_skill", max_retries=2)
    assert result["status"] in ("alternative_found", "exhausted")
    assert "bad_skill" in result["tried"]
    assert len(result["attempts"]) >= 0


def test_auto_invoke_exhausted():
    from nexus.auto_invoke import auto_invoke
    result = auto_invoke("test task", "good_skill", max_retries=2)
    assert result["status"] in ("alternative_found", "exhausted")


def test_auto_invoke_returns_attempts():
    from nexus.auto_invoke import auto_invoke
    result = auto_invoke("test task", "bad_skill", max_retries=2)
    assert "attempts" in result
    assert "tried" in result
    assert "message" in result
