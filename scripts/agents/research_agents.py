from __future__ import annotations

import asyncio
from typing import Any

from .ollama_client import OllamaClient
from .schemas import AgentResult, MarketSnapshot, clamp


SYSTEM_PROMPT = """You are a trading risk analyst. Return only JSON with:
decision approve|reject|wait, side long|short|none, confidence 0..1,
max_leverage number, stake_pct 0..1, reasons array, reject_if array.
You may reduce risk. Never increase risk above provided limits."""


class BaseResearchAgent:
    name = "base"

    def __init__(self, model: str = "qwen3:latest", use_ollama: bool = False):
        self.model = model
        self.use_ollama = use_ollama
        self.client = OllamaClient(model=model)

    async def run(self, snapshot: MarketSnapshot, context: dict[str, Any]) -> AgentResult:
        deterministic = self._deterministic(snapshot, context)
        if not self.use_ollama:
            return deterministic
        try:
            payload = await asyncio.to_thread(
                self.client.chat_json,
                SYSTEM_PROMPT,
                {
                    "agent": self.name,
                    "snapshot": snapshot.to_dict(),
                    "context": context,
                    "deterministic_baseline": deterministic.to_dict(),
                },
            )
            return self._from_payload(payload, deterministic)
        except Exception as exc:
            deterministic.reasons.append(f"ollama_unavailable:{exc}")
            deterministic.decision = "wait"
            return deterministic

    def _deterministic(self, snapshot: MarketSnapshot, context: dict[str, Any]) -> AgentResult:
        return AgentResult(agent=self.name, decision="wait", reasons=["base_agent_noop"])

    def _from_payload(self, payload: dict[str, Any], fallback: AgentResult) -> AgentResult:
        decision = payload.get("decision", fallback.decision)
        side = payload.get("side", fallback.side)
        if decision not in {"approve", "reject", "wait"}:
            decision = "wait"
        if side not in {"long", "short", "none"}:
            side = "none"
        return AgentResult(
            agent=self.name,
            decision=decision,
            side=side,
            confidence=clamp(float(payload.get("confidence", fallback.confidence)), 0.0, 1.0),
            max_leverage=clamp(float(payload.get("max_leverage", fallback.max_leverage)), 0.0, 3.0),
            stake_pct=clamp(float(payload.get("stake_pct", fallback.stake_pct)), 0.0, 0.15),
            reasons=list(payload.get("reasons", fallback.reasons))[:8],
            reject_if=list(payload.get("reject_if", fallback.reject_if))[:8],
            model=self.model,
            raw=payload,
        )


class MarketRegimeAgent(BaseResearchAgent):
    name = "market_regime"

    def _deterministic(self, snapshot: MarketSnapshot, context: dict[str, Any]) -> AgentResult:
        if snapshot.btc_regime == "parabolic":
            return AgentResult(
                agent=self.name,
                decision="reject",
                side="short",
                confidence=0.8,
                max_leverage=1.0,
                stake_pct=0.0,
                reasons=["btc_parabolic_blocks_shorts"],
                reject_if=["btc_regime_parabolic"],
            )
        return AgentResult(
            agent=self.name,
            decision="wait",
            side="none",
            confidence=0.5,
            max_leverage=3.0,
            stake_pct=0.05,
            reasons=["btc_regime_not_parabolic"],
        )


class PairScannerAgent(BaseResearchAgent):
    name = "pair_scanner"

    def _deterministic(self, snapshot: MarketSnapshot, context: dict[str, Any]) -> AgentResult:
        if snapshot.close is None:
            return AgentResult(
                agent=self.name,
                decision="wait",
                confidence=0.2,
                reasons=["missing_local_candle_data"],
            )
        return AgentResult(
            agent=self.name,
            decision="wait",
            side="none",
            confidence=0.55,
            max_leverage=3.0,
            stake_pct=0.05,
            reasons=["pair_has_recent_candle"],
        )


class StrategyValidatorAgent(BaseResearchAgent):
    name = "strategy_validator"

    def _deterministic(self, snapshot: MarketSnapshot, context: dict[str, Any]) -> AgentResult:
        # Until live analyzed dataframe wiring is added, strategy validation is advisory only.
        return AgentResult(
            agent=self.name,
            decision="wait",
            side="none",
            confidence=0.4,
            max_leverage=3.0,
            stake_pct=0.0,
            reasons=["awaiting_freqtrade_signal_bridge"],
            reject_if=["signal_older_than_one_candle"],
        )


class RiskAgent(BaseResearchAgent):
    name = "risk_agent"

    def _deterministic(self, snapshot: MarketSnapshot, context: dict[str, Any]) -> AgentResult:
        open_trades = int(context.get("open_trades", 0))
        max_open_trades = int(context.get("max_open_trades", 3))
        if open_trades >= max_open_trades:
            return AgentResult(
                agent=self.name,
                decision="reject",
                confidence=0.9,
                reasons=["max_open_trades_reached"],
                reject_if=["open_trades_gte_limit"],
            )
        return AgentResult(
            agent=self.name,
            decision="wait",
            confidence=0.6,
            max_leverage=3.0,
            stake_pct=0.05,
            reasons=["risk_capacity_available"],
        )


class SentimentAgent(BaseResearchAgent):
    name = "sentiment_agent"

    def _deterministic(self, snapshot: MarketSnapshot, context: dict[str, Any]) -> AgentResult:
        return AgentResult(
            agent=self.name,
            decision="wait",
            confidence=0.3,
            max_leverage=1.0,
            stake_pct=0.0,
            reasons=["sentiment_disabled_local_only"],
        )

