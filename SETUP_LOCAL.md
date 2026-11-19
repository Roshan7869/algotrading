# Local setup — Windows (verified 2026-11-19)

Machine: 8 vCPU / 16 GB RAM / Intel Iris Xe iGPU — CPU-only policy.

## Installed

- Repo: shallow clone of `https://github.com/Roshan7869/algotrading` → `D:\dev\algotrading` (907 MB)
- Python: `.venv` via `uv venv --python 3.13` (Python 3.13.18)
- Deps: `requirements.txt` + `requirements-hyperopt.txt` + `requirements-plot.txt`
  - freqtrade 2026.5-dev-db07ceb · ccxt 4.5.51 · numpy 2.4.4 · pandas 3.0.2 · ta-lib 0.6.8 · optuna
- Editable install: `uv pip install --no-deps -e .`
- Strategy KB: `chromadb 1.5.9` (ONNX MiniLM embeddings, CPU)

## Verified working

```
.venv\Scripts\freqtrade.exe --version                 # freqtrade 2026.5-dev-db07ceb
freqtrade list-strategies --userdir user_data         # 28 strategies, all OK, all hyperoptable
freqtrade backtesting --strategy EmaTrendFollowing -c user_data/config_backtest.json --timerange 20260401-20260516
cd strategy_db && ..\.venv\Scripts\python.exe ingest.py            # rebuild ChromaDB KB (592 chunks)
.venv\Scripts\python.exe strategy_db\gcode_bridge.py query "liquidity trap with 1:3 R:R"   # JSON results
```

## Data inventory

- Spot 1h: 13 pairs (BTC/USDT 2018-01-01 → 2026-05-16, 73,265 rows, etc.) in `user_data/data/binance/`
- Futures: 205 feather files (1h/1m/4h/5m + funding/mark) in `user_data/data/binance/futures/`

## Do NOT

- Never start the live configs: `config_live_trading_*.json`, `config_live_real.json.DANGEROUS`,
  `start_trading.sh` (10x leverage orchestrator). Dry-run / backtest only until explicitly armed.
- API keys go in `.env` per `.env.example` (house rule: `C:\Users\khatr\.config\<service>\api_key`),
  never in config JSON, never committed.

## Not installed (deliberate)

- FreqAI / freqai-rl extras — heavy ML stack, skipped for this CPU-only machine.
- FlowSurface (Rust/Tauri in `flowsurface_src/`) — no Rust toolchain installed; build later with rustup if wanted.
- `strategy_db/reranker.py` needs sentence-transformers/torch — optional path, not installed.

## Notes

- `Algo @ 2/MoondevRED` = data artifacts only (`_engine` holds `_data_storage`, no runnable code).
- Config sprawl is real: 49+ JSON configs in `user_data/`; `config_backtest.json` = futures, `config_spot.json` = spot.
- Rebuild the KB after changing `strategy/*.txt` or `strategy_db/source_data/*.json`.

## TradingAgents (2026-11-19)

- Vendored clone of TauricResearch/TradingAgents v0.7.1 at `TradingAgents/` (own git repo — update: `git -C TradingAgents pull`)
- Own venv: `TradingAgents/.venv` (py3.13, `uv pip install -e .`)
- Bridge: `scripts/trading_agents_bridge.py` writes `shared_config/tradingagents_signal.json` (replaces placeholder refresh_agents.py)
- Keys: `C:\Users\khatr\.config\tradingagents\env.ps1` — fill ONE provider line
- Verify: `TradingAgents\.venv\Scripts\python.exe scripts\trading_agents_bridge.py --check`
