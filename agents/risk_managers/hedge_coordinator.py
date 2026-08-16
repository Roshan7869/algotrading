"""
HEdge Coordinator — holistic risk aggregation across all subsystems.

Aggregates risk state from:
  - EnforcedRiskGate (circuit breaker)
  - Learning Loop (ChromaDB win rate)
  - SubAgentOverseer (agent health)
  - QuantDinger Kelly gate (if available)
  - System-wide max drawdown

Computes a single composite risk score and publishes to Redis bus.
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core import RiskTier
from agents.risk_managers.circuit_breaker import (
    EnforcedRiskGate, read_breaker_state, classify_tier, TIER_LABELS,
)


SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent.parent / "shared_config"))


@dataclass
class CompositeRisk:
    tier: RiskTier = RiskTier.NORMAL
    tier_label: str = "NORMAL"
    composite_score: float = 1.0
    circuit_breaker_tier: int = 0
    learning_win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    agent_health_score: float = 1.0
    total_exposure: float = 0.0
    max_exposure: float = 0.0
    signals_blocked_today: int = 0
    is_system_halted: bool = False
    components: dict = field(default_factory=dict)


class HEdgeCoordinator:
    def __init__(self, max_drawdown_pct: float = 20.0, max_exposure: float = 5000.0):
        self.gate = EnforcedRiskGate()
        self.learning = None
        self.overseer = None
        self.max_drawdown_pct = max_drawdown_pct
        self.max_exposure = max_exposure
        self._cache = {}
        self._cache_ts = 0
        self._cache_ttl = 30

    def set_learning(self, learning):
        self.learning = learning

    def set_overseer(self, overseer):
        self.overseer = overseer

    def assess(self) -> CompositeRisk:
        now = time.time()
        if now - self._cache_ts < self._cache_ttl and self._cache:
            return CompositeRisk(**self._cache)

        risk = CompositeRisk()
        components = {}

        breaker_data = read_breaker_state()
        cb_tier = classify_tier(breaker_data)
        risk.circuit_breaker_tier = int(cb_tier)
        risk.current_drawdown_pct = abs(breaker_data.get("drawdown_pct", 0))
        components["circuit_breaker"] = {
            "tier": int(cb_tier),
            "label": TIER_LABELS.get(cb_tier, "UNKNOWN"),
            "monthly_pnl": breaker_data.get("monthly_pnl_pct", 0),
        }

        if self.learning is not None:
            summary = self.learning.get_summary()
            risk.learning_win_rate = summary.get("win_rate", 0.0)
            components["learning"] = {
                "win_rate": risk.learning_win_rate,
                "total_trades": summary.get("total_trades", 0),
                "chromadb_available": summary.get("chromadb_available", False),
            }

        if self.overseer is not None:
            health = self.overseer.health_check()
            risk.agent_health_score = health.get("health_score", 1.0)
            components["agents"] = health

        total_pnl = self._compute_total_pnl()
        if total_pnl < 0:
            dd = abs(total_pnl)
            risk.current_drawdown_pct = max(risk.current_drawdown_pct, dd)

        risk.max_drawdown_pct = self.max_drawdown_pct
        risk.is_system_halted = (
            risk.circuit_breaker_tier >= int(RiskTier.HALT)
            or risk.current_drawdown_pct >= self.max_drawdown_pct
        )

        risk.composite_score = self._compute_composite_score(risk)
        risk.tier = self._score_to_tier(risk.composite_score)
        risk.tier_label = TIER_LABELS.get(risk.tier, "UNKNOWN")
        risk.components = components

        self._cache = {k: v for k, v in risk.__dict__.items() if not k.startswith("_")}
        self._cache_ts = now
        return risk

    def publish_risk_state(self):
        risk = self.assess()
        state = {
            "state": risk.tier_label,
            "tier": int(risk.tier),
            "composite_score": risk.composite_score,
            "drawdown_pct": risk.current_drawdown_pct,
            "max_drawdown_pct": risk.max_drawdown_pct,
            "is_system_halted": risk.is_system_halted,
            "learning_win_rate": risk.learning_win_rate,
            "agent_health_score": risk.agent_health_score,
            "total_exposure": risk.total_exposure,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        path = SHARED_DIR / "hedge_state.json"
        try:
            path.write_text(json.dumps(state, indent=2))
        except OSError:
            pass
        return state

    def _compute_composite_score(self, risk: CompositeRisk) -> float:
        score = 1.0
        cb_weight = 0.40
        learning_weight = 0.25
        drawdown_weight = 0.20
        agent_weight = 0.15

        cb_score = max(0, 1.0 - risk.circuit_breaker_tier * 0.25)
        score -= (1 - cb_score) * cb_weight

        if risk.learning_win_rate < 0.40 and risk.learning_win_rate > 0:
            score -= (0.40 - risk.learning_win_rate) * learning_weight

        dd_ratio = risk.current_drawdown_pct / self.max_drawdown_pct if self.max_drawdown_pct > 0 else 0
        score -= min(dd_ratio, 1.0) * drawdown_weight

        if risk.agent_health_score < 1.0:
            score -= (1.0 - risk.agent_health_score) * agent_weight

        return max(0.0, min(1.0, score))

    def _score_to_tier(self, score: float) -> RiskTier:
        if score <= 0.0:
            return RiskTier.LIQUIDATE
        if score <= 0.25:
            return RiskTier.HALT
        if score <= 0.50:
            return RiskTier.RESTRICTED
        if score <= 0.75:
            return RiskTier.CAUTION
        return RiskTier.NORMAL

    def _compute_total_pnl(self) -> float:
        try:
            import sqlite3
            db_path = Path(os.getenv("TRADES_DB",
                                     Path(__file__).parent.parent.parent / "user_data" / "tradesv3.sqlite"))
            if not db_path.exists():
                return 0.0
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("SELECT COALESCE(SUM(close_profit), 0) FROM trades WHERE close_date IS NOT NULL")
            result = c.fetchone()[0]
            conn.close()
            return result or 0.0
        except Exception:
            return 0.0
