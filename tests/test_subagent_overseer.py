"""
Tests for SubAgentOverseer
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agents.risk_managers.subagent_overseer import SubAgentOverseer, AgentStatus


@pytest.fixture
def overseer():
    return SubAgentOverseer(redis_host="127.0.0.1", redis_port=6379)


def test_overseer_init(overseer):
    assert len(overseer._agents) == 5
    assert "tradingagents" in overseer._agents
    assert "mirofish" in overseer._agents


def test_overseer_register_agent(overseer):
    overseer.register_agent("test_agent", max_trades_per_day=5)
    agent = overseer.get_agent("test_agent")
    assert agent is not None
    assert agent.max_trades_per_day == 5


def test_overseer_heartbeat(overseer):
    overseer.heartbeat("tradingagents", status="running")
    agent = overseer.get_agent("tradingagents")
    assert agent is not None
    assert agent.status == "running"
    assert agent.last_heartbeat > 0


def test_overseer_heartbeat_with_error(overseer):
    overseer.heartbeat("tradingagents", status="error", error="API timeout")
    agent = overseer.get_agent("tradingagents")
    assert agent.consecutive_failures == 1
    assert agent.last_error == "API timeout"


def test_overseer_health_check_initial(overseer):
    health = overseer.health_check()
    assert health["total_agents"] == 5
    assert health["healthy_agents"] == 0
    assert health["stale_agents"] == 5


def test_overseer_health_check_healthy(overseer):
    overseer.heartbeat("tradingagents", status="running")
    overseer.heartbeat("mirofish", status="running")
    health = overseer.health_check()
    assert health["healthy_agents"] >= 2


def test_overseer_record_trade(overseer):
    overseer.record_trade("tradingagents")
    agent = overseer.get_agent("tradingagents")
    assert agent.trades_today == 1


def test_overseer_record_trade_multiple(overseer):
    for _ in range(3):
        overseer.record_trade("tradingagents")
    agent = overseer.get_agent("tradingagents")
    assert agent.trades_today == 3


def test_overseer_reset_daily_counts(overseer):
    overseer.record_trade("tradingagents")
    overseer.record_trade("mirofish")
    overseer.reset_daily_counts()
    for agent in overseer._agents.values():
        assert agent.trades_today == 0


def test_overseer_agent_status_dataclass():
    status = AgentStatus(name="test", status="running", max_trades_per_day=10)
    assert status.name == "test"
    assert status.is_healthy is True
    assert status.trades_today == 0


def test_overseer_publish_health(overseer):
    with tempfile.TemporaryDirectory() as tmp:
        import agents.risk_managers.subagent_overseer as so
        old = so.SHARED_DIR
        so.SHARED_DIR = Path(tmp)
        health = overseer.publish_health()
        assert "health_score" in health
        assert (Path(tmp) / "agent_health.json").exists()
        so.SHARED_DIR = old


def test_overseer_heartbeat_new_agent(overseer):
    overseer.heartbeat("unknown_agent", status="running")
    agent = overseer.get_agent("unknown_agent")
    assert agent is not None
    assert agent.status == "running"
