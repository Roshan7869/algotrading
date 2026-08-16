"""
Dashboard — Portfolio overview, open trades, system status
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from ui.data_connector import (
    get_regime_data, get_circuit_breaker, get_hedge_state,
    get_agent_health, get_strategy_perf, get_outcome_data,
    classify_ui_tier, get_tier_label,
)

st.set_page_config(page_title="Dashboard", layout="wide")

st.markdown("# DASHBOARD")
st.markdown("---")

breaker = get_circuit_breaker()
regime = get_regime_data()
hedge = get_hedge_state()
agents = get_agent_health()
perf = get_strategy_perf()

tier = classify_ui_tier(breaker)
tier_label = get_tier_label(tier)
monthly_pnl = breaker.get("monthly_pnl_pct", 0.0)
weekly_pnl = breaker.get("weekly_pnl_pct", 0.0)
drawdown = abs(breaker.get("drawdown_pct", 0))
regime_name = regime.get("regime", "unknown")
regime_mult = regime.get("regime_multiplier", 1.0)
composite = hedge.get("composite_score", 1.0)
agent_count = len(agents.get("agents", {}))

col1, col2 = st.columns(2)

outcome_data = get_outcome_data()
trades = outcome_data.get("trades", []) if outcome_data else []

with col1:
    st.subheader("Portfolio Overview")
    total_active = sum(1 for s in perf.values() if s.get("is_active"))
    st.metric("Active Strategies", total_active)
    st.metric("Tracked Strategies", len(perf))
    total_pnl = sum(s.get("total_pnl", 0) for s in perf.values())
    st.metric("Cumulative PnL", f"${total_pnl:.2f}", f"{total_pnl:+.2f}%" if total_pnl else "—")

    if trades:
        df = pd.DataFrame(trades)
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        pnl_df = df.dropna(subset=["pnl_pct"]).copy()
        if not pnl_df.empty:
            pnl_df["cumulative_pnl"] = pnl_df["pnl_pct"].cumsum()
            recent = pnl_df.tail(30)

            fig_spark = go.Figure()
            fig_spark.add_trace(go.Scatter(
                x=recent["timestamp"],
                y=recent["cumulative_pnl"],
                mode="lines",
                line=dict(color="#00CC96", width=2),
                fill="tozeroy",
                fillcolor="rgba(0, 204, 150, 0.15)",
            ))
            fig_spark.update_layout(
                margin=dict(l=10, r=10, t=10, b=10),
                height=180,
                showlegend=False,
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=False, visible=False),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.markdown("**Recent PnL Trend (last 30 trades)**")
            st.plotly_chart(fig_spark, use_container_width=True)
        else:
            st.caption("No recent PnL data available.")
    else:
        st.caption("No recent PnL data available.")

with col2:
    st.subheader("System Status")
    color = "green" if tier < 2 else ("orange" if tier == 2 else "red")
    st.markdown(f"**Circuit Breaker:** <span style='color:{color}'>{tier_label}</span>", unsafe_allow_html=True)
    st.markdown(f"**Monthly PnL:** {monthly_pnl:+.2f}%")
    st.markdown(f"**Weekly PnL:** {weekly_pnl:+.2f}%")
    st.progress(min(drawdown / 50, 1.0) if drawdown > 0 else 0.01, text=f"Drawdown: {drawdown:.2f}%")
    st.markdown(f"**Regime:** {regime_name} (mult: {regime_mult:.2f})")
    st.markdown(f"**Risk Score:** {composite:.2f}")

st.markdown("### Recent Activity")
risk_events = [a for a in agents.get("agents", {}).values() if a.get("last_error")]
if risk_events:
    for data in risk_events[:5]:
        name = data.get("name", "unknown")
        st.warning(f"{name}: {data.get('last_error', '')}")
elif monthly_pnl < -25:
    st.warning(f"Monthly PnL {monthly_pnl:.2f}% exceeds -25% threshold")
else:
    st.info("System operational. No recent anomalies.")