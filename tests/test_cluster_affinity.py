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


def test_get_cluster_affinities_empty():
    from nexus.cluster_affinity import get_cluster_affinities
    affs = get_cluster_affinities()
    assert isinstance(affs, dict)
    assert len(affs) == 8
    for v in affs.values():
        assert v == 0.5


def test_get_cluster_affinities_with_data():
    from nexus.local_learning_store import record_outcome
    record_outcome("random_skill", "correct", "test")
    record_outcome("random_skill", "correct", "test 2")
    record_outcome("random_skill", "correct", "test 3")

    from nexus.cluster_affinity import get_cluster_affinities
    affs = get_cluster_affinities()
    assert affs["general"] == 1.0

    for c in affs:
        assert 0.0 <= affs[c] <= 1.0


def test_cluster_mapping():
    from nexus.cluster_affinity import _map_skill_to_cluster
    assert _map_skill_to_cluster("analyze_market") == "analyzer_planner"
    assert _map_skill_to_cluster("ui_dashboard") == "frontend_ui"
    assert _map_skill_to_cluster("deploy_app") == "devops_infra"
    assert _map_skill_to_cluster("test_quality") == "quality_security"
    assert _map_skill_to_cluster("kb_search") == "knowledge_wiki"
    assert _map_skill_to_cluster("random_skill") == "general"
