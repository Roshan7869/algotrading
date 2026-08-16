"""
Signals — Live signal feed from Redis bus
"""

import streamlit as st
import pandas as pd
from ui.data_connector import get_signals, get_orchestrator

st.set_page_config(page_title="Signals", layout="wide")

st.markdown("# SIGNALS")
st.markdown("---")

signals = get_signals()
orchestrator = get_orchestrator()

last_signal = signals[-1] if signals else None
last_sig_data = last_signal.get("data", {}) if last_signal else {}

col1, col2, col3 = st.columns(3)
col1.metric("Last Signal", last_sig_data.get("pair", "—"))
col2.metric("Total Signals", str(len(signals)))
col3.metric("Signal Rate", f"{len(signals):d}" if len(signals) > 0 else "0")

st.subheader("Live Signal Feed")
if signals:
    rows = []
    for s in reversed(signals):
        d = s.get("data", {})
        rows.append({
            "Time": s.get("timestamp", "")[11:19],
            "Pair": d.get("pair", ""),
            "Side": d.get("side", ""),
            "Price": f"${d.get('price', 0):.2f}",
            "Strategy": d.get("strategy", ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
else:
    df = pd.DataFrame(columns=["Time", "Pair", "Side", "Price", "Strategy"])
    st.dataframe(df, use_container_width=True)

if orchestrator:
    st.subheader("Latest Consensus")
    consensus = orchestrator.get("consensus", {})
    st.markdown(f"**Direction:** {consensus.get('direction', '—')}")
    st.markdown(f"**Action:** {consensus.get('action', '—')}")
    st.markdown(f"**Confidence:** {consensus.get('confidence', 0):.2f}")
    st.markdown(f"**Blocked:** {orchestrator.get('blocked', False)}")

st.caption("Signals appear here in real-time when system is active.")