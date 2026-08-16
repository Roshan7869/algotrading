"""
Tests for Freqtrade Bridge
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.freqtrade_bridge import FreqtradeBridge


@pytest.fixture
def bridge():
    b = FreqtradeBridge(redis_host="127.0.0.1", redis_port=6379)
    yield b
    try:
        b.stop()
    except Exception:
        pass


def test_bridge_process_signal_healthy(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        breaker_path = Path(tmp) / "circuit_breaker.json"
        breaker_path.write_text(json.dumps({
            "state": "HEALTHY", "drawdown_pct": 0, "monthly_pnl_pct": 5.0
        }))
        monkeypatch.setenv("SHARED_CONFIG_DIR", tmp)

        import importlib
        from agents.risk_managers import circuit_breaker as cb
        importlib.reload(cb)

        from engine.freqtrade_bridge import FreqtradeBridge
        b = FreqtradeBridge()
        result = b.process_signal("BTC/USDT", "long", 50000, 0.1, "test_strat")
        assert result["approved"] is True
        assert result["size_multiplier"] == 1.0
        b.stop()


def test_bridge_process_signal_blocked(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        breaker_path = Path(tmp) / "circuit_breaker.json"
        breaker_path.write_text(json.dumps({
            "state": "PAUSED", "monthly_pnl_pct": -33.21
        }))
        monkeypatch.setenv("SHARED_CONFIG_DIR", tmp)

        import importlib
        from agents.risk_managers import circuit_breaker as cb
        importlib.reload(cb)

        from engine.freqtrade_bridge import FreqtradeBridge
        b = FreqtradeBridge()
        result = b.process_signal("BTC/USDT", "long", 50000, 0.1, "test_strat")
        assert result["approved"] is False
        b.stop()


def test_bridge_process_signal_short_restricted(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        breaker_path = Path(tmp) / "circuit_breaker.json"
        breaker_path.write_text(json.dumps({
            "state": "RESTRICTED", "drawdown_pct": 20, "monthly_pnl_pct": -5
        }))
        monkeypatch.setenv("SHARED_CONFIG_DIR", tmp)

        import importlib
        from agents.risk_managers import circuit_breaker as cb
        importlib.reload(cb)

        from engine.freqtrade_bridge import FreqtradeBridge
        b = FreqtradeBridge()
        result = b.process_signal("BTC/USDT", "short", 50000, 0.1, "test_strat")
        assert result["approved"] is False
        b.stop()


def test_bridge_process_signal_caution_reduces_size(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        breaker_path = Path(tmp) / "circuit_breaker.json"
        breaker_path.write_text(json.dumps({
            "state": "CAUTION", "drawdown_pct": 10, "monthly_pnl_pct": -5
        }))
        monkeypatch.setenv("SHARED_CONFIG_DIR", tmp)

        import importlib
        from agents.risk_managers import circuit_breaker as cb
        importlib.reload(cb)

        from engine.freqtrade_bridge import FreqtradeBridge
        b = FreqtradeBridge()
        result = b.process_signal("BTC/USDT", "long", 50000, 0.1, "test_strat")
        assert result["approved"] is True
        assert result["size_multiplier"] == 0.75
        b.stop()


def test_bridge_process_pnl(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SHARED_CONFIG_DIR", tmp)
        from engine.freqtrade_bridge import FreqtradeBridge
        b = FreqtradeBridge()
        result = b.process_pnl("BTC/USDT", 150.0, "trade_001")
        b.stop()


def test_bridge_stop(bridge):
    bridge.stop()
    assert bridge._running is False
