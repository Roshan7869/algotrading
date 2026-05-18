# Cross-Project Intelligence Report

**Date:** 2026-05-15  
**Analyzed:** Kronos, QuantDinger v3, AI-Trader, ruflo-neural-trader, MoondevRED Engine, Strategy DB

---

## 1. Kronos (AAAI 2026 — Foundation Model for Financial K-lines)

**Repo:** https://github.com/Roshan7869/Kronos  
**Cloned to:** /tmp/analysis/Kronos

### Architecture
- **Model:** Decoder-only transformer (GPT-2 style) with Binary Spherical Quantization (BSQuantizer)
- **Tokenization:** OHLCV → 2-level hierarchical discrete tokens (s1_bits + s2_bits)
  - Level 1: Macro trend (up/down/flat)
  - Level 2: Microstructure patterns within each macro state
- **Sizes:** mini (4.1M params), small (24.7M), base (102.3M) — all runnable on consumer GPU
- **Context window:** lookback=512 candles, predict=48 candles forward (10% forward ratio)

### Key Components
| File | Purpose |
|------|---------|
| `model/kronos.py` | Core model: KronosForPrediction with BSQuantizer, hierarchical tokenization |
| `model/config.py` | Model configs: KronosConfig with s1_bits, s2_bits, lookback_window, predict_window |
| `finetune_csv/` | Fine-tuning pipeline: YAML configs per dataset, train_ratio=0.9/val=0.1 |
| `backtest/` | KronosBacktester class with Chinese market examples |
| `data/` | DataLoader: OHLCV → tokenized sequences, multi-exchange support |

### Fine-tuning Pipeline
```yaml
# Example config structure (config_ali09988_candle5)
model_size: base
train_ratio: 0.9
val_ratio: 0.1
lookback_window: 512
predict_window: 48
learning_rate: 2.0e-4
batch_size: 64
epochs: 3
```

### Actionable Takeaways for Algotrading
1. **Fine-tune Kronos-base on our 1h crypto OHLCV** (BTC, ETH, SOL, RENDER, PEPE) — replaces lagging indicators for trend detection
2. **Use predict_window=12** (3 hours of 15m candles) as confirmation filter for AroonMomentum entries
3. **Hierarchical tokenization concept**: Our strategy should differentiate macro trend (4h+) from micro entry (15m) — this is exactly the dual-timescale approach Kronos learned automatically
4. **KronosBacktester** can validate strategy predictions vs actual outcomes

---

## 2. QuantDinger v3 (AI Quant Operating System)

**Repo:** https://github.com/Roshan7869/QuantDinger  
**Cloned to:** /tmp/analysis/QuantDinger

### Architecture
- **Dual strategy model:** IndicatorStrategy (dataframe/vectorized) → ScriptStrategy (event-driven stateful)
- **Agent API:** 5 risk classes (read-only, backtest, paper, simulation, live) with per-token permissions
- **MCP integration:** `mcp_server/` directory exposes quant capabilities as native MCP tools
- **Strategy compiler:** Runtime Python → executable compilation

### Key Components
| File | Purpose |
|------|---------|
| `src/quant/dinger/strategies/indicator.py` | IndicatorStrategy base class — vectorized signal computation on dataframes |
| `src/quant/dinger/strategies/scripts.py` | ScriptStrategy base class — event-driven, stateful, bar-by-bar execution |
| `src/quant/dinger/api/server.py` | FastAPI server with rate limiting, auth, kill switches |
| `src/quant/dinger/risk/classifier.py` | 5-tier risk classification: read_only → backtest → paper → simulation → live |
| `src/quant/dinger/agents/personas.py` | P4 (external AI agent) + P5 (autonomous strategy AI) with least-privilege |
| `src/quant/dinger/mcp/server.py` | MCP tool server exposing strategies, backtesting, portfolio analysis |

### Strategy Graduation Pattern (Critical Insight)
```python
# Current Algotrading: strategies go STRAIGHT to ScriptStrategy complexity
# QuantDinger approach: validate at IndicatorStrategy level FIRST

class AroonMomentum(IndicatorStrategy):
    """Vectorized signal computation — fast backtest, no state"""
    def indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df['aroon_up'] = aroon(df, period=14, scalar=100)
        df['aroon_down'] = aroon(df, period=14, scalar=-100)
        df['signal'] = np.where(df['aroon_up'] > 70, 1, np.where(df['aroon_down'] < -70, -1, 0))
        return df

# Only AFTER walk-forward validation does it graduate to:
class AroonMomentumScript(ScriptStrategy):
    """Event-driven, stateful execution — handles partial fills, timeouts, retries"""
    def on_bar(self, bar: Bar) -> Signal:
        # Stateful logic with position tracking
        ...
```

### Actionable Takeaways
1. **Adopt risk classification model** for our circuit breaker: tiers map directly
   - read_only → `dry_run: true` with Telegram alerts only
   - backtest → walk-forward validation required
   - paper → `dry_run: true` with full agent pipeline
   - simulation → live with 1x leverage, 1 max trade
   - live → full execution with all risk controls
2. **Add IndicatorStrategy base class** to Freqtrade strategies — validate signals vectorized before going event-driven
3. **Strategy graduation pipeline:** New strategies must pass walk-forward at IndicatorStrategy level before upgrading to full execution
4. **MCP server pattern:** Expose strategy_db queries and neural-trader capabilities as MCP tools

---

## 3. AI-Trader (HKUDS — Agent-Native Trading Platform)

**Repo:** https://github.com/Roshan7869/AI-Trader  
**Cloned to:** /tmp/analysis/AI-Trader

### Architecture
- **Skill-driven registration:** Agents read SKILL.md URLs to auto-configure
- **3 signal tiers:** Strategy (discussion) → Operation (copy-trade) → Execution (live)
- **Market Intel layer:** REST API `/api/market-intel/overview` returning macro regime, ETF flows, featured stocks, grouped news
- **Polymarket integration:** Public prediction market data feeds
- **Copy-trading with explicit kill switches:** Per-provider position sync with opt-in

### Key Components
| File | Purpose |
|------|---------|
| `skills/ai4trade/SKILL.md` | Skill definition: market analysis, portfolio optimization, risk management |
| `skills/industry_analyst/SKILL.md` | Industry sector analysis skill |
| `skills/tech_stock_analyst/SKILL.md` | Technical analysis + fundamental screening |
| `app/api/market_intel.py` | Market intel API: macro regime, ETF flows, news clustering |
| `app/api/strategies.py` | Trading signal API with tier classification |

### Signal Taxonomy (Critical Insight)
```python
# AI-Trader signal_class enum:
class SignalTier(Enum):
    DISCUSSION = "discussion"    # Low confidence, informational only
    OPERATION = "operation"       # Medium confidence, copy-trade eligible
    EXECUTION = "execution"       # High confidence, live trading eligible

# Current Algotrading: ALL agent outputs treated equally (binary buy/sell)
# Proposed: Tag each TradingAgents output with confidence tier
```

### Actionable Takeaways
1. **Build Market Intel service** — our system has ZERO macro context
   - Fear & Greed Index (alternative.me API)
   - BTC dominance (CoinGecko)
   - Total crypto market cap
   - S&P 500 / VIX for macro regime
   - Fed rate decisions calendar
2. **Signal confidence taxonomy** — tag agent outputs:
   - `DISCUSSION`: 1-2 indicators agree, no Kronos confirmation → alert only
   - `OPERATION`: 3+ indicators + regime alignment → dry-run trade
   - `EXECUTION`: All confirmations + positive Kelly → live trade
3. **Copy-trade pattern with kill switches** — for strategy graduation

---

## 4. ruflo-neural-trader (Hermes Plugin)

**Location:** /home/roshan/Downloads/ruflo/plugins/ruflo-neural-trader/  
**Status:** INSTALLED but NOT INTEGRATED into Algotrading

### Architecture
- **6 specialized skills:** regime, risk, signal, train, portfolio, backtest
- **4 agent personas:** trading-strategist (opus), risk-analyst (sonnet), market-analyst (sonnet), backtest-engineer (sonnet)
- **Rust/NAPI backtest engine:** 8-19x faster than Python-based backtesting
- **Walk-forward validation:** Built-in `--walk-forward` flag
- **Position sizing methods:** Kelly, Half-Kelly, Vol-adjusted, Risk-parity
- **Z-score anomaly detection:** spike, drift, flatline, oscillation, pattern-break, cluster-outlier

### Key Commands We Should Use
```bash
# Regime detection (CRITICAL — we have NO regime detection in current system)
npx neural-trader --regime-detect --symbol BTC/USDT --timeframe 15m

# Walk-forward backtesting (we have ZERO out-of-sample testing)
npx neural-trader --backtest --strategy AroonMomentum --walk-forward --train-ratio 0.7

# Position sizing (replaces our disconnected position_sizer.py)
npx neural-trader --position-sizing half-kelly --capital 1000 --risk 0.02

# Portfolio correlation analysis
npx neural-trader --correlation --portfolio current --flag-threshold 0.8

# Anomaly detection on current trades
npx neural-trader --anomaly-detect --source trades.sqlite --methods spike,drift,pattern-break
```

### Agent Configuration
```yaml
# From trading-strategist agent definition:
personality: |
  You are an expert crypto trading strategist.
  Analyze market data, identify patterns, and generate trading signals.
  Use regime-aware analysis to adapt strategy parameters.
  Always consider risk management and position sizing.
tools:
  - regime_detect
  - risk_assess
  - signal_generate
  - portfolio_optimize
model: opus  # or sonnet for cost savings
```

### Actionable Takeaways
1. **Install neural-trader in Algotrading environment**: `npm install @anthropic/neural-trader` or use the ruflo plugin
2. **Wire regime detection to signal bus**: JSON output → `/shared_config/regime.json`
3. **Replace custom `position_sizer.py`** with `npx neural-trader --position-sizing half-kelly`
4. **Use Rust/NAPI backtester** for walk-forward validation instead of Freqtrade's built-in (8-19x faster)
5. **Add MCP server** to expose neural-trader tools to TradingAgents: `claude mcp add neural-trader -- npx neural-trader mcp start`

---

## 5. MoondevRED Engine (Local Project)

**Location:** /home/roshan/Downloads/Algotrading/Algo @ 2/MoondevRED/  
**Analysis file:** /home/roshan/Downloads/Algotrading/MoondevRED_Engine_DeepDive.md

### Key Findings
- **9-layer architecture** with Claude/GPT strategy generators
- **4 RBI variants:** v1 (basic), v2 (crossover + indicators), v3 (crossover + Fib), PP (squeeze/breakout)
- **Fragmented strategies:** Each variant stored separately, no unified evaluation
- **No walk-forward or out-of-sample testing** in the generator pipeline
- **Good execution logging:** JSON schema with consistent top-level envelope across all variants

### Actionable Takeaways
1. **Unify RBI variants** into a single parameterized strategy rather than 4 separate files
2. **Add walk-forward validation step** after strategy generation
3. **Cross-validate generated strategies** against strategy_db patterns before deployment

---

## 6. Algotrading Infrastructure Scripts (Already Built but Disconnected)

### `scripts/circuit_breaker.py` — 3-tier drawdown protection
```python
HEALTHY  (dd < 15%) → normal trading
WARNING  (dd > 25%) → alerts, reduces max open trades
CRITICAL (dd > 40%) → kills Freqtrade process, closes positions
```
- **Status:** Written, NOT running. Should be started with `--watch` flag immediately.

### `scripts/risk_management/position_sizer.py` — Inverse volatility weighting
- **Status:** Written, NOT connected to Freqtrade config. The allocation weights function exists but nothing calls it.

### `scripts/risk_management/portfolio_monitor.py` — Drawdown + position monitoring
- **Status:** Written, uses Telegram alerts. NOT integrated with circuit_breaker.py

### `scripts/orchestrate.py` — Master orchestrator
- Wires Freqtrade + TradingAgents + Telegram + Risk + Health monitoring
- Validates .env variables, runs preflight checks
- **Status:** Written, can be started with `--mode paper`

### `strategy_db/strategy_agents.py` — 3-layer agent system
- Layer 1: Router Agent (classifies query → structured search params)
- Layer 2: Research Agent (hierarchical ChromaDB retrieval)
- Layer 3: Synthesis Agent (combines chunks → generates strategy code)
- Uses LangChain + ChatOllama (deepseek-v4-flash:cloud)
- **Status:** Working, but outputs don't feed back into strategy optimization

### `strategy_db/gcode_bridge.py` — CLI bridge
- Commands: query, get, list-types, list-conditions, to-config
- 443 chunks, 34-field schema, all-MiniLM-L6-v2 embeddings
- **Status:** Working, referenced in AGENTS.md

---

## 7. Research-Backed Validation

### Walk-Forward Optimization (Pardo, 1992/2008)
- **Gold standard** for strategy validation
- Process: Optimize on 70% of data, test on 30%, shift forward, repeat
- **Current gap:** Our system has ZERO walk-forward validation. All backtests are in-sample only.
- **Implementation:** Use neural-trader `--walk-forward` or build TRAP system from Trading_RESEARCH_PREVIEW_SYSTEM.md

### Kelly Criterion Variants
| Method | Formula | Our Context |
|--------|---------|-------------|
| Full Kelly | f* = (bp - q) / b | -0.09 (negative → don't trade current strategy) |
| Half Kelly | f* / 2 | Safer, reduces variance by 50% while only reducing growth by 25% |
| Optimal-f (Vince) | Terminal wealth relative maximized across all trade outcomes | More sophisticated than flat Kelly for non-normal distributions |
| Vol-Adjusted | f* × (realized_vol / target_vol) | Scale down in high vol, scale up in low vol |

### Regime Detection Methods
| Method | Source | Accuracy | Implementation |
|--------|--------|----------|----------------|
| Hidden Markov Model | Kronos paper, quant literature | 65-75% | `npx neural-trader --regime-detect` |
| ADX + Aroon threshold | Pring (1991) | 55-65% | Simple, currently partially in AroonMomentum |
| VIX / Fear-Greed | Market context | 60-70% | Need to build market_intel_service |
| Kronos prediction | AAAI 2026 paper | 70-80% on trained assets | Fine-tune Kronos-base on our crypto |

### Ensemble Weighting Schemes
| Method | Current | Proposed |
|--------|---------|----------|
| Flat vote | MACD+RSI+Bollinger+Supertrend+ADX+DMI all equal | FAILS — 34.1% win rate |
| Regime-adaptive | N/A | Weight momentum in trending, mean-reversion in ranging |
| Confidence-weighted | N/A | Each indicator weighted by its recent accuracy (rolling 30d) |
| Kronos prior | N/A | Kronos prediction as trend prior, indicators confirm |

---

## 8. Quick Reference: File Locations

| Artifact | Path |
|----------|------|
| Optimization Roadmap | `/home/roshan/Downloads/Algotrading/OPTIMIZATION_ROADMAP.md` |
| Architecture DAG | `/home/roshan/Downloads/Algotrading/ARCHITECTURE_DAG.md` |
| State Analysis | `/home/roshan/Downloads/Algotrading/ALGOTRADING_STATE_ANALYSIS.md` |
| Research/TRAP System | `/home/roshan/Downloads/Algotrading/Trading_RESEARCH_PREVIEW_SYSTEM.md` |
| MoondevRED Deep Dive | `/home/roshan/Downloads/Algotrading/MoondevRED_Engine_DeepDive.md` |
| This Report | `/home/roshan/Downloads/Algotrading/CROSS_PROJECT_INTELLIGENCE.md` |
| Circuit Breaker | `/home/roshan/Downloads/Algotrading/scripts/circuit_breaker.py` |
| Position Sizer | `/home/roshan/Downloads/Algotrading/scripts/risk_management/position_sizer.py` |
| Portfolio Monitor | `/home/roshan/Downloads/Algotrading/scripts/risk_management/portfolio_monitor.py` |
| Orchestrator | `/home/roshan/Downloads/Algotrading/scripts/orchestrate.py` |
| Strategy Agents | `/home/roshan/Downloads/Algotrading/strategy_db/strategy_agents.py` |
| Leverage Config | `/home/roshan/Downloads/Algotrading/user_data/strategies/leverage_config.py` |
| Kronos Clones | `/tmp/analysis/Kronos/` |
| QuantDinger Clones | `/tmp/analysis/QuantDinger/` |
| AI-Trader Clones | `/tmp/analysis/AI-Trader/` |
| Neural Trader Plugin | `/home/roshan/Downloads/ruflo/plugins/ruflo-neural-trader/` |

---

*This document serves as the persistent knowledge base for cross-project analysis. Referenced by OPTIMIZATION_ROADMAP.md and future optimization sessions.*