# My Trading Rules & Project Knowledge

## Core Trading Principles
- Always use stop losses — never risk more than 1-2% per trade
- Favor 1:3 risk-reward or better
- Only trade during high-liquidity sessions (London open, NY open, Asian overlap)
- Avoid trading during major news events unless the strategy specifically exploits them
- No revenge trading — after 2 consecutive losses, stop for the day

## Strategy Preferences
- Liquidity-based setups (stop hunts, sweep of equal lows/highs) are preferred
- FVG and Order Block confluence increases confidence
- CVD divergence is the primary exit signal
- Always check higher timeframe (4H/1D) bias before taking a 15m or 1h setup

## Project Architecture
- **Algotrading** runs on freqtrade with Python 3.10+
- ChromaDB stores 592 YouTube strategy chunks (collection: `trading_strategies`)
- NEXUS at `/home/roshan/nexus/` handles tool routing via FAISS + SQLite
- The learning loop connects trade outcomes to strategy metadata
- MCP server at `strategy_db/mcp_server.py` exposes 9 tools via stdio
- UI is a Streamlit app at `ui/` with Bloomberg-style dark theme

## Key Commands
- Query strategies: `python3 strategy_db/gcode_bridge.py query "your query"`
- Ingest strategies: `python3 strategy_db/ingest.py`
- Sync outcomes: `python3 strategy_db/outcome_sync.py`
- Check NEXUS health: `python3 -c "from nexus import bridge; ..."`
- Run all tests: `pytest` (146 pass, 3 known skips)

## Rules for AI Agents
- Prefer Python stdlib solutions; avoid adding new dependencies
- Use `sys.path.insert(0, ...)` pattern for intra-project imports
- Silent `except: pass` is forbidden — always log or re-raise
- All MCP tools must have full JSON Schema input validation
- Verify changes with tests before reporting completion
