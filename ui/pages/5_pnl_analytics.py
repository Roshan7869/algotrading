"""
PnL Analytics — Performance charts, drawdown curves
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from ui.data_connector import get_pnl, get_strategy_perf, get_outcome_data

st.set_page_config(page_title="PnL Analytics", layout="wide")

st.markdown("# PNL ANALYTICS")
st.markdown("---")

pnl_events = get_pnl()
perf = get_strategy_perf()

total_pnl = sum(s.get("total_pnl", 0) for s in perf.values())
total_trades = sum(s.get("trades", 0) for s in perf.values())
wins = sum(1 for s in perf.values() if s.get("win_rate", 0) > 0.5)
losses = sum(1 for s in perf.values() if s.get("trades", 0) > 0 and s.get("win_rate", 0) <= 0.5)
win_rate = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total PnL", f"${total_pnl:.2f}")
col2.metric("Win Rate", f"{win_rate:.0%}")
col3.metric("Total Trades", str(total_trades))
col4.metric("Strategies", str(len(perf)))

outcome_data = get_outcome_data()
trades = outcome_data.get("trades", []) if outcome_data else []

if trades:
    st.subheader("Outcome History Charts")
    df = pd.DataFrame(trades)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    pnl_df = df.dropna(subset=["pnl_pct"]).copy()
    if not pnl_df.empty:
        pnl_df["cumulative_pnl"] = pnl_df["pnl_pct"].cumsum()

        col_left, col_right = st.columns(2)

        with col_left:
            fig_equity = go.Figure()
            fig_equity.add_trace(go.Scatter(
                x=pnl_df["timestamp"], y=pnl_df["cumulative_pnl"],
                mode="lines", name="Cumulative PnL",
                line=dict(color="#00CC96")
            ))
            fig_equity.update_layout(
                title="Equity Curve (Cumulative PnL %)",
                xaxis_title="Date",
                yaxis_title="Cumulative PnL (%)",
                margin=dict(l=20, r=20, t=40, b=20),
                height=350,
            )
            st.plotly_chart(fig_equity, use_container_width=True)

        with col_right:
            rolling_max = pnl_df["cumulative_pnl"].cummax()
            pnl_df["drawdown"] = pnl_df["cumulative_pnl"] - rolling_max
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=pnl_df["timestamp"], y=pnl_df["drawdown"],
                mode="lines", fill="tozeroy", name="Drawdown",
                line=dict(color="#EF553B")
            ))
            fig_dd.update_layout(
                title="Drawdown",
                xaxis_title="Date",
                yaxis_title="Drawdown (%)",
                margin=dict(l=20, r=20, t=40, b=20),
                height=350,
            )
            st.plotly_chart(fig_dd, use_container_width=True)
    else:
        st.info("No trades with PnL data available for equity/drawdown charts.")

    wr_df = df.dropna(subset=["is_win", "setup_names"]).copy()
    if not wr_df.empty:
        wr_df["strategy"] = wr_df["setup_names"].apply(
            lambda x: x[0] if isinstance(x, list) and len(x) > 0 else "Unknown"
        )
        win_rate_df = (
            wr_df.assign(is_win_int=wr_df["is_win"].astype(int))
            .groupby("strategy")
            .agg(wins=("is_win_int", "sum"), total=("is_win_int", "count"))
            .reset_index()
        )
        win_rate_df = win_rate_df[win_rate_df["total"] > 0]
        if not win_rate_df.empty:
            win_rate_df["win_rate"] = win_rate_df["wins"] / win_rate_df["total"]
            win_rate_df = win_rate_df.sort_values("win_rate", ascending=True)

            fig_wr = px.bar(
                win_rate_df,
                x="win_rate",
                y="strategy",
                orientation="h",
                title="Win Rate by Strategy",
                labels={"win_rate": "Win Rate", "strategy": "Strategy"},
                text=win_rate_df["win_rate"].apply(lambda x: f"{x:.0%}"),
                color="win_rate",
                color_continuous_scale="RdYlGn",
                range_color=[0, 1],
            )
            fig_wr.update_layout(
                margin=dict(l=20, r=20, t=40, b=20),
                height=max(350, len(win_rate_df) * 35),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_wr, use_container_width=True)
        else:
            st.info("No strategy data available for win rate chart.")
    else:
        st.info("No strategy data available for win rate chart.")
else:
    st.info("No outcome history data available for charts.")

st.subheader("Strategy Performance")
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

if pnl_events:
    st.subheader("Recent PnL Events")
    rows = []
    for ev in reversed(pnl_events[-20:]):
        d = ev.get("data", {})
        rows.append({
            "Time": ev.get("timestamp", "")[11:19],
            "Pair": d.get("pair", ""),
            "PnL": f"${d.get('pnl', 0):.2f}",
            "Trade ID": d.get("trade_id", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

st.caption("Detailed PnL charts available when trade history exists.")