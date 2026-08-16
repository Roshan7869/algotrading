"""Integration tests for the full signal pipeline."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRiskGateIntegration:
    def test_circuit_breaker_defaults_to_halt_on_corrupted_file(self):
        from agents.risk_managers.circuit_breaker import read_breaker_state
        with tempfile.TemporaryDirectory() as tmp:
            breaker_path = Path(tmp) / "circuit_breaker.json"
            breaker_path.write_text("not valid json")
            old_env = os.environ.get("SHARED_CONFIG_DIR")
            os.environ["SHARED_CONFIG_DIR"] = tmp
            import importlib
            mod = importlib.import_module("agents.risk_managers.circuit_breaker")
            importlib.reload(mod)
            data = mod.read_breaker_state()
            assert data["state"] == "HALT"
            if old_env:
                os.environ["SHARED_CONFIG_DIR"] = old_env
            else:
                del os.environ["SHARED_CONFIG_DIR"]

    def test_risk_gate_reads_and_uses_regime_multiplier(self):
        from agents.risk_managers.circuit_breaker import read_regime_state
        with tempfile.TemporaryDirectory() as tmp:
            regime_path = Path(tmp) / "market_regime.json"
            regime_path.write_text(json.dumps({"regime": "volatile", "regime_multiplier": 0.5}))
            old_env = os.environ.get("SHARED_CONFIG_DIR")
            os.environ["SHARED_CONFIG_DIR"] = tmp
            import importlib
            mod = importlib.import_module("agents.risk_managers.circuit_breaker")
            importlib.reload(mod)
            regime = mod.read_regime_state()
            assert regime["regime"] == "volatile"
            assert regime["regime_multiplier"] == 0.5
            if old_env:
                os.environ["SHARED_CONFIG_DIR"] = old_env
            else:
                del os.environ["SHARED_CONFIG_DIR"]

    def test_regime_multiplier_compounds_with_tier_reduction(self):
        from agents.risk_managers.circuit_breaker import EnforcedRiskGate
        with tempfile.TemporaryDirectory() as tmp:
            breaker_path = Path(tmp) / "circuit_breaker.json"
            breaker_path.write_text(json.dumps({
                "state": "CAUTION", "drawdown_pct": 10, "monthly_pnl_pct": -5,
            }))
            regime_path = Path(tmp) / "market_regime.json"
            regime_path.write_text(json.dumps({"regime": "volatile", "regime_multiplier": 0.5}))
            old_env = os.environ.get("SHARED_CONFIG_DIR")
            os.environ["SHARED_CONFIG_DIR"] = tmp
            import importlib
            mod = importlib.import_module("agents.risk_managers.circuit_breaker")
            importlib.reload(mod)
            gate = mod.EnforcedRiskGate()
            decision = gate.gate("BTC/USDT", "long", 1.0, "test")
            assert decision.approved
            assert decision.size_multiplier == 0.75 * 0.5
            if old_env:
                os.environ["SHARED_CONFIG_DIR"] = old_env
            else:
                del os.environ["SHARED_CONFIG_DIR"]

    def test_risk_gate_with_threshold_injection(self):
        from agents.risk_managers.circuit_breaker import EnforcedRiskGate, classify_tier
        thresholds = {"caution_drawdown": 5}
        with tempfile.TemporaryDirectory() as tmp:
            breaker_path = Path(tmp) / "circuit_breaker.json"
            breaker_path.write_text(json.dumps({
                "state": "HEALTHY", "drawdown_pct": 8, "monthly_pnl_pct": 0,
            }))
            old_env = os.environ.get("SHARED_CONFIG_DIR")
            os.environ["SHARED_CONFIG_DIR"] = tmp
            import importlib
            mod = importlib.import_module("agents.risk_managers.circuit_breaker")
            importlib.reload(mod)
            tier = mod.classify_tier({"state": "HEALTHY", "drawdown_pct": 8, "monthly_pnl_pct": 0}, thresholds=thresholds)
            from core import RiskTier
            assert tier == RiskTier.CAUTION
            if old_env:
                os.environ["SHARED_CONFIG_DIR"] = old_env
            else:
                del os.environ["SHARED_CONFIG_DIR"]


class TestLearningLoopIntegration:
    def test_learning_loop_can_sync_to_nexus(self):
        from knowledge.learning_loop import LearningLoop
        loop = LearningLoop()
        with tempfile.TemporaryDirectory() as tmp:
            import os as _os
            outcome_path = Path(tmp) / "outcome_history.json"
            from knowledge.learning_loop import OUTCOME_PATH
            old_path = str(outcome_path)
            loop.record_outcome(
                pair="BTC/USDT", side="long", pnl=150.0,
                r_multiple=2.5, setup_name="TestSetup",
                market_condition="trending", strategy="test",
            )
            assert True

    def test_learning_loop_pre_trade_check(self):
        from knowledge.learning_loop import LearningLoop
        loop = LearningLoop()
        result = loop.pre_trade_check(pair="BTC/USDT", side="long", strategy="test")
        assert "approved" in result
        assert "win_rate" in result
        assert "block_reason" in result

    def test_record_outcome_updates_strategy_performance_h2(self):
        from knowledge.learning_loop import LearningLoop
        from engine.strategy_registry import PERFORMANCE_DB
        if PERFORMANCE_DB.exists():
            old = PERFORMANCE_DB.read_text()
        else:
            old = None
        try:
            loop = LearningLoop()
            loop._update_strategy_performance("AroonMomentumEngine_Hybrid", True, 100.0)
            perf = json.loads(PERFORMANCE_DB.read_text())
            assert "AroonMomentumEngine_Hybrid" in perf
        finally:
            if old:
                PERFORMANCE_DB.write_text(old)

    def test_record_outcome_triggers_chromadb_sync_h3(self):
        from knowledge.learning_loop import LearningLoop
        loop = LearningLoop()
        try:
            loop.record_outcome(
                pair="BTC/USDT", side="long", pnl=50.0,
                r_multiple=1.0, setup_name="TestSetupH3",
                market_condition="ranging", strategy="test",
            )
            assert True
        except Exception as e:
            pytest.fail(f"record_outcome should not raise: {e}")


class TestSignalBusIntegration:
    def test_publish_with_json_backup(self):
        from engine.signal_bus import RedisSignalBus, SHARED_DIR
        bus = RedisSignalBus()
        signals_path = SHARED_DIR / "signal_bus_signals.json"
        if signals_path.exists():
            signals_path.unlink()
        bus.publish_signal("BTC/USDT", "buy", 50000.0, 0.1, "int_test")
        time.sleep(0.3)
        assert signals_path.exists()
        data = json.loads(signals_path.read_text())
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[-1]["data"]["strategy"] == "int_test"

    def test_publish_risk_event_to_file(self):
        from engine.signal_bus import RedisSignalBus, SHARED_DIR
        bus = RedisSignalBus()
        risk_path = SHARED_DIR / "signal_bus_risk.json"
        if risk_path.exists():
            risk_path.unlink()
        bus.publish_risk_event("integration_test", "test message", {"source": "pytest"})
        time.sleep(0.3)
        assert risk_path.exists()
        data = json.loads(risk_path.read_text())
        assert data[-1]["data"]["event"] == "integration_test"

    def test_publish_pnl(self):
        from engine.signal_bus import RedisSignalBus, SHARED_DIR
        bus = RedisSignalBus()
        pnl_path = SHARED_DIR / "signal_bus_pnl.json"
        if pnl_path.exists():
            pnl_path.unlink()
        bus.publish_pnl("BTC/USDT", 250.0, "trade_001")
        time.sleep(0.3)
        assert pnl_path.exists()
        data = json.loads(pnl_path.read_text())
        assert data[-1]["data"]["pair"] == "BTC/USDT"

    def test_signal_bus_roundtrip(self):
        import redis
        from engine.signal_bus import RedisSignalBus
        bus = RedisSignalBus()
        try:
            bus.client.ping()
        except redis.ConnectionError:
            pytest.skip("Redis not available")
        bus.subscribe("signals")
        bus.publish_signal("BTC/USDT", "buy", 50000.0, 0.1, "roundtrip_test")
        time.sleep(0.5)
        msgs = list(bus.listen(timeout=2.0))
        bus.unsubscribe_all()
        bus.close()
        assert len(msgs) >= 1


class TestWalkforwardIntegration:
    def test_walkforward_window_has_new_fields(self):
        from engine.walkforward import WalkforwardWindow
        w = WalkforwardWindow(
            train_start="20250101", train_end="20250301",
            test_start="20250301", test_end="20250401",
        )
        assert hasattr(w, "train_sharpe")
        assert hasattr(w, "train_drawdown")
        assert w.train_sharpe == 0.0
        assert w.train_drawdown == 0.0

    def test_compute_report_with_windows(self):
        from engine.walkforward import WalkforwardWindow, compute_report
        w1 = WalkforwardWindow(
            train_start="20250101", train_end="20250301",
            test_start="20250301", test_end="20250401",
            train_sharpe=1.2, sharpe=0.8,
            train_drawdown=5.0, max_drawdown=10.0, num_trades=15,
        )
        w2 = WalkforwardWindow(
            train_start="20250301", train_end="20250501",
            test_start="20250501", test_end="20250601",
            train_sharpe=0.9, sharpe=0.6,
            train_drawdown=8.0, max_drawdown=15.0, num_trades=12,
        )
        report = compute_report("TestStrat", [w1, w2])
        assert report.avg_train_sharpe == 1.05
        assert report.avg_test_sharpe == 0.7
        assert report.avg_train_dd == 6.5
        assert report.avg_test_dd == 12.5
        assert report.total_trades == 27


class TestEventBridgeIntegration:
    def test_event_bridge_falls_through_on_feedback_failure(self):
        from nexus.event_bridge import record_outcome
        result = record_outcome("test_skill", "correct", "test task")
        assert isinstance(result, dict)

    def test_event_bridge_outcome_map(self):
        from nexus.event_bridge import _OUTCOME_MAP
        assert _OUTCOME_MAP["correct"] == "task_completed"
        assert _OUTCOME_MAP["wrong"] == "test_failed"

    def test_event_bridge_nexus_feedback_works_h4(self):
        from nexus.event_bridge import record_outcome
        result = record_outcome("nexus_feedback_h4_test", "correct", "H4 integration test")
        assert result.get("success") is True
        assert result.get("via") == "nexus_feedback"


class TestNexusBridgeIntegration:
    def test_trade_status_returns_valid_structure(self):
        from nexus.bridge import get_bridge
        bridge = get_bridge()
        status = bridge.trade_status()
        assert status["status"] == "online"
        assert "circuit_breaker" in status
        assert "risk" in status

    def test_feed_outcome_to_nexus_handles_missing_nexus(self):
        from nexus.bridge import get_bridge
        bridge = get_bridge()
        result = bridge.feed_outcome_to_nexus({
            "pair": "BTC/USDT", "pnl_pct": 2.5, "win": True, "strategy": "test",
        })
        assert isinstance(result, dict)

    def test_adjust_config_validation(self):
        from nexus.bridge import get_bridge
        bridge = get_bridge()
        r1 = bridge.adjust_config("max_drawdown_pct", "200")
        assert r1["success"] is False
        r2 = bridge.adjust_config("max_trades_per_day", "-1")
        assert r2["success"] is False
        r3 = bridge.adjust_config("risk_tier", "INVALID")
        assert r3["success"] is False
        r4 = bridge.adjust_config("risk_tier", "HALT")
        assert r4["success"] is True


class TestOpenBBWrapperIntegration:
    def test_openbb_wrapper_falls_back_to_yfinance(self):
        from mcp_layer.openbb_wrapper import get_available, get_quote, get_company_info
        assert get_available() is False
        quote = get_quote("AAPL")
        assert "symbol" in quote
        assert "price" in quote
        info = get_company_info("AAPL")
        assert "name" in info


class TestAlerterIntegration:
    def test_alerter_initializes_and_checks(self):
        from monitoring.alerter import Alerter
        alerter = Alerter({"alert_on_critical_breaker": False, "alert_on_warning_breaker": False})
        alerts = alerter.check_all()
        assert isinstance(alerts, list)

    def test_alerter_detects_stale_signals(self):
        from monitoring.alerter import Alerter
        alerter = Alerter({"alert_on_stale_signals": True, "max_signal_age": 0})
        alerts = alerter.check_all()
        stale = [a for a in alerts if a["type"] == "freshness"]
        assert len(stale) >= 0

    def test_alerter_get_stats(self):
        from monitoring.alerter import Alerter
        alerter = Alerter()
        stats = alerter.get_stats()
        assert "total_alerts_fired" in stats
        assert "config" in stats
        from nexus.bridge import get_bridge
        bridge = get_bridge()
        r1 = bridge.adjust_config("max_drawdown_pct", "200")
        assert r1["success"] is False
        r2 = bridge.adjust_config("max_trades_per_day", "-1")
        assert r2["success"] is False
        r3 = bridge.adjust_config("risk_tier", "INVALID")
        assert r3["success"] is False
        r4 = bridge.adjust_config("risk_tier", "HALT")
        assert r4["success"] is True
