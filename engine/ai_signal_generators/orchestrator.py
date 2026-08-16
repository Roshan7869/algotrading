"""SignalOrchestrator — runs all generators through risk gate → bus pipeline."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core import Signal
from engine.ai_signal_generators.registry import get_registry
from engine.ai_signal_generators.miroshark_wrapper import MiroSharkGenerator
from engine.ai_signal_generators.trading_agents_wrapper import TradingAgentsGenerator
from engine.ai_signal_generators.macro_analyst import MacroAnalystGenerator
from engine.ai_signal_generators.kronos_runner import KronosGenerator

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent.parent / "shared_config"))


class SignalOrchestrator:
    def __init__(self):
        self._registry = get_registry()
        self._initialized = False
        self._bus = None

    @property
    def bus(self):
        if self._bus is None:
            from engine.signal_bus import RedisSignalBus
            self._bus = RedisSignalBus()
        return self._bus

    def initialize(self):
        if self._initialized:
            return
        self._registry.register(MiroSharkGenerator())
        self._registry.register(TradingAgentsGenerator())
        self._registry.register(MacroAnalystGenerator())
        self._registry.register(KronosGenerator())
        self._initialized = True

    def run_pipeline(self, pair: str) -> dict:
        self.initialize()

        signals = self._registry.generate_all(pair)
        consensus = self._registry.consensus(pair)

        risk_gate_result = self._check_risk_gate(consensus)
        learning_result = self._check_learning(consensus)

        blocked = risk_gate_result.get("blocked", False) or learning_result.get("blocked", False)
        block_reasons = []
        if risk_gate_result.get("blocked"):
            block_reasons.append(risk_gate_result["reason"])
        if learning_result.get("blocked"):
            block_reasons.append(learning_result["reason"])

        if not blocked:
            self._publish_signal(consensus)

        pipeline_result = {
            "pair": pair,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "consensus": consensus.to_dict(),
            "signals": [s.to_dict() for s in signals],
            "risk_gate": risk_gate_result,
            "learning_gate": learning_result,
            "blocked": blocked,
            "block_reasons": block_reasons,
            "published": not blocked,
        }

        self._publish_pipeline_result(pipeline_result)
        return pipeline_result

    def run_all(self, pairs: Optional[list[str]] = None) -> dict:
        if pairs is None:
            pairs = ["BTC/USDT", "ETH/USDT"]
        results = {}
        for pair in pairs:
            results[pair] = self.run_pipeline(pair)
        return {"pairs": results, "timestamp": datetime.now(timezone.utc).isoformat()}

    def _check_risk_gate(self, signal: Signal) -> dict:
        from agents.risk_managers.circuit_breaker import read_breaker_state, classify_tier
        from core import RiskTier

        breaker = read_breaker_state()
        tier = classify_tier(breaker)

        if tier >= RiskTier.HALT:
            return {"blocked": True, "tier": int(tier), "reason": f"Circuit breaker HALT/LIQUIDATE (tier {tier})"}
        if tier == RiskTier.RESTRICTED and signal.direction == "short":
            return {"blocked": True, "tier": int(tier), "reason": f"Circuit breaker RESTRICTED — shorts blocked"}

        return {"blocked": False, "tier": int(tier), "reason": "Risk gate passed"}

    def _check_learning(self, signal: Signal) -> dict:
        try:
            from knowledge.learning_loop import LearningLoop
            loop = LearningLoop()
            result = loop.pre_trade_check(
                pair=signal.pair,
                side=signal.direction,
                market_condition="",
                signal_type=signal.action,
                strategy=signal.source,
            )
            approved = result.get("approved", True)
            block_reason = result.get("block_reason", "")
            return {
                "blocked": not approved,
                "reason": "Learning gate passed" if approved else f"Learning gate blocked: {block_reason}",
                "win_rate": result.get("win_rate"),
            }
        except Exception as e:
            return {"blocked": False, "reason": f"Learning check skipped: {e}"}

    def __init__(self):
        self._registry = get_registry()
        self._initialized = False
        self._bus = None

    @property
    def bus(self):
        if self._bus is None:
            from engine.signal_bus import RedisSignalBus
            self._bus = RedisSignalBus()
        return self._bus

    def initialize(self):
        if self._initialized:
            return
        self._registry.register(MiroSharkGenerator())
        self._registry.register(TradingAgentsGenerator())
        self._registry.register(MacroAnalystGenerator())
        self._registry.register(KronosGenerator())
        self._initialized = True

    def _publish_signal(self, signal: Signal):
        try:
            self.bus.publish_signal(
                pair=signal.pair,
                side=signal.direction,
                price=signal.price,
                amount=signal.quantity,
                strategy=signal.source,
                signal_id=f"orch_{int(time.time())}_{signal.pair.replace('/', '_')}",
            )
        except Exception:
            self._write_json(SHARED_DIR / "orchestrator_signal.json", signal.to_dict())

    def _publish_pipeline_result(self, result: dict):
        self._write_json(SHARED_DIR / "orchestrator_result.json", result)

    def _write_json(self, path: Path, data: dict):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, default=str))
        except OSError:
            pass


_orchestrator: Optional[SignalOrchestrator] = None


def get_orchestrator() -> SignalOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SignalOrchestrator()
    return _orchestrator
