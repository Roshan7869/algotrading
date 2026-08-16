"""Tests for nexus/bridge.py and nexus/mcp_tools.py"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus.bridge import NexusBridge, get_bridge
from nexus.mcp_tools import get_tool_definitions, TOOL_DEFINITIONS


class TestNexusBridge:
    def test_singleton(self):
        b1 = get_bridge()
        b2 = get_bridge()
        assert b1 is b2

    def test_trade_status_returns_expected_keys(self):
        b = get_bridge()
        status = b.trade_status()
        assert "status" in status
        assert "circuit_breaker" in status
        assert "risk" in status
        assert "timestamp" in status
        assert status["status"] == "online"

    def test_trade_status_circuit_breaker_fields(self):
        b = get_bridge()
        cb = b.trade_status()["circuit_breaker"]
        assert "tier" in cb
        assert "tier_name" in cb
        assert "state" in cb
        assert isinstance(cb["tier"], int)

    def test_trade_status_risk_fields(self):
        b = get_bridge()
        risk = b.trade_status()["risk"]
        assert "composite_score" in risk
        assert "max_drawdown_pct" in risk
        assert "drawdown_breached" in risk

    def test_adjust_config_unknown_key(self):
        b = get_bridge()
        result = b.adjust_config("nonexistent_key", "value")
        assert result["success"] is False

    def test_adjust_config_max_drawdown(self):
        b = get_bridge()
        result = b.adjust_config("max_drawdown_pct", "15")
        assert result["success"] is True
        assert result["key"] == "max_drawdown_pct"
        assert result["value"] == "15"

    def test_adjust_config_max_trades(self):
        b = get_bridge()
        result = b.adjust_config("max_trades_per_day", "5")
        assert result["success"] is True

    def test_adjust_config_risk_tier(self):
        b = get_bridge()
        result = b.adjust_config("risk_tier", "NORMAL")
        assert result["success"] is True

    def test_feed_outcome(self):
        b = get_bridge()
        result = b.feed_outcome_to_nexus({
            "pair": "BTC/USDT",
            "pnl_pct": 2.5,
            "win": True,
            "strategy": "test_strat",
        })
        assert isinstance(result, dict)

    def test_record_coach_outcome(self):
        b = get_bridge()
        result = b.record_coach_outcome({
            "trade_id": "t1",
            "pair": "BTC/USDT",
            "pnl_pct": 1.0,
            "win": True,
            "strategy": "test_strat",
        })
        assert isinstance(result, dict)

    def test_read_json_missing_file(self):
        b = get_bridge()
        result = b._read_json(Path("/nonexistent/file.json"))
        assert result is None


class TestNexusMcpTools:
    def test_tool_definitions_count(self):
        defs = get_tool_definitions()
        assert len(defs) == 15

    def test_tool_definitions_have_required_fields(self):
        for tool in get_tool_definitions():
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    def test_tool_definitions_unique_names(self):
        defs = get_tool_definitions()
        names = [d["name"] for d in defs]
        assert len(names) == len(set(names)), "Duplicate tool names"

    def test_handle_unknown_tool(self):
        from nexus.mcp_tools import handle_tool_call
        result = handle_tool_call("nonexistent", {})
        assert "error" in result

    def test_handle_trade_status(self):
        from nexus.mcp_tools import handle_tool_call
        result = handle_tool_call("trade_status", {})
        assert result["status"] == "online"

    def test_handle_adjust_config(self):
        from nexus.mcp_tools import handle_tool_call
        result = handle_tool_call("adjust_config", {"key": "max_drawdown_pct", "value": "20"})
        assert result["success"] is True

    def test_handle_check_learning_status(self):
        from nexus.mcp_tools import handle_tool_call
        result = handle_tool_call("check_learning_status", {})
        assert "collection" in result or "error" in result


class TestEventBridge:
    def test_record_outcome_no_nexus(self):
        from nexus.event_bridge import record_outcome
        result = record_outcome("test_skill", "correct", "test task")
        assert isinstance(result, dict)
