# Algotrading Project — Full Architectural Audit

**Project Root:** `/home/roshan/Downloads/Algotrading/`
**Date:** 2026-05-22
**Auditor:** Hermes Agent
**Purpose:** Map full architecture, identify integration points for new Fincept components

---

## 1. EXECUTIVE SUMMARY

This is a **multi-agent algorithmic trading platform** built on a forked Freqtrade engine, extended with:
- 5+ AI signal generators (MiroShark, TradingAgents, MacroAnalyst, Kronos, sentiment)
- A ChromaDB-powered strategy knowledge base with HMM regime detection
- A dual-bus signal system (Redis pub/sub + atomic JSON files)
- 65+ trading strategies including 9 ChromaDB-derived hedge strategies
- A Rust-based charting layer (Flowsurface)
- Swarm orchestration for multi-agent consensus
- Streamlit-based monitoring UI
- NEXUS MCP bridge for external AI tool access

The architecture is **event-driven** with two signal planes:
1. **Real-time**: Redis pub/sub (`engine/signal_bus.py` → `RedisSignalBus`)
2. **Config/state**: Atomic JSON files (`shared_config/signal_bus.py` → `AtomicFileBus`)

All signal producers write through both buses. All strategies read through either.

---

## 2. TOPOLOGY DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ENTRY POINTS                                     │
│  start_local.sh ─→ (freqtrade, nexus-http, nexus-mcp, strategy-kb,  │
│                     finance-mcp, streamlit)                           │
│  docker-compose.yml ─→ (freqtrade, redis, postgres, mirofish,       │
│                          tradingagents, streamlit, jupyter)          │
└────────────────┬────────────────────────────────────────────────────┘
                 │
    ┌────────────▼────────────────────────────────────────────────┐
    │              SHARED CONFIG / SIGNAL BUS                      │
    │  shared_config/ (18 JSON files + AtomicFileBus)              │
    │  Redis (4 channels: signals, risk, pnl, commands)           │
    └──────┬──────────┬──────────┬──────────┬──────────────────────┘
           │          │          │          │
    ┌──────▼──┐ ┌─────▼────┐ ┌──▼──────┐ ┌─▼──────────┐
    │SIGNAL   │ │ RISK     │ │PNL      │ │ COMMANDS   │
    │PRODUCERS│ │ GATES    │ │TRACKING │ │(orchestr.) │
    └─────────┘ └──────────┘ └─────────┘ └────────────┘
         ▲           ▲            ▲
    ┌────┴─────┐ ┌───┴──────┐ ┌──┴──────────┐
    │MiroShark │ │Circuit   │ │Learning    │
    │Brain     │ │Breaker   │ │Loop        │
    │          │ │(5-tier)  │ │(40%WR gate)│
    ├──────────┤ ├──────────┤ ├────────────┤
    │TradingAg.│ │HEdgeCoor.│ │Outcome     │
    │Graph     │ │(composite│ │Feedback    │
    ├──────────┤ │ risk)    │ │            │
    │MacroAnal.│ ├──────────┤ ├────────────┤
    │          │ │SubAgent  │ │StrategyDB  │
    ├──────────┤ │Overseer  │ │(ChromaDB)  │
    │Kronos    │ │          │ │            │
    ├──────────┤ └──────────┘ └────────────┘
    │Sentiment │        ▲
    │Pipeline  │        │
    └──────────┘   ┌────┴─────────────────────┐
                   │ FREQTRADE ENGINE (core)   │
                   │ - IStrategy interface      │
                   │ - Exchange layer (30+)     │
                   │ - SQLite persistence       │
                   │ - RPC/API server           │
                   │ 65+ strategies read bus     │
                   └───────────────────────────┘
                        │              │
                  ┌─────▼─────┐  ┌────▼──────────┐
                  │EXCHANGES  │  │FLOWSURFACE    │
                  │(ccxt)     │  │(Rust charts)  │
                  │30+ backends│ │via NDJSON     │
                  └───────────┘  └───────────────┘
                        │
                  ┌─────▼─────┐  ┌──────────────┐
                  │STREAMLIT  │  │NEXUS MCP     │
                  │UI (8501)  │  │Bridge (8080)  │
                  └───────────┘  └───────────────┘
```

---

## 3. ENTRY POINTS

| Entry Point | Type | Port/Path | Starts |
|-------------|------|-----------|--------|
| `start_local.sh start` | Shell script | — | 6 services (nexus-http:8080, nexus-mcp, strategy-kb, finance-mcp, streamlit:8501) |
| `docker-compose.yml --profile core` | Docker Compose | freqtrade:8080, redis:6379 | freqtrade, redis |
| `docker-compose.yml --profile full` | Docker Compose | + mirofish:3000/5001, tradingagents | All above + AI agents |
| `docker-compose.yml --profile dev` | Docker Compose | + streamlit:8501, jupyter:8888, postgres:5432 | Full + dev tools |
| `freqtrade main.py` | Python CLI | — | `freqtrade trade [--strategy X] [--config Y]` |
| `TradingAgents/main.py` | Python CLI | — | Single-shot TradingAgents graph propagation |
| `strategy_db/mcp_server.py` | MCP stdio | stdio | ChromaDB strategy KB as MCP tools |
| `mcp_layer/finance_mcp_server.py` | MCP stdio | stdio | Financial data tools (yfinance) |
| `nexus/server/nexus_http_daemon.py` | Python HTTP | :8080 | NEXUS HTTP API |
| `nexus/server/nexus-mcp-enhanced.py` | MCP stdio | stdio | NEXUS MCP tools |

**Data flow at startup:**
1. Redis starts (message bus backbone)
2. Postgres starts (optional, for persistence beyond SQLite)
3. Freqtrade engine starts with strategy + config → connects to exchange via ccxt
4. AI signal generators start → write signals to shared_config JSON + Redis
5. MiroShark brain evaluates composite signal → writes `miroshark_brain.json`
6. Streamlit UI connects to Redis + shared_config for display

---

## 4. CONFIG SYSTEM

### 4.1 Layer 1: Freqtrade Native Config
- **Format:** JSON files in `user_data/`
- **Key file:** `user_data/config_market_ready.json` (referenced by docker-compose)
- **Fields:** exchange creds, pairs, timeframe, risk params, db-url
- **Consumed by:** Freqtrade engine at startup via `--config` flag

### 4.2 Layer 2: Shared Config (AtomicFileBus)
- **Location:** `shared_config/` (18 JSON files)
- **Interface:** `shared_config.signal_bus.AtomicFileBus`
- **Key methods:**
  ```python
  bus = AtomicFileBus()
  bus.write(filename: str, data: dict) -> bool     # Atomic write (temp → rename)
  bus.read(filename: str, max_age: int = None) -> Optional[dict]  # With staleness check
  bus.read_rating(filename) -> Optional[str]       # Convenience: read 'rating' field
  bus.read_score(filename) -> float                # Convenience: read sentiment_score/score
  bus.is_stale(filename, max_age=300) -> bool      # Check staleness without loading
  bus.list_signals() -> list[str]                  # List all JSON signal files
  ```
- **Thread safety:** Yes (process-level lock via `threading.Lock`)
- **Write metadata:** Every write adds `_timestamp` and `_written_by` (PID)

### 4.3 Shared Config File Inventory

| File | Writer | Schema | Purpose |
|------|--------|--------|---------|
| `circuit_breaker.json` | Risk gates, optimization_plan | `{state, drawdown_pct, max_drawdown_pct, max_trades_per_day, transition_reason}` | 5-tier risk state |
| `market_regime.json` | Signal bus (HMM detector) | `{pair, regime, regime_probs, regime_multiplier, all_regimes}` | Current HMM regime |
| `sentiment_signal.json` | Sentiment pipeline | `{sentiment_score, raw_score, article_count, dominant}` | News sentiment |
| `tradingagents_signal.json` | TradingAgents bridge | `{ticker, rating, risk_assessment.approval, final_trade_decision}` | LLM agent rating |
| `leverage_signal.json` | Dynamic leverage module | `{leverage}` | Dynamic leverage |
| `miroshark_brain.json` | MiroShark | `{action, confidence, regime, direction, suggested_leverage, scores{regime,sentiment,outcome,agents,circuit_breaker,composite}, reasoning[]}` | Composite AI brain decision |
| `orchestrator_signal.json` | SignalOrchestrator | `{pair, action, confidence, direction, source, price, leverage, reason, metadata}` | Consensus signal from generators |
| `outcome_feedback.json` | Outcome sync | `{win_rate, total_trades, wins, avg_r_multiple, long/short_rate, regime_stats}` | Historical performance |
| `agent_health.json` | SubAgentOverseer | `{health_score, total_agents, healthy_agents, stale_agents, agents{...}}` | Agent monitoring |
| `hedge_state.json` | HEdgeCoordinator | Composite risk state | Aggregated risk |
| `alerter_config.json` | Alerter config | `{slack_webhook_url, generic_webhook_url, min_pnl_alert, alert_on_*}` | Alert settings |
| `signal_bus_signals.json` | RedisSignalBus backup | Array of signal messages | JSON backup of Redis signals |
| `signal_bus_risk.json` | RedisSignalBus backup | Array of risk messages | JSON backup of Redis risk events |
| `signal_bus_pnl.json` | RedisSignalBus backup | Array of PnL messages | JSON backup of Redis PnL |
| `signal_bus_commands.json` | RedisSignalBus backup | Array of command messages | JSON backup of Redis commands |

### 4.4 Environment Variables
- `SHARED_CONFIG_DIR` — Override shared_config path (default: `./shared_config`)
- `PYTHONPATH` — Set to project root by `start_local.sh`
- Docker `.env` — Exchange API keys, DB credentials, LLM endpoints

### **INTEGRATION POINT:** New Fincept components can:
1. Read any `shared_config/*.json` via `AtomicFileBus.read()` (no deps beyond Python stdlib)
2. Write new signal files to `shared_config/` via `AtomicFileBus.write()`
3. Environment variable `SHARED_CONFIG_DIR` allows isolated testing

---

## 5. SIGNAL / EVENT BUS

### 5.1 RedisSignalBus (`engine/signal_bus.py`)
- **Backend:** Redis 7 (persistent, `--appendonly yes`, 256MB LRU)
- **Channels:** `signals`, `risk`, `pnl`, `commands`
- **Interface:**
  ```python
  bus = RedisSignalBus(host="127.0.0.1", port=6379)
  bus.publish(channel: str, message: dict) -> bool
  bus.subscribe(channel: str)
  bus.subscribe_all()
  bus.listen(timeout: Optional[float]) -> Generator[dict]
  bus.unsubscribe(channel: str)
  bus.close()
  
  # Convenience methods:
  bus.publish_signal(pair, side, price, amount, strategy, signal_id)
  bus.publish_risk_event(event_type, message, details)
  bus.publish_pnl(pair, pnl, trade_id)
  ```
- **Message format:** `{"type": channel, "timestamp": ISO8601, "data": {...}}`
- **Dual-write:** Every publish also writes to `shared_config/signal_bus_{channel}.json` (JSON backup, capped at 1000 messages)

### 5.2 AtomicFileBus (`shared_config/signal_bus.py`)
- **Backend:** Filesystem (atomic temp → rename)
- **Interface:** See Config System section 4.2
- **Primary for:** Config state, slow-changing signals (regime, sentiment, circuit breaker)
- **Bridge function:** `get_engine_bus()` returns `RedisSignalBus` if available, falls back to `AtomicFileBus`

### **INTEGRATION POINT:**
- New components should **subscribe** to Redis channels for real-time events
- For durable state (regime, risk tier), use `AtomicFileBus.read()` with `max_age` staleness checks
- To inject signals, write to `shared_config/{name}_signal.json` AND publish to Redis `signals` channel

---

## 6. CORE TYPES (`core/__init__.py`)

```python
class Signal:           # name, direction, confidence, source, timestamp, metadata
class RiskTier(IntEnum): # NORMAL=0, CAUTION=1, RESTRICTED=2, HALT=3, LIQUIDATE=4
class TradeDecision:     # action, confidence, direction, leverage, reasoning, source, timestamp
```

### **INTEGRATION POINT:** All new components should import `Signal`, `RiskTier`, `TradeDecision` from `core` for type consistency across the system.

---

## 7. FREQTRADE ENGINE (`freqtrade/`)

### 7.1 Strategy Interface (`freqtrade/strategy/interface.py`)
- **Base class:** `IStrategy` (INTERFACE_VERSION=3)
- **Key methods a strategy must/may implement:**
  ```python
  class IStrategy:
      INTERFACE_VERSION: int = 3
      minimal_roi: dict         # {0: 0.10, 30: 0.05, ...}
      stoploss: float           # -0.10 = 10% stop
      max_open_trades: int
      trailing_stop: bool
      trailing_stop_positive: float
      trailing_stop_positive_offset: float
      trailing_only_offset_is_reached: bool
      use_custom_stoploss: bool
      timeframe: str            # "1h", "5m", etc.
      
      def populate_indicators(self, dataframe: DataFrame) -> DataFrame
      def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame  # ← KEY HOOK
      def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame
      def custom_stoploss(self, trade, current_time, current_rate, ... ) -> float
      def custom_stake_amount(self, trade, current_time, current_rate, ... ) -> float
      def confirm_trade_entry(self, pair, order_type, amount, rate, ... ) -> bool
      def confirm_trade_exit(self, pair, trade, order_type, amount, rate, ... ) -> bool
      def leverage(self, pair, current_time, current_rate, ... ) -> float
  ```
- **Data flow:** `populate_indicators()` → `populate_entry_trend()` → `populate_exit_trend()`
- **Entry signal format:** DataFrame columns `enter_long`, `enter_short` (0 or 1)
- **Exit signal format:** DataFrame columns `exit_long`, `exit_short` (0 or 1)
- **65+ strategies** in `user_data/strategies/`

### 7.2 Exchange Layer (`freqtrade/exchange/`)
- **Base:** `freqtrade/exchange/exchange.py` (ccxt wrapper)
- **30+ exchange-specific backends:** binance, bybit, okx, kraken, kucoin, bitget, bingx, hyperliquid, etc.
- **Interface pattern:** Each exchange inherits from `Exchange` base class
- **Key methods:**
  ```python
  exchange.fetch_ticker(pair) -> dict
  exchange.fetch_ohlcv(pair, timeframe, since, limit) -> list[[ts,o,h,l,c,v]]
  exchange.create_order(pair, ordertype, side, amount, price) -> dict
  exchange.cancel_order(order_id, pair) -> dict
  exchange.fetch_balance() -> dict
  exchange.fetch_trades(pair, since, limit) -> list
  ```
- **Precision handling:** `amount_to_contract_precision()`, `price_to_precision()`

### 7.3 Persistence (`freqtrade/persistence/`)
- **Database:** SQLite (default: `user_data/tradesv3.sqlite`)
- **ORM:** SQLAlchemy
- **Key models:**
  - `Trade` — `trades` table: id, pair, stake_amount, amount, open_rate, close_rate, profit_abs, profit_ratio, ...
  - `Order` — `orders` table: id, ft_trade_id, order_type, side, price, cost, ...
  - `PairLock` — `pairlocks` table: id, pair, reason, active
  - `WalletHistory` — wallet snapshots over time
  - `_CustomData` — key-value store attached to trades
  - `_KeyValueStoreModel` — global key-value store
- **Init:** `init_db(db_url: str)` creates engine + session factory
- **Alternative DB:** Postgres supported via `--db-url postgresql://...`

### 7.4 RPC Layer (`freqtrade/rpc/`)
- **Classes:** `RPC`, `RPCManager`, `RPCHandler`, `RPCException`
- **Purpose:** API server for external queries (WebUI, Telegram bot, etc.)
- **Enables:** External systems to query trade status, force entries/exits

### **INTEGRATION POINTS for Fincept:**
1. **New strategy** → Subclass `IStrategy`, implement `populate_entry_trend/exit_trend`
2. **New data source** → Override `populate_indicators()` to add indicator columns
3. **Trade filtering** → Override `confirm_trade_entry()` / `confirm_trade_exit()`
4. **Custom risk** → Override `custom_stoploss()` / `custom_stake_amount()`
5. **Leverage control** → Override `leverage()` method
6. **New exchange** → Add exchange backend subclass in `freqtrade/exchange/`
7. **Trade persistence** → Read SQLite directly or use `_CustomData` wrapper for trade-attached metadata

---

## 8. AI SIGNAL GENERATORS (`engine/ai_signal_generators/`)

### 8.1 Generator Registry
```python
# From engine/ai_signal_generators/__init__.py:
SignalGenerator        # Base abstract class
GeneratorRegistry      # Registration + discovery
SignalOrchestrator     # Runs all generators, produces consensus signal
MiroSharkGenerator     # Wraps MiroShark brain
TradingAgentsGenerator # Wraps TradingAgents graph
MacroAnalystGenerator  # Macro economic analysis
KronosGenerator        # Time-cycle analysis
```

### 8.2 SignalOrchestrator
- Runs all registered generators
- Produces consensus (majority voting or weighted average)
- Writes to `shared_config/orchestrator_signal.json`
- Schema: `{pair, action, confidence, direction, source, price, leverage, reason, metadata}`

### 8.3 MiroShark Brain (`miroshark/brain.py`)
- **Composite scoring** from 5 dimensions:
  - Regime (HMM detector → 0-1 score)
  - Sentiment (FinBERT pipeline → 0-1 score)
  - Outcome (ChromaDB win rate → 0-1 score)
  - Agents (TradingAgents rating → 0-1 score)
  - Circuit breaker (risk tier → 0-1 score)
- **Output:** `miroshark_brain.json` with `action`, `confidence`, `direction`, `suggested_leverage`, `reasoning[]`
- **Action mapping:** composite score → {STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL}

### 8.4 TradingAgents (`TradingAgents/`)
- **Graph-based** multi-agent system: Analyst → Researcher → Trader → Risk Manager
- **LLM-powered** (GPT-5.4-mini, DeepSeek-v4)
- **Data vendors:** yfinance (configurable)
- **Output:** `shared_config/tradingagents_signal.json` with `rating` (Buy/Sell/Hold/Strong Buy/Strong Sell)
- **Bridge:** `TradingAgents/tradingagents/freqtrade_bridge.py`
  - `run_tradingagents(ticker, trade_date) -> dict`
  - `load_signal(path) -> dict`
  - CLI: `python -m tradingagents.freqtrade_bridge --ticker BTC/USDT --date 2026-05-22`

### **INTEGRATION POINT:**
- New Fincept signal generators should implement the `SignalGenerator` interface and register with `GeneratorRegistry`
- Output must be written to `shared_config/{name}_signal.json` via `AtomicFileBus`
- Subscribe to Redis `signals` channel to receive other generators' outputs

---

## 9. RISK MANAGEMENT (`agents/risk_managers/`)

### 9.1 EnforcedRiskGate — Circuit Breaker (`circuit_breaker.py`)
- **5 tiers:** NORMAL(0) → CAUTION(75% size) → RESTRICTED(50%, no shorts) → HALT(no entries) → LIQUIDATE(close all)
- **Config:** Reads `shared_config/circuit_breaker.json`
- **Fail-safe:** Defaults to HALT(tier 3) on missing/corrupt config
- **Interface:**
  ```python
  gate = EnforcedRiskGate(breaker_path="shared_config/circuit_breaker.json")
  tier = gate.read_breaker_state()  # → RiskTier
  gate.enforce_breakers_on_strategy(dataframe) -> DataFrame  # Zeroes entries when HALT/LIQUIDATE
  classify_tier(state_str: str) -> RiskTier
  ```
- **Strategy integration:** Call `enforce_breakers_on_strategy(df)` inside `populate_entry_trend()`

### 9.2 HEdgeCoordinator (`hedge_coordinator.py`)
- **Aggregates** risk from 4 sources:
  1. Circuit breaker state → 0-1
  2. Learning loop win rate → 0-1
  3. SubAgentOverseer health score → 0-1
  4. Total PnL → 0-1
- **Output:** Composite risk score (0-1) → mapped to `RiskTier`
- **Caching:** 30-second TTL

### 9.3 SubAgentOverseer (`subagent_overseer.py`)
- **Monitors:** tradingagents, mirofish, learning_loop, scripts_agent_runner, market_regime
- **Per-agent:** heartbeat TTL, max trades/day, consecutive failure tracking
- **Health check:** `{health_score, total_agents, healthy_agents, stale_agents, agents{...}}`
- **Writes:** `shared_config/agent_health.json`
- **Interface:**
  ```python
  overseer = SubAgentOverseer(redis_host="127.0.0.1", redis_port=6379)
  overseer.heartbeat(name, status, error)
  overseer.record_trade(name)
  overseer.health_check() -> dict
  overseer.publish_health()
  ```

### **INTEGRATION POINT:**
- New risk sources → Add to `HEdgeCoordinator` aggregation
- New agents → Register with `SubAgentOverseer.register_agent(name, max_trades_per_day)`
- Write risk state to `shared_config/circuit_breaker.json` to control trading

---

## 10. KNOWLEDGE & LEARNING (`knowledge/`, `strategy_db/`)

### 10.1 ChromaDB Strategy Knowledge Base (`strategy_db/`)
- **Storage:** `strategy_db/chroma_db/` (ChromaDB persistent)
- **Collections:** 
  - `trading_strategies` — Main strategy chunks (youtube transcripts parsed into structured chunks)
  - `news_sentiment` — FinBERT-embedded news articles
- **Schema** (`strategy_db/schema.py`):
  ```python
  @dataclass
  class StrategyChunk:
      chunk_id: str
      source_type: str           # "youtube"
      youtube_url: str
      video_title: str
      channel_name: str
      setup_name: str            # e.g. "Risk to Zero ASAP"
      setup_type: str            # entry, exit, confirmation, risk_management, ...
      timeframe: str
      market_condition: str      # trending, ranging, volatile
      strategy_style: str        # scalping, swing, intraday_breakout
      assets_applicable: list[str]
      chunk_text: str            # Full strategy description
      entry_condition: str
      confirmation_signal: str
      stop_loss_rule: str
      target_exit_rule: str
      invalidation_condition: str
      risk_reward: str
      position_sizing: str
      psychology_note: str
      edge_description: str
      confluence_factors: list[str]
      keywords: list[str]        # CVD, absorption, breakout, LVN, etc.
      transcript_evidence: str
      author_concept: bool
      confidence: Optional[float]
  ```
- **Outcome metadata** (added by `outcome_sync`):
  - `outcome_win_rate`, `outcome_avg_pnl_pct`, `outcome_avg_r_multiple`, `outcome_regime_win_rates`

### 10.2 RuntimeVDBridge (`strategy_db/runtime_bridge.py`)
- **Singleton** with TTL cache (300s) — strategies query ChromaDB at runtime during `populate_indicators()`
- **Interface:**
  ```python
  bridge = RuntimeVDBridge()  # Singleton
  bridge.query(text, top_k=3, setup_type=None, use_hybrid=False) -> list[dict]
  bridge.query_entry_setups(text, top_k=3) -> list[dict]
  bridge.query_risk_rules(text, top_k=3) -> list[dict]
  bridge.is_available() -> bool
  bridge.clear_cache()
  ```
- **Hybrid search:** BM25 + dense fusion via `strategy_db.search.StrategyDB.hybrid_search()`
- **Used by:** 65+ strategies at runtime for adaptive parameter selection

### 10.3 HMM Regime Detector (`strategy_db/regime_detector_hmm.py`)
- **Model:** 4-state Gaussian HMM (trending_up, trending_down, ranging, volatile)
- **Features:** returns, realized_vol, high_low_range, ema_slope
- **Data:** Feather files from `user_data/data/binance/futures/`
- **Interface:**
  ```python
  detector = HMMRegimeDetector()
  detector.load()  # Load pretrained model from regime_hmm.pkl
  regime, metrics = detector.predict(df, lookback=100)
  # regime: "trending_up" | "trending_down" | "ranging" | "volatile"
  # metrics: {regime_probs, regime_stability, volatility_20, returns_20}
  ```

### 10.4 Learning Loop (`knowledge/learning_loop.py`)
- **Pre-trade gate:** Queries ChromaDB for similar setups, blocks if win_rate < 40%
- **Post-trade:** Records outcomes to `outcome_history.json`
- **Feedback:** `outcome_sync` pushes outcomes back into ChromaDB chunk metadata
- **Interface:**
  ```python
  loop = LearningLoop()
  loop.check_before_trade(pair, side, market_condition, strategy) -> bool  # True = allowed
  loop.record_outcome(pair, side, pnl, r_multiple, setup_name, market_condition)
  loop.get_win_rate(pair, side, market_condition) -> float
  ```

### 10.5 Trade Encoder (`knowledge/trade_encoder.py`)
- Converts (pair, side, market_condition, strategy, indicators) → semantic search query for ChromaDB
- Converts trade outcomes → structured dict for `outcome_history.json`
- **Interface:**
  ```python
  encode_trade_query(pair, side, market_condition, signal_type, strategy, indicators) -> str
  encode_trade_outcome(pair, side, pnl, r_multiple, setup_name, market_condition, strategy) -> dict
  ```

### 10.6 Strategy KB MCP Server (`strategy_db/mcp_server.py`)
- **Transport:** MCP stdio protocol
- **9 tools:** query_strategies, query_user_knowledge, get_strategy, list_setup_types, list_market_conditions, strategy_stats, regime_detect, strategy_context, regime_aware_search, outcome_sync, sentiment_query
- **Registered in:** Hermes config as `strategy-kb`

### **INTEGRATION POINTS for Fincept:**
1. **New data sources** → Ingest into ChromaDB via `strategy_db/ingest.py` pattern (add to `trading_strategies` collection)
2. **New collections** → Create in same ChromaDB instance, query via MCP
3. **Runtime adaptation** → Strategies call `RuntimeVDBridge.query()` — new data appears automatically
4. **User knowledge** → Add markdown files to `user_kb/`, query via `query_user_knowledge`
5. **Regime detection** → Call `HMMRegimeDetector.predict()` or read `shared_config/market_regime.json`
6. **Outcome feedback** → Write to `outcome_history.json`, run `outcome_sync` to update ChromaDB metadata

---

## 11. EXCHANGE LAYER

| Component | Technology | Interface |
|-----------|-----------|-----------|
| Freqtrade Exchange | ccxt (Python) | `Exchange` base class + 30+ subclasses |
| Data files | Feather format | `user_data/data/binance/futures/{PAIR}-{TF}-futures.feather` |
| Flowsurface | Rust + NDJSON | `LocalConnector` reads `.jsonl` files from `~/.local/share/flowsurface/` |
| Finance MCP | yfinance | `FinanceMcpServer` — MCP stdio tools |

**Data format for OHLCV:**
- Freqtrade: `list[[timestamp, open, high, low, close, volume]]`
- Feather: pandas DataFrame with columns `date, open, high, low, close, volume`
- Flowsurface NDJSON: `{"t": unixms, "o": float, "h": float, "l": float, "c": float, "v": float}`

### **INTEGRATION POINT:**
- To add a new exchange, subclass `freqtrade/exchange/exchange.py`
- To add a new data source, implement `populate_indicators()` with the data, or extend `FinanceMcpServer`
- Flowsurface `LocalConnector` accepts `.jsonl` files — any component writing to that dir appears in charts

---

## 12. BACKTESTING PIPELINE

| Component | Location | Purpose |
|-----------|----------|---------|
| Freqtrade backtesting | `freqtrade/optimize/backtesting.py` | Core backtest engine |
| HEdge deploy | `HEdge/deploy.py` | Copies strategies to `user_data/strategies/` |
| HEdge configs | `HEdge/build_configs.py` | Generates freqtrade config JSON per strategy |
| HEdge backtests | `HEdge/scripts/run_all_backtests.sh` | Sequential/tmux batch backtester |
| Strategy DB eval | `strategy_db/eval/` | Strategy evaluation framework |
| Backtest sync | `strategy_db/backtest_sync.py` | Syncs backtest results into ChromaDB |
| Flowsurface bridge | `engine/flowsurface_bridge.py` | Exports backtest data as NDJSON |

### **INTEGRATION POINT:**
- New Fincept backtesting results → Write via `backtest_sync` pattern into ChromaDB
- Visual analysis → Export backtest PnL via `flowsurface_bridge.py` (reads SQLite trades DB + feather OHLCV + outcome_history.json → NDJSON)

---

## 13. LIVE EXECUTION PIPELINE

```
1. AI Signal Generators produce signals → shared_config/*.json + Redis
2. MiroShark Brain reads all signals → composite decision → miroshark_brain.json
3. SignalOrchestrator runs consensus → orchestrator_signal.json
4. Risk Gates check:
   a. EnforcedRiskGate reads circuit_breaker.json → may zero entries
   b. LearningLoop queries ChromaDB win rate → may block if <40%
   c. HEdgeCoordinator aggregates composite risk → adjusts position sizing
5. Freqtrade strategy's populate_entry_trend() reads signals + risk state
6. confirm_trade_entry() final gate
7. Order placed via exchange layer (ccxt)
8. Trade tracked in SQLite (tradesv3.sqlite)
9. On exit: populate_exit_trend() + confirm_trade_exit()
10. Outcome recorded → outcome_history.json → outcome_sync → ChromaDB metadata
```

### **INTEGRATION POINT:**
- Step 4: New risk gates can intercept at `confirm_trade_entry()` or by writing to `shared_config/circuit_breaker.json`
- Step 1: New signal generators write to `shared_config/` + Redis
- Step 10: New outcome recorders can push to `outcome_history.json`

---

## 14. MONITORING & ALERTING (`monitoring/alerter.py`)

- **Interface:**
  ```python
  alerter = Alerter(config_path="shared_config/alerter_config.json")
  alerter.send_alert(message, level="info")    # → Slack webhook / generic webhook
  alerter.alert_critical_breaker()
  alerter.alert_warning_breaker()
  alerter.alert_large_pnl(pnl)
  alerter.alert_stale_signals()
  ```
- **Config:** `shared_config/alerter_config.json`
- **Triggers:** circuit breaker state change, large PnL event, stale signals
- **Destinations:** Slack webhook, generic webhook (configurable)

### **INTEGRATION POINT:**
- Call `alerter.send_alert()` from any component
- Extend `Alerter` class for new destinations (Discord, Telegram, PagerDuty)
- New alert conditions: add check methods to `Alerter`, register in config

---

## 15. UI LAYER (`ui/`)

### 15.1 Streamlit App (`ui/app.py`)
- **Port:** 8501
- **Pages:** Dashboard, Trade Log, Risk Monitor, Strategy Performance, Agent Status
- **Data layer:** `ui/data_layer.py` — reads from Redis + shared_config + SQLite

### 15.2 Data Layer (`ui/data_layer.py`)
```python
class DataLayer:
    def get_current_positions() -> list[dict]
    def get_recent_trades(limit) -> list[dict]
    def get_risk_state() -> dict
    def get_signal_status() -> dict
    def get_agent_health() -> dict
    def get_pnl_history(days) -> list[dict]
```

### 15.3 Flowsurface (`flowsurface_src/`)
- **Language:** Rust (egui-based charting)
- **Connectors:** `LocalConnector` reads NDJSON/JSONL from local filesystem
- **Charts:** OHLCV candlestick, volume, equity curve, trade markers
- **Data bridge:** `engine/flowsurface_bridge.py` exports from SQLite + feather files

### **INTEGRATION POINT:**
- Add new Streamlit pages in `ui/pages/`
- Extend `DataLayer` with new query methods
- Feed Flowsurface charts via NDJSON files in `~/.local/share/flowsurface/market_data/algotrading/`

---

## 16. SWARM ORCHESTRATION (`swarm/`)

### 16.1 Swarm Engine (`swarm/engine.py`)
- **5 presets** as YAML files:
  - `daily_committee` — CEO + 3 analysts (daily 08:00 UTC)
  - `crisis_response` — Emergency risk response
  - `strategy_optimizer` — Strategy parameter tuning
  - `macro_scan` — Macro economic scanning
  - `sub_agent_trading` — Sub-agent delegation
- **Interface:**
  ```python
  engine = SwarmEngine()
  engine.load_preset(preset_name) -> SwarmConfig
  engine.run_swarm(config, task) -> dict
  engine.run_swarm_with_bridge(config, task, bus) -> dict  # With Redis integration
  ```
- **Agent tools referenced:** `trade_status`, `execute_backtest`, `check_learning_status`, `mcp_get_quote`, `mcp_get_ohlcv`, `mcp_get_ta`, `mcp_get_news`

### **INTEGRATION POINT:**
- New swarm presets → Add YAML to `swarm/presets/`
- New agent tools → Register with NEXUS or directly in YAML tool lists
- Swarm output flows through `shared_config/` + Redis

---

## 17. NEXUS BRIDGE (`nexus/`)

### 17.1 HTTP Daemon (`nexus/server/nexus_http_daemon.py`)
- **Port:** 8080
- **Health check:** `GET /health`
- **Purpose:** REST API for NEXUS routing, skill discovery, learning feedback

### 17.2 Bridge Module (`nexus/bridge.py`)
- Connects NEXUS tool routing to the Algotrading subsystem
- Routes tasks to appropriate skills/MCP tools
- Manages outcome feedback loop

### 17.3 MCP Tools (`nexus/mcp_tools.py`)
- Exposes NEXUS as MCP server for AI agent consumption
- Tools for skill discovery, routing, outcome reporting

### **INTEGRATION POINT:**
- NEXUS is the **external AI agent gateway** — any new Fincept MCP tool should be registered here
- `nexus_http_daemon` at port 8080 is the REST entry for external systems

---

## 18. MCP LAYER (`mcp_layer/`)

### FinanceMcpServer (`mcp_layer/finance_mcp_server.py`)
- **Transport:** MCP stdio
- **~10 tools:**
  - `get_quote(ticker)` — Current price
  - `get_ohlcv(ticker, interval, period)` — OHLCV data
  - `get_ta(ticker)` — Technical indicators
  - `screen_stocks(filter)` — Stock screening
  - `get_news(ticker)` — Company news
  - `get_company_info(ticker)` — Company fundamentals
  - `get_institutional_holders(ticker)` — Institutional ownership
  - `get_recommendations(ticker)` — Analyst recommendations
  - `get_earnings(ticker)` — Earnings data
  - `get_actions(ticker)` — Corporate actions
- **Backend:** yfinance (no API key needed for basic usage)

### **INTEGRATION POINT:**
- This is the **primary data ingestion MCP** for external AI agents
- New data sources (e.g., Fincept fundamental data APIs) would extend this server or create a parallel one
- Registered in `start_local.sh` as `finance-mcp` service

---

## 19. DATABASE SCHEMA SUMMARY

### SQLite: `user_data/tradesv3.sqlite`
| Table | Key Columns | Purpose |
|-------|------------|---------|
| `trades` | id, pair, stake_amount, amount, open_rate, close_rate, profit_abs/ratio, is_open, strategy | Active/closed trade records |
| `orders` | id, ft_trade_id, order_type, side, price, cost, status, ft_is_open | All exchange orders |
| `pairlocks` | id, pair, reason, active, lock_end_time | Pair-level trading locks |
| `wallet_history` | id, stake_currency, stake_amount, total, timestamp | Balance snapshots |
| `custom_data` | id, ft_trade_id, type, key, value | Trade-attached metadata |
| `key_value_store` | id, key, value | Global key-value store |

### ChromaDB: `strategy_db/chroma_db/`
| Collection | Schema | Purpose |
|------------|--------|---------|
| `trading_strategies` | StrategyChunk metadata + embeddings | Strategy knowledge base |
| `news_sentiment` | Sentiment + article metadata + embeddings | News intelligence |

### Redis (in-memory, persisted to disk)
| Channel | Message Format | Purpose |
|---------|---------------|---------|
| `signals` | `{pair, side, price, amount, strategy, signal_id}` | Trade signals |
| `risk` | `{event, message, details}` | Risk events |
| `pnl` | `{pair, pnl, trade_id}` | PnL updates |
| `commands` | Various | Control commands |

### Postgres (optional, dev profile)
- Same schema as SQLite, via `--db-url postgresql://...`

### **INTEGRATION POINT:**
- New tables → Add SQLAlchemy models in `freqtrade/persistence/`
- New ChromaDB collections → Create via `chromadb.PersistentClient` in `strategy_db/`
- New Redis channels → Add to `CHANNELS` dict in `engine/signal_bus.py`

---

## 20. COMPLETE INTEGRATION POINTS SUMMARY

### Where Fincept Components Can Plug In

| # | Integration Point | Layer | Method | Data Format |
|---|-------------------|-------|--------|-------------|
| 1 | **New Signal Generator** | AI Signals | Implement `SignalGenerator`, register in `GeneratorRegistry` | Write to `shared_config/{name}_signal.json` + Redis `signals` |
| 2 | **New Risk Gate** | Risk Mgmt | Update `HEdgeCoordinator` weights + write `circuit_breaker.json` | `AtomicFileBus.write("circuit_breaker.json", ...)` |
| 3 | **New Strategy Data** | Knowledge | Ingest into ChromaDB `trading_strategies` collection | `StrategyChunk` dataclass + `ingest.py` pattern |
| 4 | **New MCP Tool Server** | MCP Layer | Create MCP stdio server, register in `start_local.sh` | MCP protocol (Tool/InputSchema/TextContent) |
| 5 | **New Exchange Backend** | Exchange | Subclass `freqtrade/exchange/exchange.py` | ccxt-compatible API |
| 6 | **New Strategy** | Trading | Subclass `IStrategy`, implement `populate_entry_trend()` | DataFrame columns `enter_long/short`, `exit_long/short` |
| 7 | **New Risk Tier** | Risk | Extend `RiskTier` enum + `EnforcedRiskGate` tiers | JSON state in `circuit_breaker.json` |
| 8 | **New Agent** | Swarm/Agents | Register with `SubAgentOverseer` + add YAML preset | Heartbeat via Redis |
| 9 | **New Alert Channel** | Monitoring | Extend `Alerter` class | Webhook config in `alerter_config.json` |
| 10 | **New UI Page** | UI | Add Streamlit page in `ui/pages/` | Read via `DataLayer` or `AtomicFileBus` |
| 11 | **New Chart Data** | Flowsurface | Write NDJSON to `~/.local/share/flowsurface/market_data/` | `{"t": ms, "o": f, "h": f, "l": f, "c": f, "v": f}` |
| 12 | **New Outcome Source** | Learning | Write to `outcome_history.json` + call `outcome_sync` | `encode_trade_outcome()` format |
| 13 | **New Market Data** | Data | Write feather to `user_data/data/binance/futures/` | pandas feather: `date,o,h,l,c,v` |
| 14 | **New News Source** | Sentiment | Add to `FinBERTNewsEmbedder` pipeline | ChromaDB `news_sentiment` collection |
| 15 | **NEXUS Tool Registration** | NEXUS | Register MCP server in NEXUS config | MCP stdio protocol |
| 16 | **New DB Table** | Persistence | Add SQLAlchemy model in `freqtrade/persistence/` | SQLAlchemy ORM |
| 17 | **Shared Config Signal** | Bus | `AtomicFileBus.write("{name}.json", data)` | Any JSON dict |
| 18 | **Redis Channel** | Bus | Add to `CHANNELS` dict + use `bus.publish()` | `{"type": ch, "timestamp": ISO, "data": {...}}` |

---

## 21. DEPENDENCY MAP (Module → Depends On → Depended On By)

```
freqtrade/          → ccxt, sqlalchemy, pandas, numpy
                    → is depended on by: engine/freqtrade_bridge, HEdge/deploy, docker-compose

engine/             → redis, shared_config/signal_bus, core
                    → is depended on by: miroshark, agents, swarm, ui

shared_config/      → (stdlib only — json, os, tempfile, threading)
                    → is depended on by: EVERYTHING (all modules read/write here)

strategy_db/         → chromadb, sentence_transformers, hmmlearn, pandas
                    → is depended on by: knowledge/learning_loop, engine/ai_signal_generators, mcp_server

knowledge/          → strategy_db (ChromaDB), shared_config
                    → is depended on by: miroshark/brain, strategies (learning_loop gate)

agents/             → engine/signal_bus (Redis), shared_config
                    → is depended on by: miroshark/brain (composite risk), strategies (circuit breaker)

miroshark/          → knowledge, agents, engine, shared_config
                    → is depended on by: engine/ai_signal_generators

nexus/              → (external NEXUS system at /home/roshan/nexus/)
                    → is depended on by: start_local.sh, external AI tools

mcp_layer/          → yfinance, mcp SDK
                    → is depended on by: start_local.sh, swarm agents

ui/                 → streamlit, redis, shared_config, sqlite
                    → is depended on by: nothing (terminal display only)

swarm/              → engine, shared_config, YAML presets
                    → is depended on by: start_local.sh (if enabled)

monitoring/         → shared_config, requests (webhooks)
                    → is depended on by: circuit breaker alerts, stale signal alerts

flowsurface_src/    → Rust egui, local filesystem (NDJSON/JSONL)
                    → is depended on by: nothing (visual only)
                    → depends on: engine/flowsurface_bridge.py (data export)

TradingAgents/      → LangGraph, LLM APIs, yfinance
                    → is depended on by: engine/ai_signal_generators
                    → writes to: shared_config/tradingagents_signal.json

HEdge/              → strategy_db (ChromaDB source), freqtrade (IStrategy)
                    → is depended on by: user_data/strategies (via deploy.py)
```

---

## 22. KEY OBSERVATIONS & RISKS

1. **Single point of failure:** `shared_config/` is the shared state backbone. If filesystem fills or corrupts, entire system degrades. Mitigation: `AtomicFileBus` does atomic writes with temp→rename, but no disk-space monitoring.

2. **Redis dependency:** Redis is listed as `required: false` in docker-compose, but `RedisSignalBus`, `SubAgentOverseer`, and UI all depend on it. System degrades gracefully (falls back to file-based bus), but real-time features break.

3. **ChromaDB singleton collision:** `RuntimeVDBridge` and `strategy_db/mcp_server.py` both access ChromaDB. Singleton pattern prevents multiple clients from same process, but cross-process access works.

4. **No schema enforcement on shared_config JSON:** Any component can write any shape to any file. `AtomicFileBus` ensures write atomicity but not schema validity. Consider adding validators.

5. **Strategy count (65+) vs. active strategy (1):** Docker-compose runs only `AroonMomentumEngine_Hybrid`. Other strategies need manual `--strategy` selection or backtesting. No dynamic strategy switching.

6. **MiroShark brain is the central decision aggregator** — it reads ALL other subsystems and produces the composite decision. Any new Fincept component that affects trading should ensure MiroShark can read its output.

7. **Postgres is underutilized:** Defined in compose but freqtrade defaults to SQLite. Only useful if `--db-url` is changed.

---

*End of Architectural Audit*