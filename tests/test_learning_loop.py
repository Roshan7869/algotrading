"""
Tests for Learning Loop (ChromaDB integration)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from knowledge.learning_loop import LearningLoop


@pytest.fixture
def loop():
    return LearningLoop(min_win_rate=0.40)


@pytest.fixture
def loop_with_history(loop, tmp_path):
    outcome_path = tmp_path / "outcome_history.json"
    old_path = None
    import knowledge.learning_loop as ll
    old_path = ll.OUTCOME_PATH
    ll.OUTCOME_PATH = outcome_path
    history = {
        "trades": [
            {"pair": "BTC/USDT", "side": "long", "pnl": 100.0, "r_multiple": 2.0,
             "setup_name": "Breakout", "market_condition": "trending", "strategy": "test"},
            {"pair": "BTC/USDT", "side": "long", "pnl": -50.0, "r_multiple": -1.0,
             "setup_name": "Breakout", "market_condition": "trending", "strategy": "test"},
        ],
        "chunk_stats": {
            "Breakout": {
                "total_trades": 2, "wins": 1, "losses": 1,
                "total_pnl": 50.0, "total_r_multiple": 1.0,
                "regime_breakdown": {
                    "trending": {"trades": 2, "wins": 1, "pnl": 50.0, "r_multiple": 1.0}
                }
            },
            "RSI Divergence": {
                "total_trades": 5, "wins": 3, "losses": 2,
                "total_pnl": 200.0, "total_r_multiple": 4.0,
                "regime_breakdown": {
                    "ranging": {"trades": 5, "wins": 3, "pnl": 200.0, "r_multiple": 4.0}
                }
            },
        }
    }
    outcome_path.write_text(json.dumps(history))
    yield loop
    ll.OUTCOME_PATH = old_path


def test_learning_loop_init(loop):
    assert loop.min_win_rate == 0.40


def test_learning_loop_summary_empty(loop):
    with tempfile.TemporaryDirectory() as tmp:
        import knowledge.learning_loop as ll
        old = ll.OUTCOME_PATH
        ll.OUTCOME_PATH = Path(tmp) / "empty.json"
        s = loop.get_summary()
        assert s["total_trades"] == 0
        assert s["trades_in_log"] == 0
        ll.OUTCOME_PATH = old


def test_learning_loop_record_outcome(loop):
    with tempfile.TemporaryDirectory() as tmp:
        import knowledge.learning_loop as ll
        old = ll.OUTCOME_PATH
        ll.OUTCOME_PATH = Path(tmp) / "outcome_history.json"
        loop.record_outcome("BTC/USDT", "long", 150.0, 2.5, "TestSetup", "trending", "test")
        history = json.loads((Path(tmp) / "outcome_history.json").read_text())
        assert len(history["trades"]) == 1
        assert "TestSetup" in history["chunk_stats"]
        assert history["chunk_stats"]["TestSetup"]["total_trades"] == 1
        ll.OUTCOME_PATH = old


def test_learning_loop_get_setup_win_rate(loop_with_history):
    rate = loop_with_history.get_setup_win_rate("Breakout")
    assert rate == 0.5


def test_learning_loop_get_setup_win_rate_nonexistent(loop_with_history):
    rate = loop_with_history.get_setup_win_rate("NonExistent")
    assert rate is None


def test_learning_loop_get_summary(loop_with_history):
    s = loop_with_history.get_summary()
    assert s["total_trades"] == 7
    assert s["total_wins"] == 4
    assert s["total_losses"] == 3
    assert s["unique_setups"] == 2


def test_learning_loop_is_available(loop):
    assert isinstance(loop.is_available(), bool)


def test_learning_loop_pre_trade_blocked(loop_with_history):
    result = loop_with_history.pre_trade_check(
        pair="BTC/USDT", side="long", strategy="test"
    )
    assert "approved" in result
    assert "win_rate" in result


def test_learning_loop_aggregate_win_rate_empty(loop):
    result = loop._aggregate_win_rate([])
    assert result[0] == 0.0
    assert result[1] == 0
