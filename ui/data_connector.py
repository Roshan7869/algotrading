"""
Data Connector — single bridge between Streamlit pages and real data sources.

Replaces scattered data_layer imports with centralized DataManager access.
Uses st.cache_data(ttl=30) for auto-refresh every 30 seconds.

Priority: DataManager (cached, event-driven) > data_layer (JSON file reads) > safe defaults.
"""

import logging
import streamlit as st

from core import get_data_manager, get_event_bus
from core.event_bus import EventTypes

from ui.data_layer import (
    get_strategy_performance,
    get_outcome_history,
    get_orchestrator_result,
    classify_ui_tier,
    get_tier_label,
)

logger = logging.getLogger(__name__)

_dm = None


def _get_dm():
    global _dm
    if _dm is None:
        try:
            _dm = get_data_manager()
        except Exception as e:
            logger.warning("DataManager init failed: %s", e)
    return _dm


@st.cache_data(ttl=30, show_spinner=False)
def get_regime_data() -> dict:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_regime()
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_regime failed: %s", e)
    from ui.data_layer import get_market_regime
    return get_market_regime()


@st.cache_data(ttl=30, show_spinner=False)
def get_circuit_breaker() -> dict:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_circuit_breaker()
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_circuit_breaker failed: %s", e)
    from ui.data_layer import get_circuit_breaker as _dl_breaker
    return _dl_breaker()


@st.cache_data(ttl=30, show_spinner=False)
def get_active_strategy() -> dict:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_active_strategy()
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_active_strategy failed: %s", e)
    return {}


@st.cache_data(ttl=30, show_spinner=False)
def get_hedge_state() -> dict:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_hedge_state()
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_hedge_state failed: %s", e)
    from ui.data_layer import get_hedge_state as _dl_hedge
    return _dl_hedge()


@st.cache_data(ttl=30, show_spinner=False)
def get_positions() -> list:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_positions()
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_positions failed: %s", e)
    return []


@st.cache_data(ttl=30, show_spinner=False)
def get_pnl() -> list:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_pnl()
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_pnl failed: %s", e)
    from ui.data_layer import get_pnl_events
    return get_pnl_events()


@st.cache_data(ttl=30, show_spinner=False)
def get_signals(limit: int = 50) -> list:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_signals(limit=limit)
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_signals failed: %s", e)
    from ui.data_layer import get_signals as _dl_signals
    return _dl_signals(limit)


@st.cache_data(ttl=30, show_spinner=False)
def get_agent_health() -> dict:
    dm = _get_dm()
    if dm is not None:
        try:
            data = dm.get_agent_health()
            if data is not None:
                return data
        except Exception as e:
            logger.debug("DataManager get_agent_health failed: %s", e)
    from ui.data_layer import get_agent_health
    return get_agent_health()


@st.cache_data(ttl=60, show_spinner=False)
def get_strategy_perf() -> dict:
    return get_strategy_performance()


@st.cache_data(ttl=60, show_spinner=False)
def get_outcome_data() -> dict:
    data = get_outcome_history()
    return data if data else {}


@st.cache_data(ttl=60, show_spinner=False)
def get_orchestrator() -> dict:
    data = get_orchestrator_result()
    return data if data else {}


@st.cache_data(ttl=30, show_spinner=False)
def get_risk_events(limit: int = 50) -> list:
    from ui.data_layer import get_risk_events
    return get_risk_events(limit)


@st.cache_data(ttl=30, show_spinner=False)
def get_risk_tier() -> str:
    dm = _get_dm()
    if dm is not None:
        try:
            tier = dm.get_risk_tier()
            if tier is not None:
                return tier
        except Exception as e:
            logger.debug("DataManager get_risk_tier failed: %s", e)
    breaker = get_circuit_breaker()
    tier_int = classify_ui_tier(breaker)
    return get_tier_label(tier_int)


def subscribe_to_events(event_type: EventTypes, callback):
    bus = get_event_bus()
    bus.subscribe(event_type, callback)


def check_data_manager_status() -> tuple:
    dm = _get_dm()
    if dm is not None:
        return (True, "DataManager connected")
    return (False, "DataManager unavailable — using file fallback")


def clear_all_caches():
    st.cache_data.clear()