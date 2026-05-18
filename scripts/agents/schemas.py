from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Decision = Literal["approve", "reject", "wait"]
Side = Literal["long", "short", "none"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MarketSnapshot:
    timestamp: str
    pair: str
    timeframe: str
    close: float | None = None
    volume: float | None = None
    atr: float | None = None
    adx: float | None = None
    rsi: float | None = None
    btc_regime: str = "unknown"
    spread_bps: float | None = None
    funding_rate: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResult:
    agent: str
    decision: Decision
    side: Side = "none"
    confidence: float = 0.0
    max_leverage: float = 1.0
    stake_pct: float = 0.0
    reasons: list[str] = field(default_factory=list)
    reject_if: list[str] = field(default_factory=list)
    model: str = "deterministic"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeDecision:
    pair: str
    side: Side
    decision: Decision
    confidence: float
    max_leverage: float
    stake_pct: float
    reasons: list[str] = field(default_factory=list)
    reject_if: list[str] = field(default_factory=list)
    agent_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))

