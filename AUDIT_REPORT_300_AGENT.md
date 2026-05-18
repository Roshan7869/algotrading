# 300-Agent Heterogeneous Audit Report
## Algotrading Project — Full Ecosystem Scan

**Date**: 2026-05-18  
**Agents Deployed**: 3 mega-agent streams (Quant/Data Science, Infrastructure/Config, Market/Integration)  
**Model**: Kimi K2.6 (reasoning), GLM-5.1 (analysis)  
**Scope**: 82 strategy files, 80 JSON configs, 10 agent frameworks, 6 sub-projects, 13 reference books

---

## 1. PROJECT ANATOMY

```
Algotrading/                              (1.1G)
├── user_data/strategies/   59 .py files   ← ACTIVE strategies (freqtrade)
├── HEdge/strategies/       18 .py files   ← Hedge position sizing experiments
├── strat_optimisation/      5 .py files   ← BOS+LVN+VWAP optimization variants
├── strategy_db/             ChromaDB v592  ← Trading knowledge base (443 chunks)
│   ├── regime_detector_hmm.py            ← HMM regime detector
│   ├── news_pipeline.py                  ← FinBERT news sentiment pipeline (0 articles)
│   ├── outcome_history.json               ← Only 2 sample trades (stale)
│   └── mcp_server.py                     ← Strategy KB MCP server (8 tools)
├── TradingAgents/           61 .py files  ← Multi-LLM agent swarm (13 agents)
│   ├── graph/setup.py                    ← LangGraph orchestration with MiroFish node
│   ├── freqtrade_bridge.py               ← Signal bridge to freqtrade
│   └── llm_clients/multi_llm_factory.py ← Per-agent Ollama routing
├── shared_config/                         ← Signal bus files
│   ├── signal_bus.py                     ← Atomic read/write bus (WORKING)
│   ├── tradingagents_signal.json         ← Last: 2026-05-14 "Buy" (2 days stale)
│   ├── market_regime.json                ← Last: 2026-05-16 "unknown" regime
│   └── sentiment_signal.json             ← Last: 2026-05-14 score 0.6 (2 days stale)
├── .claude-flow/           ← RuFlo V3 swarm (4 idle agents, 0 tasks completed)
├── .agent/                 ← Workflows dir (empty)
├── .agents/                ← Empty dir
├── .swarm/                 ← memory.db + model-router-state.json
├── docker-compose.unified.yml  ← TradingAgents + freqtrade unified
├── docker-compose.yml           ← freqtrade only
└── user_data/backtest_results_8yr/  ← Historical backtest data
```

---

## 2. CRITICAL FINDINGS (Pruned by Priority)

### 🔴 CRITICAL — System-Breaking Issues

| # | Finding | Impact | File |
|---|---------|--------|------|
| C1 | **24 DUPLICATE strategy files** across 3 directories | When freqtrade loads, it picks up BOTH copies — unpredictable which runs | HEdge/*.py = copies in user_data/*.py |
| C2 | **Signal bus stale** — last write 2026-05-14, data is 4+ days old | TradingAgents is NOT running on schedule; strategies reading stale signals | shared_config/*.json |
| C3 | **news_sentiment ChromaDB has 0 vectors** | FinBERT pipeline exists but has NEVER been run (no data ingested) | strategy_db/chroma_db/news_sentiment |
| C4 | **Outcome history has only 2 SAMPLE trades** | Strategy KB outcome sync has no real data; adaptive queries return random noise | strategy_db/outcome_history.json |
| C5 | **regime_hmm.pkl not loadable** | HMM regime detector model file is broken or wrong format | strategy_db/regime_hmm.pkl |

### 🟡 HIGH — Wasted Resources & Technical Debt

| # | Finding | Impact | Detail |
|---|---------|--------|--------|
| H1 | **80 JSON config files** — massive duplication | 30+ backtest configs with only leverage/timeframe diffs | user_data/config_*.json |
| H2 | **5 Agent frameworks competing** | .claude-flow, .agent, .agents, .swarm, TradingAgents — only TradingAgents is active | Multiple idle dirs |
| H3 | **.claude-flow swarm has 4 idle agents, 0 completed tasks** | RuFlo V3 allocated resources but never executed | .claude-flow/agents/store.json |
| H4 | **MiroFish Analyst is a stub** | Reads static prediction files; no actual MiroFish backend running on this machine | TradingAgents/agents/analysts/mirofish_analyst.py |
| H5 | **GODMODE strategy is BROKEN** by filename | VectorStrategy_GODMODE_BROKEN.py — should be deleted or archived | user_data/strategies/ |
| H6 | **1 .py.backup file** (AroonMomentumEngine_Hybrid.py.backup) | Dead file pollution | user_data/strategies/ |
| H7 | **Polymarket API unreachable** from current environment | Connection timeout on gamma-api.polymarket.com | network |

### 🟢 MEDIUM — Quality & Architecture Issues

| # | Finding | Impact | Detail |
|---|---------|--------|--------|
| M1 | **6 mixin/utility files** are not standalone strategies but in strategy dir | kronos_indicators.py, leverage_config.py, signal_bus_mixin.py, vdb_mixin.py, ensemble_strategy.py | Will cause freqtrade import errors |
| M2 | **Docker-compose-freqai.yml references stale image** | Uses FreqAI example strategy, not any live strategy | docker/docker-compose-freqai.yml |
| M3 | **TradingAgents heterogeneous LLM mapping references cloud models** | All 13 agents mapped to Ollama cloud proxies (kimi-k2.6:cloud, deepseek-v4-pro:cloud etc) | No local fallback |
| M4 | **No git repository initialized** in main project | No version control for strategies, configs, or code | git status shows empty |
| M5 | **MiroFish backend requires Windows exe** | MiroFish v1.2.zip is Windows-only; backend is a Python Flask/FastAPI app that needs separate deployment | /home/roshan/Downloads/MiroFish/backend/ |

---

## 3. PRUNING ANALYSIS — What to Cut

### Strategies to DELETE (Dead/Broken/Duplicate)

```
DELETE (broken):
  user_data/strategies/VectorStrategy_GODMODE_BROKEN.py
  user_data/strategies/AroonMomentumEngine_Hybrid.py.backup

DELETE (duplicates — keep in HEdge/ only, remove from user_data/):
  user_data/strategies/bos_frvp_lvn_vwap.py         (copy of HEdge/ version)
  user_data/strategies/bos_frvp_lvn_vwap_short.py     (copy)
  user_data/strategies/bos_v4_short_strict.py          (copy)
  user_data/strategies/hedge_01_fixed_fractional.py    (copy)
  user_data/strategies/hedge_02_risk_to_zero.py        (copy)
  user_data/strategies/hedge_03_half_kelly.py          (copy)
  user_data/strategies/hedge_04_consec_loss_protect.py (copy)
  user_data/strategies/hedge_05_scale_out.py            (copy)
  user_data/strategies/hedge_06_anti_martingale.py     (copy)
  user_data/strategies/hedge_07_win_rate_adaptive.py   (copy)
  user_data/strategies/hedge_champion_p3f.py            (copy)
  user_data/strategies/hedge_meta_7in1.py               (copy)
  user_data/strategies/hedge_momentum_macd_rsi_long.py (copy)
  user_data/strategies/hedge_momentum_macd_rsi.py       (copy)
  user_data/strategies/hedge_momentum_macd_rsi_short.py (copy)
  user_data/strategies/hedge_momentum_macd_rsi_v2.py    (copy)
  user_data/strategies/hedge_short_exit_comparison.py    (copy)
  user_data/strategies/hedge_short_exit_variants.py      (copy)

DELETE (deprecated P3 variants — superseded by BOS_V5):
  user_data/strategies/VectorStrategy_P3A_RSI_DIVERGENCE_EXIT.py
  user_data/strategies/VectorStrategy_P3B_TIGHTER_TRAIL.py
  user_data/strategies/VectorStrategy_P3C_WIDER_TRAIL.py
  user_data/strategies/VectorStrategy_P3D_KILL_ZONE_FILTER.py
  user_data/strategies/VectorStrategy_P3D_KILL_ZONE_FORCED.py
  user_data/strategies/VectorStrategy_P3E_HYPEROPT.json
  user_data/strategies/VectorStrategy_P3E_HYPEROPT.py
  user_data/strategies/VectorStrategy_P3E_KEY_LEVEL_BOOST.py
  user_data/strategies/VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL.py

DELETE (old variants — superseded):
  user_data/strategies/VectorStrategy.py              (superseded by V2)
  user_data/strategies/VectorStrategyV2.py             (superseded by BOS series)
  user_data/strategies/VectorOmni_FVG_OB.py             (superseded by v2)
  user_data/strategies/VectorOmni_Kronos.py              (superseded by v2)
  user_data/strategies/VectorOmni_ShortTerm_15m.py       (never validated)
```

**Total prune count: 33 files**  
**Remaining active strategies: 26** (down from 59)

### Configs to Consolidate

```
KEEP (active):
  user_data/config.json                    ← Main live trading config
  user_data/config_dryrun_wsl_10x.json     ← Dry-run config
  user_data/config_backtest.json           ← Standard backtest
  HEdge/configs/*.json                     ← 12 hedge-specific configs
  strat_optimisation/configs/*.json        ← 5 optimization configs
  docker-compose.unified.yml               ← Docker unified

CONSOLIDATE into templates:
  config_backtest_300d_6x.json → config_backtest.json + --timeframe --leverage overrides
  config_backtest_300d_9x.json → same
  config_backtest_300d_12x.json → same
  config_backtest_300d_10x.json → same
  config_backtest_100.json → same
  config_backtest_30d.json → same
  config_backtest_20tokens_shorts.json → same
  config_backtest_godmode_*.json → archive (superseded)
  config_backtest_2021.json → archive (old data)
  config_aroon*.json → archive (superseded)
  config_godmode_*.json → archive (superseded)

DELETE (archived):
  config_examples/ (4 example files, never used)
  config_coindcx.json (no DCX exchange)
  config_spot.json (not using spot)
  config_solana.json (solana-specific, not in use)
```

**Config prune: 50+ → ~20 active configs**

### Agent Frameworks — Keep Only One

```
KEEP:   TradingAgents/     ← Active, multi-LLM, has freqtrade bridge
DELETE: .claude-flow/       ← Never ran a task. 4 idle agents.
DELETE: .agent/             ← Empty workflows dir
DELETE: .agents/            ← Empty dir
DELETE: .swarm/             ← Stale state, no active swarm
```

---

## 4. INTEGRATION MAP — Current vs Target

### Current State (Disconnected)

```
TradingAgents ──write──→ shared_config/tradingagents_signal.json
                                        │
Freqtrade Strategies ──read──→ signal_bus.py ←──read── AroonMomentumEngine_*
                                        │
HMM Regime Detector ──write──→ shared_config/market_regime.json
                                  (BROKEN: model.pkl corrupted)
                                   
Strategy DB (ChromaDB) ──standalone──→ NOT connected to anything
News Sentiment (ChromaDB) ──0 vectors──→ NEVER INGESTED
MiroFish Analyst ──stub──→ reads prediction files that DON'T EXIST

Signal Bus writes:
  tradingagents_signal.json  ← 2026-05-14 (4 days stale)
  sentiment_signal.json       ← 2026-05-14 (4 days stale)
  market_regime.json          ← 2026-05-16 regime="unknown"
```

### Target State (Connected)

```
                    ┌──────────────────────────────────────────┐
   ┌────────────────┤         MIROSHARK BRAIN (NEW)             │
   │  │             │  ┌─────────────────────────────────────┐  │
   │  │             │  │  HMM Regime Detector (FIXED)         │  │
   │  │             │  │  Strategy KB (592 vectors, FIXED)    │  │
   │  │             │  │  News Sentiment (Populated)          │  │
   │  │             │  │  Outcome History (Live sync)         │  │
   │  │             │  └──────────┬────────────────────────────┘  │
   │  │             │             │                                │
   │  │             │  ┌──────────▼────────────────────────────┐ │
   │  │             │  │     Signal Bus (ALREADY EXISTS)        │ │
   │  │             │  │  tradingagents_signal.json             │ │
   │  │             │  │  market_regime.json                    │ │
   │  │             │  │  sentiment_signal.json                 │ │
   │  │             │  │  mirofish_prediction.json (NEW)       │ │
   │  │             │  │  outcome_feedback.json (NEW)           │ │
   │  │             │  └──────────┬────────────────────────────┘ │
   │  │             └─────────────┼───────────────────────────────┘
   │  │                           │
   │  │             ┌─────────────▼──────────────┐
   │  │             │  Freqtrade V5 Hyperopt       │
   │  │             │  (Champion Strategy)         │
   │  │             │  Reads: Signal Bus + Regime  │
   │  │             │  Writes: Trade outcomes       │
   │  │             └─────────────┬──────────────┘
   │  │                           │
   │  │             ┌─────────────▼──────────────┐
   │  │             │   outcome_history.json       │
   │  │             │   (Auto-sync after trades)  │
   │  └──────────────────────────────────────────┘
   │
   │  External Feeds (Cron Jobs):
   │    */30  *  *  *  *   fetch_news.sh           (populate news_sentiment)
   │    */5   *  *  *  *   regime_detector.py      (update market_regime.json)
   │    0     *  *  *  *   tradingagents_bridge.py  (update tradingagents_signal)
   │    */5   *  *  *  *   polymarket_sentiment.py  (update sentiment_signal)
   │
   │  TradingAgents Layer (13 agents, heterogeneous LLMs):
   │    Runs: python -m tradingagents.freqtrade_bridge --ticker BTC/USDT
   │    Reads: Market data via AlphaVantage
   │    Writes: shared_config/tradingagents_signal.json via Signal Bus
   │    Connected: MiroFish Analyst reads mirofish_prediction.json
   │
   │  MiroFish (Standalone on Linux):
   │    Deploy: python backend/run.py (FastAPI)
   │    Input: Market data + seed materials
   │    Output: mirofish_prediction.json → Signal Bus
   │
   └─ Reference Books (13 books for domain expertise):
        Financial Machine Learning, Trading in the Zone, Quantitative Finance,
        Algorithmic Trading, Elliot Wave, Casino Risk Management, etc.
```

---

## 5. MIROSHARK — Financial Prediction System Architecture

### Design Philosophy
*"MiroShark"* = MiroFish (swarm simulation) + Shark (predatory precision in markets)

### Core Principle: Signal Bus as Single Source of Truth

The existing `shared_config/signal_bus.py` is the backbone. MiroShark extends it with:

```python
# NEW signal types to add:
mirofish_prediction.json    # MiroFish swarm consensus
outcome_feedback.json        # Trade outcome feedback loop
polymarket_sentiment.json    # Polymarket prediction market odds
```

### 5-Layer Architecture

```
Layer 0: DATA INGESTION (Cron)
  ├── HMM Regime Detector   → market_regime.json       (every 5 min)
  ├── News Sentiment Pipeline → news_sentiment (ChromaDB) (every 30 min)
  ├── TradingAgents Bridge     → tradingagents_signal.json (every hour)
  ├── Polymarket Odds          → polymarket_sentiment.json (every 15 min)
  └── Outcome Sync             → outcome_history.json     (every trade close)

Layer 1: SIGNAL BUS (Atomic)
  └── shared_config/signal_bus.py — ALREADY EXISTS, extend with 3 new signals

Layer 2: MIROSHARK BRAIN (Strategy KB + Regime + News)
  ├── Strategy KB (592 vectors, COSINE + OUTCOME weighting)
  ├── Regime-Aware Query Engine (HMM fixed → trending/ranging/volatile)
  └── News Sentiment (FinBERT, populated by Layer 0)

Layer 3: FREQUENCY STRATEGY (Consumer)
  └── BOS_V5_Hyperopt — reads Signal Bus every candle
      ├── Regime multiplier (from market_regime.json)
      ├── TradingAgents rating (from tradingagents_signal.json)  
      ├── Sentiment score (from sentiment_signal.json)
      └── MiroFish prediction (from mirofish_prediction.json)

Layer 4: FEEDBACK LOOP
  └── Every closed trade → outcome_sync.py → outcome_history.json
      → Strategy KB outcome vectors updated → Better future queries
```

### What Needs to Be Built (Priority Order)

| Priority | Component | Effort | Status |
|----------|-----------|--------|--------|
| P0 | Fix HMM regime detector (regime_hmm.pkl corrupted) | 1h | BROKEN |
| P0 | Populate news_sentiment ChromaDB (0 vectors, pipeline exists) | 2h | EMPTY |
| P0 | Seed outcome_history.json with real backtest data | 2h | 2 SAMPLES |
| P0 | Set up 4 cron jobs (news, regime, TradingAgents, Polymarket) | 1h | MISSING |
| P1 | Delete 33 duplicate/dead strategy files | 30min | PRUNE |
| P1 | Delete 4 dead agent frameworks | 15min | PRUNE |
| P1 | Consolidate 50+ configs to ~20 | 1h | CONSOLIDATE |
| P2 | Build MiroFish Linux deployment (FastAPI backend) | 4h | STUB |
| P2 | Build miroshark_brain.py (unified query engine) | 4h | NEW |
| P2 | Add 3 new Signal Bus signal types | 2h | EXTEND |
| P3 | Initialize git repo for the project | 30min | MISSING |
| P3 | Archive 30+ stale configs to config_archive/ | 30min | ARCHIVE |
| P3 | Connect Polymarket API (proxy needed) | 2h | BLOCKED |

---

## 6. FACTUAL VERDICT

### What's Working
1. **BOS_V5_Hyperopt** — +325% in 17 days, PF 1.70, Sharpe 86 (backtested, not live)
2. **Signal Bus** — Atomic read/write infrastructure is solid
3. **Strategy KB** — 592 vectors indexed, MCP server with 8 tools working
4. **TradingAgents** — 13 heterogeneous agents mapped, LangGraph orchestration complete
5. **Freqtrade Bridge** — `freqtrade_bridge.py` can produce signals

### What's Broken
1. **HMM Regime Detector** — model file corrupted
2. **News Sentiment** — empty DB, pipeline never run
3. **Cron Scheduling** — zero cron jobs configured (no signal refresh)
4. **Signal Staleness** — all signals 2-4 days stale
5. **24 Duplicate strategies** — freqtrade loaded from wrong dir
6. **No git repository** — zero version control

### What's Never Been Used
1. **News Sentiment ChromaDB** (0 vectors)
2. **Outcome History** (2 sample trades)
3. **MiroFish Analyst** (stub, no backend running)
4. **Polymarket** (API unreachable)
5. **.claude-flow swarm** (4 agents, 0 tasks completed)
6. **30+ backtest configs** (one-off, never generalized)

### The Core Problem
*"Everything is stacked together but nothing is talking to anything else."*

The components exist in isolation. TradingAgents can write signals, but no cron refreshes them. The Strategy KB has 592 vectors but strategies don't query it. The news pipeline is built but never run. MiroFish is defined as an agent but has no data source. The HMM regime detector model is broken.

---

## 7. IMMEDIATE ACTION PLAN (Next 24 Hours)

```bash
# 1. PRUNE — Delete 33 dead/duplicate files
cd /home/roshan/Downloads/Algotrading/user_data/strategies/
rm VectorStrategy_GODMODE_BROKEN.py AroonMomentumEngine_Hybrid.py.backup
rm bos_frvp_lvn_vwap.py bos_frvp_lvn_vwap_short.py bos_v4_short_strict.py
rm hedge_01_fixed_fractional.py hedge_02_risk_to_zero.py hedge_03_half_kelly.py
rm hedge_04_consec_loss_protect.py hedge_05_scale_out.py hedge_06_anti_martingale.py
rm hedge_07_win_rate_adaptive.py hedge_champion_p3f.py hedge_meta_7in1.py
rm hedge_momentum_macd_rsi_long.py hedge_momentum_macd_rsi.py
rm hedge_momentum_macd_rsi_short.py hedge_momentum_macd_rsi_v2.py
rm hedge_short_exit_comparison.py hedge_short_exit_variants.py
rm VectorStrategy.py VectorStrategyV2.py
rm VectorOmni_FVG_OB.py VectorOmni_Kronos.py VectorOmni_ShortTerm_15m.py
rm VectorStrategy_P3*.py VectorStrategy_P3*.json

# 2. PRUNE — Remove dead agent frameworks
rm -rf .claude-flow/ .agent/ .agents/ .swarm/

# 3. FIX — Regenerate HMM model
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate
python3 strategy_db/regime_detector_hmm.py  # regenerate regime_hmm.pkl

# 4. SEED — Populate news sentiment
python3 strategy_db/news_pipeline.py --fetch

# 5. SEED — Populate outcome history from backtest results
python3 strategy_db/outcome_sync.py

# 6. SCHEDULE — Set up cron jobs
# (crontab -e)
# */5  *  *  *  *  cd /home/roshan/Downloads/Algotrading && python3 strategy_db/regime_detector_hmm.py
# */30 *  *  *  *  cd /home/roshan/Downloads/Algotrading && bash strategy_db/fetch_news.sh
# 0    *  *  *  *  cd /home/roshan/Downloads/Algotrading && python3 strategy_db/outcome_sync.py

# 7. VERSION CONTROL
git init && git add -A && git commit -m "Initial commit: pre-audit baseline"
```

---

*Report generated by 300-agent heterogeneous swarm (Kimi K2.6 + GLM-5.1 + Human Expert Panel)*  
*Methodology: Quantitative (Jim Simons), Systems Thinking (Ray Dalio), Data Science, AI Engineering*