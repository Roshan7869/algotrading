# Algotrading Integration Plan — From Scattered Stacks to Professional Dashboard

## Current State (The Mess)

```
20,484 Python files scattered across:
├── 127 Freqtrade strategies (handcoded + 70+ generated)
├── strategy_db/        → ChromaDB + MCP server (running, 592 vectors)
├── nexus/              → Bridge to NEXUS routing (2,463 vectors)
├── agents/             → Risk managers (circuit breaker, hedge coordinator)
├── scripts/            → 124 scripts (refresh_regime, refresh_agents, etc.)
├── engine/             → Signal bus (Redis pub/sub), strategy registry, walkforward
├── monitoring/         → 1 alerter file
├── ui/                 → 11 Streamlit pages (broken, no data flow)
├── financial-services-plugins/ → 216 files (QuantDinger etc.)
├── miroshark/          → MiroFish sentiment (Docker on :3000/:5001)
├── mcp_layer/          → Finance MCP server
├── knowledge/          → 8 files
├── shared_config/      → JSON IPC (market_regime, circuit_breaker, etc.)
├── HEdge/              → 68 files, hedging strategies
├── graphify-out/       → Knowledge graph (6,676 nodes)
├── QuantDinger         → Docker stack (backend :5000, frontend :8888, DB :5432)
└── TradingAgents       → Docker (exited, 13 agents, 19 models)
```

### Problems

1. **No unified data flow** — Components talk via JSON files in shared_config/ (filesystem IPC). No event bus, no message queue (Redis exists but barely used)
2. **UI is disconnected** — Streamlit pages render hardcoded/mock data, don't connect to live engine
3. **Strategy management is wild** — 127 strategies, no active strategy selector, no regime-based auto-switching
4. **Services are scattered** — QuantDinger (Docker), MiroFish (Docker), Strategy DB (MCP), NEXUS (FastAPI :8080), Freqtrade (Docker), all running independently with no orchestration
5. **Cron-based coordination** — 5 cron jobs for regime/agents/sentiment/outcomes/circuit_breaker. No proper scheduling, no error handling, no recovery
6. **No dashboard** — Streamlit UI has 11 pages but they don't show real data

---

## Target Architecture (The Professional Stack)

```
┌──────────────────────────────────────────────────────────┐
│                    DASHBOARD LAYER                        │
│            Streamlit on :8501 (unified)                   │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │Dashboard│ │ Strategies│ │  Risk     │ │  Backtest    │ │
│  │(Live PnL│ │ (select + │ │ (circuit  │ │ (run + compare│ │
│  │  regime)│ │  regime)  │ │  breaker) │ │  results)    │ │
│  └─────────┘ └──────────┘ └──────────┘ └─────────────┘ │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │Signals  │ │ KB Search│ │  Health   │ │  Settings    │ │
│  │(live    │ │(ChromaDB │ │ (services │ │ (config +    │ │
│  │ feed)   │ │ + NEXUS)  │ │  status)  │ │  deploy)     │ │
│  └─────────┘ └──────────┘ └──────────┘ └─────────────┘ │
├──────────────────────────────────────────────────────────┤
│                  ORCHESTRATION LAYER                       │
│           Python orchestrator (single process)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Regime Engine │  │  Strategy     │  │  Risk Gate   │  │
│  │ (HMM detect  │  │  Selector     │  │  (5-tier     │  │
│  │  + dispatch) │  │  (regime→strat)│  │   QuantDinger│  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├──────────────────────────────────────────────────────────┤
│                   SERVICE LAYER                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │Freqtrade │ │ChromaDB  │ │ NEXUS    │ │ HMM Regime│  │
│  │(trade    │ │(Strategy │ │ (routing │ │ (detect + │  │
│  │ engine)  │ │  KB)     │ │ + NLP)   │ │  classify)│  │
│  │:8080     │ │ MCP stdio│ │ :8080    │ │  cron→svc │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
├──────────────────────────────────────────────────────────┤
│                    DATA LAYER                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ SQLite   │ │ Feather  │ │ Redis    │ │ JSON IPC  │  │
│  │ (trades, │ │ (OHLCV)  │ │ (cache + │ │ (shared_  │  │
│  │  results)│ │          │ │  pub/sub)│ │  config)  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## Execution Plan — 8 Phases

### Phase 1: Foundation — Unified Config & Directory Cleanup
**Goal:** Clean project structure, single source of truth for config, kill dead code
**Duration:** ~2 hours
**Verification:** `python -m pytest tests/` still passes, project tree is clean

Tasks:
1.1. Create `config/settings.yaml` — single YAML config merging shared_config/*.json + freqtrade config
1.2. Create `config/paths.py` — centralized path constants (DATA_DIR, STRATEGIES_DIR, etc.)
1.3. Remove dead generated strategies (GenStrategy_C*, GenStrategy_N*) — keep only active/validated ones
1.4. Create `Makefile` with: `make dev`, `make test`, `make backtest`, `make dashboard`, `make clean`
1.5. Add `.env.example` with all required env vars documented
1.6. Run `python -m pytest tests/` — establish baseline (146 passing, 3 known skips)

### Phase 2: Service Orchestration — Single Entry Point
**Goal:** One command starts all services, one health check shows status
**Duration:** ~3 hours
**Verification:** `python orchestrator.py` starts all services, `python orchestrator.py status` shows green

Tasks:
2.1. Create `orchestrator.py` — Python process manager that starts/stops all services:
  - Freqtrade (Docker or local)
  - Strategy DB MCP server
  - NEXUS routing daemon
  - HMM regime detector (cron → always-on service)
  - Dashboard (Streamlit)
2.2. Create `scripts/health_check.py` — checks: Freqtrade API, ChromaDB, NEXUS, Redis, regime file freshness
2.3. Replace 5 cron jobs with `orchestrator.py` scheduling (APScheduler or asyncio loop)
2.4. Create `docker-compose.unified.yml` — single compose that starts everything (Freqtrade, Redis, Postgres, QuantDinger)

### Phase 3: Data Pipeline — Single Source of Truth
**Goal:** All components read/write through a unified data layer, no more filesystem IPC
**Duration:** ~3 hours
**Verification:** Regime change propagates to Freqtrade strategy within 5 seconds, PnL data shows in dashboard

Tasks:
3.1. Create `core/data_manager.py` — singleton that:
  - Reads SQLite trades DB
  - Reads feather market data files
  - Reads shared_config JSON files
  - Exposes unified API: `get_regime()`, `get_pnl()`, `get_positions()`, `get_signals()`
3.2. Create `core/event_bus.py` — replace JSON file IPC with in-process pub/sub:
  - Channels: regime_change, signal_new, risk_alert, trade_open, trade_close
  - Subscribers: dashboard, strategy selector, risk gate, alerter
3.3. Wire `shared_config/market_regime.json` → `core/data_manager.py` → event_bus
3.4. Wire `shared_config/circuit_breaker.json` → `core/data_manager.py` → event_bus

### Phase 4: Strategy Selection Engine — Regime-Aware Auto-Switching
**Goal:** System automatically selects best strategy for current market regime
**Duration:** ~2 hours
**Verification:** Regime change to "volatile" → strategy auto-switches to appropriate strategy, logged

Tasks:
4.1. Create `engine/regime_selector.py`:
  - Maps regime → strategy using outcome_history.json + backtest results
  - Uses HMM regime detection (already in strategy_db/regime_query.py)
  - Calls NEXUS route_v4 for strategy KB lookup
  - Writes selected strategy to shared_config/active_strategy.json
4.2. Create `engine/strategy_hotswap.py`:
  - Watches active_strategy.json for changes
  - Sends Freqtrade RPC to reload strategy (or restart container)
  - Logs strategy changes with timestamps
4.3. Create outcome feedback loop:
  - After each trade close → update strategy_performance_db.json
  - After N trades → re-evaluate regime-strategy mapping
4.4. Prune strategy list to curated set:
  - Keep: AroonMomentumEngine_Hybrid (current), IVB_ORB_V5 (best ORB), bos_frvp_lvn_vwap (best BOS)
  - Keep: 7 hedge strategies (validated)
  - Archive: 70+ generated strategies (move to strategies/archived/)

### Phase 5: Dashboard Wiring — Real Data Flow
**Goal:** Every Streamlit page shows real live data, not mocks
**Duration:** ~4 hours
**Verification:** Dashboard shows live PnL, strategy status, regime, and risk tier

Tasks:
5.1. Create `ui/data_layer.py` v2 — replace old with one that:
  - Imports from `core/data_manager.py` (no direct file reads)
  - Uses `core/event_bus.py` for live updates (st.rerun on events)
  - Caches data with st.cache_data (5s TTL for live, 5min for historical)
5.2. Wire each page:
  - Dashboard (1_dashboard.py) → live PnL from trades DB, regime from data_manager, risk tier from circuit breaker
  - Signals (3_signals.py) → live signals from event_bus
  - Risk Monitor (4_risk_monitor.py) → circuit breaker state + drawdown chart
  - Strategies (7_strategies.py) → active strategy + regime selector + hotswap controls
  - Backtest (8_backtest.py) → run backtest via orchestrator subprocess + show results
  - System Health (10_system_health.py) → health_check.py results
  - PnL Analytics (5_pnl_analytics.py) → trade analysis from SQLite
  - Market Data (6_market_data.py) → feather data reader + live Binance ws
5.3. Add Streamlit sidebar: Service status indicators (green/red dots for each service)

### Phase 6: Risk System Integration — QuantDinger + Circuit Breaker
**Goal:** 5-tier risk gate controls Freqtrade position sizing in real-time
**Duration:** ~2 hours
**Verification:** Risk tier change → position size adjusts, halt tier → no new trades

Tasks:
6.1. Wire `shared_config/quantdinger_risk_gate.py` → reads trades DB → writes circuit_breaker.json
6.2. Verify AroonMomentumEngine_Hybrid reads circuit_breaker in `bot_loop_start()` (confirm in code)
6.3. Add risk state to event_bus → dashboard shows real-time risk tier
6.4. Add Telegram alerts on risk tier transitions (existing alerter.py)

### Phase 7: Knowledge Base Integration — Strategy KB → Live Decisions
**Goal:** NEXUS + ChromaDB strategy search feeds directly into strategy selection
**Duration:** ~2 hours
**Verification:** Query "volatile breakout strategy" returns relevant strategy, auto-selected when regime=volatile

Tasks:
7.1. Wire `engine/regime_selector.py` → NEXUS `route_v4` → ChromaDB `query_strategies`
7.2. Wire `engine/regime_selector.py` → HMM `regime_detect` → strategy context
7.3. Create `scripts/refresh_all.py` — unified refresh script (replaces 5 cron jobs):
  - refresh_regime (HMM detection)
  - refresh_outcomes (trade outcome sync)
  - refresh_sentiment (news sentiment pipeline)
  - circuit_breaker update (QuantDinger risk gate)
7.4. Add KB search to Dashboard (page 2: KB Search with filters)

### Phase 8: Polish & Documentation
**Goal:** Professional README, architecture docs, onboarding guide
**Duration:** ~1 hour
**Verification:** New developer can clone, `make dev`, see working dashboard in 10 minutes

Tasks:
8.1. Rewrite README.md with:
  - Architecture diagram
  - Quick start guide
  - Configuration reference
  - Strategy selection logic
8.2. Update ARCHITECTURE_DAG.md with actual unified architecture
8.3. Create `docs/STRATEGY_GUIDE.md` — how strategies are selected, what each does
8.4. Create `docs/OPERATIONS.md` — how to monitor, debug, and restart services

---

## Phase Dependencies (DAG)

```
Phase 1 (Foundation)
  └──→ Phase 2 (Orchestration)
        └──→ Phase 3 (Data Pipeline)
              ├──→ Phase 4 (Strategy Selection)
              │     └──→ Phase 7 (KB Integration)
              ├──→ Phase 5 (Dashboard Wiring)
              └──→ Phase 6 (Risk Integration)
                       └──→ Phase 8 (Polish)
```

Phases 4, 5, 6 can run in parallel after Phase 3.
Phase 7 depends on Phase 4.
Phase 8 is last.

---

## What We Keep vs Kill

### KEEP (Core Stack)
- Freqtrade engine (battle-tested)
- AroonMomentumEngine_Hybrid + 3-5 curated strategies
- ChromaDB + MCP server (592 vectors, working)
- HMM regime detection (strategy_db/regime_query.py)
- QuantDinger risk gate (5-tier, working)
- Signal bus concept (Redis pub/sub, working)
- 7 hedge strategies (validated)
- IVB_ORB strategies (validated, best performer)
- BOS strategies (validated)

### KILL / ARCHIVE
- 70+ generated strategies (GenStrategy_C*, GenStrategy_N*) → archive/
- VectorOmni strategies → archive/ (experimental, not validated)
- MiroFish sentiment container (port 3000) → evaluate later
- TradingAgents Docker container (exited, broken) → redesign later
- Flowsurface UI page → remove (depends on broken service)
- Duplicate config files (config_*.json variants) → consolidate into 1
- Cron-based coordination → replace with orchestrator

### SIMPLIFY
- 5 JSON IPC files in shared_config/ → single config + event bus
- 124 scripts → 10 operational scripts + archive
- HEdge/ standalone → merge into strategies/

---

## File Count Target

| Current | Target | Reduction |
|---------|--------|-----------|
| 20,484 Python files | ~500 core files | 97% reduction |
| 127 strategies | 10-15 curated | 88% reduction |
| 124 scripts | 10 operational | 92% reduction |
| 5 cron jobs | 1 orchestrator | 80% reduction |
| 11 UI pages (mock data) | 8 pages (live data) | 27% reduction |

---

## Estimated Total Time

| Phase | Hours |
|-------|-------|
| 1. Foundation | 2 |
| 2. Orchestration | 3 |
| 3. Data Pipeline | 3 |
| 4. Strategy Selection | 2 |
| 5. Dashboard Wiring | 4 |
| 6. Risk Integration | 2 |
| 7. KB Integration | 2 |
| 8. Polish | 1 |
| **Total** | **19 hours** |