import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def clean_all():
    outcomes = Path(__file__).parent.parent / "nexus" / "outcomes.jsonl"
    if outcomes.exists():
        outcomes.unlink()
    db = Path(__file__).parent.parent / "nexus" / "reflection.db"
    if db.exists():
        db.unlink()
    yield
    if outcomes.exists():
        outcomes.unlink()
    if db.exists():
        db.unlink()


@pytest.fixture(autouse=True)
def seed_outcomes():
    from nexus.local_learning_store import record_outcome
    for i in range(5):
        record_outcome("good_strat", "correct", f"seed_{i}")
    record_outcome("bad_strat", "wrong", "seed_fail")


@pytest.fixture(autouse=True)
def patch_nexus_files():
    with (
        patch("nexus.event_bridge.NEXUS_FEEDBACK") as mock_fb,
        patch("nexus.event_bridge.NEXUS_CLI") as mock_cli,
    ):
        mock_fb.exists.return_value = False
        mock_cli.exists.return_value = False
        yield


def test_classify_error():
    from nexus.self_reflection import classify_error
    assert classify_error("null pointer") == "null_reference"
    assert classify_error("module not found") == "missing_dependency"
    assert classify_error("timeout after 30s") == "timeout"
    assert classify_error("connection refused") == "network_error"
    assert classify_error("random message") == "general_failure"


def test_record_failure():
    from nexus.self_reflection import record_failure
    result = record_failure("bad_strat", "test failure")
    assert result["status"] == "logged"
    assert result["error_type"] == "general_failure"
    assert result["alternatives_found"] >= 1
    assert result["alternatives"][0]["name"] == "good_strat"


def test_find_alternatives():
    from nexus.self_reflection import find_alternatives
    alts = find_alternatives("bad_strat")
    assert len(alts) >= 1
    assert alts[0]["name"] == "good_strat"
    assert alts[0]["win_rate"] == 1.0


def test_record_failure_wired_from_event_bridge():
    from nexus.event_bridge import record_outcome
    result = record_outcome("bad_strat", "wrong", "test fail from bridge")
    assert result["success"] is True
    assert "reflection" in result
    assert result["reflection"]["status"] == "logged"


def test_get_failure_stats_empty():
    from nexus.self_reflection import get_failure_stats
    stats = get_failure_stats()
    assert stats["enabled"] is True
    assert stats["total_failures"] >= 0


def test_get_failure_stats_after_failures():
    from nexus.self_reflection import record_failure, get_failure_stats
    record_failure("bad_strat", "fail one")
    record_failure("bad_strat", "fail two")
    stats = get_failure_stats()
    assert stats["total_failures"] >= 2
