"""
MiroShark Brain — Weighted Scoring Engine

Reads all Signal Bus channels and produces a composite trading decision:
  - Market regime (HMM)
  - Sentiment (news)
  - Outcome feedback (win rate, R-multiple)
  - TradingAgents signal
  - Circuit breaker
  - Leverage signal

The Brain emits a single composite signal:
  action: STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL | PAUSE
  confidence: 0.0 - 1.0
  regime: from HMM
  direction: long | short | none
  suggested_leverage: 1-10x
  reasoning: list of factors
"""

import json
import sys
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared_config.signal_bus import get_bus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [brain] %(message)s",
)
log = logging.getLogger(__name__)

# ── Signal Weights ───────────────────────────────────
WEIGHTS = {
    "regime": 0.30,
    "sentiment": 0.20,
    "outcome": 0.25,
    "agents": 0.15,
    "circuit_breaker": 0.10,
}

LEVERAGE_FLOOR = 3.0  # minimum leverage when approved
LEVERAGE_CEILING = 10.0  # max leverage (user preference)
MAX_DAILY_LOSS_PCT = 5.0  # circuit breaker threshold

# ── Regime Score Mapping ────────────────────────────
REGIME_SCORES = {
    "trending_up": 0.85,
    "trending_down": 0.70,  # short bias still strong
    "ranging": 0.40,        # reduced activity
    "volatile": 0.25,        # cautious
    "unknown": 0.50,         # neutral
}

# ── Sentiment Score Mapping ─────────────────────────
SENTIMENT_MULTIPLIER = {
    "bullish": 1.2,
    "bearish": 0.8,
    "neutral": 1.0,
}

# ── Agent Rating Mapping ────────────────────────────
AGENT_SCORES = {
    "Strong Buy": 0.95,
    "Buy": 0.80,
    "Neutral": 0.50,
    "Sell": 0.20,
    "Strong Sell": 0.05,
}


@dataclass
class BrainSignal:
    action: str  # STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL, PAUSE
    confidence: float
    regime: str
    direction: str  # long, short, none
    suggested_leverage: float
    scores: dict  # individual component scores
    reasoning: list  # list of factor descriptions
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MiroSharkBrain:
    """Weighted scoring engine that fuses all Signal Bus channels."""

    def __init__(self, bus=None):
        self.bus = bus or get_bus()

    def _read_regime(self) -> dict:
        data = self.bus.read("market_regime.json", max_age=600)  # 10min staleness
        if not data:
            log.warning("Regime signal missing or stale")
            return {"regime": "unknown", "regime_multiplier": 1.0, "regime_stability": 0.0}
        return data

    def _read_sentiment(self) -> dict:
        data = self.bus.read("sentiment_signal.json", max_age=1800)  # 30min staleness
        if not data:
            log.warning("Sentiment signal missing or stale")
            return {"sentiment_score": 0.5, "dominant": "neutral"}
        return data

    def _read_outcomes(self) -> dict:
        data = self.bus.read("outcome_feedback.json", max_age=7200)  # 2hr staleness
        if not data:
            log.warning("Outcome signal missing or stale")
            return {"win_rate": 0.5, "total_trades": 0, "short_win_rate": 0.5, "long_win_rate": 0.5}
        return data

    def _read_agents(self) -> dict:
        data = self.bus.read("tradingagents_signal.json", max_age=900)  # 15min staleness
        if not data:
            log.warning("Agents signal missing or stale")
            return {"rating": "Neutral", "confidence": 0.5}
        return data

    def _read_circuit_breaker(self) -> dict:
        data = self.bus.read("circuit_breaker.json", max_age=3600)
        if not data:
            return {"state": "UNKNOWN", "daily_pnl_pct": 0.0, "weekly_pnl_pct": 0.0}
        return data

    def _read_leverage(self) -> dict:
        data = self.bus.read("leverage_signal.json", max_age=3600)
        if not data:
            return {"leverage": 3.0}
        return data

    def _score_regime(self, regime_data: dict) -> tuple[float, str]:
        regime = regime_data.get("regime", "unknown")
        stability = regime_data.get("regime_stability", 0.5)
        multiplier = regime_data.get("regime_multiplier", 1.0)
        base_score = REGIME_SCORES.get(regime, 0.5)
        # Stability modifier (0.5 stability = no change, 1.0 = +0.1, 0.0 = -0.1)
        stability_adj = (stability - 0.5) * 0.2 if stability else 0.0
        score = base_score + stability_adj
        score *= multiplier  # regime multiplier reduces/enhances
        return round(max(0.0, min(1.0, score)), 4), regime

    def _score_sentiment(self, sentiment_data: dict) -> float:
        raw_score = sentiment_data.get("sentiment_score", 0.5)
        dominant = sentiment_data.get("dominant", "neutral")
        multiplier = SENTIMENT_MULTIPLIER.get(dominant, 1.0)
        score = raw_score * multiplier
        return round(max(0.0, min(1.0, score)), 4)

    def _score_outcomes(self, outcome_data: dict) -> float:
        wr = outcome_data.get("win_rate", 0.5)
        total = outcome_data.get("total_trades", 0)
        short_wr = outcome_data.get("short_win_rate", 0.5)
        avg_r = outcome_data.get("avg_r_multiple", 0.0)

        # Base: win rate (already 0-1)
        score = wr

        # Sample size discount: < 30 trades = less reliable
        if total < 10:
            score = score * 0.5 + 0.25  # pull toward neutral
        elif total < 30:
            score = score * 0.75 + 0.125

        # R-multiple bonus: >0.5 R is strong
        if avg_r > 0.5:
            score = min(1.0, score + 0.05)
        elif avg_r < 0.0:
            score = max(0.0, score - 0.1)

        # Short bias bonus (core edge is SHORT)
        if short_wr > 0.7:
            score = min(1.0, score + 0.03)

        return round(max(0.0, min(1.0, score)), 4)

    def _score_agents(self, agent_data: dict) -> float:
        rating = agent_data.get("rating", "Neutral")
        confidence = agent_data.get("confidence", 0.5)
        base = AGENT_SCORES.get(rating, 0.5)
        # Weight by confidence
        score = base * 0.7 + confidence * 0.3
        return round(max(0.0, min(1.0, score)), 4)

    def _score_circuit_breaker(self, cb_data: dict) -> float:
        state = cb_data.get("state", "UNKNOWN")
        if state == "PAUSED" or state == "HALTED":
            return 0.0  # Hard stop
        daily_pnl = cb_data.get("daily_pnl_pct", 0.0)
        weekly_pnl = cb_data.get("weekly_pnl_pct", 0.0)
        # Daily loss > threshold reduces score
        if daily_pnl < -MAX_DAILY_LOSS_PCT:
            return 0.1
        elif daily_pnl < 0:
            return 0.6 + min(0.3, daily_pnl * 0.1)  # slight loss = cautious
        else:
            return 1.0  # no circuit breaker concern

    def decide(self) -> BrainSignal:
        """Produce composite trading decision from all signals."""
        # Read all signals
        regime_data = self._read_regime()
        sentiment_data = self._read_sentiment()
        outcome_data = self._read_outcomes()
        agent_data = self._read_agents()
        cb_data = self._read_circuit_breaker()
        leverage_data = self._read_leverage()

        # Score each component
        regime_score, regime = self._score_regime(regime_data)
        sentiment_score = self._score_sentiment(sentiment_data)
        outcome_score = self._score_outcomes(outcome_data)
        agent_score = self._score_agents(agent_data)
        cb_score = self._score_circuit_breaker(cb_data)

        # Weighted composite
        composite = (
            regime_score * WEIGHTS["regime"]
            + sentiment_score * WEIGHTS["sentiment"]
            + outcome_score * WEIGHTS["outcome"]
            + agent_score * WEIGHTS["agents"]
            + cb_score * WEIGHTS["circuit_breaker"]
        )

        # Direction from regime
        if regime == "trending_up":
            direction = "long"
        elif regime == "trending_down":
            direction = "short"
        elif regime == "volatile":
            direction = "short"  # SHORT bias (core edge)
        elif regime == "ranging":
            direction = "none"
        else:
            direction = "short"  # default SHORT (core edge is SHORT-only)

        # Action threshold
        if cb_score < 0.1:
            action = "PAUSE"
            confidence = 0.0
        elif composite >= 0.80:
            action = "STRONG_BUY" if direction == "long" else "STRONG_SELL"
            confidence = composite
        elif composite >= 0.65:
            action = "BUY" if direction == "long" else "SELL"
            confidence = composite
        elif composite >= 0.45:
            action = "NEUTRAL"
            confidence = composite
        elif composite >= 0.30:
            action = "SELL" if direction == "long" else "BUY"
            confidence = 1.0 - composite
        else:
            action = "PAUSE"
            confidence = 0.0

        # Leverage: base from signal, modulated by confidence and regime
        base_lev = leverage_data.get("leverage", 3.0)
        regime_mult = regime_data.get("regime_multiplier", 1.0)
        suggested_leverage = round(
            max(LEVERAGE_FLOOR, min(LEVERAGE_CEILING, base_lev * regime_mult * confidence)),
            1,
        )

        # Build reasoning
        reasoning = [
            f"regime={regime} (score={regime_score}, stability={regime_data.get('regime_stability', 0):.2f})",
            f"sentiment={sentiment_data.get('dominant', '?')} (score={sentiment_score})",
            f"outcomes: WR={outcome_data.get('win_rate', 0):.2%} over {outcome_data.get('total_trades', 0)} trades (score={outcome_score})",
            f"agents: {agent_data.get('rating', '?')} (score={agent_score})",
            f"circuit_breaker: {cb_data.get('state', '?')} (score={cb_score})",
            f"composite={composite:.3f} → action={action}, direction={direction}",
        ]

        scores = {
            "regime": regime_score,
            "sentiment": sentiment_score,
            "outcome": outcome_score,
            "agents": agent_score,
            "circuit_breaker": cb_score,
            "composite": round(composite, 4),
        }

        signal = BrainSignal(
            action=action,
            confidence=round(confidence, 4),
            regime=regime,
            direction=direction,
            suggested_leverage=suggested_leverage,
            scores=scores,
            reasoning=reasoning,
        )

        return signal

    def run_once(self) -> BrainSignal:
        """Run a single decision cycle and write to bus."""
        signal = self.decide()

        # Write composite signal to bus
        self.bus.write("miroshark_brain.json", {
            "action": signal.action,
            "confidence": signal.confidence,
            "regime": signal.regime,
            "direction": signal.direction,
            "suggested_leverage": signal.suggested_leverage,
            "scores": signal.scores,
            "reasoning": signal.reasoning,
            "timestamp": signal.timestamp,
        })

        log.info(f"Decision: {signal.action} {signal.direction} "
                 f"(confidence={signal.confidence:.3f}, leverage={signal.suggested_leverage})")
        return signal


def main():
    brain = MiroSharkBrain()
    signal = brain.run_once()
    print(json.dumps({
        "action": signal.action,
        "confidence": signal.confidence,
        "regime": signal.regime,
        "direction": signal.direction,
        "suggested_leverage": signal.suggested_leverage,
        "scores": signal.scores,
        "reasoning": signal.reasoning,
    }, indent=2))


if __name__ == "__main__":
    main()