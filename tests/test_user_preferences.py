from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_store():
    path = Path(__file__).parent.parent / "nexus" / "user_preferences.json"
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()


def test_get_all_empty():
    from nexus.user_preferences import get_all
    assert get_all() == {}


def test_set_and_get():
    from nexus.user_preferences import set, get
    result = set("theme", "dark")
    assert result["success"] is True
    assert get("theme") == "dark"


def test_get_default():
    from nexus.user_preferences import get
    assert get("nonexistent", "default_val") == "default_val"


def test_delete():
    from nexus.user_preferences import set, delete, get
    set("key1", "val1")
    result = delete("key1")
    assert result["success"] is True
    assert get("key1") is None


def test_delete_nonexistent():
    from nexus.user_preferences import delete
    result = delete("nonexistent")
    assert result["success"] is False


def test_list_keys():
    from nexus.user_preferences import set, list_keys
    set("pref_a", "a")
    set("pref_b", "b")
    keys = list_keys()
    assert "pref_a" in keys
    assert "pref_b" in keys
    assert "_updated_at" not in keys


def test_round_trip():
    from nexus.user_preferences import set, get_all
    set("strategy", "trend_following")
    set("max_leverage", "2.0")
    all_prefs = get_all()
    assert all_prefs["strategy"] == "trend_following"
    assert all_prefs["max_leverage"] == "2.0"
