"""
Portfolio — Positions, balance, exposure
"""

import streamlit as st
import pandas as pd
from ui.data_connector import get_strategy_perf, get_circuit_breaker, get_pnl, get_positions

st.set_page_config(page_title="Portfolio", layout="wide")

st.markdown("# PORTFOLIO")
st.markdown("---")

perf = get_strategy_perf()
breaker = get_circuit_breaker()
pnl_data = get_pnl()
positions = get_positions()

total_pnl = sum(s.get("total_pnl", 0) for s in perf.values())
total_trades = sum(s.get("trades", 0) for s in perf.values())
monthly_pnl = breaker.get("monthly_pnl_pct", 0.0)

col1, col2, col3 = st.columns(3)
col1.metric("Strategies Tracked", str(len(perf)))
col2.metric("Total Trades", str(total_trades))
col3.metric("Monthly PnL", f"{monthly_pnl:+.2f}%")

st.subheader("Strategy Positions")
if perf:
    rows = []
    for name, data in sorted(perf.items()):
        if data.get("trades", 0) > 0:
            rows.append({
                "Strategy": name,
                "Trades": data.get("trades", 0),
                "Win Rate": f"{data.get('win_rate', 0):.0%}",
                "PnL": f"${data.get('total_pnl', 0):.2f}",
                "Active": "Yes" if data.get("is_active") else "No",
            })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No strategies with trade history yet.")

if positions:
    st.subheader("Open Positions (from DB)")
    pos_rows = []
    for pos in positions:
        pos_rows.append({
            "Pair": pos.get("pair", pos.get("symbol", "")),
            "Side": pos.get("trade_type", pos.get("side", "")),
            "Open Date": str(pos.get("open_date", ""))[:19],
            "Stake": f"${pos.get('stake_amount', 0):.2f}",
            "PnL": f"${pos.get('close_profit_abs', pos.get('profit_abs', 0)):.2f}",
        })
    if pos_rows:
        st.dataframe(pd.DataFrame(pos_rows), use_container_width=True)

st.subheader("Recent PnL")
if pnl_data:
    rows = []
    for ev in reversed(pnl_data[-10:]):
        d = ev.get("data", {})
        rows.append({
            "Time": ev.get("timestamp", "")[11:19],
            "Pair": d.get("pair", ""),
            "PnL": f"${d.get('pnl', 0):.2f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.caption("No trades recorded yet.")