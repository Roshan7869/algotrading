from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_registry():
    path = Path(__file__).parent.parent / "nexus" / "skills_registry.json"
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()


def test_list_empty():
    from nexus.skill_manager import list_skills
    assert list_skills() == []


def test_add_and_get():
    from nexus.skill_manager import add_skill, get_skill, list_skills
    result = add_skill("test_skill", "A test skill", "testing", tags=["test"])
    assert result["success"] is True

    skill = get_skill("test_skill")
    assert skill is not None
    assert skill["name"] == "test_skill"
    assert skill["description"] == "A test skill"

    skills = list_skills()
    assert len(skills) == 1


def test_add_duplicate():
    from nexus.skill_manager import add_skill
    add_skill("dup_skill", "first")
    result = add_skill("dup_skill", "second")
    assert result["success"] is False


def test_remove():
    from nexus.skill_manager import add_skill, remove_skill, get_skill
    add_skill("removable", "to be removed")
    result = remove_skill("removable")
    assert result["success"] is True
    assert get_skill("removable") is None


def test_remove_nonexistent():
    from nexus.skill_manager import remove_skill
    result = remove_skill("nonexistent")
    assert result["success"] is False


def test_update():
    from nexus.skill_manager import add_skill, update_skill, get_skill
    add_skill("updatable", "original")
    update_skill("updatable", description="updated")
    skill = get_skill("updatable")
    assert skill["description"] == "updated"


def test_update_nonexistent():
    from nexus.skill_manager import update_skill
    result = update_skill("nonexistent", description="test")
    assert result["success"] is False
