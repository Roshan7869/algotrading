"""MiroShark Brain wrapper — deterministic weighted scoring engine."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core import Signal
from engine.ai_signal_generators.base import SignalGenerator

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent.parent / "shared_config"))


class MiroSharkGenerator(SignalGenerator):
    name = "miroshark"
    description = "MiroShark Brain — weighted signal fusion from 5 channels"

    def __init__(self):
        super().__init__()
        self._brain = None

    def _lazy_init(self):
        if self._brain is not None:
            return
        try:
            from miroshark import MiroSharkBrain, BrainSignal
            self._brain = MiroSharkBrain
            self._BrainSignal = BrainSignal
        except ImportError:
            self._brain = None

    def generate(self, pair: str) -> Signal:
        self._lazy_init()
        if self._brain is None:
            return self._fallback(pair)

        try:
            brain = self._brain()
            decision = brain.decide()
            return Signal(
                pair=pair,
                action=self._map_action(getattr(decision, "action", "NEUTRAL")),
                confidence=getattr(decision, "confidence", 0.5),
                direction=getattr(decision, "direction", "neutral"),
                source=self.name,
                leverage=getattr(decision, "suggested_leverage", 1.0),
                reason="; ".join(getattr(decision, "reasoning", [])) or "MiroShark decision",
            )
        except Exception as e:
            return self._fallback(pair, str(e))

    def _fallback(self, pair: str, error: str = "") -> Signal:
        brain_path = SHARED_DIR / "miroshark_brain.json"
        try:
            data = json.loads(brain_path.read_text())
            return Signal(
                pair=pair,
                action=self._map_action(data.get("action", "NEUTRAL")),
                confidence=data.get("confidence", 0.5),
                direction=data.get("direction", "neutral"),
                source=self.name,
                leverage=data.get("leverage", 1.0),
                reason=f"From miroshark_brain.json" + (f" (fallback: {error})" if error else ""),
            )
        except (FileNotFoundError, json.JSONDecodeError):
            return Signal(
                pair=pair,
                action="NEUTRAL",
                confidence=0.0,
                direction="neutral",
                source=self.name,
                reason=f"MiroShark unavailable: {error}" if error else "MiroShark unavailable",
            )

    @staticmethod
    def _map_action(action: str) -> str:
        mapping = {
            "STRONG_BUY": "STRONG_BUY",
            "BUY": "BUY",
            "NEUTRAL": "NEUTRAL",
            "SELL": "SELL",
            "STRONG_SELL": "STRONG_SELL",
            "PAUSE": "NEUTRAL",
        }
        return mapping.get(action.upper(), "NEUTRAL")
