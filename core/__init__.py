"""Core data contracts — pure data types shared across all layers.

This module MUST NOT import anything from engine, agents, or knowledge.
Only stdlib imports are allowed.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional


@dataclass
class Signal:
    pair: str
    action: str
    confidence: float
    direction: str
    source: str
    price: Optional[float] = None
    leverage: float = 1.0
    reason: str = ""
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def is_entry(self) -> bool:
        return self.action in ("STRONG_BUY", "BUY")

    @property
    def is_exit(self) -> bool:
        return self.action in ("STRONG_SELL", "SELL")

    @property
    def numeric_action(self) -> int:
        return {"STRONG_SELL": -2, "SELL": -1, "NEUTRAL": 0, "HOLD": 0, "BUY": 1, "STRONG_BUY": 2}.get(self.action, 0)

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "action": self.action,
            "confidence": self.confidence,
            "direction": self.direction,
            "source": self.source,
            "price": self.price,
            "leverage": self.leverage,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class RiskTier(IntEnum):
    NORMAL = 0
    CAUTION = 1
    RESTRICTED = 2
    HALT = 3
    LIQUIDATE = 4


@dataclass
class TradeDecision:
    approved: bool
    reason: str = ""
    size_multiplier: float = 1.0
    tier: int = 0

    @classmethod
    def APPROVED(cls, size_multiplier=1.0):
        return cls(approved=True, reason="approved", size_multiplier=size_multiplier)

    @classmethod
    def BLOCKED(cls, reason):
        return cls(approved=False, reason=reason, size_multiplier=0.0)

    @classmethod
    def REDUCED(cls, size_multiplier, reason):
        return cls(approved=True, reason=reason, size_multiplier=size_multiplier)


@dataclass
class StrategyInfo:
    name: str
    module_path: str
    description: str = ""
    is_active: bool = False
    timeframe: str = "1h"
    can_short: bool = False
    trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    tags: list = field(default_factory=list)


def get_data_manager():
    from core.data_manager import DataManager
    return DataManager()


def get_event_bus():
    from core.event_bus import get_event_bus as _get_bus
    return _get_bus()
