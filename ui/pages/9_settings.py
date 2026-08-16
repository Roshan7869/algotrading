"""
Settings — System configuration, API keys, broker settings
"""

import json
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Settings", layout="wide")

st.markdown("# SETTINGS")
st.markdown("---")

SHARED_DIR = Path(__file__).parent.parent.parent / "shared_config"

# ── Connection ──
st.subheader("Connection")
redis_host = st.text_input("Redis Host", "127.0.0.1")
redis_port = st.number_input("Redis Port", value=6379, step=1)

# ── Trading ──
st.subheader("Trading")
trading_mode = st.selectbox("Mode", ["dry_run", "live"])
max_open_trades = st.number_input("Max Open Trades", value=5, step=1)
stake_amount = st.number_input("Stake Amount", value=60.0, step=1.0)
max_leverage = st.number_input("Max Leverage", value=6, step=1)

# ── Risk ──
st.subheader("Risk")
max_drawdown = st.number_input("Max Drawdown %", value=20, step=1)
circuit_breaker_state = st.selectbox("Circuit Breaker", ["NORMAL", "CAUTION", "RESTRICTED", "HALT", "LIQUIDATE"], index=3)

# ── API Keys ──
st.subheader("API Keys")
st.caption("API keys managed via .env file and shared_config.")

save_clicked = st.button("Save Settings")

if save_clicked:
    errors = []
    
    if not (1 <= max_drawdown <= 100):
        errors.append("Max Drawdown % must be between 1 and 100.")
    
    if errors:
        for err in errors:
            st.error(err)
    else:
        try:
            # Write connection settings
            connection_path = SHARED_DIR / "connection.json"
            connection_data = {"redis_host": redis_host, "redis_port": int(redis_port)}
            if connection_path.exists():
                existing = json.loads(connection_path.read_text())
                existing.update(connection_data)
                connection_data = existing
            connection_path.write_text(json.dumps(connection_data, indent=2))
            
            # Write trading settings
            trading_path = SHARED_DIR / "trading.json"
            trading_data = {
                "mode": trading_mode,
                "max_open_trades": int(max_open_trades),
                "stake_amount": float(stake_amount),
                "max_leverage": int(max_leverage),
            }
            if trading_path.exists():
                existing = json.loads(trading_path.read_text())
                existing.update(trading_data)
                trading_data = existing
            trading_path.write_text(json.dumps(trading_data, indent=2))
            
            # Write risk settings (merge into circuit_breaker.json)
            circuit_path = SHARED_DIR / "circuit_breaker.json"
            circuit_data = {
                "max_drawdown_pct": float(max_drawdown),
                "state": circuit_breaker_state,
            }
            if circuit_path.exists():
                existing = json.loads(circuit_path.read_text())
                existing.update(circuit_data)
                circuit_data = existing
            circuit_path.write_text(json.dumps(circuit_data, indent=2))
            
            st.toast("Settings saved successfully!", icon="✅")
            st.success("Settings saved to shared_config/*.json")
        except Exception as e:
            st.error(f"Failed to save settings: {e}")
