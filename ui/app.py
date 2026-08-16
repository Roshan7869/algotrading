"""
Algotrading Streamlit UI — Bloomberg-inspired dark theme
"""

import streamlit as st
from ui.data_connector import (
    get_circuit_breaker, get_strategy_perf, get_hedge_state,
    classify_ui_tier, get_tier_label, check_data_manager_status,
)

st.set_page_config(
    page_title="Algotrading Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp { background-color: #0a0a0a; }
    .stSidebar { background-color: #111111; }
    h1, h2, h3 { color: #ffd700 !important; font-family: 'Courier New', monospace; }
    .stMarkdown, .stText { color: #cccccc; font-family: 'Courier New', monospace; }
    .stButton button {
        background-color: #1a1a1a;
        color: #ffd700;
        border: 1px solid #333;
        font-family: 'Courier New', monospace;
    }
    .stButton button:hover { border-color: #ffd700; }
    .css-1d391kg { background-color: #111111; }
    .stDataFrame { font-family: 'Courier New', monospace; }
    .stMetric label { color: #ffd700; }
    .stMetric value { color: #00ff00; }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("## <span style='color:#ffd700'>ALGOTRADING</span>", unsafe_allow_html=True)
st.sidebar.markdown("### <span style='color:#666'>Terminal v1.0</span>", unsafe_allow_html=True)
st.sidebar.markdown("---")

pages = {
    "Dashboard": "📊",
    "Portfolio": "💰",
    "Signals": "📡",
    "Risk Monitor": "⚠️",
    "PnL Analytics": "📈",
    "Market Data": "🔍",
    "Strategies": "⚙️",
    "Backtest": "🧪",
    "Flowsurface Charts": "📊",
    "System Health": "🏥",
    "Settings": "🔧",
}

for page_name, icon in pages.items():
    st.sidebar.markdown(f"{icon} {page_name}")

breaker = get_circuit_breaker()
tier = classify_ui_tier(breaker)
tier_label = get_tier_label(tier)
monthly_pnl = breaker.get("monthly_pnl_pct", 0.0)
pnl_color = "#00ff00" if monthly_pnl >= 0 else "#ff4444"
system_color = "#00ff00" if tier < 2 else ("#ffaa00" if tier == 2 else "#ff4444")

dm_ok, dm_msg = check_data_manager_status()
dm_indicator = "🟢" if dm_ok else "🟡"

st.sidebar.markdown("---")
st.sidebar.markdown(f"<span style='color:{system_color};font-size:0.8em'>System: {tier_label}</span>", unsafe_allow_html=True)
st.sidebar.markdown(f"<span style='color:{pnl_color};font-size:0.8em'>Monthly: {monthly_pnl:+.2f}%</span>", unsafe_allow_html=True)
st.sidebar.markdown(f"<span style='color:#888;font-size:0.8em'>{dm_indicator} DataManager</span>", unsafe_allow_html=True)

st.markdown("# ALGOTRADING TERMINAL")
st.markdown("---")

perf = get_strategy_perf()
hedge = get_hedge_state()
total_pnl = sum(s.get("total_pnl", 0) for s in perf.values())
total_trades = sum(s.get("trades", 0) for s in perf.values())
wins = sum(1 for s in perf.values() if s.get("win_rate", 0) > 0.5)
losses = sum(1 for s in perf.values() if s.get("trades", 0) > 0 and s.get("win_rate", 0) <= 0.5)
win_rate = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0
drawdown = abs(breaker.get("drawdown_pct", 0))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Active Strategies", str(sum(1 for s in perf.values() if s.get("is_active"))))
col2.metric("Total Trades", str(total_trades))
col3.metric("Win Rate", f"{win_rate:.0%}")
col4.metric("Drawdown", f"{drawdown:.2f}%")

st.markdown("## Quick Actions")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.page_link("pages/2_portfolio.py", label="View Portfolio")
with c2:
    st.page_link("pages/3_signals.py", label="Check Signals")
with c3:
    st.page_link("pages/8_backtest.py", label="Run Backtest")
with c4:
    st.page_link("pages/4_risk_monitor.py", label="System Status")

st.markdown("---")
st.markdown("<span style='color:#555'>Algotrading Terminal v1.0 — Powered by Freqtrade + Redis + MCP</span>", unsafe_allow_html=True)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30000, key="datarefresh")
except ImportError:
    pass