"""Tests for AI Signal Generators (Phase 6)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import Signal
from engine.ai_signal_generators.base import SignalGenerator
from engine.ai_signal_generators.registry import GeneratorRegistry, get_registry
from engine.ai_signal_generators.miroshark_wrapper import MiroSharkGenerator
from engine.ai_signal_generators.trading_agents_wrapper import TradingAgentsGenerator
from engine.ai_signal_generators.macro_analyst import MacroAnalystGenerator
from engine.ai_signal_generators.kronos_runner import KronosGenerator
from engine.ai_signal_generators.orchestrator import SignalOrchestrator, get_orchestrator


class TestSignal:
    def test_default_timestamp(self):
        s = Signal(pair="BTC/USDT", action="BUY", confidence=0.8, direction="long", source="test")
        assert s.timestamp != ""

    def test_is_entry(self):
        assert Signal(pair="X", action="BUY", confidence=0.5, direction="long", source="t").is_entry
        assert Signal(pair="X", action="STRONG_BUY", confidence=0.8, direction="long", source="t").is_entry
        assert not Signal(pair="X", action="SELL", confidence=0.5, direction="short", source="t").is_entry

    def test_is_exit(self):
        assert Signal(pair="X", action="SELL", confidence=0.5, direction="short", source="t").is_exit
        assert Signal(pair="X", action="STRONG_SELL", confidence=0.8, direction="short", source="t").is_exit

    def test_numeric_action(self):
        assert Signal(pair="X", action="STRONG_BUY", confidence=0.5, direction="long", source="t").numeric_action == 2
        assert Signal(pair="X", action="STRONG_SELL", confidence=0.5, direction="short", source="t").numeric_action == -2
        assert Signal(pair="X", action="NEUTRAL", confidence=0.5, direction="neutral", source="t").numeric_action == 0

    def test_to_dict(self):
        s = Signal(pair="BTC/USDT", action="BUY", confidence=0.8, direction="long", source="test")
        d = s.to_dict()
        assert d["pair"] == "BTC/USDT"
        assert d["action"] == "BUY"
        assert d["source"] == "test"


class TestSignalGenerator:
    def test_base_generator(self):
        class TestGen(SignalGenerator):
            name = "test"
            description = "test gen"
            def generate(self, pair): return Signal(pair=pair, action="BUY", confidence=0.5, direction="long", source="test")

        gen = TestGen()
        assert gen.name == "test"
        assert gen.enabled
        gen.disable()
        assert not gen.enabled
        gen.enable()
        assert gen.enabled

    def test_generate_multi(self):
        class TestGen(SignalGenerator):
            name = "test"
            description = "test gen"
            def generate(self, pair): return Signal(pair=pair, action="BUY", confidence=0.5, direction="long", source="test")

        gen = TestGen()
        signals = gen.generate_multi(["BTC/USDT", "ETH/USDT"])
        assert len(signals) == 2
        assert signals[0].pair == "BTC/USDT"
        assert signals[1].pair == "ETH/USDT"


class TestGeneratorRegistry:
    def test_register_and_list(self):
        reg = GeneratorRegistry()
        gen = MiroSharkGenerator()
        reg.register(gen)
        assert "miroshark" in reg.list_names()
        assert reg.get("miroshark") is gen

    def test_unregister(self):
        reg = GeneratorRegistry()
        gen = MiroSharkGenerator()
        reg.register(gen)
        reg.unregister("miroshark")
        assert "miroshark" not in reg.list_names()

    def test_list_enabled(self):
        reg = GeneratorRegistry()
        gen1 = MiroSharkGenerator()
        gen2 = TradingAgentsGenerator()
        gen2.disable()
        reg.register(gen1)
        reg.register(gen2)
        enabled = reg.list_enabled()
        assert "miroshark" in enabled
        assert "tradingagents" not in enabled

    def test_generate_all(self):
        reg = GeneratorRegistry()
        gen = MiroSharkGenerator()
        reg.register(gen)
        signals = reg.generate_all("BTC/USDT")
        assert len(signals) >= 1
        assert all(isinstance(s, Signal) for s in signals)

    def test_consensus_single_generator(self):
        reg = GeneratorRegistry()
        gen = MiroSharkGenerator()
        reg.register(gen)
        consensus = reg.consensus("BTC/USDT")
        assert isinstance(consensus, Signal)

    def test_consensus_weighted(self):
        reg = GeneratorRegistry()

        class BullGen(SignalGenerator):
            name = "bull"
            description = ""
            def generate(self, pair): return Signal(pair=pair, action="STRONG_BUY", confidence=0.9, direction="long", source="bull")

        class BearGen(SignalGenerator):
            name = "bear"
            description = ""
            def generate(self, pair): return Signal(pair=pair, action="STRONG_SELL", confidence=0.8, direction="short", source="bear")

        reg.register(BullGen())
        reg.register(BearGen())

        consensus = reg.consensus("BTC/USDT")
        assert consensus.source == "consensus"


class TestMiroSharkGenerator:
    def test_generate_returns_signal(self):
        gen = MiroSharkGenerator()
        signal = gen.generate("BTC/USDT")
        assert isinstance(signal, Signal)
        assert signal.pair == "BTC/USDT"
        assert signal.source == "miroshark"

    def test_map_action(self):
        assert MiroSharkGenerator._map_action("STRONG_BUY") == "STRONG_BUY"
        assert MiroSharkGenerator._map_action("PAUSE") == "NEUTRAL"
        assert MiroSharkGenerator._map_action("SELL") == "SELL"


class TestTradingAgentsGenerator:
    def test_generate_returns_signal(self):
        gen = TradingAgentsGenerator()
        signal = gen.generate("BTC/USDT")
        assert isinstance(signal, Signal)
        assert signal.pair == "BTC/USDT"

    def test_map_action(self):
        assert TradingAgentsGenerator._map_action("bullish") == "BUY"
        assert TradingAgentsGenerator._map_action("bearish") == "SELL"
        assert TradingAgentsGenerator._map_action("HOLD") == "NEUTRAL"


class TestMacroAnalystGenerator:
    def test_generate_returns_signal(self):
        gen = MacroAnalystGenerator()
        signal = gen.generate("BTC/USDT")
        assert isinstance(signal, Signal)
        assert signal.pair == "BTC/USDT"
        assert signal.action in ("BUY", "SELL", "NEUTRAL")


class TestKronosGenerator:
    def test_generate_returns_signal(self):
        gen = KronosGenerator()
        signal = gen.generate("BTC/USDT")
        assert isinstance(signal, Signal)
        assert signal.pair == "BTC/USDT"


class TestSignalOrchestrator:
    def test_initialize(self):
        orch = get_orchestrator()
        orch.initialize()
        reg = orch._registry
        assert "miroshark" in reg.list_names()
        assert "tradingagents" in reg.list_names()
        assert "macro_analyst" in reg.list_names()
        assert "kronos" in reg.list_names()

    def test_run_pipeline_returns_dict(self):
        orch = SignalOrchestrator()
        result = orch.run_pipeline("BTC/USDT")
        assert "pair" in result
        assert "consensus" in result
        assert "signals" in result
        assert "risk_gate" in result
        assert "learning_gate" in result
        assert "blocked" in result
        assert result["pair"] == "BTC/USDT"

    def test_run_pipeline_blocked_during_halt(self):
        orch = SignalOrchestrator()
        result = orch.run_pipeline("BTC/USDT")
        risk = result["risk_gate"]
        assert "tier" in risk
        if risk.get("blocked"):
            assert risk.get("reason", "") != ""

    def test_run_all(self):
        orch = SignalOrchestrator()
        result = orch.run_all()
        assert "pairs" in result
        assert "timestamp" in result
