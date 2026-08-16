"""
Backtest — Run and view backtest results
"""

import subprocess
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Backtest", layout="wide")

st.markdown("# BACKTEST")
st.markdown("---")

PROJECT_ROOT = Path(__file__).parent.parent.parent
FREQTRADE_BIN = PROJECT_ROOT / ".venv" / "bin" / "freqtrade"
USER_DATA = PROJECT_ROOT / "user_data"

# Discover config files
config_files = sorted(USER_DATA.glob("config*.json"))
config_names = [f.name for f in config_files]

# Discover strategies
strategy_dir = USER_DATA / "strategies"
strategy_files = sorted([f.stem for f in strategy_dir.glob("*.py") if not f.name.startswith("_")])

col1, col2 = st.columns([1, 2])

with col1:
    selected_config_name = st.selectbox("Config", config_names, index=config_names.index("config_backtest.json") if "config_backtest.json" in config_names else 0)
    selected_config = str(USER_DATA / selected_config_name)
    
    strategy = st.selectbox("Strategy", strategy_files, index=strategy_files.index("AroonMomentumEngine_Hybrid") if "AroonMomentumEngine_Hybrid" in strategy_files else 0)
    timerange = st.text_input("Timerange", "20250101-20250518")
    
    run_clicked = st.button("Run Backtest")

with col2:
    if run_clicked:
        if not FREQTRADE_BIN.exists():
            st.error(f"freqtrade not found at {FREQTRADE_BIN}")
        else:
            cmd = [
                str(FREQTRADE_BIN),
                "backtesting",
                "--config", selected_config,
                "--strategy", strategy,
                "--timerange", timerange,
                "--userdir", str(USER_DATA),
            ]
            
            with st.spinner("Running backtest..."):
                try:
                    result = subprocess.run(
                        cmd,
                        cwd=str(PROJECT_ROOT),
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                except subprocess.TimeoutExpired:
                    st.error("Backtest timed out after 5 minutes.")
                    result = None
                except Exception as e:
                    st.error(f"Failed to run backtest: {e}")
                    result = None
            
            if result is not None:
                if result.returncode != 0:
                    st.error(f"Backtest failed (exit code {result.returncode})")
                    if result.stderr:
                        st.code(result.stderr[-2000:], language="bash")
                
                # Show last lines of stdout (basic metrics or summary)
                output = result.stdout
                if output:
                    st.subheader("Backtest Output")
                    # Try to find summary lines
                    lines = output.splitlines()
                    # Look for profit/summary lines near the end
                    summary_lines = []
                    capture = False
                    for line in reversed(lines):
                        if any(k in line for k in ("Profit", "Summary", "Backtested", "Win rate", "Drawdown", "Avg profit")):
                            summary_lines.append(line)
                            capture = True
                        elif capture and line.strip() == "":
                            break
                    
                    if summary_lines:
                        summary_lines.reverse()
                        st.code("\n".join(summary_lines[-30:]), language="text")
                    else:
                        # Fallback: show last 40 lines
                        st.code("\n".join(lines[-40:]), language="text")
                else:
                    st.info("No stdout produced.")
                
                st.caption(f"Command: `{' '.join(cmd)}`")
    else:
        st.info("Backtest results appear here. Run a backtest to see results.")
        st.subheader("Last Backtest")
        st.caption("No backtest results cached.")
