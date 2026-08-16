"""
System Health — agent heartbeats, signal bus stats, data freshness
"""

import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from ui.data_connector import (
    get_strategy_perf, get_agent_health, get_circuit_breaker,
    get_regime_data, get_signals, check_data_manager_status, clear_all_caches,
)
from ui.data_layer import read_json, SHARED_DIR

st.set_page_config(page_title="System Health", layout="wide")
st.markdown("# SYSTEM HEALTH")
st.markdown("---")

dm_ok, dm_msg = check_data_manager_status()
dm_color = "#00ff00" if dm_ok else "#ff4444"
st.markdown(f"**DataManager:** <span style='color:{dm_color}'>{dm_msg}</span>", unsafe_allow_html=True)

if st.button("Clear All Caches"):
    clear_all_caches()
    st.toast("Caches cleared!")

PROJECT_ROOT = Path(__file__).parent.parent.parent

col1, col2, col3, col4 = st.columns(4)

UPSTREAM_FILES = {
    "Signal Bus (signals)": "signal_bus_signals.json",
    "Signal Bus (risk)": "signal_bus_risk.json",
    "Signal Bus (PnL)": "signal_bus_pnl.json",
    "Circuit Breaker": "circuit_breaker.json",
    "Market Regime": "market_regime.json",
    "Hedge State": "hedge_state.json",
    "Agent Health": "agent_health.json",
    "Orchestrator Result": "orchestrator_result.json",
    "TradingAgents Signal": "tradingagents_signal.json",
    "Outcome Feedback": "outcome_feedback.json",
}

now_ts = time.time()
fresh_count = 0
stale_count = 0
missing_count = 0
bus_entries = {}

for label, name in UPSTREAM_FILES.items():
    path = SHARED_DIR / name
    if not path.exists():
        missing_count += 1
    else:
        mtime = path.stat().st_mtime
        age = now_ts - mtime
        if age < 600:
            fresh_count += 1
        else:
            stale_count += 1
        if name.startswith("signal_bus_"):
            data = read_json(path)
            bus_entries[label] = len(data) if isinstance(data, list) else 0

col1.metric("Fresh Files", fresh_count)
col2.metric("Stale Files", stale_count)
col3.metric("Missing Files", missing_count)
col4.metric("Config Files", len(UPSTREAM_FILES))

st.markdown("## Data Freshness")

freshness_data = []
for label, name in UPSTREAM_FILES.items():
    path = SHARED_DIR / name
    if not path.exists():
        freshness_data.append({"File": name, "Status": "MISSING", "Age": "N/A", "Size": "N/A"})
    else:
        mtime = path.stat().st_mtime
        age = now_ts - mtime
        size_kb = path.stat().st_size / 1024
        status = "OK" if age < 300 else ("STALE" if age < 3600 else "OLD")
        freshness_data.append({
            "File": name,
            "Status": status,
            "Age": f"{int(age)}s",
            "Size": f"{size_kb:.1f}KB",
        })

st.dataframe(freshness_data, use_container_width=True)

st.markdown("## Signal Bus Activity")

if bus_entries:
    bus_rows = [{"Channel": k, "Events": v} for k, v in sorted(bus_entries.items(), key=lambda x: -x[1])]
    st.dataframe(bus_rows, use_container_width=True)
else:
    st.info("No signal bus files found")

agents = get_agent_health()
st.markdown("## Agent Heartbeats")
if agents:
    agent_dict = agents.get("agents", {})
    if isinstance(agent_dict, dict) and agent_dict:
        agent_rows = []
        for name, info in sorted(agent_dict.items()):
            last_seen = info.get("last_seen", info.get("heartbeat", ""))
            status = info.get("status", "unknown")
            trades = info.get("trades_placed", info.get("trades", 0))
            agent_rows.append({
                "Agent": name,
                "Status": status,
                "Last Seen": str(last_seen)[:19],
                "Trades": trades,
                "Actions": info.get("actions_taken", info.get("actions", 0)),
            })
        st.dataframe(agent_rows, use_container_width=True)
    else:
        st.info("No agent heartbeat data available")
else:
    st.info("Agent health file not found")

st.markdown("## Component Availability")

components = [
    ("ChromaDB", SHARED_DIR.parent / "strategy_db" / "chroma_db"),
    ("Redis Signal Bus", SHARED_DIR / "signal_bus_signals.json"),
    ("Streamlit UI", None),
    ("Circuit Breaker", SHARED_DIR / "circuit_breaker.json"),
    ("NEXUS Bridge", SHARED_DIR.parent / "nexus" / "bridge.py"),
    ("DataManager", None),
]

comp_rows = []
for label, check_path in components:
    if label == "Streamlit UI":
        comp_rows.append({"Component": label, "Status": "RUNNING", "Detail": "Streamlit process"})
    elif label == "DataManager":
        comp_rows.append({"Component": label, "Status": "OK" if dm_ok else "FALLBACK", "Detail": dm_msg})
    elif check_path and check_path.exists():
        comp_rows.append({"Component": label, "Status": "AVAILABLE", "Detail": str(check_path)})
    else:
        comp_rows.append({"Component": label, "Status": "UNAVAILABLE", "Detail": ""})

st.dataframe(comp_rows, use_container_width=True)

st.markdown("## Performance DB")
perf = get_strategy_perf()
if perf:
    total_strats = len(perf)
    active = sum(1 for s in perf.values() if s.get("is_active"))
    total_trades = sum(s.get("trades", 0) for s in perf.values())
    total_pnl = sum(s.get("total_pnl", 0) for s in perf.values())
    mc, mc2, mc3, mc4 = st.columns(4)
    mc.metric("Strategies Tracked", total_strats)
    mc2.metric("Active", active)
    mc3.metric("Total Trades", total_trades)
    mc4.metric("Total PnL", f"${total_pnl:.2f}")
else:
    st.info("Performance DB not yet created")

st.markdown("---")
st.markdown(f"<span style='color:#555'>Last refreshed: {datetime.now().strftime('%H:%M:%S')}</span>", unsafe_allow_html=True)