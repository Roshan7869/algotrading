"""
Tests for Strategy Registry
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core import StrategyInfo
from engine.strategy_registry import StrategyRegistry, PERFORMANCE_DB


@pytest.fixture
def registry():
    reg = StrategyRegistry()
    yield reg


@pytest.fixture
def tmp_perf(monkeypatch, tmp_path):
    perf_path = tmp_path / "perf.json"
    perf_path.write_text("{}")
    monkeypatch.setattr("engine.strategy_registry.PERFORMANCE_DB", perf_path)
    yield perf_path


def test_scan_discovers_strategies(registry):
    registry.scan(force=True)
    all_strats = registry.list_strategies()
    assert len(all_strats) > 0
    names = [s.name for s in all_strats]
    assert "AroonMomentumEngine_Hybrid" in names


def test_get_existing_strategy(registry):
    registry.scan(force=True)
    info = registry.get("AroonMomentumEngine_Hybrid")
    assert info is not None
    assert info.name == "AroonMomentumEngine_Hybrid"


def test_get_nonexistent_strategy(registry):
    registry.scan(force=True)
    info = registry.get("NonExistentStrategy")
    assert info is None


def test_list_active_only(registry):
    registry.scan(force=True)
    active = registry.list_strategies(active_only=True)
    for s in active:
        assert s.is_active


def test_set_active(registry):
    registry.scan(force=True)
    registry.set_active("AroonMomentumEngine_Hybrid", True)
    info = registry.get("AroonMomentumEngine_Hybrid")
    assert info is not None
    assert info.is_active


def test_update_performance(registry, tmp_perf):
    registry.scan(force=True)
    registry.update_performance("AroonMomentumEngine_Hybrid", won=True, pnl=150.0)
    info = registry.get("AroonMomentumEngine_Hybrid")
    assert info is not None
    assert info.trades == 1
    assert info.win_rate == 1.0
    assert info.total_pnl == 150.0


def test_update_performance_loss(registry, tmp_perf):
    registry.scan(force=True)
    registry.update_performance("AroonMomentumEngine_Hybrid", won=False, pnl=-50.0)
    info = registry.get("AroonMomentumEngine_Hybrid")
    assert info is not None
    assert info.trades == 1
    assert info.win_rate == 0.0
    assert info.total_pnl == -50.0


def test_select_by_regime(registry):
    registry.scan(force=True)
    trending = registry.select_by_regime("trending")
    assert len(trending) > 0
    names = [s.name for s in trending]
    assert "EmaTrendFollowing" in names


def test_select_by_regime_unknown(registry):
    registry.scan(force=True)
    unknown = registry.select_by_regime("unknown_regime")
    assert unknown == []


def test_save_and_load_performance():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "perf.json"
        old_path = Path(os.path.join(os.path.dirname(__file__), "..", "user_data", "strategy_performance_db.json"))
        import engine.strategy_registry as sr
        orig = sr.PERFORMANCE_DB
        sr.PERFORMANCE_DB = db_path
        reg = StrategyRegistry()
        reg.scan(force=True)
        reg.update_performance("AroonMomentumEngine_Hybrid", won=True, pnl=100.0)
        assert db_path.exists()
        data = json.loads(db_path.read_text())
        assert "AroonMomentumEngine_Hybrid" in data
        sr.PERFORMANCE_DB = orig


def test_strategy_info_defaults():
    info = StrategyInfo(name="Test", module_path="/tmp/test.py")
    assert info.name == "Test"
    assert info.trades == 0
    assert info.win_rate == 0.0
    assert info.total_pnl == 0.0
    assert info.is_active is False
