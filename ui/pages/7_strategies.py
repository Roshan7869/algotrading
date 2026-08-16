"""
Strategies — Active strategy registry and management
"""

import streamlit as st
import pandas as pd
from ui.data_connector import get_strategy_perf, get_active_strategy, get_regime_data

st.set_page_config(page_title="Strategies", layout="wide")

st.markdown("# STRATEGIES")
st.markdown("---")

st.subheader("Active Strategy")
active = get_active_strategy()
regime = get_regime_data()

if active:
    strategy_name = active.get("strategy", active.get("name", "—"))
    st.markdown(f"**Current:** {strategy_name}")
    st.markdown(f"**Source:** {active.get('source', '—')}")
    st.markdown(f"**Reason:** {active.get('switch_reason', active.get('reason', '—'))}")
    ts = active.get("_timestamp", "")
    if ts:
        st.markdown(f"**Updated:** {ts[:19]}")
    prev = active.get("previous_strategy", "")
    if prev:
        st.caption(f"Previous: {prev}")
else:
    st.info("No active strategy recorded.")

st.markdown(f"**Market Regime:** {regime.get('regime', 'unknown')} (multiplier: {regime.get('regime_multiplier', 1.0):.2f})")

st.subheader("Strategy Performance")
perf = get_strategy_perf()
if perf:
    rows = []
    for name, data in sorted(perf.items()):
        rows.append({
            "Strategy": name,
            "Trades": data.get("trades", 0),
            "Win Rate": f"{data.get('win_rate', 0):.0%}",
            "Total PnL": f"${data.get('total_pnl', 0):.2f}",
            "Active": "Yes" if data.get("is_active") else "No",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("No strategy performance data available.")

st.subheader("Regime Strategy Defaults")
from engine.regime_selector import REGIME_STRATEGY_DEFAULTS
for regime_name, strategies in REGIME_STRATEGY_DEFAULTS.items():
    with st.expander(f"{regime_name}"):
        for s in strategies:
            st.markdown(f"- **{s['strategy']}**: {s['reason']}")

st.subheader("Strategy Settings")
st.info("Strategy configuration loaded from shared_config.")