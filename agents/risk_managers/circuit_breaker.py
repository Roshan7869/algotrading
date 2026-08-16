"""
EnforcedCircuitBreaker — PHYSICALLY BLOCKS trades when risk limits are breached.

This is NOT advisory middleware. It sits between signal generation and execution.
All orders MUST pass through this gate. It cannot be bypassed.

Tiers:
  0: NORMAL      — Full trading
  1: CAUTION     — 75% position size
  2: RESTRICTED  — 50% position size, no shorts
  3: HALT        — No new entries (current PAUSE state)
  4: LIQUIDATE   — Close all positions immediately
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core import RiskTier, TradeDecision


TIER_LABELS = {
    RiskTier.NORMAL: "NORMAL",
    RiskTier.CAUTION: "CAUTION",
    RiskTier.RESTRICTED: "RESTRICTED",
    RiskTier.HALT: "HALT",
    RiskTier.LIQUIDATE: "LIQUIDATE",
}


SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent.parent / "shared_config"))
BREAKER_PATH = SHARED_DIR / "circuit_breaker.json"
REGIME_PATH = SHARED_DIR / "market_regime.json"

DEFAULT_THRESHOLDS = {
    "liquidate_drawdown": 50,
    "liquidate_consecutive_sl": 3,
    "halt_monthly_pnl": -25,
    "halt_drawdown": 35,
    "restricted_drawdown": 20,
    "caution_drawdown": 10,
}


def read_breaker_state() -> dict:
    """Read circuit breaker state from JSON file (current backend).
    Defaults to HALT on corrupted/missing file (fail-safe)."""
    try:
        if BREAKER_PATH.exists():
            data = json.loads(BREAKER_PATH.read_text())
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"state": "HALT", "tier": 3}


def read_regime_state() -> dict:
    """Read current market regime from JSON file."""
    try:
        if REGIME_PATH.exists():
            return json.loads(REGIME_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"regime": "unknown", "regime_multiplier": 1.0, "regime_stability": 0.0}


def classify_tier(breaker_data: dict, thresholds: Optional[dict] = None) -> RiskTier:
    """Classify breaker state into a RiskTier using configurable thresholds."""
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    state = breaker_data.get("state", "UNKNOWN")
    drawdown = abs(breaker_data.get("drawdown_pct", 0))
    monthly_pnl = breaker_data.get("monthly_pnl_pct", 0)
    consecutive_sl = breaker_data.get("consecutive_sl", 0)

    if state == "LIQUIDATE" or drawdown > t["liquidate_drawdown"] or consecutive_sl >= t["liquidate_consecutive_sl"]:
        return RiskTier.LIQUIDATE
    if state == "HALT" or state == "PAUSED" or monthly_pnl < t["halt_monthly_pnl"] or drawdown > t["halt_drawdown"]:
        return RiskTier.HALT
    if state == "RESTRICTED" or drawdown > t["restricted_drawdown"]:
        return RiskTier.RESTRICTED
    if state == "CAUTION" or drawdown > t["caution_drawdown"]:
        return RiskTier.CAUTION
    return RiskTier.NORMAL


class EnforcedRiskGate:
    """Middleware that ALL trades MUST pass through. Physically blocks when conditions met."""

    def __init__(self, system_drawdown_limit: float = -0.20,
                 thresholds: Optional[dict] = None):
        self.system_drawdown_limit = system_drawdown_limit
        self._thresholds = thresholds or {}
        self._cache = {}
        self._cache_ts = 0
        self._cache_ttl = 60

    def gate(self, pair: str, side: str, amount: float, strategy: str = "") -> TradeDecision:
        now = time.time()
        if now - self._cache_ts > self._cache_ttl:
            self._refresh_cache()

        breaker = self._cache.get("breaker", {})
        regime = self._cache.get("regime", {})
        tier = classify_tier(breaker, thresholds=self._thresholds)
        label = TIER_LABELS.get(tier, "UNKNOWN")
        regime_mult = float(regime.get("regime_multiplier", 1.0))

        if tier >= RiskTier.LIQUIDATE:
            return TradeDecision.BLOCKED(
                f"LIQUIDATE: Circuit breaker in LIQUIDATE state. "
                f"Drawdown: {breaker.get('drawdown_pct', 0)}%"
            )

        if tier >= RiskTier.HALT:
            return TradeDecision.BLOCKED(
                f"HALT: Circuit breaker is {label}. "
                f"Monthly PnL: {breaker.get('monthly_pnl_pct', 0)}%. "
                f"Reason: {breaker.get('transition_reason', 'No new entries allowed')}"
            )

        if tier >= RiskTier.RESTRICTED:
            if side.lower() in ("short", "sell"):
                return TradeDecision.BLOCKED("RESTRICTED: Shorts disabled in RESTRICTED tier")
            base_mult = 0.5
            return TradeDecision.REDUCED(
                base_mult * regime_mult,
                f"RESTRICTED: {base_mult*100:.0f}% position (regime adj: {regime_mult:.2f}). "
                f"Drawdown: {breaker.get('drawdown_pct', 0)}%"
            )

        if tier >= RiskTier.CAUTION:
            base_mult = 0.75
            return TradeDecision.REDUCED(
                base_mult * regime_mult,
                f"CAUTION: {base_mult*100:.0f}% position (regime adj: {regime_mult:.2f}). "
                f"Drawdown: {breaker.get('drawdown_pct', 0)}%"
            )

        return TradeDecision.APPROVED(size_multiplier=regime_mult)

    def _refresh_cache(self):
        self._cache = {
            "breaker": read_breaker_state(),
            "regime": read_regime_state(),
        }
        self._cache_ts = time.time()


def enforce_breakers_on_strategy(dataframe, metadata, strategy_name=""):
    """Call this from populate_entry_trend to enforce circuit breaker per-pair."""
    import pandas as pd

    gate = EnforcedRiskGate()
    pair = metadata.get("pair", "unknown")
    decision = gate.gate(pair, "long", 1.0, strategy_name)

    if not decision.approved:
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0
        if "enter_tag" in dataframe.columns:
            dataframe.loc[:, "enter_tag"] = f"BLOCKED:{decision.reason[:50]}"

    return dataframe, decision
