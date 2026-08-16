"""
Tests for HEdge Coordinator
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agents.risk_managers.hedge_coordinator import HEdgeCoordinator, CompositeRisk
from core import RiskTier


@pytest.fixture
def hedge():
    return HEdgeCoordinator(max_drawdown_pct=20.0, max_exposure=5000.0)


def test_hedge_init(hedge):
    assert hedge.max_drawdown_pct == 20.0
    assert hedge.max_exposure == 5000.0


def test_hedge_assess_no_learning_no_overseer(hedge):
    risk = hedge.assess()
    assert isinstance(risk, CompositeRisk)
    assert 0.0 <= risk.composite_score <= 1.0
    assert risk.tier_label in ("NORMAL", "CAUTION", "RESTRICTED", "HALT", "LIQUIDATE")


def test_hedge_assess_components(hedge):
    risk = hedge.assess()
    assert "circuit_breaker" in risk.components
    assert "learning" not in risk.components
    assert "agents" not in risk.components


def test_hedge_composite_score_range(hedge):
    for cb_tier in range(5):
        mock_risk = CompositeRisk(
            tier=RiskTier(cb_tier),
            circuit_breaker_tier=cb_tier,
            learning_win_rate=0.5,
            current_drawdown_pct=5.0,
            agent_health_score=1.0,
        )
        score = hedge._compute_composite_score(mock_risk)
        assert 0.0 <= score <= 1.0, f"Score out of range for tier {cb_tier}: {score}"


def test_hedge_score_to_tier():
    hedge = HEdgeCoordinator()
    assert hedge._score_to_tier(0.0) == RiskTier.LIQUIDATE
    assert hedge._score_to_tier(0.20) == RiskTier.HALT
    assert hedge._score_to_tier(0.40) == RiskTier.RESTRICTED
    assert hedge._score_to_tier(0.60) == RiskTier.CAUTION
    assert hedge._score_to_tier(0.80) == RiskTier.NORMAL


def test_hedge_publish_risk_state(hedge):
    with tempfile.TemporaryDirectory() as tmp:
        import agents.risk_managers.hedge_coordinator as hc
        old = hc.SHARED_DIR
        hc.SHARED_DIR = Path(tmp)
        state = hedge.publish_risk_state()
        assert "state" in state
        assert "composite_score" in state
        assert (Path(tmp) / "hedge_state.json").exists()
        hc.SHARED_DIR = old


def test_hedge_composite_score_drawdown_high(hedge):
    risk = CompositeRisk(circuit_breaker_tier=0, current_drawdown_pct=15.0)
    score = hedge._compute_composite_score(risk)
    assert score < 1.0


def test_hedge_composite_score_cb_halt(hedge):
    risk = CompositeRisk(circuit_breaker_tier=4)
    score = hedge._compute_composite_score(risk)
    assert score <= 0.6


def test_hedge_system_halted(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        breaker_path = Path(tmp) / "circuit_breaker.json"
        breaker_path.write_text(json.dumps({
            "state": "PAUSED", "monthly_pnl_pct": -33.21
        }))
        monkeypatch.setenv("SHARED_CONFIG_DIR", tmp)
        import agents.risk_managers.hedge_coordinator as hc
        import agents.risk_managers.circuit_breaker as cb
        import importlib
        importlib.reload(cb)
        importlib.reload(hc)
        hedge = hc.HEdgeCoordinator()
        risk = hedge.assess()
        assert risk.is_system_halted is True
