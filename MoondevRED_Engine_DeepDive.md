# MoondevRED Engine — Deep-Dive Report

## 1. Engine Architecture & Directory Structure

```text
/home/roshan/Downloads/Algotrading/Algo @ 2/MoondevRED
│
├── _engine/
│   ├── 01_foundation/
│   │   ├── exchange_connectors/
│   │   └── trading_utilities/
│   ├── 02_data_acquisition/
│   │   ├── market_feeds/
│   │   ├── social_media_feeds/
│   │   └── web_scrapers/
│   ├── 03_strategy_development/
│   │   ├── idea_research/
│   │   ├── strategy_generators/
│   │   └── strategy_library/
│   │       └── custom/
│   ├── 04_validation_testing/
│   │   └── backtest_runners/
│   ├── 05_live_execution/
│   │   ├── arbitrage_trading/
│   │   ├── copy_trading/
│   │   ├── solana_trading/
│   │   └── trade_execution/
│   ├── 06_safety_monitoring/
│   │   ├── compliance_rules/
│   │   └── risk_monitors/
│   ├── 07_user_operations/
│   │   ├── alert_notifications/
│   │   ├── content_creation/
│   │   └── user_engagement/
│   ├── _agent_framework/          ← Swarm / agent orchestration layer
│   ├── _data_storage/             ← Central data lake
│   │   ├── code_runner/
│   │   ├── execution_results/     ← Legacy/base backtest logs
│   │   ├── ohlcv/                  ← Raw market data
│   │   ├── rbi/                    ← RBI legacy runs (e.g. 03_14_2025)
│   │   ├── rbi_v2/                 ← RBI Version 2 (classic indicators)
│   │   ├── rbi_v3/                 ← RBI Version 3 (crossover + Fib)
│   │   └── rbi_pp/                 ← RBI PP / task-queue runs (squeeze/breakout)
│   ├── _llm_providers/            ← GPT/Claude wrappers
│   └── _utilities/
│
├── backups/
│   └── src_backup/                 ← Mirror of historical src + data
├── reports/
│   └── audit_report.txt
├── .claude/
│   └── skills/
│       └── moon-dev-trading-agents/ ← Claude Code integration
└── docs/
    └── examples/
```

### Execution Flow (Simplified)

```
┌──────────────────┐     ┌──────────────────────────┐     ┌────────────────┐
│   OHLCV Feeds    │────▶│ 03_strategy_development    │────▶│  Strategy .py  │
└──────────────────┘     │ (Claude / GPT generators)  │     └───────┬────────┘
                         └──────────────────────────┘             │
                                                                  ▼
                         ┌──────────────────────────┐     ┌────────────────────┐
                         │ 04_validation_testing    │◀────│ backtesting.py     │
                         │   (backtest_runners)     │     │   (core engine)    │
                         └───────────┬──────────────┘     └────────────────────┘
                                     │
                                     ▼
                         ┌──────────────────────────┐
                         │ _data_storage/rbi_vX/  │
                         │ execution_results/*.json │
                         └──────────────────────────┘
```

---

## 2. Execution Result JSON Schema

Every execution artifact under `_data_storage/` shares the **exact same top-level envelope**. There are **no structured trade arrays** or per-bar equity curves at the JSON layer.

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | `true` when `return_code == 0` |
| `return_code` | `int` | Shell exit code (always `0` in stored runs) |
| `stdout` | `str` | Complete emoji-rich strategy log + `backtesting.py` summary block |
| `stderr` | `str` | Python warnings (usually `UserWarning` about `pd.DateTimeIndex`) |
| `execution_time` | `float` | Wall-clock runtime in seconds (~1.3–1.6 s per run) |
| `timestamp` | `str` | ISO-8601 timestamp of the run (`YYYY-MM-DDTHH:MM:SS...`) |

### Top-Level Example

```json
{
  "success": true,
  "return_code": 0,
  "stdout": "🌙 Moon Dev: Initializing …\n…",
  "stderr": "",
  "execution_time": 1.580923,
  "timestamp": "2025-10-25T06:09:27.662132"
}
```

### PnL Calculation
PnL is **computed inside `backtesting.py`**, not stored as structured JSON fields. The engine calls:

```python
bt = Backtest(data, StrategyClass, cash=<variable>, commission=0.002)
```

- **Commission:** `0.002` (0.2 % of order value in the observed runs).
- **Cash:** varies by strategy / version (`100,000`, `1,000,000`, or `10,000,000`).
- **Trade PnL:**
  ```
  PnL = (ExitPrice - EntryPrice) * Size * Direction - Fees
  ```

### Metrics Stored Per Trade
Per-trade records exist **only inside `stdout`** as a printed `backtesting.py` `_trades` DataFrame. In every JSON log the DataFrame body is truncated to `...`, so the artifact captures:

| Metric (portfolio-level) | Source in stdout |
|--------------------------|-------------------|
| `# Trades` | Backtest summary block |
| `Win Rate [%]` | Backtest summary block |
| `Best / Worst / Avg. Trade [%]` | Backtest summary block |
| `Profit Factor` | Backtest summary block |
| `Expectancy [%]` | Backtest summary block |
| `SQN` | Backtest summary block |
| `Max. Drawdown [%]` | Backtest summary block |
| `Sharpe / Sortino / Calmar Ratio` | Backtest summary block |
| `Exposure Time [%]` | Backtest summary block |
| `_trades` DataFrame | Truncated (`...`); not parseable in JSON |

---

## 3. RBI Version Differences

| Version | Directory | Filename Convention | Architecture / Stdout Style | Strategies Found |
|---------|-----------|---------------------|----------------------------|------------------|
| **rbi (base)** | `_data_storage/execution_results/` or `rbi/03_14_2025/…` | `StrategyName_BT_YYYYMMDD_HHMMSS.json` | Legacy flat storage. Stderr reveals original Dropbox dev path (`src/data/rbi/`). | `CoTrendalNeutral` |
| **rbi_v2** | `rbi_v2/MM_DD_YYYY/execution_results/` | `StrategyName_HHMMSS.json` | Classic technical-indicator focus. Heavy "Moon Dev Debug" emoji logs. | `BandedReversion`, `BandedRSITrend`, `DynamicVWAPTrend`, `GannSMAConvergence`, `RsiBreakoutMomentum`, `VolatilityCorridorPutter`, `VolatilityDivergence`, `FibonacciDivergence` |
| **rbi_v3** | `rbi_v3/MM_DD_YYYY/execution_results/` | `StrategyName_HHMMSS.json` | Crossover + confluence emphasis. Prints `Backtest Bar` with SMA/EMA + Fibonacci levels. | `AdaptiveDivergence`, `GoldenCrossover` |
| **rbi_pp** | `rbi_pp/MM_DD_YYYY/execution_results/` | `T##_StrategyName_HHMMSS.json` | **Task-queue naming** (`T00`, `T02`, `T08`). Squeeze & breakout logic. Often prints `SL`, `TP`, `Size`, `Risk`. | `PulsarFlow`, `CascadeReversal`, `MomentumSqueeze` |

*Note:* `rbi_pp` likely stands for a **parallel pipeline** or **task-processor queue**, indicated by the `T##` task-slot prefix.

---

## 4. Complete Strategy Catalog (14 Strategies)

> **Universal Timeframe:** All backtests run on **15-minute bars** (Start: `2023-01-01 00:00:00`, End: `2023-11-20 19:15:00`, ~31,065 bars).

### 4.1 PulsarFlow *(rbi_pp)*
- **Indicators:** MFI (Money Flow Index), ADX, Volume
- **Entry Logic:** ADX must exceed a trend-strength threshold (~20–25). When ADX is strong, enter on MFI extremes (`MFI > 60` long, `MFI < 40` short) with sufficient volume.
- **Exit Logic:** Volume too low or ADX dropping back below threshold closes/skip position.
- **RBI Version:** `rbi_pp`
- **Sample Performance:** 0 trades in sampled run (choppy market / low ADX).

### 4.2 CascadeReversal *(rbi_pp)*
- **Indicators:** Consecutive bar streaks, Volume
- **Entry Logic:** Count consecutive down (or up) bars. After **4 consecutive down bars**, evaluate volume filter on the 4th bar. If volume is **not** excessive, enter long (contrarian reversal).
- **Exit Logic:** Opposite streak resets the position or stop/target hit.
- **RBI Version:** `rbi_pp`
- **Sample Performance:** 0 trades in sampled run (volume filter failed repeatedly).

### 4.3 MomentumSqueeze *(rbi_pp)*
- **Indicators:** Bollinger Bandwidth (`Bandwidth = (Upper − Lower) / Middle`), MACD
- **Entry Logic:** Detect **squeeze** (low bandwidth). Wait for a bullish breakout above recent high (or bearish below recent low). Confirm with MACD cross (`Bullish MACD cross confirmed!` / `Bearish MACD cross confirmed!`).
- **Exit Logic:** Time-based breakout-window expiry, or SL/TP hit. Stdout shows explicit risk sizing:
  ```
  SHORT ENTRY at 16655.52, SL: 16784.71, TP: 16397.13, Size: 77, Risk: 10000.00
  ```
- **RBI Version:** `rbi_pp`
- **Sample Performance:** 56 trades, 35.7 % win rate, +0.31 % return (1 M base).

### 4.4 CoTrendalNeutral *(rbi base)*
- **Indicators:** SMA50 proxy (implied from dynamic SL behavior), ATR (for SL/TP)
- **Entry Logic:** Continuous mean-reversion short entries against a fast moving average. Enters every bar with a tight SL (~24 pts) and TP (~73 pts), creating ~1:3 risk-reward.
- **Exit Logic:** Explicit `"Exit Short Position at X"` when stop or target is hit.
- **RBI Version:** `rbi` (legacy / base)
- **Sample Performance:** 5 trades, 0 % win rate, −3.0 % return (1 M base).

### 4.5 AdaptiveDivergence *(rbi_v3)*
- **Indicators:** Swing Highs / Swing Lows, RSI, ATR
- **Entry Logic:** Confirms swing points (`New swing low/high confirmed at bar X`). Trades **divergence** — e.g. bullish when price makes a lower low but RSI makes a higher low. Skips when ATR is below average (`Low volatility filter: ATR X <= Avg Y`).
- **Exit Logic:** Swing reversal or trailing stop.
- **RBI Version:** `rbi_v3`
- **Sample Performance:** 40 trades, 30 % win rate, −11.75 % return (1 M base).

### 4.6 GoldenCrossover *(rbi_v3)*
- **Indicators:** SMA20/50/100/200, RSI, ATR, Fibonacci retracement (61.8 %, 50 %)
- **Entry Logic:** Classic golden-cross style signal (fast SMA crosses above slow SMA) combined with RSI and ATR filters. Uses Fibonacci levels for confluence (`Fib Calc: 61.8% Level …`).
- **Exit Logic:** Trailing stop (`Position: Bars X, RR Y, Current SL Z`).
- **RBI Version:** `rbi_v3`
- **Sample Performance:** 33 trades, 12.1 % win rate, −8.30 % return (1 M base).

### 4.7 BandedReversion *(rbi_v2)*
- **Indicators:** Moving Average, ATR, RSI, dynamic Bands (`LowerBand`, implied `UpperBand`)
- **Entry Logic:** Mean-reversion when price touches or pierces the lower band (`MA - ATR * multiplier`, multiplier ≈ 1.5) with RSI confirmation.
- **Exit Logic:** Reversion toward MA.
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 0 trades in sampled run.

### 4.8 BandedRSITrend *(rbi_v2)*
- **Indicators:** RSI, dynamic RSI Bands (`Upper` / `Lower` on RSI itself), Price MA
- **Entry Logic:** RSI breaks above its upper band or below its lower band, confirmed by price relative to its MA.
- **Exit Logic:** RSI crosses back into neutral band.
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 264 trades, 10.6 % win rate, −17.48 % return (100 k base).

### 4.9 DynamicVWAPTrend *(rbi_v2)*
- **Indicators:** VWAP (cumulative), ADX
- **Entry Logic:** Enter only when price crosses VWAP **and** `ADX >= 25`. Weak ADX causes skip (`ADX too weak (<25), skipping trade`).
- **Exit Logic:** Price crosses back through VWAP or trailing stop.
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 1 trade, 0 % win rate, −4.98 % return (10 M base).

### 4.10 GannSMAConvergence *(rbi_v2)*
- **Indicators:** SMA5, Price
- **Entry Logic:** Long when price > SMA5 and SMA5 converges upward; short when price < SMA5 and falling.
- **Exit Logic:** Trailing stop hit (`Trailing Stop Hit! ✨ Closing Long Position`).
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 396 trades, 21.5 % win rate, −54.9 % return (100 k base).

### 4.11 RsiBreakoutMomentum *(rbi_v2)*
- **Indicators:** RSI, Close
- **Entry Logic:** Enter when RSI breaks out of a consolidation zone / threshold with momentum.
- **Exit Logic:** RSI reversion or stop/target.
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 0 trades in sampled run.

### 4.12 VolatilityCorridorPutter *(rbi_v2)*
- **Indicators:** VIX-SPX Correlation, VIX level, Expiration Day flag
- **Entry Logic:** Correlation and VIX must sit inside a specific "corridor" (range) to sell volatility / put spreads. Stdout format: `VIX-SPX Correlation: X | VIX: Y | Exp Day: False`.
- **Exit Logic:** Corridor break or options time-stop.
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 13 trades, 7.7 % win rate, −0.86 % return (100 k base).

### 4.13 VolatilityDivergence *(rbi_v2)*
- **Indicators:** Price, RSI, ATR
- **Entry Logic:** Detects **divergence** between price and RSI (`Bullish divergence detected! Price LL at X, RSI HL at Y`).
- **Exit Logic:** Divergence resolves or stop/target.
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 0 trades in sampled run.

### 4.14 FibonacciDivergence *(rbi_v2)*
- **Indicators:** Swing Highs / Lows, Trend confirmation, Fibonacci levels
- **Entry Logic:** Confirms swing structure (`Confirmed Swing High/Low at X on bar Y`), then uses trend direction and Fibonacci retracement for entries.
- **Exit Logic:** Swing reversal of opposite direction or trailing stop.
- **RBI Version:** `rbi_v2`
- **Sample Performance:** 109 trades, 33.0 % win rate, −8.97 % return (100 k base).

---

## 5. Key Engine Observations

1. **backtesting.py Is the Core:** Every strategy stdout ends with the exact same `backtesting.py` summary block (`_strategy`, `_equity_curve`, `_trades`). Strategy code is not present in this tree; only execution logs are stored.
2. **Capital Is Not Normalized:** `cash` varies across runs (`100k`, `1M`, `10M`), making cross-strategy comparison difficult without normalization.
3. **Position Sizing Is Risk-Based:** `rbi_pp` strategies explicitly compute `Size = Risk / abs(Entry − StopLoss)`, usually risking ~`$10,000` per trade.
4. **All JSONs Are Process Logs:** There is no separate `trades.json` or `metrics.json`. Everything lives inside `stdout`.
5. **Claude Integration:** `.claude/skills/moon-dev-trading-agents/` indicates the engine is designed to be driven or extended by Claude Code agents.
6. **Source Code Lives Elsewhere:** `stderr` paths (`/Users/md/Dropbox/dev/github/...`) show the actual `.py` files are maintained in a Dropbox-synced repo outside this storage-only tree.

---

*Report generated from full tree scan and sample extraction of 31+ execution logs across `rbi`, `rbi_v2`, `rbi_v3`, and `rbi_pp`.*
