"""Tests for EnforcedRiskGate"""

import json
import os
import sys
import tempfile
import importlib
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import RiskTier, TradeDecision
from agents.risk_managers.circuit_breaker import (
    EnforcedRiskGate,
    classify_tier,
)


def make_breaker(state="HEALTHY", drawdown=0, monthly=0, reason=""):
    return {
        "state": state,
        "drawdown_pct": drawdown,
        "monthly_pnl_pct": monthly,
        "consecutive_sl": 0,
        "transition_reason": reason,
        "_timestamp": "2026-05-19T00:00:00+00:00",
    }


def _gate_with_state(state_dict):
    """Create EnforcedRiskGate that reads from a temp dir with given state."""
    tmp = tempfile.mkdtemp()
    breaker_path = Path(tmp) / "circuit_breaker.json"
    breaker_path.write_text(json.dumps(state_dict))
    old_env = os.environ.get("SHARED_CONFIG_DIR")
    os.environ["SHARED_CONFIG_DIR"] = tmp
    mod = importlib.import_module("agents.risk_managers.circuit_breaker")
    importlib.reload(mod)
    gate = mod.EnforcedRiskGate()
    os.environ.pop("SHARED_CONFIG_DIR", None)
    if old_env is not None:
        os.environ["SHARED_CONFIG_DIR"] = old_env
    return gate


def test_tier_classification_healthy():
    data = make_breaker("HEALTHY", 0, 0)
    assert classify_tier(data) == RiskTier.NORMAL


def test_tier_classification_caution():
    data = make_breaker("CAUTION", 10, 0)
    assert classify_tier(data) == RiskTier.CAUTION


def test_tier_classification_halt_paused():
    data = make_breaker("PAUSED", 0, -33.21)
    assert classify_tier(data) == RiskTier.HALT


def test_tier_classification_halt_monthly():
    data = make_breaker("HEALTHY", 0, -30)
    assert classify_tier(data) == RiskTier.HALT


def test_tier_classification_liquidate():
    data = make_breaker("LIQUIDATE", 55, 0)
    assert classify_tier(data) == RiskTier.LIQUIDATE


def test_gate_blocks_when_halted():
    gate = _gate_with_state(make_breaker("PAUSED", 0, -33.21, "Weekly drawdown breach"))
    decision = gate.gate("BTC/USDT", "long", 1.0, "test")
    assert not decision.approved, "Should block trades during PAUSE"
    assert "HALT" in decision.reason


def test_gate_allows_when_healthy():
    gate = _gate_with_state(make_breaker("HEALTHY", 0, 5.0))
    decision = gate.gate("BTC/USDT", "long", 1.0, "test")
    assert decision.approved
    assert decision.size_multiplier == 1.0


def test_gate_reduces_on_caution():
    gate = _gate_with_state(make_breaker("CAUTION", 10, 0))
    decision = gate.gate("BTC/USDT", "long", 1.0, "test")
    assert decision.approved
    assert decision.size_multiplier == 0.75


def test_gate_restricts_shorts():
    gate = _gate_with_state(make_breaker("RESTRICTED", 20, 0))
    decision = gate.gate("BTC/USDT", "short", 1.0, "test")
    assert not decision.approved
    assert "Shorts disabled" in decision.reason


def test_gate_reduces_on_restricted():
    gate = _gate_with_state(make_breaker("RESTRICTED", 20, 0))
    decision = gate.gate("BTC/USDT", "long", 1.0, "test")
    assert decision.approved
    assert decision.size_multiplier == 0.5


def test_gate_liquidate():
    gate = _gate_with_state(make_breaker("LIQUIDATE", 55, 0))
    decision = gate.gate("BTC/USDT", "long", 1.0, "test")
    assert not decision.approved
    assert "LIQUIDATE" in decision.reason


def test_reads_from_breaker_file():
    with tempfile.TemporaryDirectory() as tmp:
        breaker_path = Path(tmp) / "circuit_breaker.json"
        breaker_path.write_text(json.dumps(make_breaker("PAUSED", 0, -33.21)))
        os.environ["SHARED_CONFIG_DIR"] = tmp
        mod = importlib.import_module("agents.risk_managers.circuit_breaker")
        importlib.reload(mod)
        data = mod.read_breaker_state()
        assert data["state"] == "PAUSED"
        del os.environ["SHARED_CONFIG_DIR"]


def test_decision_dataclass():
    d1 = TradeDecision.APPROVED()
    assert d1.approved and d1.size_multiplier == 1.0

    d2 = TradeDecision.BLOCKED("test reason")
    assert not d2.approved and d2.reason == "test reason"

    d3 = TradeDecision.REDUCED(0.5, "reduced")
    assert d3.approved and d3.size_multiplier == 0.5


def test_gate_cache_hit():
    gate = _gate_with_state(make_breaker("HEALTHY", 0, 5.0))
    d1 = gate.gate("BTC/USDT", "long", 1.0, "test")
    assert d1.approved
    d2 = gate.gate("ETH/USDT", "long", 1.0, "test")
    assert d2.approved
