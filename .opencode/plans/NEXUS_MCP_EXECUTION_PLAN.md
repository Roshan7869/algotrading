# NEXUS MCP Execution Plan — Phases 0–6

## Orchestration Architecture

Every phase is driven by **NEXUS as the orchestrator** — not by me manually coding. NEXUS spawns agents, routes skills, tracks state gates, verifies outputs, and reports outcomes for continuous learning.

```
NEXUS ORCHESTRATOR
│
├── nexus_design_plan()        → Creates typed DAG for phase
├── nexus_cluster_activate()   → Activates domain clusters (architect, devops_infra, quality_security)
├── nexus_find_skills()        → Routes task to matching skills
├── nexus_execute_phase()      → Executes phase via RuFlo agent swarm
├── nexus_verify_phase()       → Verifies output against state gates
├── nexus_update_state()       → Updates system state on completion
└── nexus_report_outcome()     → Reports outcome for Thompson learning
```

---

## Phase 0: Stop the Bleeding (Day 1–2)

### State Gates
```
PRE:  circuit_breaker.json exists AND is PAUSED
      broker_runtime is LIVE (freqtrade running)
      -33.21% monthly drawdown confirmed
POST: circuit_breaker PAUSE physically blocks entries
      docker-compose.yml collapsed to 1 file
      Momentum MCP installed and responding
```

### Task DAG (3 parallel agents)

```
                    ┌─────────────────────────────┐
                    │  nexus_design_plan(          │
                    │    task="Phase 0: emergency  │
                    │           circuit breaker",  │
                    │    project="trading"         │
                    │  )                          │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │  nexus_cluster_activate(     │
                    │    clusters="devops_infra,   │
                    │              quality_security│
                    │  )                          │
                    └──────────────┬──────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
            ▼                      ▼                      ▼
   Task 0.1                Task 0.2                Task 0.3
   Circuit Breaker         Single Compose          Momentum MCP
   Enforcement
            │                      │                      │
            ▼                      ▼                      ▼
   ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
   │ nexus_find_    │    │ nexus_find_    │    │ nexus_find_    │
   │ skills(        │    │ skills(        │    │ skills(        │
   │  "circuit      │    │  "docker       │    │  "mcp server   │
   │   breaker")    │    │   compose")    │    │   install")    │
   └───────┬────────┘    └───────┬────────┘    └───────┬────────┘
           │                    │                      │
           ▼                    ▼                      ▼
   ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
   │ nexus_auto_    │    │ nexus_auto_    │    │ nexus_auto_    │
   │ route(         │    │ route(         │    │ route(         │
   │  task="Create   │    │  task="Collapse│    │  task="Install  │
   │  EnforcedRisk- │    │  19 docker     │    │  Momentum MCP  │
   │  Gate.py that  │    │  files into   1│    │  as MCP server │
   │  blocks trades │    │  compose with  │    │  for Claude")  │
   │  during HALT")  │    │  profiles")    │    │                │
   └───────┬────────┘    └───────┬────────┘    └───────┬────────┘
           │                    │                      │
           ▼                    ▼                      ▼
   ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
   │ Agent creates: │    │ Agent creates:  │    │ Agent creates: │
   │ agents/risk_   │    │ docker-compose  │    │ MCP server     │
   │ managers/      │    │ .yml with       │    │ config in      │
   │ circuit_breaker│    │ profiles:       │    │ claude.json    │
   │ .py            │    │ core/full/dev   │    │                │
   │                │    │                 │    │                │
   │ Reads from:    │    │ Collapses:      │    │ Tests:         │
   │ bus:breaker    │    │ docker/ +       │    │ screen_stocks  │
   │ (Redis)        │    │ TradingAgents/  │    │ returns data   │
   │                │    │ .github/        │    │                │
   │ Writes to:     │    │                 │    │                │
   │ TradeDecision  │    │ Single mount:   │    │                │
   │ BLOCKED        │    │ ./user_data     │    │                │
   └───────┬────────┘    └───────┬────────┘    └───────┬────────┘
           │                    │                      │
           └────────────────────┼──────────────────────┘
                                │
                                ▼
                    ┌─────────────────────────────┐
                    │  nexus_verify_phase(         │
                    │    plan_id=P0,              │
                    │    phase_id="phase-0-stop"  │
                    │  )                          │
                    │  Checks:                    │
                    │  1. circuit_breaker.py      │
                    │     test_blocks_when_paused │
                    │     → PASS                  │
                    │  2. docker compose up -d    │
                    │     → 3 containers running  │
                    │  3. momentum-mcp screen     │
                    │     → AAPL data returned    │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │  nexus_update_state(         │
                    │    state_json='{"phase0":   │
                    │    "complete", "circuit_    │
                    │    breaker":"enforced",     │
                    │    "mcp":"momentum_online"}' │
                    │  )                          │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │  nexus_report_outcome(       │
                    │    skill_name="circuit-     │
                    │    breaker-enforcer",        │
                    │    outcome="correct",        │
                    │    project="trading"         │
                    │  )                          │
                    └─────────────────────────────┘
```

### NEXUS Calls for Phase 0

```python
# === STEP 1: Route task to skills ===
result = await nexus_find_skills(
    task="Create circuit breaker enforcer that blocks trades when PAUSED",
    project="trading"
)
# Returns: [{"name": "risk-manager", "confidence": 0.92}, ...]

skill = await nexus_get_skill("risk-manager")
# Injects the full skill instructions into the agent context

# === STEP 2: Create execution plan ===
plan = await nexus_design_plan(
    task="Phase 0: Emergency circuit breaker enforcement",
    project="trading"
)
# Returns plan_id="plan_p0"

# === STEP 3: Activate clusters ===
await nexus_cluster_activate(
    clusters="quality_security,devops_infra",
    project="trading"
)

# === STEP 4: Execute with agent swarm ===
await nexus_execute_phase(
    plan_id="plan_p0",
    phase_id="phase-0-stop"
)

# === STEP 5: Verify ===
verification = await nexus_verify_phase(
    plan_id="plan_p0",
    phase_id="phase-0-stop"
)
# Returns: {"passed": True, "checks": {...}}

# === STEP 6: Update state ===
await nexus_update_state(
    state_json='{"phase0":"complete","circuit_breaker":"enforced","mcp":"momentum_online"}'
)

# === STEP 7: Learn from outcome ===
await nexus_report_outcome(
    skill_name="circuit-breaker-enforcer",
    outcome="correct",
    project="trading",
    task_summary="Phase 0: circuit breaker now physically blocks trades during PAUSE"
)
```

---

## Phase 1: Foundation (Week 1)

### State Gates
```
PRE:  phase0 = complete
POST: Redis Pub/Sub bus operational (publish/subscribe/read)
      MCP gateway routes to Momentum MCP + TerminalQ
      Streamlit skeleton renders all 9 pages
      All tests pass (bus CRUD, MCP discovery, UI load)
```

### Task DAG

```
                     Phase 0 complete
                           │
                           ▼
                  nexus_design_plan("Phase 1")
                  nexus_cluster_activate("architect,devops_infra")
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
       Task 1.1        Task 1.2        Task 1.3
    Redis Bus         MCP Gateway     Streamlit UI
    (2 days)          (1 day)          (3 days)
            │              │              │
            ▼              ▼              ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ nexus_find_  │ │ nexus_find_  │ │ nexus_find_  │
    │ skills(      │ │ skills(      │ │ skills(      │
    │  "redis bus  │ │  "mcp        │ │  "streamlit  │
    │   pub/sub")  │ │  gateway")   │ │  dashboard") │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           ▼                ▼                ▼
    ┌─────────────────────────────────────────────────┐
    │           PARALLEL AGENT EXECUTION               │
    │                                                  │
    │ Agent 1.1a: engine/signal_bus.py                 │
    │   - UnifiedSignalBus class (publish/subscribe/   │
    │     read/is_stale/list_channels)                 │
    │   - Redis Pub/Sub + PostgreSQL persistence       │
    │   - TTL-based staleness detection                │
    │   - Tests: pub/sub/read/stale/failover           │
    │                                                  │
    │ Agent 1.1b: Demo script                          │
    │   - python -c "from engine.signal_bus import *"  │
    │   - Publish test signal                          │
    │   - Subscribe and verify delivery                │
    │   - Kill Redis, verify PG fallback                │
    │                                                  │
    │ Agent 1.2: mcp_layer/mcp_client.py               │
    │   - McpDataGateway class                         │
    │   - Server registry (momentum, terminalq)        │
    │   - Tool discovery + normalization               │
    │   - Fallback chain between servers               │
    │   - Tests: discover/route/fallback               │
    │                                                  │
    │ Agent 1.3: ui/ streamlit skeleton                │
    │   - app.py with dark Bloomberg theme             │
    │   - 9 pages: Dashboard, Backtest, Live,          │
    │     Strategies, Risk, Knowledge, MCP Terminal,   │
    │     Agent Log, Macro, Settings                   │
    │   - Reusable components (trade_table, pnl_chart, │
    │     signal_feed, mcp_query)                      │
    │   - Plotly charts, ag-grid tables                │
    └─────────────────────────────────────────────────┘
                           │
                           ▼
                  nexus_verify_phase()
                  Checks:
                  1. bus.publish("test",{x:1}) + bus.read("test") == {x:1}
                  2. bus.is_stale("test", max_age=0) == True
                  3. mcp_gateway.screen_stocks({"market":"crypto"}) returns list
                  4. streamlit loads all 9 pages without errors
                  5. all 20+ tests pass
                           │
                           ▼
                  nexus_update_state({"phase1":"complete","bus":"redis_online"})
                  nexus_report_outcome(skill_name="signal-bus-architect", outcome="correct")
```

### NEXUS MCP Workflow for Phase 1

```python
# === Phase 1: Foundation ===

# 1. Design the plan
p1 = await nexus_design_plan("Phase 1: Foundation - Redis bus, MCP gateway, Streamlit UI", "trading")

# 2. Activate relevant clusters
await nexus_cluster_activate("architect,devops_infra")

# 3. Execute Task 1.1: Signal Bus (parallel agents)
await nexus_execute_phase(plan_id=p1, phase_id="phase-1-bus")

# 4. Verify bus
v1 = await nexus_verify_phase(plan_id=p1, phase_id="phase-1-bus")
assert v1["passed"]

# 5. Execute Task 1.2: MCP Gateway
await nexus_execute_phase(plan_id=p1, phase_id="phase-1-mcp")

# 6. Execute Task 1.3: Streamlit UI (parallel to MCP)
await nexus_execute_phase(plan_id=p1, phase_id="phase-1-streamlit")

# 7. Final verification
v_all = await nexus_verify_phase(plan_id=p1, phase_id="phase-1-all")
if v_all["passed"]:
    await nexus_update_state({"phase1":"complete","bus":"redis_online"})
    await nexus_report_outcome("signal-bus-architect", "correct", "trading")
```

---

## Phase 2: Consolidation (Week 2)

### State Gates
```
PRE:  phase1 = complete, bus = online
POST: Strategy registry catalogs all 90+ strategies
      Dead variants pruned (VectorOmni: keep 2, archive 7)
      Freqtrade wired to signal bus
      Walkforward backtest runner operational
      UI Dashboard + Backtest pages functional
```

### Task DAG

```
                    nexus_design_plan("Phase 2: Consolidation")
                    nexus_cluster_activate("architect,quality_security")
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
       Task 2.1          Task 2.2          Task 2.3
    Strategy           Wire Freqtrade     Backtest Runner
    Registry           to Bus             (pybroker-style)
    (2 days)           (2 days)           (2 days)
            │                │                │
            ▼                ▼                ▼
    ┌─────────────────────────────────────────────────┐
    │ Agent 2.1a: Build strategy registry             │
    │   - Scan user_data/strategies for *.py files    │
    │   - Run quick backtest on each (1 month)        │
    │   - Generate config/strategies/registry.yaml    │
    │     with: name, path, status, sharpe, wr, dd    │
    │   - Mark active/archived based on metrics       │
    │                                                │
    │ Agent 2.1b: Prune dead variants                 │
    │   - Compare all 9 VectorOmni backtests          │
    │   - Keep best 2, archive 7                      │
    │   - Compare 52 generated strategies              │
    │   - Integrate top 10 into registry, archive 42  │
    │   - Deduplicate kronos_indicators.py            │
    │                                                │
    │ Agent 2.2: engine/strategy_runner.py            │
    │   - Adapter wrapping Freqtrade strategy         │
    │   - populate_entry_trend → bus.read() signals   │
    │   - Each entry → risk_gate.gate()               │
    │   - Each exit → knowledge.learn_from_trade()    │
    │   - Replace AroonMomentumEngine_Hybrid default   │
    │                                                │
    │ Agent 2.3: engine/backtest_runner.py            │
    │   - Walkforward analysis (N windows, M periods) │
    │   - pybroker-style: Sharpe, Sortino, DD, CAGR   │
    │   - Bootstrap confidence intervals on metrics   │
    │   - UI integration on Backtest page             │
    └─────────────────────────────────────────────────┘
                             │
                             ▼
                    nexus_verify_phase()
                    Checks:
                    1. registry.yaml has all strategies with status
                    2. Freqtrade reads signals from bus (not JSON files)
                    3. backtest_runner.run("ensemble", "2025-01", "2026-01") returns valid metrics
                    4. old JSON signal files: no new writes in 24h
                    nexus_update_state({"phase2":"complete","freqtrade":"bus_wired"})
```

---

## Phase 3: ChromaDB Learning (Week 3)

### State Gates
```
PRE:  phase2 = complete, freqtrade wired to bus
POST: ChromaDB learn+query cycle operational
      Pre-trade hook blocks trades when WR < 40%
      443 YouTube chunks integrated and queryable
      Post-trade reflection writes to NEXUS Thompson beliefs
      UI Knowledge Base page functional
```

### Task DAG

```
                    nexus_design_plan("Phase 3: ChromaDB Learning")
                    nexus_cluster_activate("architect,analyzer_planner")
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
       Task 3.1          Task 3.2          Task 3.3
    ChromaDB Client     Pre-trade Hook     443 Chunks
    + Trade Encoder     + Post-trade       Integration
    (2 days)            Reflection          (1 day)
            │                │                │
            ▼                ▼                ▼
    ┌─────────────────────────────────────────────────┐
    │ Agent 3.1: knowledge/                           │
    │   - chromadb_client.py: PersistentChromaDB      │
    │   - vector_store.py: Collection management      │
    │   - trade_memory.py: Trade → vector encoder     │
    │   - Encodes: regime, strategy, signal features,  │
    │     risk params, market conditions, outcome     │
    │   - Collections: trade_outcomes, mistake_library│
    │   - Tests: learn+query+recall accuracy          │
    │                                                │
    │ Agent 3.2: Integration hooks                    │
    │   - Pre-trade: encode current state → query     │
    │     ChromaDB → BLOCK if WR<40%                  │
    │   - Post-trade: encode outcome → store vector   │
    │   - Also: feed win/loss into NEXUS Thompson     │
    │     beliefs for continuous learning             │
    │   - Tests: hook blocks on low-confidence setups  │
    │                                                │
    │ Agent 3.3: Existing ChromaDB integration        │
    │   - Load strategy_db/chromadb (443 chunks)      │
    │   - Create strategy_patterns collection          │
    │   - Pre-trade: find similar strategy patterns   │
    │   - UI: browse + search + similarity view       │
    └─────────────────────────────────────────────────┘
                             │
                             ▼
                    nexus_verify_phase()
                    Checks:
                    1. learn(trade) → query(similar_state) returns trade in results
                    2. pre_trade_hook(WIN_RATE=0.3) → BLOCKED
                    3. pre_trade_hook(WIN_RATE=0.8) → APPROVED
                    4. chromium query returns YouTube chunks
                    5. Thompson beliefs updated after each trade
                    nexus_update_state({"phase3":"complete","chromadb":"online"})
```

---

## Phase 4: Risk Management (Week 4)

### State Gates
```
PRE:  phase3 = complete, chromadb = online
POST: EnforcedRiskGate physically blocks/caps all trades
      HEdge coordinator manages shared position limits
      System max drawdown enforced across ALL strategies
      Circuit breaker PAUSE = real halt (verified)
      SubAgentOverseer manages parallel sub-agents
      UI Risk Manager page functional
```

### Task DAG

```
                    nexus_design_plan("Phase 4: Risk Management")
                    nexus_cluster_activate("quality_security,architect")
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
       Task 4.1          Task 4.2          Task 4.3
    Enforced           HEdge              SubAgent
    Risk Gate          Coordinator        Overseer
    (2 days)           (1 day)            (1 day)
            │                │                │
            ▼                ▼                ▼
    ┌─────────────────────────────────────────────────┐
    │ Agent 4.1: agents/risk_managers/                │
    │   - circuit_breaker.py: reads bus:breaker       │
    │     TIER 0-4 enforcement                        │
    │   - kelly_sizer.py: dynamic Kelly from trade    │
    │     history + ChromaDB                          │
    │   - quantdinger_gate.py: 5-tier classification  │
    │   - EnforcedRiskGate: middleware that ALL       │
    │     orders pass through.                        │
    │     Gate check order:                           │
    │     1. Breaker state (tier >= 3 → BLOCK)        │
    │     2. System drawdown (> max → BLOCK)           │
    │     3. ChromaDB query (WR < 40% → BLOCK)        │
    │     4. Kelly sizing (cap position)              │
    │     5. HEdge limits (shared position check)     │
    │                                                │
    │ Agent 4.2: agents/risk_managers/               │
    │   hedge_coordinator.py                         │
    │   - Shared position tracker for 9 HEdge strats  │
    │   - Limits: max combined trades=5, max exposure │
    │   - If Meta7in1 has 4 open → block champion     │
    │                                                │
    │ Agent 4.3: agents/risk_managers/               │
    │   sub_agent_overseer.py                        │
    │   - Tracks aggregate risk across sub-agents     │
    │   - Stops any sub-agent hitting drawdown limit  │
    │   - Reports to bus:risk for UI display          │
    │   - Pattern from claude-code-trading-terminal   │
    └─────────────────────────────────────────────────┘
                             │
                             ▼
                    nexus_verify_phase()
                    Checks:
                    1. set breaker=HALT → all trade decisions return BLOCKED
                    2. HEdge Meta7in1 has 4 open → champion trade returns BLOCKED
                    3. system_drawdown > limit → all strategies BLOCKED
                    4. ChromaDB WR=0.2 → BLOCKED with reason
                    5. Sub-agent reaches DD limit → overseer stops it
                    6. UI Risk Manager page shows all tiers + limits
                    nexus_update_state({"phase4":"complete","risk_gate":"enforced"})
```

---

## Phase 5: NEXUS/RuFlo Integration (Week 5)

### State Gates
```
PRE:  phase4 = complete, risk_gate = enforced
POST: 31 algotrading skills materialized on disk
      nexus/bridge.py connects NEXUS ↔ trading engine
      MCP tools: trade_status, execute_backtest, adjust_config
      5 swarm presets operational
      Thompson beliefs updated from trade outcomes
      Coach integration feeding from trade data
      UI Agent Log page functional
```

### Task DAG

```
                    nexus_design_plan("Phase 5: NEXUS/RuFlo Integration")
                    nexus_cluster_activate("analyzer_planner,architect")
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
       Task 5.1          Task 5.2          Task 5.3
    Materialize         NEXUS Bridge      Swarm Presets
    31 Skills           + MCP Tools       (5 YAML files)
    (1 day)             (2 days)          (1 day)
            │                │                │
            ▼                ▼                ▼
    ┌─────────────────────────────────────────────────┐
    │ Agent 5.1: nexus/skills/*.skill.md              │
    │   - Read 31 records from nexus.db resource table│
    │   - Write each to .skill.md file on disk        │
    │   - Register with NEXUS routing                 │
    │   - Skills include:                             │
    │     strategy_selector, risk_monitor,            │
    │     backtest_runner, mcp_terminal,              │
    │     macro_analyst, trade_auditor,               │
    │     market_regime, sentiment_analyst,           │
    │     portfolio_optimizer, etc.                   │
    │                                                │
    │ Agent 5.2: nexus/bridge.py + mcp_tools.py       │
    │   - nexus/bridge.py bidirectional bridge       │
    │     NEXUS → Trading: 3 MCP tools                │
    │       trade_status() → positions, PnL, risk     │
    │       execute_backtest(s,p) → metrics           │
    │       adjust_config(k,v) → bool                 │
    │     Trading → NEXUS: 2 feedback paths           │
    │       feed_outcome_to_nexus(trade) → Thompson   │
    │       coach.record_outcome(trade) → Coach scores│
    │                                                │
    │ Agent 5.3: swarm/presets/                       │
    │   - daily_committee.yaml: CEO + 3 analysts      │
    │   - crisis_response.yaml: emergency drawdown    │
    │   - strategy_optimizer.yaml: 3 agents compare   │
    │   - macro_scan.yaml: macro + alt data           │
    │   - sub_agent_trading.yaml: parallel overseer   │
    └─────────────────────────────────────────────────┘
                             │
                             ▼
                    nexus_verify_phase()
                    Checks:
                    1. ls nexus/skills/*.skill.md returns 31 files
                    2. nexus_find_skills("risk monitor") returns risk_monitor skill
                    3. trade_status() MCP call returns real positions
                    4. execute_backtest("ensemble",...) returns metrics
                    5. Thompson belief updates after trade outcome fed back
                    6. All 5 swarm presets load without YAML errors
                    nexus_update_state({"phase5":"complete","nexus_bridge":"online"})
```

---

## Phase 6: AI Signal Generators + Macro (Week 6)

### State Gates
```
PRE:  phase5 = complete, nexus_bridge = online
POST: TradingAgents LangGraph publishes to bus
      MiroShark composite scoring publishes to bus
      Kronos foundation model forecasting on bus
      Macro analyst tracking Fed/econ indicators
      Alternative data agent (SEC, insider trading)
      UI Live Trading + Macro pages functional
      All signal generators go through risk gate
```

### Task DAG

```
                    nexus_design_plan("Phase 6: AI Signal Generators")
                    nexus_cluster_activate("analyzer_planner,architect")
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
       Task 6.1          Task 6.2          Task 6.3
    Port Trading-       Port MiroShark    Kronos + Macro
    Agents to Bus       + Vibe Shadow     + Alt Data
    (2 days)            (2 days)          (2 days)
            │                │                │
            ▼                ▼                ▼
    ┌─────────────────────────────────────────────────┐
    │ Agent 6.1: agents/signal_generators/            │
    │   tradingagents_graph.py                        │
    │   - Read TradingAgents graph (LangGraph)        │
    │   - Wrap as bus agent: subscribe to market      │
    │     data channel → run analyst debate →         │
    │     publish signal to bus:signal                │
    │   - 5 analysts: market, sentiment, news,        │
    │     fundamentals, mirofish                      │
    │   - CEO manager + CRO manager + 3 debaters     │
    │   - B3 bonus scorer → final rating              │
    │   - ALL signals go through EnforcedRiskGate     │
    │                                                │
    │ Agent 6.2: agents/signal_generators/           │
    │   miroshark_agent.py + shadow_account.py       │
    │   - MiroShark: composite score from regime +   │
    │     sentiment + outcome + agents + breaker      │
    │   - Publish to bus:signal every cycle          │
    │   - Shadow account: behavioral analysis from   │
    │     broker journal (Vibe-Trading pattern)       │
    │                                                │
    │ Agent 6.3: agents/signal_generators/ + agents/ │
    │   analysts/                                     │
    │   - kronos_agent.py: load Kronos-mini model    │
    │     (4.1M params, CPU), subscribe to market     │
    │     data, publish OHLCV forecasts to bus        │
    │   - macro_analyst.py: track Fed, CPI, GDP,     │
    │     unemployment → publish to bus:macro        │
    │   - alt_data_analyst.py: SEC filings, insider  │
    │     trades, congressional trades (Equables     │
    │     pattern) → publish to bus:signal           │
    └─────────────────────────────────────────────────┘
                             │
                             ▼
                    nexus_verify_phase()
                    Checks:
                    1. TradingAgents signal appears on bus:signal
                    2. MiroShark composite score publishes
                    3. Kronos forecast returns valid OHLCV predictions
                    4. Macro analyst correctly identifies Fed rate regime
                    5. Alt data analyst returns real SEC filing data
                    6. ALL signals BLOCKED when risk gate tier >= 3
                    nexus_update_state({"phase6":"complete","all_agents":"online"})
```

---

## Phase 7: Polish & Extend (Week 7)

### State Gates
```
PRE:  phase6 = complete, all_agents = online
POST: Monitoring alerts on critical events (Telegram/Discord)
      Integration tests pass for entire pipeline
      OpenBB SDK integrated as data backbone
      Documentation complete
      One-command deploy: docker compose --profile full up -d
      Rollback capability: strategy versioning + revert
```

### Task DAG

```
                    nexus_design_plan("Phase 7: Polish & Extend")
                    nexus_cluster_activate("quality_security,devops_infra")
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
       Task 7.1          Task 7.2          Task 7.3
    Monitoring         Integration        Documentation
    + Alerts           Tests              + OpenBB
    (1 day)            (2 days)           (2 days)
            │                │                │
            ▼                ▼                ▼
    ┌─────────────────────────────────────────────────┐
    │ Agent 7.1: Monitoring                            │
    │   - Telegram bot for alerts                      │
    │   - Discord webhook for position updates         │
    │   - Alerts on:                                   │
    │     • Circuit breaker tripped                    │
    │     • Drawdown breach (> -15%, -20%, -25%)       │
    │     • Stale signals (bus TTL expired)            │
    │     • Strategy failure (3 consecutive losses)    │
    │     • NEXUS agent crash                          │
    │                                                │
    │ Agent 7.2: Integration tests                    │
    │   - End-to-end: data → bus → risk → exec → PnL  │
    │   - Bus failover: Redis down → PG fallback      │
    │   - Risk gate: all tiers block correctly         │
    │   - ChromaDB: learn → query → accuracy ≥ 95%    │
    │   - MCP: all 50+ tools discoverable             │
    │   - NEXUS bridge: bidirection comms work        │
    │                                                │
    │ Agent 7.3: OpenBB + docs                        │
    │   - Integrate OpenBB SDK as primary data source │
    │   - Fallback chain: OpenBB → CCXT → yfinance    │
    │   - strategy versioning (git tags per deploy)   │
    │   - Rollback script: git revert + docker down   │
    │   - One-command deploy docs                     │
    └─────────────────────────────────────────────────┘
                             │
                             ▼
                    nexux_verify_phase()
                    nexus_audit_plan()
                    All checks pass across all 7 phases
                    Complete system operational
                    nexus_add_learning_note(note=..., project="trading")
```

---

## Combined Orchestration Script

```python
# EXECUTION ORCHESTRATOR
# This is the master script that NEXUS runs to execute all 7 phases

async def execute_unified_platform():
    """Orchestrate all 7 phases using NEXUS MCP tools."""
    
    design = await nexus_design_plan(
        "Build unified algotrading platform: bus → risk → chromadb → nexus → agents",
        "trading"
    )
    
    outcomes = []
    
    for phase_def in [
        ("phase-0-stop",     "quality_security,devops_infra"),
        ("phase-1-foundation","architect,devops_infra"),
        ("phase-2-consolidate","architect,quality_security"),
        ("phase-3-learning",  "architect,analyzer_planner"),
        ("phase-4-risk",      "quality_security,architect"),
        ("phase-5-nexus",     "analyzer_planner,architect"),
        ("phase-6-agents",    "analyzer_planner,architect"),
        ("phase-7-polish",    "quality_security,devops_infra"),
    ]:
        phase_id, clusters = phase_def
        
        # Precondition check
        pre = await nexus_check_preconditions(phase_id)
        if not pre["met"]:
            print(f"Preconditions not met for {phase_id}: {pre['missing']}")
            break
        
        # Activate clusters for this phase
        await nexus_cluster_activate(clusters, "trading")
        
        # Execute
        result = await nexus_execute_phase(plan_id=design, phase_id=phase_id)
        
        # Verify
        verification = await nexus_verify_phase(plan_id=design, phase_id=phase_id)
        
        if verification["passed"]:
            # Update state gates
            status_key = phase_id.replace("-", "_")
            await nexus_update_state({status_key: "complete"})
            
            # Log success
            outcomes.append({"phase": phase_id, "status": "passed"})
            await nexus_report_outcome(f"{phase_id}", "correct", "trading")
        else:
            # Log failure + find alternatives
            outcomes.append({"phase": phase_id, "status": "failed"})
            await nexus_report_outcome(f"{phase_id}", "wrong", "trading")
            alternatives = await nexus_find_alternatives_on_failure(
                phase_id, f"Phase {phase_id} verification failed", "trading"
            )
            print(f"Alternatives: {alternatives}")
            break
    
    # Final audit
    await nexus_audit_plan(plan_id=design)
    
    # Record learning
    await nexus_add_learning_note(
        note=f"Unified platform build complete. {sum(1 for o in outcomes if o['status']=='passed')}/{len(outcomes)} phases passed.",
        project="trading",
        task_type="build",
        tools="nexus,ruflo,mcp,chromadb"
    )
    
    return outcomes
```

---

## NEXUS Hallucination Gate

Every phase verifies tool calls before execution:

```python
# Before executing any agent's tool call:
await nexus_hallucination_gate(
    tool_name=proposed_tool,
    active_set_json=json.dumps(tier1_tools + tier2_tools)
)
# If tool is hallucinated (not in active set) → REJECT
```

---

## Learning from Each Phase

Every phase outcome feeds back into NEXUS Thompson Sampling:

```
Phase N complete
      │
      ▼
nexus_report_outcome(skill, "correct"/"wrong", project="trading")
      │
      ▼
Thompson Sampling updates belief distribution for that skill
      │
      ▼
Next time a similar task is routed:
  - Skills that passed get higher Thompson alpha
  - Skills that failed trigger Self-Reflection + alternative search
  - Cluster affinities adjust (which clusters are most useful)
```

---

## Summary: NEXUS MCP Tools Used

| Tool | Usage |
|------|-------|
| `nexus_design_plan` | Create typed DAG for each phase |
| `nexus_execute_phase` | Execute phase via agent swarm |
| `nexus_verify_phase` | Verify output against state gates |
| `nexus_audit_plan` | Full audit after all phases complete |
| `nexus_find_skills` | Route each task to matching skills |
| `nexus_get_skill` | Load skill instructions into agent context |
| `nexus_cluster_activate` | Activate relevant domain clusters per phase |
| `nexus_update_state` | Update global state gates after phase |
| `nexus_check_preconditions` | Verify state gates before phase |
| `nexus_report_outcome` | Report outcome for Thompson learning |
| `nexus_hallucination_gate` | Reject hallucinated tool calls |
| `nexus_find_alternatives_on_failure` | Find alternatives when phase fails |
| `nexus_add_learning_note` | Persist learnings from the build |

Total: **12 NEXUS MCP tools** orchestrate the full execution across **7 phases**, **~20 parallel agents**, **~40 files created**, all with verification gates, rollback points, and automatic learning feedback.
