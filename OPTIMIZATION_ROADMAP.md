# Algotrading Optimization Roadmap

## Gap Analysis + Actionable Plan Based on First-Principles Research

**Date:** 2026-05-15  
**Sources:** Kronos (AAAI 2026), QuantDinger v3, AI-Trader, ruflo-neural-trader, strategy_db (443 chunks), MoondevRED Engine, QuantDinger Agent API design, Pardo Walk-Forward Analysis, Kelly/Vince Optimal-f

---

## 1. CURRENT SYSTEM DIAGNOSIS

### What's Working
| Component | Status | Notes |
|-----------|--------|-------|
| Trailing stop | **Strong** | 83/84 winners, avg +5.99% | 
| Freqtrade infrastructure | **Stable** | Docker, Redis, PostgreSQL, Telegram alerts |
| TradingAgents (LangGraph) | **Functional** | 13 agents, 19 models, checkpoint/resume |
| Strategy DB (ChromaDB) | **Rich** | 443 strategy chunks, 34-field schema, 5 query modes |
| Circuit breaker | **Present** | 3-tier (15%/25%/40% drawdown thresholds) |
| Orchestration | **Working** | orchestrate.py wires FT + agents + risk + alerts |

### Critical Failures
| Problem | Evidence | Root Cause |
|---------|----------|------------|
| **AroonMomentum loses 80.4%** | 356-day backtest, 3x leverage | Stop-loss exits dominate (223/614 at -5.27% avg) while trailing stop works — the entry timing is wrong, not the exit |
| **Kelly f\* = -0.09** | Negative edge | The strategy has NO statistical edge at current parameters — any position sizing amplifies losses |
| **Ensemble loses -80.75%** | 356 days, 34.1% win rate | Multi-vote indicator consensus fails in crypto momentum regimes |
| **Risk is downstream** | DAG L6 → no edge from Risk → TradingAgents | Risk can only react after bad trades; can't prevent them |
| **No live feedback loop** | Freqtrade outcomes don't feed back to agents | Agents use same strategies regardless of performance |
| **3-model concurrent cap** | Ollama resource limit | LangGraph forced sequential, losing parallelism |

---

## 2. CROSS-PROJECT INTELLIGENCE

### 2.1 Kronos (AAAI 2026 — Foundation Model for Financial K-lines)
**What it does:** Pre-trained decoder-only transformer on 45+ global exchanges, converts OHLCV → hierarchical discrete tokens via Binary Spherical Quantization (BSQuantizer), then autoregressive prediction.

**Key innovations we can extract:**
- **Hierarchical tokenization**: OHLCV → 2-level quantization (s1_bits + s2_bits) preserves both trend and microstructure
- **Multi-scale context**: lookback_window=512, predict_window=48 (10% forward-looking)
- **Fine-tunable on custom data**: `finetune_csv/` pipeline with YAML configs, train_ratio=0.9/val=0.1
- **Built-in backtesting**: `KronosBacktester` class with Chinese-market data examples
- **Model sizes**: mini (4.1M params), small (24.7M), base (102.3M) — all run on consumer GPU

**Action:** Fine-tune Kronos-base on our AroonMomentum 1h crypto candles. Use its predictions as an upstream signal to TradingAgents, replacing or supplementing the current trend detection.

### 2.2 QuantDinger v3 (AI Quant Operating System)
**Key architectural patterns:**
- **Capability-based API security**: 5 risk classes (read-only → live execution), per-token permissions, kill switches
- **IndicatorStrategy (dataframe) → ScriptStrategy (event-driven)**: Start with vectorized signal research, graduate to bar-by-bar stateful execution only when needed
- **Agent persona framework**: P4 (external AI agent) + P5 (autonomous strategy AI) with least-privilege access
- **MCP integration**: The `mcp_server/` directory exposes quant capabilities as MCP tools
- **Strategy compiler**: Runtime strategy compilation from Python → executable

**Actions:**
1. Adopt QuantDinger's **risk classification model** for our circuit breaker tiers
2. Use the **IndicatorStrategy → ScriptStrategy graduation pattern** — currently all our strategies run at ScriptStrategy complexity without first validating at IndicatorStrategy level
3. Consider their MCP server pattern for exposing strategy_db queries as native MCP tools

### 2.3 AI-Trader (HKUDS — Agent-Native Trading Platform)
**Key patterns:**
- **Skill-driven agent registration**: Agents read a SKILL.md URL to auto-configure
- **3 signal types**: Strategy (discussion), Operation (copy-trade), Discussion (collaboration)
- **Market Intel layer**: `/api/market-intel/overview` → macro regime, ETF flows, featured stocks, grouped news
- **Polymarket integration**: Public data feeds for prediction markets
- **Copy-trading with kill switches**: Per-provider position sync with explicit opt-in

**Actions:**
1. Implement a **Market Intel layer** similar to AI-Trader's — our system has NO macro context (no VIX, no fear/greed, no ETF flow data)
2. Add a **signal-type taxonomy** — currently all TradingAgents outputs are treated equally; they should be tagged as conviction levels (discussion/operation/execution)

### 2.4 ruflo-neural-trader Plugin
**Key capabilities:**
- **6 specialized skills**: regime, risk, signal, train, portfolio, backtest
- **4 agent personas**: trading-strategist (opus), risk-analyst (sonnet), market-analyst (sonnet), backtest-engineer (sonnet)
- **Rust/NAPI backtest engine**: 8-19x faster than Python
- **Z-score anomaly detection**: spike, drift, flatline, oscillation, pattern-break, cluster-outlier
- **Walk-forward validation**: Built-in `--walk-forward` flag
- **Kelly + Half-Kelly + Vol-adjusted sizing**: Already implemented in the CLI

**Critical gap:** We have neural-trader available as a Ruflo plugin but it's NOT integrated into our Algotrading system. This is unused infrastructure.

**Actions:**
1. Install neural-trader npm package in the Algotrading environment
2. Wire `npx neural-trader --regime-detect` output to the TradingAgents signal bus
3. Replace our custom `position_sizer.py` with `npx neural-trader --position-sizing kelly`
4. Use `npx neural-trader --backtest --walk-forward` instead of Freqtrade's built-in backtester for validation

### 2.5 MoondevRED Engine
**9-layer architecture** with Claude/GPT strategy generators, but:
- Multiple RBI (RBIv1, v2, v3, PP) strategy variants → fragmentation, no unified evaluation
- Strategy generators produce code that's stored but not systematically compared
- No walk-forward or out-of-sample testing in the generator pipeline

### 2.6 Strategy DB (ChromaDB)
- 443 chunks from YouTube strategy content
- Hierarchical Router → Research → Synthesis agent pipeline (3-layer)
- LangChain integration with Ollama LLM
- **Gap:** The agent pipeline uses `deepseek-v4-flash:cloud` for classification but doesn't feed results back into strategy parameter optimization

---

## 3. ROOT CAUSE ANALYSIS

### Why AroonMomentum Loses Money (The 80.4% Problem)

```
Entry → WRONG TIMING (signal lag on 1h candles)
  ↓
Stop Loss → TRIGGERED TOO OFTEN (fixed 5.27% stop)
  ↓        [223/614 trades = 36.3% stopped out]
  ↓
Trailing Stop → WORKS when entry is right (83/84 winners)
  ↓
Net → NEGATIVE because stop-loss losses ($1,175 avg loss) exceed trailing gains (+5.99% avg win)
```

**The problem is NOT the exit strategy — it's the entry signal.** Aroon oscillator on 1h candles has too much lag for crypto volatility. Fixing position sizing or stop levels won't help until entries improve.

**Why Kelly is negative:** With 42.2% win rate and average loss exceeding average win on a risk-adjusted basis, there's no edge. Kelly says "don't trade this strategy."

---

## 4. OPTIMIZATION ROADMAP (5 Phases)

### PHASE 1: Stop the Bleeding (Week 1 — Immediate)

**Priority: CRITICAL — prevent further capital loss**

| # | Action | Implementation | Impact |
|---|--------|---------------|--------|
| 1.1 | **Disable AroonMomentum live trading** | Set `max_open_trades = 0` or remove from active config | Stops -80.4% losses immediately |
| 1.2 | **Switch Freqtrade to dry-run** | `dry_run: true` in config until Phase 2 validates | Zero capital at risk during optimization |
| 1.3 | **Activate circuit breaker watchdog** | `python3 scripts/circuit_breaker.py --watch` (already written, not running) | Prevents >40% drawdown |
| 1.4 | **Reduce leverage from 3x to 1x** | Edit `leverage_config.py` default from 3 to 1 | 3x leverage amplifies stop-loss damage by 3x |
| 1.5 | **Add upstream risk gate** | Add edge from Risk → TradingAgents in DAG (currently missing) | Stop agents from generating signals when regime is hostile |

**Expected result:** Capital decay stops. Risk-managed baseline restored.

### PHASE 2: Fix Entry Signals (Weeks 2-3)

**Priority: HIGH — the core problem**

| # | Action | Implementation | Impact |
|---|--------|---------------|--------|
| 2.1 | **Switch to higher-frequency candles** | Change from 1h → 15m, run AroonMomentum on 15m | Reduces signal lag from ~1h to ~15m |
| 2.2 | **Add Kronos prediction as confirmation filter** | Fine-tune Kronos-mini on our crypto OHLCV, use predict_window=12 as trend confirmation | ML confirmation reduces false entries |
| 2.3 | **Integrate neural-trader regime detection** | `npx neural-trader --regime-detect --symbol BTC/USDT` → fed into signal bus | Only enter trades in favorable regimes |
| 2.4 | **Implement multi-timeframe confirmation** | EMA trend on 4h + entry on 15m + Kronos prediction alignment | 3-layer confirmation eliminates whipsaws |
| 2.5 | **Add market intel layer** | Scrape fear/greed index, BTC dominance, total market cap into signal bus JSON | Macro context prevents counter-trend entries |

**Validation:** Walk-forward test (Pardo method) — optimize on 70% of data, test on 30%, shift forward. Require positive Kelly f* before going live.

### PHASE 3: Fix Position Sizing & Risk (Weeks 3-4)

**Priority: HIGH — sizing amplifies both wins and losses**

| # | Action | Implementation | Impact |
|---|--------|---------------|--------|
| 3.1 | **Replace custom position_sizer.py with Kelly-based sizing** | Use `npx neural-trader --position-sizing half-kelly` or implement Vince Optimal-f | Fractional Kelly prevents overbetting when edge is small |
| 3.2 | **Implement Regime-Adaptive Leverage** | Leverage = 1x in ranging, 2x in trending, 0x in volatile | Our MoondevRED engine has `dynamic_leverage.py` but it's not wired to regime detection |
| 3.3 | **Add inverse-volatility position weighting** | Already in `position_sizer.py` — WIRE IT INTO FREQTRADE CONFIG | Currently implemented but not connected |
| 3.4 | **Portfolio-level correlation monitor** | Use neural-trader `--correlation --portfolio current --flag-threshold 0.8` | Prevents opening 5 correlated long positions simultaneously |
| 3.5 | **Upstream risk gate (from DAG fix)** | Risk agent evaluates BEFORE TradingAgents generates signals | Current: risk only acts AFTER trade execution |

**Risk Management Hierarchy (from QuantDinger pattern):**
```
Layer 0: Strategy-Level Stop (per-trade, already exists)
Layer 1: Position Sizing (Kelly Half, vol-adjusted)
Layer 2: Regime Filter (only trade in favorable conditions)
Layer 3: Portfolio Correlation (prevent cluster risk)
Layer 4: Circuit Breaker (25% warning, 40% kill switch)
Layer 5: Upstream Gate (Risk → Agents, NOT downstream)
```

### PHASE 4: Ensemble & ML Integration (Weeks 4-6)

**Priority: MEDIUM — enhance once fundamentals are solid**

| # | Action | Implementation | Impact |
|---|--------|---------------|--------|
| 4.1 | **Hierarchical Ensemble (not flat vote)** | Weight indicators by regime: momentum weight in trending, mean-reversion weight in ranging | Current flat vote (MACD+RSI+Bollinger+Supertrend+ADX+DMI) fails because all vote equally regardless of market state |
| 4.2 | **Kronos prediction pipeline** | Fine-tune on 1h crypto → generate 48-candle forecasts → use as trend prior | Foundation model replaces lagging indicators for trend detection |
| 4.3 | **Kronos + TradingAgents feedback loop** | Kronos predictions → TradingAgents signal bus → Freqtrade executes → outcomes → ChromaDB → Kronos retraining | Closes the current open-loop where trade outcomes don't feed back |
| 4.4 | **Strategy DB → Strategy Generator** | MoondevRED-style generators query ChromaDB for similar setups, generate variant strategies with slight parameter shifts | Currently ChromaDB is read-only; generators should produce new strategies from DB patterns |
| 4.5 | **QuantDinger-style strategy graduation** | New strategies start as IndicatorStrategy (vectorized backtest) → graduate to ScriptStrategy (event-driven) only after walk-forward validation | Prevents untested strategies from going straight to live execution |

### PHASE 5: Infrastructure & Automation (Weeks 6-8)

**Priority: LOWER — sustain and scale**

| # | Action | Implementation | Impact |
|---|--------|---------------|--------|
| 5.1 | **AI-Trader-style market intel service** | Build `/api/market-intel/overview` equivalent — fear/greed, BTC dominance, ETF flows, macro regime | External context for all agent decisions |
| 5.2 | **MCP server for strategy DB** | Like QuantDinger's `mcp_server/`, expose ChromaDB queries as MCP tools | Makes strategy DB accessible to all agents natively |
| 5.3 | **Automated walk-forward validation pipeline** | TRAP system from `Trading_RESEARCH_PREVIEW_SYSTEM.md` — preview.py, estimate.py, backtest_query.py, walk_forward.py, dashboard.py | Systematic testing replaces ad-hoc backtests |
| 5.4 | **Signal confidence taxonomy** | Tag each TradingAgents output as Discussion/Operation/Execution (AI-Trader pattern) | Prevents low-confidence signals from executing with same weight as high-confidence |
| 5.5 | **neural-trader MCP bridge** | Add `neural-trader` MCP server to TradingAgents config: `claude mcp add neural-trader -- npx neural-trader mcp start` | 112+ tools available to all agents |
| 5.6 | **Rust/NAPI backtest acceleration** | Use neural-trader's Rust engine for strategy validation (8-19x faster) | Faster iteration = more strategies tested = better selection |

---

## 5. QUICK WINS (Do Today)

These can be implemented in under 1 hour each:

1. **Set `max_open_trades: 0`** on AroonMomentum config → stops live losses immediately
2. **Set `dry_run: true`** → zero risk during optimization  
3. **Change `leverage_config.py` default from 3 to 1** → stop amplifying losses
4. **Start circuit_breaker watchdog**: `python3 scripts/circuit_breaker.py --watch`
5. **Wire `position_sizer.py` into Freqtrade config** → it's written but not connected
6. **Add regime detection via neural-trader**: `npx neural-trader --regime-detect --symbol BTC/USDT`
7. **Change AroonMomentum timeframe from 1h to 15m** → reduce signal lag by 4x

---

## 6. KPIs & Success Criteria

| Metric | Current | Phase 2 Target | Phase 4 Target |
|--------|---------|---------------|---------------|
| Win rate | 42.2% | >50% | >55% |
| Kelly f* | -0.09 | >0.05 | >0.15 |
| Max drawdown | 81.5% | <25% | <15% |
| Avg win | +5.99% | +4% (faster exits) | +6% (better entries) |
| Avg loss | -5.27% | -2% (tighter stops + better entries) | -1.5% |
| Walk-forward OOS profit | Not tested | >0 | >10% annualized |
| Regime accuracy | N/A | >60% | >75% |

---

## 7. ARCHITECTURE CHANGES

### Current Flow (Broken)
```
TradingAgents → Signal Bus → Freqtrade → Execute → (no feedback loop)
                                  ↑
                        Risk Monitor (reactive, downstream)
```

### Proposed Flow
```
Kronos Predictions ──→ ┐
                        │
Market Intel ──────────→ │
                        │
Regime Detection ──────→ Signal Bus ──→ Risk Gate ──→ TradingAgents ──→ Freqtrade
                              ↑              │                                    │
                              │              └── BLOCK if regime hostile        │
                              │                                                  │
                              └──── Position Sizer (Half-Kelly) ←─────────────┘
                                            ↑                         │
                                  ChromaDB Strategy DB         Trade Outcomes
                                        ↑                           │
                                  Strategy Generator ←──────────────┘
                                   (from DB patterns)        Feedback Loop
```

### Key DAG Edges to Add
1. **Risk → TradingAgents** (upstream gate, blocks signals in hostile regime)
2. **Freqtrade Outcomes → ChromaDB** (closes feedback loop)
3. **ChromaDB → Strategy Generator** (pattern-driven strategy creation)
4. **Kronos → Signal Bus** (ML predictions as input)
5. **Market Intel → Risk Gate** (macro context for regime filter)

---

## 8. RESEARCH BACKED JUSTIFICATIONS

| Technique | Source | Evidence |
|-----------|--------|----------|
| Walk-forward validation | Pardo (1992, 2008) | "Gold standard" for strategy validation — our system has ZERO out-of-sample testing |
| Half-Kelly position sizing | Thorp (1969), Vince (1990) | Currently using 3x fixed leverage; Half-Kelly maximizes growth rate while minimizing ruin probability |
| Regime-adaptive leverage | Hull (2005), QuantDinger v3 | Fixed leverage is the #1 cause of drawdown amplification |
| Hierarchical tokenization | Kronos (AAAI 2026) | BSQuantizer preserves both trend and microstructure — better than flat indicators |
| Risk-as-upstream-gate | QuantDinger API design | Capability-based risk classes prevent execution, not just monitor after |
| Multi-timeframe confirmation | Pring (1991), Murphy (1999) | Single timeframe entries are the most common failure mode in systematic trading |
| Strategy graduation pipeline | QuantDinger IndicatorStrategy → ScriptStrategy | Prevents untested strategies from going to live execution |
| Signal confidence taxonomy | AI-Trader 3-tier model | Discussion → Operation → Execution, with kill switches at each tier |

---

## 9. FILES TO CREATE/MODIFY

| File | Action | Phase |
|------|--------|-------|
| `user_data/strategies/AroonMomentumEngine_Hybrid.py` | Change timeframe to 15m, add Kronos confirmation | 2 |
| `user_data/strategies/signal_bus_mixin.py` | Add regime filter, market intel, Kronos signals | 2 |
| `scripts/leverage_config.py` | Default 1x, regime-adaptive (1x/2x/0x) | 3 |
| `scripts/risk_management/position_sizer.py` | Connect to Freqtrade config, add Half-Kelly | 3 |
| `scripts/circuit_breaker.py` | Add upstream Risk → Agents gate | 1 |
| `scripts/market_intel_service.py` | NEW — fear/greed, BTC dominance, ETF flows | 4 |
| `scripts/kronos_bridge.py` | NEW — Kronos prediction → signal bus JSON | 4 |
| `scripts/neural_trader_bridge.py` | NEW — regime, risk, signal MCP bridge | 2 |
| `scripts/walk_forward_pipeline.py` | NEW — Pardo walk-forward validation (part of TRAP) | 4 |
| `strategy_db/mcp_server.py` | NEW — Expose ChromaDB as MCP tools | 5 |
| `TradingAgents/dag_config.py` | Add Risk → Agents upstream edge | 1 |
| `user_data/config_live_analysis.json` | `dry_run: true`, `max_open_trades: 0` | 1 |

---

*Generated from cross-project analysis of Kronos, QuantDinger v3, AI-Trader, ruflo-neural-trader, MoondevRED Engine, and strategy_db (443 chunks). All recommendations are grounded in the specific code artifacts, configs, and backtest data found in the system.*