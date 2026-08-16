"""
Risk Monitor — Circuit breaker, drawdown limits, risk metrics
"""

import streamlit as st
from ui.data_connector import (
    get_circuit_breaker, get_regime_data, get_hedge_state,
    get_risk_events, classify_ui_tier, get_tier_label, get_active_strategy,
)

st.set_page_config(page_title="Risk Monitor", layout="wide")

st.markdown("# RISK MONITOR")
st.markdown("---")

breaker = get_circuit_breaker()
regime = get_regime_data()
hedge = get_hedge_state()
risk_events = get_risk_events()
active_strategy = get_active_strategy()

tier = classify_ui_tier(breaker)
tier_label = get_tier_label(tier)
state = breaker.get("state", "UNKNOWN")
monthly_pnl = breaker.get("monthly_pnl_pct", 0.0)
drawdown = abs(breaker.get("drawdown_pct", 0))
max_dd = breaker.get("max_drawdown_pct", 20.0)
reason = breaker.get("transition_reason", "")
composite = hedge.get("composite_score", 1.0)
breached = hedge.get("drawdown_breached", False)
regime_name = regime.get("regime", "unknown")
regime_mult = regime.get("regime_multiplier", 1.0)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Circuit Breaker")
    if tier >= 3:
        st.error(f"STATE: {state}")
    elif tier >= 2:
        st.warning(f"STATE: {state}")
    else:
        st.success(f"STATE: {state}")
    st.markdown(f"**Tier:** {tier_label} ({tier})")
    st.markdown(f"**Monthly PnL:** {monthly_pnl:+.2f}%")
    if reason:
        st.markdown(f"**Trigger:** {reason}")

with col2:
    st.subheader("Risk Limits")
    st.metric("Max Drawdown", f"{max_dd:.0f}%")
    st.metric("Current Drawdown", f"{drawdown:.2f}%")
    st.metric("Composite Risk Score", f"{composite:.2f}")
    st.metric("Drawdown Breached", "YES" if breached else "NO")

st.subheader("Market Regime")
col_a, col_b, col_c = st.columns(3)
col_a.metric("Regime", regime_name)
col_b.metric("Multiplier", f"{regime_mult:.2f}")
col_c.metric("Stability", f"{regime.get('regime_stability', 0):.2f}")

st.subheader("Risk Tiers")
tiers = {
    "NORMAL": "Full trading allowed",
    "CAUTION": "75% position size",
    "RESTRICTED": "50% size, no shorts",
    "HALT": "No new entries (current)",
    "LIQUIDATE": "Close all positions",
}
for t_name, desc in tiers.items():
    active = t_name == tier_label
    st.markdown(f"{'➤' if active else ' '} **{t_name}:** {desc}")

st.subheader("Active Strategy")
if active_strategy:
    st.markdown(f"**Strategy:** {active_strategy.get('strategy', active_strategy.get('name', '—'))}")
    st.markdown(f"**Source:** {active_strategy.get('source', '—')}")
    ts = active_strategy.get('_timestamp', '')
    if ts:
        st.markdown(f"**Last Updated:** {ts[:19]}")
else:
    st.info("No active strategy recorded.")

if risk_events:
    st.subheader("Recent Risk Events")
    for ev in reversed(risk_events[-5:]):
        d = ev.get("data", {})
        st.warning(f"{ev.get('timestamp', '')[:19]}: {d.get('event', '')} — {d.get('message', '')}")