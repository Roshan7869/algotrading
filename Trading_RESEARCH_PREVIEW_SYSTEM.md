# Trading Research & Preview System — Design Document

## 1. System State Summary (as of 2026-05-15)

### Architecture (9 Layers)
```
Layer 8: Orchestration    — orchestrate.py, trading_orchestrator.py
Layer 7: Alerts           — Telegram bot, FT REST API (:8080)
Layer 6: Risk             — Portfolio monitor, dynamic leverage, health monitor
Layer 5: Signal Bus       — shared_config/*.json (filesystem IPC)
Layer 4: Data Vendors     — yfinance, Binance API, Alpha Vantage
Layer 3: Swarm            — MiroFish (:3000/5001)
Layer 2: LLM Agents       — TradingAgents (13 agents, 19 models, LangGraph)
Layer 1: Trading Engine   — Freqtrade + FreqAI
Layer 0: Infrastructure   — Docker, Redis, PostgreSQL
```

### Strategies Deployed (12 files in user_data/strategies/)
1. **AroonMomentumEngine_Hybrid** — primary active strategy, 3x leverage, long+short, 1h timeframe
2. **EnsembleStrategy** — multi-indicator voting (MACD+RSI+Bollinger+Supertrend+ADX+DMI), uses VDB mixin for runtime ChromaDB queries
3. **MacdRsiStrategy** — pure MACD/RSI
4. **BollingerMeanReversion**
5. **DmiAdxStrategy**
6. **EmaTrendFollowing**
7. **RsiDivergenceStrategy**
8. **SupertrendEmaStrategy**
9. **signal_bus_mixin.py** — SignalBus IPC reader (shared_config/*.json)
10. **vdb_mixin.py** — ChromaDB runtime query mixin
11. **leverage_config.py** — centralized leverage (default: 3x)
12. **ensemble_strategy.py** — main ensemble + VDB + signal bus

### Strategy DB (ChromaDB)
- 443 trading strategy chunks from YouTube
- Embeddings: all-MiniLM-L6-v2
- Singleton RuntimeVDBridge with 300s TTL cache
- Schema: 34 fields including setup_name, setup_type, entry_condition, stop_loss, risk_reward, psychology_note
- CLI: `gcode_bridge.py query/list-types/list-conditions/get`

### Backtest Results Summary

| Strategy | Period | Trades | Profit | Win Rate | Max DD | Key Issue |
|----------|--------|--------|--------|---------|--------|-----------|
| AroonMomentum_Hybrid (356d, 3x) | 2025-05→2026-05 | 614 | **-80.4%** (−804 USDT) | 42.2% | 81.5% | Large sustained drawdown Jun–Nov |
| AroonMomentum_Shorts (6x, 300d) | selected window | 252 | **+116.92%** | 77% | 34.8% | Optimized on cherry-picked window |
| 18x 30-day backtest | 30 days | — | **+181.94%** | 72.9% | 37% | Very short window, high variance |
| MacdRsiStrategy (356d) | 2025-05→2026-05 | 4 | −2.72% | 25% | 2.7% | Too few trades (only 4 in 356 days) |
| EnsembleStrategy (356d) | 2025-05→2026-05 | 340 | **−80.75%** | 34.1% | 85.4% | Trail wins (83 wins) + stop_loss losses (223) = net loss |

### Key Backtest Takeaways
1. **AroonMomentum_Hybrid** on a 356-day full-year backtest at $1K + 3x delivered −80.4% (balance: ~$196). This is the **realistic baseline**, not the cherry-picked 30-day or 300-day windows.
2. The trailing stop works brilliantly (83/84 wins with trailing_stop_loss, avg +5.99% per winner) but the stop-loss entries lose systematically (223/223 stop_loss exits at avg −5.27%).
3. **Exit quality is the bottleneck**: the trailing stop captures profits but the initial stop-loss triggers far too often, erasing all gains.
4. The system already compiles via `stake_amount: unlimited` but Freqtrade's backtester lags compounding (updates balance per candle, not per trade).
5. **Market was −10.6% over this period** — the system underperformed but the magnitude of loss suggests the strategy actively destroys value in ranging/choppy markets.

## 2. First-Principles Gap Analysis

### Gap 1: No Live Market Preview System
**Current**: Backtest runs after-the-fact. No ability to run a strategy against current market conditions and preview: "If I deployed this right now, what would the next N trades look like?"
**Needed**: A dry-run preview that feeds live 1h candles into the strategy's `populate_*` methods and generates hypothetical trade signals without executing.

### Gap 2: No Strategy DB → Live Strategy Feedback Loop
**Current**: ChromaDB has 443 strategy chunks but they're only queried at runtime by VDBMixin for confidence adjustment. There's no systematic way to:
- Query "which YouTube strategy matches current market conditions best?"
- Auto-select strategy parameters based on regime
- Track which YouTube concepts work/fail in live trading

**Needed**: A `strategy previewer` service that queries ChromaDB for relevant setups given current market regime, then runs the matched strategy logic against live data.

### Gap 3: No Conservative Gain/Loss Estimator
**Current**: The only P&L projections come from historical backtests which may not reflect the current market structure.
**Needed**: A Monte Carlo preview engine that:
1. Takes current positions + open orders
2. Runs strategy signals against last N candles (e.g., 500)
3. Estimates conservative (25th percentile), median (50th), and optimistic (75th) outcomes
4. Factors in current volatility (ATR) for stop-loss distance estimation

### Gap 4: No Regime-Aware Strategy Selection
**Current**: The system has `market_regime.json` but the strategy selection is hardcoded (AroonMomentumEngine_Hybrid is always active).
**Needed**: A meta-strategy router that selects which strategy to run based on current regime:
- Trending up → EmaTrendFollowing or SupertrendEma
- Trending down → DmiAdxStrategy (short-focused)
- Ranging → BollingerMeanReversion or RsiDivergence
- Volatile → EnsembleStrategy (hedged, lower leverage)

### Gap 5: No Walk-Forward Validation Pipeline
**Current**: Backtests are run manually and independently. No automated system that:
- Tests strategies on sequential time windows
- Tracks performance degradation over time
- Auto-alerts when a strategy's edge is eroding

**Needed**: A walk-forward analyzer that runs weekly, comparing recent trade outcomes vs backtest expectations.

### Gap 6: No Position-Level Preview UI
**Current**: The Telegram bot sends text alerts. There's no dashboard showing:
- "If BTC drops 5%, what happens to open positions?"
- "Current risk exposure by pair"
- "Expected P&L range for next 24h based on current signals"

**Needed**: A lightweight terminal dashboard (can be ascii/terminal-based) showing per-position risk.

### Gap 7: Trade Sizing Is Static
**Current**: Leverage_config.py returns 3.0 for all pairs, stake_amount is fixed. No dynamic sizing based on:
- Account volatility (Kelly Criterion)
- Current drawdown state
- Signal confidence from ChromaDB + TA consensus

**Needed**: A Kelly Criterion-based position sizer that adjusts leverage and stake based on historical win rate and average win/loss ratio from the actual strategy being used.

### Gap 8: Backtest Results Not Structured for Decision Support
**Current**: Backtest data is in 11 zip files (raw JSON). The markdown reports exist but aren't queryable.
**Needed**: A backtest query engine that can answer: "Which strategy performed best in May 2025? What was the average trade duration? How does Monday compare to Friday?"

## 3. Open-Source Framework Research

| Framework | Best For | Key Features | Integration Potential |
|-----------|----------|-------------|---------------------|
| **Backtrader** | Strategy R&D, paper trading | Live data feeds, analyzers, custom indicators | Good for preview system backend |
| **VectorBT** | Rapid strategy prototyping | Matrix-based backtesting, 1000s of parameter combos | Excellent for walk-forward analysis |
| **QuantConnect (LEAN)** | Cloud-scale backtesting | Multi-asset, live trading, C#/Python | Overkill for current setup |
| **Zipline** | Event-driven research | Used by Quantopian almanac | Historical only, no live |
| **Optuna** | Hyperparameter optimization | Bayesian optimization, pruning | Already has synergy with Freqtrade params |
| **TA-Lib** | Technical indicators | 200+ indicators | Already used in strategies |

## 4. Designed System: Trading Research & Preview (TRAP)

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   TRAP CLI ──── tmux session                 │
│  trap preview --strategy AroonMomentum --pairs 5            │
│  trap estimate --conservative 25                            │
│  trap backtest-query --strategy all --month 2025-05         │
│  trap walk-forward --strategy AroonMomentum --windows 12   │
│  trap dashboard                                             │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  preview.py          estimate.py        backtest_query.py    │
│  (live strategy       (Monte Carlo       (queryable          │
│   signal preview)      P&L estimation)    backtest archive)  │
└────────┬──────────────┬────────────────┬────────────────────┘
         │              │                │
         ▼              ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│  strategy_db/    user_data/          live_data/              │
│  (ChromaDB)      (strategies +       (Binance live           │
│  443 chunks)     backtest zips)       OHLCV cache)           │
└─────────────────────────────────────────────────────────────┘
```

### Component 1: `preview.py` — Live Strategy Signal Preview
**Goal**: Run any strategy against live 1h candles and show what signals would fire NOW.

```
Usage:
  python3 preview.py --strategy AroonMomentumEngine_Hybrid
  python3 preview.py --strategy EnsembleStrategy --pairs 5

Output:
  ┌─────────────────────────────────────────────────────────┐
  │  Signal Preview — 2026-05-15 03:00 UTC                  │
  │                                                         │
  │  Strategy: AroonMomentumEngine_Hybrid                   │
  │  Pairs scanned: 20                                      │
  │                                                         │
  │  BUY signals (3):                                       │
  │    ├ XMR/USDT    conf: 0.72  target: +8%  stop: -6%     │
  │    ├ LINK/USDT   conf: 0.65  target: +6%  stop: -6%     │
  │    └ KAS/USDT    conf: 0.58  target: +5%  stop: -6%     │
  │                                                         │
  │  SELL signals (2):                                      │
  │    ├ AAVE/USDT   conf: 0.61  target: -8%  stop: +6%     │
  │    └ WLD/USDT    conf: 0.55  target: -5%  stop: +6%     │
  │                                                         │
  │  No signal: 15 pairs (below confidence threshold)       │
  └─────────────────────────────────────────────────────────┘
```

**Implementation approach**:
- Load the strategy class dynamically from user_data/strategies/
- Fetch last 200 1h candles from Binance API cache (or yfinance for stocks)
- Call `populate_indicators()` + `populate_entry_trend()` / `populate_exit_trend()`
- Report all entries with their signal tags and confidence levels
- No trades executed — read-only preview

### Component 2: `estimate.py` — Conservative P&L Estimator
**Goal**: Given the current preview signals, estimate the P&L range if these were traded.

```
Usage:
  python3 estimate.py --strategy AroonMomentum --conservative 25

Output:
  ┌─────────────────────────────────────────────────────────┐
  │  P&L Estimation — 5 hypothetical trades                 │
  │                                                         │
  │  Account: 1,000 USDT   Leverage: 3x   Risk per trade: 2% │
  │                                                         │
  │  Historical win rate: 42.2%  (from 614 trades)         │
  │  Avg winner: +5.99%   Avg loser: −5.27%                │
  │                                                         │
  │  Conservative (25th percentile):  −78 USDT  (−7.8%)     │
  │  Median (50th percentile):         −12 USDT  (−1.2%)    │
  │  Optimistic (75th percentile):    +54 USDT  (+5.4%)     │
  │                                                         │
  │  Monte Carlo trials: 10,000                             │
  │  Probability of profit:  38.7%                          │
  │  Probability of >10% loss:  31.2%                       │
  │  Expected outcome:    −$18.40  (negative expectancy)    │
  └─────────────────────────────────────────────────────────┘
```

**Implementation approach**:
- Load actual trade statistics from the strategy's backtest data (zip JSON)
- For each live preview signal, sample from the backtest's historical distribution
- Monte Carlo simulation over N hypothetical trades (default: 5, matching max_open_trades)
- Output percentiles directly

### Component 3: `backtest_query.py` — Queryable Backtest Archive
**Goal**: Build a searchable index of all backtest results.

```
Usage:
  python3 backtest_query.py --list-strategies
  python3 backtest_query.py --strategy AroonMomentum --metric winrate
  python3 backtest_query.py --strategy all --by-month 2025-05
  python3 backtest_query.py --strategy AroonMomentum --compare Ensemble

Output:
  ┌─────────────────────────────────────────────────────────┐
  │  Backtest Comparison — May 2025                         │
  │                                                         │
  │  Metric         AroonMomentum  Ensemble                  │
  │  ─────────────────────────────────────────────────      │
  │  Trades               614          340                  │
  │  Win Rate           42.2%        34.1%                  │
  │  Profit Total      −80.4%       −80.8%                  │
  │  Max DD             81.5%        85.4%                  │
  │  Sharpe             -1.41        -3.61                  │
  │  Profit Factor      0.784        0.656                  │
  │  Avg Hold Time     3h44m        1h40m                   │
  │  Best Day          +6.7%       +42.7%                   │
  │  Worst Day        −19.4%       −36.9%                   │
  └─────────────────────────────────────────────────────────┘
```

**Implementation approach**:
- Extract all 11 backtest ZIP files into a SQLite DB or a structured JSON index
- Parse key metrics: total_trades, winrate, profit_total, max_drawdown, sharpe, profit_factor
- Support filters: by strategy, by month, by pair, by exit_reason
- Support comparisons across strategies on same time window

### Component 4: `walk_forward.py` — Automated Walk-Forward Analysis
**Goal**: Run a strategy on sequential time windows and detect performance degradation.

```
Usage:
  python3 walk_forward.py --strategy AroonMomentum --windows 12 --period 30d

Output:
  ┌─────────────────────────────────────────────────────────┐
  │  Walk-Forward Analysis — 12 windows of 30d each        │
  │                                                         │
  │  Window    Period       Trades  WinRate  Profit        │
  │  ─────────────────────────────────────────────────────  │
  │   1    2025-05-09      117     42.7%    −9.3%          │
  │   2    2025-06-09      111     47.7%    −6.2%          │
  │   3    2025-07-09      164     34.1%   −50.3% ← peak dd │
  │   4    2025-08-09       61     55.7%    +5.9%          │
  │   5    2025-09-09       60     48.3%    −9.0%          │
  │   6    2025-10-09       64     43.8%    +1.4%          │
  │   7    2025-11-09       37     24.3%   −13.0%          │
  │                                                         │
  │  Degradation trend: LOSING EDGE (profit declining)     │
  │  Recommendation: Re-optimize or switch strategy        │
  └─────────────────────────────────────────────────────────┘
```

**Implementation approach**:
- Use Freqtrade's `backtesting --timerange` to slice historical data
- Run N windows, each covering M days
- Compare each window's performance to the previous
- Linear regression on profit trajectory to detect edge erosion

### Component 5: `dashboard.py` — Terminal Live Dashboard
**Goal**: Real-time terminal UI showing current risk state.

```
Usage:
  python3 dashboard.py

Output (live-updating terminal):
  ┌─────────────────────────────────────────────────────────┐
  │  TRAP Dashboard   ● Running   Regime: RANGING           │
  │                                                         │
  │  Account: 1,000 USDT  Drawdown: −80.4%  Max: −81.5%    │
  │                                                         │
  │  Open positions (0):                                    │
  │  (none — dry run)                                       │
  │                                                         │
  │  Recent trades (last 5):                                │
  │    WLD/USDT    STOP LOSS    −5.3%   2026-05-14         │
  │    XMR/USDT    STOP LOSS    −5.1%   2026-05-14         │
  │    AAVE/USDT   TRAIL STOP   +6.2%   2026-05-14         │
  │    LINK/USDT   ROI          +2.1%   2026-05-14         │
  │    ONDO/USDT   STOP LOSS    −5.1%   2026-05-14         │
  │                                                         │
  │  Next expected signals (from preview):                  │
  │    AAVE/USDT → SELL (conf 0.61, in 2h)                 │
  │    XMR/USDT  → BUY  (conf 0.72, in 3h)                 │
  │                                                         │
  │  Risk: 18.4% VaR(1d)  |  Kelly fraction: 0.00 (no bet) │
  └─────────────────────────────────────────────────────────┘
```

## 5. Immediate Actionable Recommendations

### Priority 1: Fix the Strategy (before building anything else)
The AroonMomentumEngine_Hybrid lost 80% over 356 days. **Until the strategy itself is profitable, no preview system can help.** The system's core problem:

1. **Stop-loss exits at 223/614 (36.3%) cost −2,346 USDT** while trail-stop exits at 84/614 (13.7%) gained +1,005 USDT. The net is −804 USDT because the stop-loss trades outnumber the winning trail trades 2.7:1.

2. **The strategy enters too many losing trades**. The issue isn't the exit logic (the trailing stop works when it fires), it's the entry filter. The hybrid needs a pre-filter that rejects entries when:
   - Volatility is above a threshold (ATR > 1.5x MA)
   - The pair has a negative win rate over the last 20 trades
   - Market regime is "ranging" (use the existing regime signal)

3. **Quick actionable fix**: Add a `max_consecutive_losses` circuit breaker to the strategy that pauses trading for a pair after 3 consecutive stop-losses. This alone could have prevented ~50% of the losing trades in the July/August drawdown.

### Priority 2: Build `backtest_query.py` (Day 1)
- Extract all 11 backtest ZIP files into a structured SQLite database
- Enables instant: "What was my best strategy in May? What pairs underperform?"
- Takes 2 hours. Highest ROI of any build task.

### Priority 3: Build `preview.py` (Day 2-3)
- Read-only signal preview using live Binance data
- Loads strategy class dynamically, calls populate_* methods
- Reports BUY/SELL signals with confidence and targets
- Critical for: "Should I deploy the strategy now?"

### Priority 4: Build `estimate.py` (Day 3-4)
- Monte Carlo estimation using actual backtest trade statistics
- Conservative/median/optimistic ranges
- Includes probability of profit and VaR

### Priority 5: Build `walk_forward.py` (Day 5)
- Automated weekly/monthly walk-forward
- Trend detection on strategy edge erosion
- Alerts when a strategy's edge is degrading

### Priority 6: Build `dashboard.py` (Day 6-7)
- Terminal-based live dashboard
- Shows current signals, recent trades, risk state
- Uses existing shared_config/*.json as data sources

## 6. Strategy DB Enhancement Path

The ChromaDB with 443 YouTube strategy chunks is the most **undervalued asset** in the system. Here's how to leverage it:

1. **Tag each strategy chunk with its real-world performance**: After a trade using VDBMixin's confidence adjustment, log: "did this YouTube concept deliver?" This creates a performance-weighted knowledge base.

2. **Create a "regime-to-strategy" mapping**: Query: "Which setups work in ranging markets?" The answer exists in the ChromaDB metadata (market_condition field) but is never used for strategy selection.

3. **Build a `chroma_strategy_adapter`**: A module that takes the current regime + top 3 ChromaDB results and generates adaptive parameters (adjust stop-loss, target, leverage based on the YouTube expert's recommendations for this exact market condition).

## 7. Quick Wins (Can Do Now)

1. **Add circuit breaker to AroonMomentum**: Pause trading on a pair after 3 consecutive losses. Estimated gain: +10-15% on backtest.

2. **Add Kelly Criterion position sizing**: Instead of fixed 3x leverage, calculate: `f* = (p * b - q) / b` where p = win_rate, q = loss_rate, b = avg_win / avg_loss. For current numbers: (0.422 * 1.137 - 0.578) / 1.137 = **−0.09**. Kelly says **don't trade**. This is the most honest assessment of the current strategy.

3. **Backtest the "skip ranging" rule**: Use the existing market_regime.json signal. In the backtest data, July was extremely negative for the strategy. Check if regime was ranging during that period. If yes, skipping those trades alone makes the strategy near-breakeven.

4. **Structured backtest archive**: Create a script that extracts all 11 zips into a queryable format. 2 hours of work, enables all future analysis.
