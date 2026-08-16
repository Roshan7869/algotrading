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
def patch_nexus_files():
    with (
        patch("nexus.event_bridge.NEXUS_FEEDBACK") as mock_fb,
        patch("nexus.event_bridge.NEXUS_CLI") as mock_cli,
    ):
        mock_fb.exists.return_value = False
        mock_cli.exists.return_value = False
        yield


def test_record_outcome_local_fallback():
    from nexus.event_bridge import record_outcome

    result = record_outcome("test_skill", "correct", "test task")
    assert result["success"] is True
    assert result["via"] == "local_store"

    path = Path(__file__).parent.parent / "nexus" / "outcomes.jsonl"
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["skill_name"] == "test_skill"
    assert entry["outcome"] == "correct"
    assert entry["task_summary"] == "test task"


def test_record_outcome_multiple():
    from nexus.event_bridge import record_outcome

    for i in range(3):
        record_outcome(f"skill_{i}", "correct" if i % 2 == 0 else "wrong", f"task_{i}")

    from nexus.local_learning_store import get_outcomes, get_stats

    outcomes = get_outcomes()
    assert len(outcomes) == 3

    stats = get_stats()
    assert stats["total"] == 3
    assert stats["correct"] == 2
    assert stats["wrong"] == 1
    assert stats["win_rate"] == pytest.approx(2 / 3, rel=1e-3)


def test_record_outcome_wrong():
    from nexus.event_bridge import record_outcome

    result = record_outcome("test_skill", "wrong", "failed task")
    assert result["success"] is True
    assert result["via"] == "local_store"


def test_local_learning_store_direct():
    from nexus.local_learning_store import record_outcome, get_outcomes, get_stats

    record_outcome("direct_skill", "correct", "direct test")
    outcomes = get_outcomes()
    assert len(outcomes) == 1
    assert outcomes[0]["skill_name"] == "direct_skill"

    stats = get_stats()
    assert stats["total"] == 1
    assert stats["correct"] == 1


def test_empty_store():
    from nexus.local_learning_store import get_outcomes, get_stats

    assert get_outcomes() == []
    stats = get_stats()
    assert stats["total"] == 0
    assert stats["win_rate"] == 0.0


def test_import_event_bridge():
    from nexus import event_bridge

    assert hasattr(event_bridge, "record_outcome")
    assert hasattr(event_bridge, "NEXUS_DIR")
    assert hasattr(event_bridge, "NEXUS_FEEDBACK")
    assert hasattr(event_bridge, "NEXUS_CLI")
