# Unified Algotrading System — Architecture Plan v2

**Date:** 2026-05-19
**Approach:** First-principles analysis across 30+ reference projects
**Target:** Single unified system with Bloomberg-inspired Streamlit UI, ChromaDB learning, MCP data layer, NEXUS/RuFlo orchestration

---

## 1. Executive Summary

### What We're Building

A **single unified Trading Operating System** that replaces the current fragmented Algotrading project (90+ orphaned strategies, 5 docker-compose files, 3 signal daemons, no feedback loop, circuit breaker in PAUSE but ignored) with:

- **Bloomberg-inspired Streamlit UI** — professional terminal layout with real-time data, PnL charts, signal feed, and knowledge browser
- **MCP Data Layer** — 50+ financial tools (OHLCV, stock screening, TA, charts, SEC filings, macro data) via MCP protocol plugged into our existing Hermes/NEXUS infrastructure
- **Unified message bus** (Redis Pub/Sub + PostgreSQL) replacing JSON file fragmentation
- **ChromaDB vector knowledge loop** that learns from every trade outcome, stores strategy patterns, and continuously improves
- **NEXUS/RuFlo orchestration** managing a swarm of specialized agents with sub-agent parallelization
- **Live trading + backtesting** unified under one configuration

### Reference Projects Studied (30+)

#### Tier 1: Major (1,000+ stars)
| Project | Stars | Key Ideas |
|---------|-------|-----------|
| **OpenBB** | 67,741 | Financial data SDK, CLI, GUI. Data backbone for all instruments. |
| **Qlib (Microsoft)** | 42,000 | AI-oriented ML pipeline, supervised + RL, config-driven workflow |
| **Vibe-Trading (HKUDS)** | 7,600 | 74 skills, 29 swarm presets, 8 backtest engines, persistent memory, shadow accounts |
| **AI-Trader (HKUDS)** | — | Agent-native skills (SKILL.md), copy trading, WebSocket notifications |
| **Maestro** | 1,151 | "Bloomberg Terminal for CLI Agents." Agent-driven terminal architecture. |
| **Bloomberg Terminal Clone** | 1,263 | Closest visual Bloomberg clone. Redis caching for rate limits. |

#### Tier 2: Mid-Range (50–500 stars)
| Project | Stars | Key Ideas |
|---------|-------|-----------|
| **Rust-Finance** | 341 | Ultra-low-latency Rust daemon + AI agent. Future HFT layer reference. |
| **Financial Chat (wshobson)** | 231 | LangChain + OpenBB + Claude — financial chat pattern |
| **Equables** | 107 | Self-hosted alternative data (SEC filings, insider trading, congressional). Zero API dependency. |
| **Bloomberg Terminal Free** | 108 | Python CLI + local Llama 3. Most comparable to our stack. |
| **Astras Trading UI** | 84 | Professional broker terminal (Angular) |

#### Tier 3: Niche (< 50 stars)
| Project | Stars | Key Ideas |
|---------|-------|-----------|
| **Momentum MCP** | 19 | **P0 INTEGRATION.** Drop-in MCP server: stock screening, OHLCV, TA, charts, news. |
| **claude-code-trading-terminal** | 19 | Sub-agent parallelization across wallets. Risk overseer pattern. |
| **Sentinel-Lite** | 28 | Crypto terminal + SEC filings + market scanners |
| **QuantumTerminal** | 24 | Crypto Bloomberg-inspired dashboard + on-chain analytics |
| **Vibe-Sensei** | 18 | AI personas (Buffett, Soros) — advisor pattern for strategy KB |
| **Polyterminal** | 77/13 | Bloomberg for prediction markets |
| **MacroDashboard** | 10 | Self-hosted macro dashboard (Fed, economic indicators) → regime detection input |
| **TerminalQ** | 2 | 30 MCP financial tools |

#### Core (from earlier analysis)
| Project | Key Ideas |
|---------|-----------|
| **QuantDinger** (v3.0.3) | PostgreSQL schema, AI calibration, reflection worker, MCP server, multi-exchange |
| **Kronos** (AAAI 2026) | OHLCV foundation model, BSQ tokenizer, autoregressive forecasting |
| **pybroker** (1.2.13) | Numba backtesting, walkforward analysis, bootstrap metrics |
| **Algotrading (current)** | 90+ strategies, TradingAgents (LangGraph), MiroShark, HEdge, SignalBus |
| **NEXUS (current)** | FAISS routing, Thompson Sampling, Self-Reflection, 1097 resources, Coach |
| **RuFlo (current)** | Swarm orchestration, hooks pipeline |

---

## 2. First-Principles Data Flow

```
                    +===========================================+
                    |         SINGLE UNIFIED SYSTEM             |
                    +===========================================+

  EXTERNAL MCP TOOLS (50+ tools via MCP protocol)
  +-----------+  +------------+  +-----------+  +--------------+
  | Momentum  |  | Bloomberg  |  | TerminalQ |  | OpenBB       |
  | MCP       |  | MCP        |  | 30 tools  |  | SDK (67k st) |
  | (screen,  |  | (BDP/BDH/  |  | (quotes,  |  | (all asset   |
  |  TA, OHLCV)|  |  BDS/BQL)  |  |  earnings)|  |  classes)    |
  +-----------+  +------------+  +-----------+  +--------------+
       |               |              |               |
       v               v              v               v
  +===============================================================+
  |                   MCP / DATA LAYER                            |
  |  (unified data gateway — all sources → normalized format)     |
  +===============================================================+
       |
       v
  MARKET DATA --> SIGNAL GEN --> RISK GATE --> POSITION SIZING --> EXECUTION --> PnL
       |               |             |               |                |           |
       v               v             v               v                v           v
  +---------+   +----------+   +----------+   +------------+   +----------+   +--------+
  | Data    |   | Signal   |   | Risk     |   | Position   |   | F'trade  |   | PnL    |
  | Sources |-->| Bus      |-->| Gate     |-->| Sizer      |-->| Executor |-->| Tracker|
  |(CCXT,   |   |(Redis    |   |(Kelly,   |   |(Kelly,     |   |(CCXT)    |   |        |
  | OpenBB, |   | Pub/Sub) |   | Drawdown)|   | Fixed Frac)|   |          |   |        |
  | MCP)    |   |          |   |          |   |            |   |          |   |        |
  +----+----+   +----+-----+   +----+-----+   +-----+------+   +-----+----+   +---+----+
       |             |              |                |               |            |
       +-------------+--------------+----------------+---------------+------------+
                                              |
                                              v
                                   +----------------------+
                                   |  ChromaDB Vector     |
                                   |  Knowledge Base      |
                                   |  (learn from ALL     |
                                   |   outcomes)          |
                                   +----------------------+
                                              |
                                              v
                                   +----------------------+
                                   |  NEXUS / RuFlo       |
                                   |  Orchestration       |
                                   |  (agent swarm +      |
                                   |   sub-agent parallel)|
                                   +----------------------+
                                              |
                           +------------------+------------------+
                           |                                     |
                           v                                     v
                   +---------------+                   +------------------+
                   | Streamlit UI  |                   | Agent Terminal   |
                   | (Bloomberg-   |                   | (CLI/MCP for     |
                   |  inspired)    |                   |  Claude/GPT/etc) |
                   +---------------+                   +------------------+
```

**Core principle:** Every component is an agent communicating through Redis Pub/Sub. The MCP data layer gives us 50+ financial tools out of the box. ChromaDB stores all outcomes as vectors. NEXUS orchestrates agent swarms.

---

## 3. Architecture — Component Tree

```
algotrading_unified/
│
├── ui/                              # USER INTERFACE
│   ├── app.py                       # Streamlit entry (Bloomberg-inspired dark theme)
│   ├── pages/
│   │   ├── 00_Dashboard.py          # Live PnL, positions, risk overview [Bloomberg-style]
│   │   ├── 01_Backtest.py           # Run/compare backtests, walkforward results
│   │   ├── 02_Live_Trading.py       # Start/stop, monitor live trades
│   │   ├── 03_Strategies.py         # Strategy registry, enable/disable, compare
│   │   ├── 04_Risk_Manager.py       # Circuit breaker, Kelly, drawdown, tiers
│   │   ├── 05_Knowledge_Base.py     # ChromaDB browser, similarity search, patterns
│   │   ├── 06_MCP_Terminal.py       # MCP tool playground (query Momentum MCP, etc.)
│   │   ├── 07_Agent_Log.py          # NEXUS agent activity feed, swarm status
│   │   ├── 08_Macro.py              # Macro dashboard (Fed, econ indicators, regime)
│   │   └── 09_Settings.py           # API keys, config, DB management
│   └── components/
│       ├── trade_table.py           # Dark theme data table
│       ├── pnl_chart.py             # Real-time PnL with integrated volume
│       ├── strategy_card.py         # Strategy performance card
│       ├── signal_feed.py           # Scrolling real-time signal feed
│       ├── mcp_query.py             # MCP tool query widget
│       └── macro_panel.py           # Economic indicator panel
│
├── engine/                          # CORE TRADING ENGINE
│   ├── signal_bus.py                # Unified Redis Pub/Sub (replaces 7 JSON files)
│   ├── market_data.py               # Multi-source provider (CCXT, OpenBB, MCP, yfinance)
│   ├── strategy_runner.py           # Freqtrade-compatible strategy container
│   ├── position_tracker.py          # Real-time position + PnL across ALL strategies
│   ├── order_executor.py            # CCXT order execution with retry + fallback
│   └── backtest_runner.py           # Walkforward backtest (pybroker-style metrics)
│
├── agents/                          # AI AGENTS (NEXUS + RuFlo)
│   ├── signal_generators/           # Produce trading signals
│   │   ├── tradingagents_graph.py   # LangGraph multi-analyst (5 analysts + debate)
│   │   ├── miroshark_agent.py       # Composite scoring (regime + sentiment + outcome)
│   │   ├── kronos_agent.py          # OHLCV foundation model forecasting
│   │   └── mcp_momentum_agent.py    # Query Momentum MCP for screening signals
│   ├── risk_managers/              # Gate/approve trades — ENFORCED
│   │   ├── kelly_sizer.py           # Kelly Criterion position sizing
│   │   ├── circuit_breaker.py       # PHYSICALLY ENFORCED (not advisory)
│   │   ├── quantdinger_gate.py      # 5-tier risk classification
│   │   ├── hedge_coordinator.py     # Coordinates HEdge shared limits
│   │   └── sub_agent_overseer.py    # Oversees sub-agents (from claude-code-trading-terminal)
│   ├── analysts/                    # Analyze data
│   │   ├── market_regime.py         # Regime detection (HMM + macro input)
│   │   ├── sentiment_analyst.py     # News/social sentiment
│   │   ├── shadow_account.py        # Behavioral analysis (from Vibe-Trading)
│   │   ├── pattern_matcher.py       # ChromaDB similarity search
│   │   ├── macro_analyst.py         # Fed/econ indicator tracking (from MacroDashboard)
│   │   └── alt_data_analyst.py      # SEC filings, insider trading (from Equables)
│   └── learning/                    # Learn from outcomes
│       ├── reflection_worker.py     # Post-trade reflection (from QuantDinger)
│       ├── calibration_worker.py    # AI confidence calibration
│       ├── strategy_evolver.py      # Strategy mutation/optimization
│       └── kelly_updater.py         # Dynamic Kelly from trade history
│
├── mcp_layer/                       # MCP INTEGRATION
│   ├── mcp_client.py                # Universal MCP client
│   ├── momentum_mcp.py              # Momentum MCP wrapper (screening, TA, charts)
│   ├── terminalq_mcp.py             # TerminalQ wrapper (30 financial tools)
│   ├── bloomberg_mcp.py             # Bloomberg MCP wrapper (if API available)
│   └── mcp_registry.py              # Dynamic MCP tool discovery + routing
│
├── knowledge/                       # KNOWLEDGE & LEARNING
│   ├── chromadb_client.py           # ChromaDB wrapper
│   ├── vector_store.py              # Trade outcome vectors
│   ├── trade_memory.py              # Trade → vector encoding pipeline
│   ├── pattern_discovery.py         # Similar pattern detection
│   ├── mistake_learner.py           # Encode mistakes, query pre-trade
│   └── strategy_chromadb.py         # 443 YouTube chunk integration
│
├── nexus/                           # NEXUS ORCHESTRATION
│   ├── bridge.py                    # Bidirectional NEXUS ↔ trading engine
│   ├── skills/                      # Materialized trading skills
│   │   ├── strategy_selector.skill.md
│   │   ├── risk_monitor.skill.md
│   │   ├── backtest_runner.skill.md
│   │   ├── mcp_terminal.skill.md    # Skill: query 50+ MCP tools
│   │   ├── macro_analyst.skill.md   # Skill: analyze macro data
│   │   └── trade_auditor.skill.md
│   └── mcp_tools.py                 # MCP tools: trade_status, execute_backtest, etc.
│
├── swarm/                           # RuFlo SWARM
│   ├── presets/                     # Multi-agent team configs
│   │   ├── daily_committee.yaml     # CEO + analysts + risk debate
│   │   ├── crisis_response.yaml     # Emergency drawdown handling
│   │   ├── strategy_optimizer.yaml  # Multi-agent backtest optimization
│   │   ├── macro_scan.yaml          # Macro + alt data scan
│   │   └── sub_agent_trading.yaml   # Parallel sub-agents per pair
│   └── coordinator.py              # Swarm orchestrator
│
├── config/                          # SINGLE SOURCE OF TRUTH
│   ├── settings.py                  # Pydantic settings (env + file)
│   ├── strategies/                  # Active strategy definitions
│   ├── risk/                        # Risk parameters (Kelly, drawdown limits)
│   └── mcp_servers.yaml             # MCP server registrations
│
├── data/
│   ├── postgres/                    # PostgreSQL schema + migrations
│   └── chromadb/                    # ChromaDB persistent storage
│
├── docker-compose.yml               # Single compose (profiles: core/full/dev)
├── Dockerfile
├── MCP_SERVERS.md                   # How to add MCP data sources
└── run.sh                           # One command to start
```

---

## 4. Component Deep-Dive

### 4.1 MCP Data Layer (New — Biggest Addition)

**Pattern:** We have an existing Hermes agent that speaks MCP. Now we add **financial MCP servers** as first-class data sources.

```
NEXUS Agent
    |
    | MCP protocol
    v
+===================================+
|         MCP Registry             |
|  (discovers 50+ financial tools) |
+===================================+
    |         |           |
    v         v           v
Momentum   TerminalQ   Bloomberg
MCP        (30 tools)  MCP (18)
(screen,   (quotes,    (BDP/BDH/
 TA,       earnings,   BDS/BQL)
 OHLCV,    options)
 charts)
    |         |           |
    v         v           v
+===================================+
|     Normalized Data Bus          |
|  (all sources → Redis Pub/Sub)   |
+===================================+
```

**Priority MCP servers to install:**

| MCP Server | Tools | Integration | Value |
|------------|-------|-------------|-------|
| **Momentum MCP** | Stock screening, OHLCV, TA indicators, charts, financial news | 1 hour — drop-in | AI agent can screen stocks, compute TA, generate charts |
| **TerminalQ** | 30 tools: quotes, earnings calendar, options flow, AI analysis | 1 hour — drop-in | Broad coverage of terminal features |
| **Bloomberg MCP** | 18 Bloomberg API tools (BDP, BDH, BDS, BQL) | 1 hour — if we have terminal access | Professional data |

**How it works:**
```python
# mcp_layer/mcp_client.py
class McpDataGateway:
    """Unified gateway to all MCP data sources."""
    
    def __init__(self):
        self.servers = {
            "momentum": MomentumMcpClient(),
            "terminalq": TerminalQClient(),
            "bloomberg": BloombergMcpClient(available=False),
        }
    
    async def screen_stocks(self, criteria: dict) -> List[dict]:
        """Screen stocks using Momentum MCP."""
        return await self.servers["momentum"].call("screen_stocks", criteria)
    
    async def get_technical_indicators(self, symbol: str, indicators: List[str]):
        """Get TA from Momentum MCP."""
        return await self.servers["momentum"].call("get_technical_indicators", {
            "symbol": symbol, "indicators": indicators
        })
    
    async def get_macro_data(self, indicator: str):
        """Get macro data — routes to appropriate MCP server."""
        # Try TerminalQ first, fall back to OpenBB
        ...
```

### 4.2 Signal Bus (Redis Pub/Sub)

Replaces 7 JSON files with real-time pub/sub. Every component publishes and subscribes.

```python
class UnifiedSignalBus:
    CHANNELS = {
        "signal": "bus:signal",           # Trading signals (Buy/Sell/Hold)
        "regime": "bus:regime",           # Market regime
        "sentiment": "bus:sentiment",     # Sentiment scores
        "risk": "bus:risk",               # Risk gate decisions
        "position": "bus:position",       # Position updates
        "circuit_breaker": "bus:breaker", # Circuit breaker commands
        "mcp_data": "bus:mcp",            # MCP data feeds
        "macro": "bus:macro",             # Macro indicators
        "learning": "bus:learning",       # ChromaDB learning events
    }
    
    def publish(self, channel: str, data: dict):
        """Publish to Redis + persist to PostgreSQL."""
        
    def subscribe(self, channel: str, callback: Callable):
        """Subscribe with async callback — no polling."""
```

### 4.3 ChromaDB Knowledge Loop

```python
class ChromaDBKnowledgeLoop:
    """
    Every trade outcome → vector → ChromaDB → queried before next trade.
    This is the system's memory and learning mechanism.
    """
    
    COLLECTIONS = {
        "trade_outcomes": "All completed trades with features + outcome",
        "strategy_patterns": "443 YouTube strategy chunks",
        "mistake_library": "Encoded mistakes with context",
        "market_regimes": "Regime vector snapshots",
        "mcp_insights": "Interesting patterns from MCP data",
    }
    
    def learn_from_trade(self, trade: CompletedTrade):
        """Encode and store trade outcome."""
        vector = self._encode_trade(trade)
        self.chromadb.insert("trade_outcomes", vector, metadata={
            "strategy": trade.strategy_name,
            "pair": trade.pair,
            "pnl": trade.pnl,
            "win": trade.win,
            "regime": trade.regime,
        })
        # Also feed into NEXUS Thompson beliefs
        nexus.update_thompson(trade.strategy, trade.win)
    
    def query_before_trade(self, current_state: MarketState) -> AdviceResult:
        """Query similar historical situations before entering a trade."""
        similar = self.chromadb.query(
            "trade_outcomes",
            vector=self._encode_state(current_state),
            n_results=10,
            where={"strategy": current_state.strategy_name}
        )
        win_rate = sum(1 for t in similar if t.win) / len(similar)
        return AdviceResult(
            win_rate=win_rate,
            similar_trades=similar,
            recommendation="block" if win_rate < 0.4 else "proceed"
        )
```

### 4.4 Enforced Risk Gate

```python
class EnforcedRiskGate:
    """
    PHYSICALLY BLOCKS trades. Middleware between signal and execution.
    Cannot be bypassed — all orders must pass through this gate.
    """
    TIERS = {
        0: "NORMAL",      # Full trading
        1: "CAUTION",     # 75% position size
        2: "RESTRICTED",  # 50% position size, no shorts
        3: "HALT",        # No new entries (CURRENT STATE — -33% DD)
        4: "LIQUIDATE",   # Close all positions immediately
    }
    
    def gate(self, pair, side, amount, signal_data) -> TradeDecision:
        # 1. Circuit breaker (from Redis — not JSON file)
        breaker_state = signal_bus.read("bus:breaker")
        if breaker_state.tier >= 3:
            return TradeDecision.BLOCKED("Circuit breaker HALT")
        
        # 2. System-level drawdown (aggregate across ALL strategies)
        if self.system_drawdown > settings.MAX_DRAWDOWN:
            return TradeDecision.BLOCKED("System drawdown limit")
        
        # 3. ChromaDB pre-trade check
        advice = chromadb.query_before_trade(current_state)
        if advice.win_rate < 0.4:
            return TradeDecision.BLOCKED(f"ChromaDB: {advice.win_rate:.0%} WR in similar setups")
        
        # 4. Kelly position sizing
        kelly_fraction = kelly_sizer.compute(pair, strategy)
        
        # 5. Per-strategy risk limits (HEdge coordination)
        hedge_coordinator.check_limits(pair, amount)
        
        return TradeDecision.APPROVED(size=amount * kelly_fraction)
```

### 4.5 Sub-Agent Parallelization (from claude-code-trading-terminal)

```
┌──────────────────────────────────────────────┐
│            SubAgentOverseer                   │
│   (manages risk, allocates capital,           │
│    monitors all sub-agents)                   │
└────┬──────┬──────┬──────┬──────┬─────────────┘
     │      │      │      │      │
     v      v      v      v      v
   ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐
   │S1│  │S2│  │S3│  │S4│  │S5│   Sub-agents
   │  │  │  │  │  │  │  │  │  │   (one per pair/
   │  │  │  │  │  │  │  │  │  │    strategy combo)
   └──┘  └──┘  └──┘  └──┘  └──┘
   
   Each sub-agent:
   - Runs its own strategy
   - Has its own position limits
   - Publishes to signal bus independently
   - Reports to overseer for aggregate risk
```

### 4.6 Bloomberg-Inspired UI Layout

```
+=================================================================+
|  ALGOTRADING [LOGO]  | DASHBOARD | LIVE | BACKTEST | SETTINGS  |
+=================================================================+
| +----------+  +----------------------------------------------+  |
| | PORTFOLIO |  | CHART AREA (realtime PnL + price)          |  |
| | OVERVIEW  |  |                                              |  |
| |           |  |    / \    / \    / \    / \                 |  |
| | Bal: 12.4K|  |   /   \  /   \  /   \  /   \                |  |
| | Open: 3   |  |                                              |  |
| | PnL: +5.2%|  | [1D] [1W] [1M] [3M] [1Y] [MAX]            |  |
| | DD: -8.1% |  +----------------------------------------------+  |
| | Risk: CAU |  +----------------------------------------------+  |
| | Kelly:0.15|  | WATCHLIST / POSITIONS                        |  |
| | WR: 84.9% |  | BTC/USDT Long  2.3%  $1,200  [Close]       |  |
| |           |  | ETH/USDT Short  -0.8% $800   [Close]       |  |
| | TIER 1    |  | SOL/USDT Long   4.1%  $600   [Close]       |  |
| +----------+  +----------------------------------------------+  |
+=================================================================+
| SIGNAL FEED (realtime — scrolls)                                |
| 14:32:03  BUY  BTC/USDT  Ensemble: 4/6  Kelly: 0.15  Gate: OK  |
| 14:30:01  REGIME  Volatile  |  MACRO  Fed Rate: 4.50%          |
| 14:28:15  MCP  Screened 12 new setups from Momentum MCP        |
| 14:25:00  KNOWLEDGE  Pattern: High Vol + RSI<30 = 80% WR (12/15)|
| 14:22:30  SUB-AGENT  S3(ETH): Stopped — drawdown limit reached  |
+=================================================================+
| KNOWLEDGE PANEL (bottom)                                        |
| [ChromaDB] Similar to trade #204: lost -2.1R (same setup)      |
| [MCP] Momentum: AAPL RSI(14)=32, MACD bullish crossover        |
| [MACRO] Fed: +25bp expected Jun 15  |  CPI: 3.2% y/y          |
+=================================================================+
| STATUS BAR                                                      |
| Bus: OK | Redis: OK | ChromaDB: 1,442 vectors | MCP: 3 servers |
+=================================================================+
```

### 4.7 Learning System — Full Pipeline

```
                      +================================+
                      |      LEARNING PIPELINE          |
 TRADE COMPLETED -->  | 1. Encode as ChromaDB vector    |
                      | 2. Store in trade_outcomes      |
                      | 3. Update Kelly beliefs          |
                      | 4. Run QuantDinger reflection    |
                      | 5. Calibrate AI confidence       |
                      | 6. Update NEXUS Thompson beliefs |
                      | 7. Pattern discovery (cron)      |
                      | 8. Prune stale vectors           |
                      +===============+================+
                                      |
     +--------------------------------+--------------------------------+
     |                                |                                |
     v                                v                                v
+-----------+                 +---------------+                +---------------+
| ChromaDB  |                 | PostgreSQL    |                | NEXUS         |
| trade_outcomes (vectors)    | trade_history |                | Thompson      |
| strategy_patterns (443)     | pnl_snapshots |                | beliefs       |
| mistake_library             | kelly_history |                | reflections   |
| market_regimes              | config_audit  |                | coach scores  |
+-----------+                 +---------------+                +---------------+
```

---

## 5. Fixed Gaps from Audit Report

| # | Audit Gap | How Fixed | From Which Repo |
|---|-----------|-----------|-----------------|
| 1 | Circuit breaker PAUSE ignored | EnforcedRiskGate — physically blocks. Middleware. | Algotrading audit |
| 2 | SignalBusMixin is stub | UnifiedSignalBus via Redis. All components use it. | Algotrading audit |
| 3 | VDBMixin is stub | ChromaDBClient — first-class service, not mixin. | ChromaDB-native |
| 4 | Generated strategies orphaned | Strategy registry + one-click backtest UI. | Algotrading audit |
| 5 | VectorOmni variant bloat | Registry with version lineage. Prune. | Algotrading audit |
| 6 | Leverage: 3 sources | Single config/settings.py (Pydantic). | QuantDinger pattern |
| 7 | Config path fragmentation | All relative to project root. Single docker mount. | Algotrading audit |
| 8 | MiroShark not integrated | Registered as signal generator on bus. | Algotrading audit |
| 9 | TradingAgents: scorer only | Signal generator + risk gate must still approve. | Algotrading audit |
| 10 | HEdge no coordination | hedge_coordinator — shared position limits. | Algotrading audit |
| 11 | No system-level max drawdown | risk_gate aggregates ALL strategies. | Algotrading audit |
| 12 | QuantDinger not wired | Deployed as enforced risk gate agent. | QuantDinger |
| 13 | No NEXUS↔Freqtrade bridge | nexus/mcp_tools.py | NEXUS v3 |
| 14 | Trade outcomes → NEXUS | mistake_learner → Thompson beliefs. | NEXUS v3 |
| 15 | 31 algotrading skills DB only | Materialized as skill.md files. | NEXUS v3 |
| 16 | ChromaDB never queried | Queried BEFORE every trade. | ChromaDB-native |
| 17 | Stale signal detection | Redis TTL + heartbeat. Auto-disable. | Algotrading audit |
| 18 | 19 Docker definitions | Single docker-compose with profiles. | Algotrading audit |
| 19 | No monitoring | Streamlit dashboard + alerts. | Algotrading audit |
| 20 | No feedback loop | Every trade → vector → ChromaDB → queried. | Algotrading audit |
| 21 | No MCP data sources | mcp_layer/ with Momentum MCP + TerminalQ + Bloomberg MCP | Bloomberg research |
| 22 | No macro data | macro_analyst agent + MacroDashboard patterns | Bloomberg research |
| 23 | No sub-agent parallelism | SubAgentOverseer pattern | claude-code-trading-terminal |
| 24 | No alternative data | alt_data_analyst + Equables patterns | Equables |
| 25 | No agent terminal | MCP skills + CLI interface | Maestro |
| 26 | No data backbone | OpenBB SDK integration | OpenBB |

---

## 6. Migration Phases

### Phase 0: Immediate — Stop the Bleeding (Days 1-2)
1. **Circuit breaker enforcement** — Add EnforcedRiskGate. Block new entries. Current -33% DD is unacceptable.
2. **Single docker-compose.yml** — Collapse 19 Docker definitions into one.
3. **Install Momentum MCP** — Drop-in MCP server. Get stock screening + TA + charts as agent tools today.

### Phase 1: Foundation (Week 1)
- Project structure, Pydantic config
- `engine/signal_bus.py` — Redis Pub/Sub bus (replace 7 JSON files)
- `docker-compose.yml` — PostgreSQL + Redis + Streamlit + MCP servers
- `ui/app.py` — Bloomberg-inspired Streamlit skeleton (9 pages + dark theme)
- `mcp_layer/mcp_client.py` — Unified MCP gateway (Momentum MCP + TerminalQ)

### Phase 2: Consolidation (Week 2)
- Strategy registry — catalog 90+ strategies, enable/disable from UI
- Prune dead variants (VectorOmni: keep 2 best, generated: integrate top 10)
- Wire existing Freqtrade to signal bus
- `engine/backtest_runner.py` — walkforward backtest (pybroker-style)
- UI: Dashboard + Backtest + MCP Terminal pages

### Phase 3: ChromaDB Learning (Week 3)
- `knowledge/chromadb_client.py` — vector store
- `knowledge/trade_memory.py` — trade → vector encoder
- Post-trade hook: encode + store in ChromaDB
- Pre-trade hook: query ChromaDB, adjust decisions
- Integrate existing 443 YouTube strategy chunks
- UI: Knowledge Base page

### Phase 4: Risk Management (Week 4)
- `agents/risk_managers/` — all risk agents
- `EnforcedRiskGate` — middleware layer (cannot bypass)
- HEdge coordinator — shared position limits
- System max drawdown tracker
- Circuit breaker ENFORCEMENT (PAUSE = real halt)
- SubAgentOverseer — parallel sub-agent risk oversight
- UI: Risk Manager page

### Phase 5: NEXUS/RuFlo Integration (Week 5)
- Materialize 31 algotrading skills from NEXUS DB → disk
- `nexus/bridge.py` — bidirectional bridge
- `nexus/mcp_tools.py` — MCP tools (trade_status, execute_backtest, etc.)
- `swarm/presets/` — 5 team definitions
- Thompson beliefs ← trade outcomes
- Coach integration (already shipped — 65 tests)
- UI: Agent Log page

### Phase 6: AI Signal Generators + Macro (Week 6)
- Port TradingAgents to bus (LangGraph → Redis Pub/Sub)
- Port MiroShark composite scoring
- Integrate Kronos foundation model forecasting
- `macro_analyst` — Fed/econ indicator tracking
- `alt_data_analyst` — SEC filings, insider trading (Equables)
- UI: Live Trading + Macro pages

### Phase 7: Polish & Extend (Week 7)
- Integration tests for each pipeline stage
- Telegram/Discord alerts on critical events
- OpenBB SDK integration (full market data backbone)
- Documentation, one-command deploy
- Rollback: strategy versioning + revert capability

---

## 7. Repo Integration Map

| Repo | What We Use | Where It Goes |
|------|-------------|---------------|
| **Momentum MCP** (19 stars) | Stock screening, OHLCV, TA, charts, news as MCP tools | `mcp_layer/momentum_mcp.py`, `agents/mcp_momentum_agent.py` |
| **TerminalQ** (2 stars) | 30 financial tools (quotes, earnings, options) | `mcp_layer/terminalq_mcp.py` |
| **Bloomberg MCP** (8 stars) | 18 Bloomberg API tools (conditional) | `mcp_layer/bloomberg_mcp.py` |
| **Maestro** (1,151 stars) | Agent-driven terminal architecture patterns | Design reference for `nexus/skills/mcp_terminal.skill.md` |
| **OpenBB** (67,741 stars) | Data backbone for all asset classes | `engine/market_data.py` — OpenBB SDK as primary data source |
| **Equables** (107 stars) | Self-hosted alternative data pipeline | `agents/analysts/alt_data_analyst.py` |
| **MacroDashboard** (10 stars) | Fed, economic indicator tracking | `agents/analysts/macro_analyst.py`, `ui/pages/08_Macro.py` |
| **claude-code-trading-terminal** (19 stars) | Sub-agent parallelization pattern | `agents/risk_managers/sub_agent_overseer.py` |
| **QuantDinger** | PostgreSQL schema, AI calibration, reflection | `agents/learning/reflection_worker.py`, `agents/learning/calibration_worker.py` |
| **AI-Trader** | Agent-native SKILL.md pattern, WebSocket | `nexus/skills/*.skill.md`, UI WebSocket notifications |
| **Vibe-Trading** | Swarm DAG, 29 presets, shadow account, 74 skills | `swarm/presets/`, `agents/analysts/shadow_account.py` |
| **Kronos** | OHLCV foundation model, tokenizer | `agents/signal_generators/kronos_agent.py` |
| **pybroker** | Walkforward backtesting, bootstrap | `engine/backtest_runner.py` |
| **Qlib** | ML pipeline architecture, config-driven workflow | Design reference for data pipeline |
| **Algotrading (current)** | 90+ strategies, TradingAgents, MiroShark, HEdge, 443 ChromaDB chunks | Port active subset to new architecture |
| **NEXUS (current)** | FAISS routing, Thompson, reflection, 1097 resources, Coach | `nexus/bridge.py`, Thompson beliefs ← trade outcomes |
| **RuFlo (current)** | Swarm orchestration, hooks | `swarm/coordinator.py` |
| **Bloomberg Terminal Clone** (1,263 stars) | Redis caching pattern for rate limits | `engine/market_data.py` caching layer |
| **Bloomberg Terminal Free** (108 stars) | Local Llama 3 integration | Reference for local AI inference |
| **QuantumTerminal** (24 stars) | On-chain analytics patterns | Future: on-chain data agent |
| **Sentinel-Lite** (28 stars) | Crypto monitoring + SEC viewer | Future: crypto-specific monitoring |
| **Financial Chat** (231 stars) | LangChain + OpenBB + Claude | Reference for chat-based trading agent |

---

## 8. MCP Integration — Immediate Action Items

### Priority 0 — Install This Week
```bash
# Momentum MCP — drop-in MCP server for Claude Code
# Gives us: stock screening, OHLCV, TA indicators, charts, financial news
npm install -g @anthropic/mcp-client  # if needed
# Add to claude.json:
# {
#   "mcpServers": {
#     "momentum-mcp": {
#       "command": "npx",
#       "args": ["-y", "momentum-mcp"]
#     }
#   }
# }

# TerminalQ — 30 financial tools
# Add to claude.json:
# {
#   "terminalq": {
#     "command": "npx",
#     "args": ["-y", "terminalq"]
#   }
# }
```

### Priority 1 — Study Architecture
- Clone and read `Maestro` source — understand agent-driven terminal patterns
- Clone `Equables` — understand self-hosted alternative data pipeline
- Clone `claude-code-trading-terminal` — understand sub-agent pattern

### Priority 2 — SDK Integration
- Install and evaluate OpenBB SDK as primary data backbone
- Evaluate OpenBB Agents for multi-agent data workflows

---

## 9. Key Design Principles

1. **MCP-First Data Layer** — All external data comes through MCP protocol. 50+ tools available immediately.
2. **Everything is an Agent** — Strategies, risk managers, data fetchers all publish/subscribe to the message bus. No direct imports.
3. **Learn Before Every Decision** — Query ChromaDB before entering ANY trade. Block if win rate < 40%.
4. **Risk is Enforced, Not Advisory** — Risk gates sit BETWEEN signal and execution. Cannot be bypassed.
5. **Single Source of Truth** — One config (Pydantic). One bus (Redis). One DB (PostgreSQL + ChromaDB).
6. **Feedback Loop** — Every trade outcome → vector → ChromaDB → queried by future trades → improves.
7. **Parallel Sub-Agents** — Multiple strategy/pair combinations run in parallel, overseen by a risk coordinator.
8. **Progressive Migration** — Old system runs during migration. Component-by-component replacement.

---

## 10. Questions For You

1. **Architecture direction** — Does this v2 incorporating all 30+ Bloomberg terminal projects match what you envision?
2. **Start now?** — Phase 0 (circuit breaker enforcement, single docker-compose, Momentum MCP) can begin immediately.
3. **Bloomberg Terminal access?** — Do you have access to a Bloomberg Terminal? The Bloomberg MCP requires it.
4. **Priority** — Which matters most first: (a) stopping the -33% DD bleed, (b) getting MCP data tools working, or (c) building the Streamlit UI?
5. **OpenBB SDK** — Want me to evaluate OpenBB SDK as our primary data provider and add it to the architecture?
