from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_store():
    path = Path(__file__).parent.parent / "nexus" / "session_memory.jsonl"
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()


def test_save_and_search():
    from nexus.session_memory import save_session, search_sessions
    save_session("session_1", "topic", "breakout strategy", {"source": "test"})
    save_session("session_1", "result", "profitable", {"source": "test"})

    results = search_sessions("breakout")
    assert len(results) == 1
    assert results[0]["key"] == "topic"
    assert results[0]["value"] == "breakout strategy"


def test_search_empty():
    from nexus.session_memory import search_sessions
    assert search_sessions("anything") == []


def test_get_session():
    from nexus.session_memory import save_session, get_session
    save_session("session_x", "key1", "val1")
    save_session("session_x", "key2", "val2")
    save_session("session_y", "key1", "other")

    entries = get_session("session_x")
    assert len(entries) == 2
    assert all(e["session_id"] == "session_x" for e in entries)


def test_save_returns_success():
    from nexus.session_memory import save_session
    result = save_session("test", "k", "v")
    assert result["success"] is True
    assert result["entry"]["key"] == "k"
    assert result["entry"]["value"] == "v"
