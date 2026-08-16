"""UI Data Layer — reads live data from engine files for the Streamlit dashboard."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import streamlit as st

SHARED_DIR = Path(__file__).parent.parent / "shared_config"
STRATEGY_DIR = Path(__file__).parent.parent / "user_data"


@st.cache_data(ttl=60)
def read_json(path: Path) -> Optional[dict]:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return None


@st.cache_data(ttl=60)
def get_circuit_breaker() -> dict:
    data = read_json(SHARED_DIR / "circuit_breaker.json")
    if data is None:
        return {"state": "NORMAL", "tier": 0, "drawdown_pct": 0.0, "monthly_pnl_pct": 0.0}
    return data


@st.cache_data(ttl=60)
def get_market_regime() -> dict:
    data = read_json(SHARED_DIR / "market_regime.json")
    if data is None:
        return {"regime": "unknown", "regime_multiplier": 1.0}
    return data


@st.cache_data(ttl=60)
def get_hedge_state() -> dict:
    data = read_json(SHARED_DIR / "hedge_state.json")
    if data is None:
        return {"composite_score": 1.0, "tier": "NORMAL", "drawdown_breached": False}
    return data


@st.cache_data(ttl=60)
def get_agent_health() -> dict:
    data = read_json(SHARED_DIR / "agent_health.json")
    if data is None:
        return {"agents": {}}
    return data


@st.cache_data(ttl=60)
def get_signals(limit: int = 50) -> list:
    data = read_json(SHARED_DIR / "signal_bus_signals.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data[-limit:]
    return []


@st.cache_data(ttl=60)
def get_risk_events(limit: int = 50) -> list:
    data = read_json(SHARED_DIR / "signal_bus_risk.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data[-limit:]
    return []


@st.cache_data(ttl=60)
def get_pnl_events(limit: int = 50) -> list:
    data = read_json(SHARED_DIR / "signal_bus_pnl.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data[-limit:]
    return []


@st.cache_data(ttl=60)
def get_orchestrator_result() -> Optional[dict]:
    return read_json(SHARED_DIR / "orchestrator_result.json")


@st.cache_data(ttl=60)
def get_strategy_performance() -> dict:
    data = read_json(STRATEGY_DIR / "strategy_performance_db.json")
    if data is None:
        return {}
    return data


@st.cache_data(ttl=60)
def get_outcome_history() -> Optional[dict]:
    path = Path(__file__).parent.parent / "strategy_db" / "outcome_history.json"
    return read_json(path)


def get_tier_label(tier: int) -> str:
    labels = {0: "NORMAL", 1: "CAUTION", 2: "RESTRICTED", 3: "HALT", 4: "LIQUIDATE"}
    return labels.get(tier, "UNKNOWN")


def classify_ui_tier(breaker: dict) -> int:
    drawdown = abs(breaker.get("drawdown_pct", 0))
    monthly = breaker.get("monthly_pnl_pct", 0)
    state = breaker.get("state", "UNKNOWN")
    if state == "LIQUIDATE" or drawdown > 50:
        return 4
    if state in ("HALT", "PAUSED") or monthly < -25 or drawdown > 35:
        return 3
    if state == "RESTRICTED" or drawdown > 20:
        return 2
    if state == "CAUTION" or drawdown > 10:
        return 1
    return 0
