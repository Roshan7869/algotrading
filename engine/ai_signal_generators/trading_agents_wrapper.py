"""TradingAgents wrapper — LangGraph multi-LLM trading agent swarm."""

import json
import os
from pathlib import Path
from typing import Optional

from core import Signal
from engine.ai_signal_generators.base import SignalGenerator

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent.parent / "shared_config"))


class TradingAgentsGenerator(SignalGenerator):
    name = "tradingagents"
    description = "TradingAgents — LangGraph multi-LLM agent swarm"

    def __init__(self):
        super().__init__()
        self._graph = None

    def _lazy_init(self):
        if self._graph is not None:
            return
        try:
            from TradingAgents.tradingagents.graph.trading_graph import TradingAgentsGraph
            from TradingAgents.tradingagents.default_config import DEFAULT_CONFIG

            self._graph = TradingAgentsGraph(config=DEFAULT_CONFIG)
        except ImportError:
            self._graph = None

    def generate(self, pair: str) -> Signal:
        if self._graph is not None:
            try:
                result = self._graph.run(pair)
                action = result.get("action", "NEUTRAL")
                return Signal(
                    pair=pair,
                    action=self._map_action(action),
                    confidence=result.get("confidence", 0.5),
                    direction=result.get("direction", "neutral"),
                    source=self.name,
                    leverage=result.get("leverage", 1.0),
                    reason=result.get("reasoning", "TradingAgents decision"),
                )
            except Exception as e:
                return self._fallback(pair, str(e))

        return self._fallback(pair)

    def _fallback(self, pair: str, error: str = "") -> Signal:
        signal_path = SHARED_DIR / "tradingagents_signal.json"
        try:
            data = json.loads(signal_path.read_text())
            return Signal(
                pair=pair,
                action=self._map_action(data.get("action", "NEUTRAL")),
                confidence=data.get("confidence", 0.5),
                direction=data.get("direction", "neutral"),
                source=self.name,
                reason=f"From tradingagents_signal.json" + (f" (fallback: {error})" if error else ""),
            )
        except (FileNotFoundError, json.JSONDecodeError):
            return Signal(
                pair=pair,
                action="NEUTRAL",
                confidence=0.0,
                direction="neutral",
                source=self.name,
                reason=f"TradingAgents unavailable: {error}" if error else "TradingAgents unavailable",
            )

    @staticmethod
    def _map_action(action: str) -> str:
        normalized = str(action).strip().lower()
        mapping = {
            "strong_buy": "STRONG_BUY",
            "buy": "BUY",
            "neutral": "NEUTRAL",
            "hold": "NEUTRAL",
            "sell": "SELL",
            "strong_sell": "STRONG_SELL",
            "bullish": "BUY",
            "bearish": "SELL",
        }
        return mapping.get(normalized, "NEUTRAL")
