"""
Tests for Redis Signal Bus
"""

import json
import os
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.signal_bus import RedisSignalBus, CHANNELS


@pytest.fixture
def bus():
    b = RedisSignalBus(host="127.0.0.1", port=6379)
    yield b
    try:
        b.close()
    except Exception:
        pass


def test_publish_to_valid_channel(bus):
    result = bus.publish("signals", {"test": True})
    assert result is True


def test_publish_to_invalid_channel(bus):
    with pytest.raises(ValueError):
        bus.publish("invalid_channel", {})


def test_publish_signal(bus):
    result = bus.publish_signal("BTC/USDT", "long", 50000, 0.1, "test_strat")
    assert result is True


def test_publish_risk_event(bus):
    result = bus.publish_risk_event("drawdown_breach", "Drawdown exceeded 20%")
    assert result is True


def test_publish_pnl(bus):
    result = bus.publish_pnl("BTC/USDT", 150.0, "trade_001")
    assert result is True


def test_subscribe_valid(bus):
    bus.subscribe("signals")
    bus.subscribe("risk")
    bus.subscribe("pnl")


def test_subscribe_invalid(bus):
    with pytest.raises(ValueError):
        bus.subscribe("invalid")


def test_subscribe_all(bus):
    bus.subscribe_all()
    for ch in CHANNELS:
        bus.unsubscribe(ch)


def test_json_backup_write(bus):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SHARED_CONFIG_DIR"] = tmp
        import importlib
        mod = importlib.import_module("engine.signal_bus")
        importlib.reload(mod)
        test_bus = mod.RedisSignalBus()
        test_bus.publish_signal("ETH/USDT", "long", 3000, 1.0)
        backup_path = Path(tmp) / "signal_bus_signals.json"
        assert backup_path.exists()
        data = json.loads(backup_path.read_text())
        assert len(data) > 0
        assert data[0]["data"]["pair"] == "ETH/USDT"
        del os.environ["SHARED_CONFIG_DIR"]


def test_listen_no_subscribe(bus):
    results = list(bus.listen(timeout=0.5))
    assert results == []


def test_client_property(bus):
    assert bus.client is not None
