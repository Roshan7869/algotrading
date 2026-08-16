"""
Market Data — OHLCV charts, quotes, technical indicators via MCP
"""

import streamlit as st

st.set_page_config(page_title="Market Data", layout="wide")

st.markdown("# MARKET DATA")
st.markdown("---")

col1, col2 = st.columns([1, 3])

with col1:
    symbol = st.text_input("Symbol", "AAPL")
    interval = st.selectbox("Interval", ["1d", "1wk", "1mo", "1h"])
    period = st.selectbox("Period", ["1mo", "3mo", "6mo", "1y"])

with col2:
    st.info("Connect to MCP server for live data. Enter a symbol above.")

    st.subheader("Quick Quote")
    qc1, qc2, qc3 = st.columns(3)
    qc1.metric("AAPL", "—")
    qc2.metric("MSFT", "—")
    qc3.metric("GOOGL", "—")
