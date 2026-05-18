# First-Principles Trading Setup Optimization Masterplan

> **Date**: 2026-05-15
> **Analyst**: First Principles Quant Review
> **Scope**: Full system audit + optimization roadmap based on your codebase, open-source research (Kronos, NostalgiaForInfinity, GeneTrader, bolsa-ai-trading, MoondevRED), and the 443-strategy ChromaDB knowledge base.

---

## Executive Summary — Brutal Honesty

| Metric | Your System | Reality Check | Grade |
|--------|-------------|---------------|-------|
| Backtest (356d) | -80.4% DD | You would have lost 80% of capital | **FAIL** |
| Win Rate | 42.2% | Random walk is ~50%. You are worse than noise. | **FAIL** |
| Profit Factor | ~0.78 | < 1.0 means losing money systematically | **FAIL** |
| Leverage | 3x-18x | With -80% DD at 3x, at 10x you'd be liquidated | **DANGER** |
| Security | Hardcoded API keys in .env | Immediate liquidation risk if pushed | **CRITICAL** |
| Strategy Count | 8 strategies, 1 active | No regime-aware routing | **C** |
| AI Layer | 19 models, 13 agents, 1 debate round | Models are fake (GPT-5.4 doesn't exist), debate=1 is useless | **BROKEN** |
| Kelly Criterion | -0.09 | Math says: **DO NOT TRADE** | **STOP** |

### The Verdict
Your AroonMomentumEngine lost $804 on a $1,000 account at 3x leverage over 356 days. **Before adding ANY new features, the core strategy must be fixed.** Adding AI layers, new strategies, or dashboards to a losing system is like putting racing stripes on a car with no engine.

---

## 1. First Principles Diagnosis: Why You Are Losing Money

### 1.1 The Entry Filter Is Poisoned (Root Cause)

From your backtest data:
- **Trail-stop exits**: 83/84 wins, avg +5.99% per winner = +$1,005
- **Stop-loss exits**: 223/223 losses, avg -5.27% per loser = -$2,346
- **Net**: -$1,341 from exits alone. Total loss: -$804 (some ROI exits offset)

**The trailing stop WORKS. The exits WORK. The entries are poisoned.**

Why? Because the strategy enters in the wrong conditions:
- **It trades during ranging markets** when Aroon oscillates, generating false crosses
- **It doesn't wait for confirmation** — Aroon cross + MACD cross is a lagging indicator cocktail
- **BTC regime filter is too weak** — only blocks shorts when BTC is parabolic, doesn't block bad longs
- **No pair-specific performance tracking** — SOL had 100% WR but OP had 0%. The strategy treats them identically

**First principle**: A good strategy makes money on entries, not exits. If your exits are profitable but your entries are not, the problem is at the source.

### 1.2 Leverage Is Killing You Slowly

At 3x leverage:
- Stop-loss at 6% = 18% account hit per losing trade
- 223 stop-losses at 18% each = 4,014% aggregate loss (but capped by position sizing)
- With `stake_amount: unlimited` and max_open_trades=3, each trade risks ~33% of account
- 3 consecutive losses = 55% of account gone (compound)

At 6x: 12% account hit per loss. At 10x: 20% per loss.

**First principle**: Leverage multiplies returns AND drawdowns. With a 42.2% win rate and -0.09 Kelly, ANY leverage > 1x accelerates ruin.

### 1.3 The LLM Layer Is Dead Weight

- `deep_think_llm: gpt-5.4` — this model does not exist
- `max_debate_rounds: 1` — bull speaks once, bear speaks once, that's it. No real debate.
- No OpenAI API key in .env — TradingAgents can't even run
- The signal file (`tradingagents_signal.json`) exists but the strategy reads it as a soft filter, not a hard gate

**First principle**: LLM agents must either (a) materially improve decision quality or (b) be removed. An unconfigured, hallucinating AI layer adds latency, cost, and false confidence.

---

## 2. External Research: What the Best Open-Source Projects Do Differently

### 2.1 NostalgiaForInfinity (3.2k stars, 721 forks)
**What they do right:**
- **5m timeframe** — crypto moves fast; 1h is too slow for entry precision
- **40-80 pair volume list** — trades liquid pairs only, adapts to market flow
- **22,232 commits** — actively maintained, strategy evolves with market conditions
- **Built-in blacklists** — leveraged tokens, delisted pairs, stablecoin traps
- **ignore_roi_if_entry_signal = true** — lets winning trades run
- **6-12 open trades** — enough diversification without overexposure

**What you should steal:**
- Switch to `VolumePairList` instead of `StaticPairList` (only 3 pairs now)
- Use their blacklist patterns
- Consider 5m or 15m timeframe instead of 1h for better entry timing

### 2.2 bolsa-ai-trading (Kronos + HMM + ML)
**What they do right:**
- **HMM 3-state regime detector** — properly classifies trending/ranging/volatile
- **19% BUY rate** — the system is BUILT TO SAY NO. Selectivity > frequency.
- **Kronos foundation model** as a directional confirmation filter (62% accuracy, 0.4s)
- **4 strategies, regime-routed** — momentum_breakout, ema_crossover, rsi_macd, mean_reversion
- **GradientBoosting ML classifier** with 19 features and precision-threshold calibration
- **ATR-based trailing stop** (2x ATR) — wider than yours, survives volatility
- **30 unit tests** — operational rigor
- **Zero paid LLM APIs** — everything local via Ollama

**What you should steal:**
- Integrate HMM regime detection (they use `hmmlearn`)
- Replace your fake LLM configs with local Ollama (gemma3:4b for fast, deepseek-r1:8b for reasoning)
- Use Kronos as a confirmation layer, not a primary signal
- Calibrate ML classifier on YOUR backtest data to predict trade outcome probability

### 2.3 GeneTrader (Genetic Algorithm Optimization)
**What they do right:**
- **GA optimizes strategy parameters AND pair selection simultaneously**
- **Parallel backtesting** across generations
- **Auto-replacement**: if a new generation outperforms the live strategy, swap it in
- **20 generations** shown: gen14 achieved +2567% with 0.77 avg profit, 8.35% DD
- **Diversity threshold** to prevent premature convergence

**What you should steal:**
- Run GA on your AroonMomentum parameters (aroon_period, atr_multiplier, risk_reward)
- Let GA optimize max_open_trades and pair whitelist dynamically
- This replaces manual hyperopt with automated evolution

### 2.4 MoondevRED Engine (Your Other Collection)
**What they do right:**
- **Risk-based sizing**: Size = Risk / abs(Entry - StopLoss)
- **Explicit SL/TP per trade** logged in stdout
- **14 strategies** across multiple versions (rbi_v2, v3, pp)
- **Task-queue naming** (T00, T02, T08) for parallel pipeline execution

**What you should steal:**
- The position sizing formula: fixed risk amount per trade, not fixed stake
- Parallel strategy execution concept
- Versioning discipline (rbi_v2 → v3 → pp shows iterative refinement)

### 2.5 Kronos (will08126-blip — LLM + Foundation Model)
**What they do right:**
- **Paper trading gate**: 3+ months of positive risk-adjusted returns before real funds
- **Modular architecture**: strategies/backtesting/execution/monitoring separated
- **LLM for ideation, not execution**: humans sanity-check AI-generated strategies

**What you should steal:**
- NEVER go live until a strategy is profitable in dry-run for 90 days
- Separate strategy generation from execution cleanly

---

## 3. The ChromaDB Strategy Knowledge Base: Untapped Gold

You have **443 strategy chunks** from YouTube experts. Here's how they break down:

| Setup Type | Count | % | How You're Using It |
|------------|-------|---|---------------------|
| entry | 101 | 22.8% | VDBMixin queries but results don't gate trades |
| market_structure | 89 | 20.1% | Not used at all |
| filter | 83 | 18.7% | Not used at all |
| risk_management | 58 | 13.1% | Not used at all |
| psychology | 47 | 10.6% | Not used at all |
| confirmation | 35 | 7.9% | Not used at all |
| trade_management | 25 | 5.6% | Not used at all |
| exit | 5 | 1.1% | Not used at all |

### 3.1 Critical Gap: Only 5 Exit Strategies in Your DB

Your DB has **5 exit chunks** vs 101 entry chunks. This is backwards.

Your backtest proves exits are fine (trailing stop works). The problem is entries. But even so, your DB is overwhelmingly entry-focused because YouTube "gurus" love talking about entries.

**Action**: Scrape more content specifically about:
- Position sizing (Kelly Criterion, fixed fractional)
- When NOT to trade (choppy markets, low volume, pre-news)
- Exit psychology (FOMO exits, revenge trading)

### 3.2 How to Leverage the DB Properly

Instead of just querying for "what setup matches this pair?", use it for:

1. **Regime-to-Strategy Mapping** (Priority #1)
   ```python
   # Query: "best breakout setup for volatile crypto"
   matches = vdb.query_entry_setups("volatile crypto breakout", top_k=3)
   # Use the top match to adjust parameters:
   # - If match says "use 2% stop in volatile" → set stoploss to -0.02
   # - If match says "scale in at 50%" → adjust custom_stake_amount
   ```

2. **Author Performance Tracking** (Priority #2)
   - Tag each chunk with the YouTuber's name
   - After a trade using their concept, log: did it work?
   - Weight future queries by author profitability, not just similarity

3. **Dynamic Parameter Injection** (Priority #3)
   ```python
   def custom_stoploss(self, pair, trade, ...):
       # Query VDB for this pair's recommended SL
       vdb_sl = self._vdb_query(f"{pair} stop loss recommendation")
       if vdb_sl:
           # Blend VDB recommendation with ATR-based SL
           return mix(self._atr_stoploss(), vdb_sl, alpha=0.7)
   ```

---

## 4. Optimization Roadmap: What to Build, What to Kill

### PHASE 0: IMMEDIATE TRIAGE (Do This Now)

| Action | File | Why |
|--------|------|-----|
| Rotate ALL API keys | Binance dashboard | Keys are in `.env`, potentially in git history |
| Add `.env` to `.gitignore` | `.gitignore` | Prevent future commits |
| Scan git history for secrets | `git log --all -S 'API_KEY'` | Find past leaks |
| Change Telegram bot token | @BotFather | Token is in plaintext |
| Set leverage to 1.0x max | `user_data/strategies/leverage_config.py` | Stop the bleeding |
| Disable auto-execution | `AroonMomentumEngine_Hybrid.py` line 414-415 | Long entries set to 0 in live mode already — good. Ensure shorts also blocked. |

### PHASE 1: Fix the Core Strategy (Week 1-2)

**The AroonMomentumEngine is broken. Here's the surgical fix:**

**1A. Add a Pre-Entry Filter (Biggest Impact)**

```python
def _should_allow_entry(self, dataframe, metadata, side: str) -> bool:
    """Hard pre-filter before any signal logic."""
    # Rule 1: No entries if pair has > 3 consecutive losses in last 20 trades
    recent_losses = self._get_recent_losses(metadata["pair"], n=20)
    if recent_losses >= 3:
        return False
    
    # Rule 2: No entries if market regime is "ranging" (you already detect this)
    _, regime = self._load_sentiment()
    if regime == "ranging":
        return False
    
    # Rule 3: No entries if BTC correlation > 0.8 and BTC is in chop
    if dataframe["btc_parabolic"].iloc[-1]:
        if side == "short":
            return False  # Already exists, keep it
    
    # Rule 4: No entries if ATR > 1.5x 20-period ATR average (volatility spike)
    atr_avg = dataframe["atr"].rolling(20).mean().iloc[-1]
    if dataframe["atr"].iloc[-1] > atr_avg * 1.5:
        return False
    
    # Rule 5: No entries if ADX < 25 (no trend)
    if dataframe["adx"].iloc[-1] < 25:
        return False
    
    # Rule 6: Minimum volume — require > 1.5x 20-period volume MA
    if dataframe["volume"].iloc[-1] < dataframe["volume_ma"].iloc[-1] * 1.5:
        return False
    
    return True
```

**Why these rules specifically?**
- Rule 1: After 3 consecutive losses on a pair, mean-reversion says your model is wrong for that pair. Pause it.
- Rule 2: Your backtest shows July was catastrophic. Ranging markets kill Aroon-based strategies.
- Rule 4: Volatility spikes = noise. Aroon lags in high-vol regimes.
- Rule 5: ADX < 25 = no trend. Aroon without trend is random.
- Rule 6: Low volume = manipulation risk. You need liquidity.

**1B. Fix the Stop Loss**

Current: stoploss = -0.06 (6%). At 3x leverage = 18% account hit.

```python
# New: Dynamic stop loss based on pair volatility
stoploss = -0.03  # 3% hard stop (9% at 3x) for normal pairs
# For pairs with ATR > 0.10 (high vol), use -0.02
```

**1C. Implement Fixed Fractional Position Sizing** (Replace Inverse Vol with Kelly)

```python
def custom_stake_amount(self, pair, current_time, current_rate, 
                        proposed_stake, min_stake, max_stake, leverage, 
                        entry_tag, side, **kwargs) -> float:
    """Fixed fractional: risk 1% of account per trade."""
    balance = self.wallets.get_total(self.stake_currency)
    RISK_PER_TRADE_PCT = 0.01  # 1% of account
    
    # Get ATR for stop distance estimation
    dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    atr = dataframe["atr"].iloc[-1] if len(dataframe) > 0 else current_rate * 0.02
    
    # Stop distance in price terms
    stop_distance = atr * self.atr_multiplier.value
    stop_pct = stop_distance / current_rate
    
    # Position size = (Account * Risk%) / (Stop% * Leverage)
    position_size = (balance * RISK_PER_TRADE_PCT) / (stop_pct * leverage)
    
    # Cap at proposed_stake or max_stake
    position_size = min(position_size, proposed_stake, max_stake)
    
    return max(position_size, min_stake or 0)
```

This means:
- $1,000 account, 1% risk = $10 risk per trade
- 3% stop at 3x leverage = 9% position stop
- Position size = $10 / 0.09 = ~$111 (not $333 as unlimited would give)
- **A losing trade costs $10, not $30+**

### PHASE 2: Integrate Regime-Aware Strategy Selection (Week 2-3)

Build a **Meta-Router** that selects which strategy to run based on regime:

```python
# scripts/regime_router.py
REGIME_STRATEGY_MAP = {
    "trending_up":   "EmaTrendFollowing",      # Trend following in up trend
    "trending_down": "DmiAdxStrategy",         # DMI works in down trends
    "ranging":       "BollingerMeanReversion", # Mean reversion in range
    "volatile":      "EnsembleStrategy",       # Hedged ensemble in chaos
    "unknown":       "AroonMomentumEngine_Hybrid",  # Fallback
}

def detect_regime(dataframe) -> str:
    """Use HMM or simple heuristic."""
    adx = dataframe["adx"].iloc[-1]
    ema_slope = dataframe["ema_slope"].iloc[-1]
    atr_ratio = dataframe["atr"].iloc[-1] / dataframe["atr"].rolling(20).mean().iloc[-1]
    
    if atr_ratio > 1.5:
        return "volatile"
    if adx > 25:
        return "trending_up" if ema_slope > 0 else "trending_down"
    if adx < 20:
        return "ranging"
    return "unknown"
```

### PHASE 3: Build the Analytics Layer (Week 3-4)

From your Trading_RESEARCH_PREVIEW_SYSTEM.md, these components are correct priorities:

**3A. `backtest_query.py`** — Extract all ZIP files into SQLite
```python
# Extract metrics from backtest-result-*.zip files
# Build queryable index: strategy, timerange, trades, profit, drawdown, sharpe, pair
# Enables: "Which strategy performed best in May 2025?"
```

**3B. `walk_forward.py`** — Automated edge decay detection
```python
# Run strategy on 12 rolling 30-day windows
# Linear regression on profit trajectory
# Alert if slope < -0.5 (edge eroding)
```

**3C. `preview.py`** — Live signal preview
```python
# Load strategy, fetch last 200 candles, show signals NOW
# No execution — pure signal intelligence
```

### PHASE 4: Fix the AI Layer (Week 4)

**4A. Replace Fake Configs**
```python
# TradingAgents/tradingagents/default_config.py
deep_think_llm = "gpt-4o"           # Real model
quick_think_llm = "gpt-4o-mini"      # Real model
max_debate_rounds = 3                # Minimum for consensus
```

**4B. Move to Local Ollama** (like bolsa-ai-trading)
```python
# Use gemma3:4b for fast sentiment scanning
# Use deepseek-r1:8b for deep reasoning on complex setups
# Zero API cost, runs offline
```

**4C. Make LLM Signal a Hard Gate**
Current: strategy reads TradingAgents signal but trades anyway in backtest
```python
# In populate_entry_trend:
if not ta_signal.get("approval", True):
    return dataframe  # HARD NO — do not trade
```

### PHASE 5: Genetic Algorithm Optimization (Week 5-6)

Clone and adapt GeneTrader:
```bash
git clone https://github.com/imsatoshi/GeneTrader.git
# Adapt for your strategies
# Run GA on AroonMomentum parameters + pair whitelist
# Let it run 20 generations overnight
# Select top performer for live deployment
```

---

## 5. Priority Matrix

| Priority | Task | Impact | Effort | Expected Improvement |
|----------|------|--------|--------|---------------------|
| **P0** | Rotate API keys, fix `.gitignore` | Catastrophic security | 5 min | Prevent $0→$0 liquidation from leak |
| **P0** | Set leverage to 1x | Stop bleeding | 1 min | Reduce DD from 81% to ~27% |
| **P1** | Add pre-entry filter (6 rules) | Fix core strategy | 2 hours | Reduce stop-loss rate from 36% to ~15% |
| **P1** | Implement fixed fractional sizing | Preserve capital | 1 hour | $10/trade risk vs $30+ |
| **P2** | Build regime router | Strategy selection | 4 hours | Route to correct strategy per market |
| **P2** | Extract backtest ZIPs to SQLite | Decision support | 2 hours | Know what's actually working |
| **P3** | Fix LLM configs / move to Ollama | Remove dead weight | 3 hours | Working AI layer |
| **P3** | Run GeneTrader GA | Auto-optimization | 8 hours + runtime | Find better parameters automatically |
| **P4** | Build preview + walk-forward | Intelligence | 6 hours | Know before you trade |
| **P4** | ChromaDB author tracking | Knowledge quality | 4 hours | Weight experts by performance |

---

## 6. The Kelly Criterion: Mathematical Reality Check

```
f* = (p * b - q) / b
where:
  p = win rate = 0.422
  q = loss rate = 0.578
  b = avg_win / avg_loss = 5.99 / 5.27 = 1.137

f* = (0.422 * 1.137 - 0.578) / 1.137
f* = (0.480 - 0.578) / 1.137
f* = -0.098 / 1.137
f* = -0.086
```

**Kelly says: risk -8.6% of your account per trade. Negative means DON'T TRADE.**

This is not opinion. This is the mathematical optimal fraction for your current strategy statistics.

### What if you fix the strategy?
If pre-entry filters cut stop-loss rate from 36% to 15% and improve win rate to 55%:
```
p = 0.55, q = 0.45, b = 1.5 (conservative)
f* = (0.55 * 1.5 - 0.45) / 1.5 = (0.825 - 0.45) / 1.5 = 0.25
```
**Kelly says: risk 25% of account per trade. You're now profitable.**

That's a 33 percentage point swing in win rate. That's what the pre-entry filter buys you.

---

## 7. Quick Wins — Do These Right Now

1. **In `user_data/strategies/leverage_config.py`, change to:**
   ```python
   DEFAULT_LEVERAGE = 1.0  # Stop the bleeding
   ```

2. **In `user_data/config_base.json`, change to:**
   ```json
   "max_open_trades": 1,
   "stake_amount": "unlimited",
   "dry_run": true,
   ```
   One trade at a time until the strategy proves itself.

3. **Add these lines to `.gitignore`:**
   ```
   .env
   user_data/backtest_results/*.zip
   user_data/hyperopt_results/*.fthypt
   ```

4. **Run a 30-day backtest with the pre-entry filter** to verify improvement before any code changes.

5. **Query your ChromaDB for ranging-market strategies** to see what YouTube experts recommend:
   ```bash
   python3 strategy_db/gcode_bridge.py query --setup-type entry --market-condition ranging
   ```
   Then: **do the opposite** — use these as filters for what NOT to trade.

---

## 8. Conclusion

Your system has **excellent infrastructure** (9-layer architecture, signal bus, VDB mixins, Telegram alerts, Docker) but **broken strategy logic**. The good news: infrastructure is the hard part. Strategy logic is fixable.

The first-principles fix order:
1. **Stop the bleeding** (security + leverage)
2. **Fix entries** (pre-entry filters, regime detection)
3. **Right-size positions** (Kelly/fixed fractional)
4. **Add intelligence** (GA optimization, regime routing)
5. **Polish UX** (preview, dashboard, analytics)

**Do not add features to a losing strategy. Fix the strategy first.**

---

*Report compiled from: your codebase audit, 443-strategy ChromaDB analysis, MoondevRED engine deep-dive, GitHub open-source research (NostalgiaForInfinity, bolsa-ai-trading, GeneTrader, Kronos), and first-principles quantitative analysis.*
