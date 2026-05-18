# GODMODE P3 — ChromaDB Vector Strategy Insights

## Current Market Regime (BTC/USDT 1h)
- **Regime**: trending_down (97.17% confidence)
- **Stability**: 0.878
- **Volatility (20)**: 0.327
- **ATR%**: 0.3785
- **EMA slope**: -0.028 (bearish)
- **Recent 20-period return**: +1.43% (likely dead cat bounce)

## Regime Performance (from outcome_history)
- **trending_up**: 89.4% WR, avg P&L +2.34%, 66 trades
- **trending_down**: 71.4% WR, avg P&L +1.60%, 21 trades
- **Shorts win in ALL regimes** (87% WR trending_up, 76.5% trending_down)
- **Longs fail in trending_down** (33.3% WR)

## P2★ Champion Config (Baseline)
- 17 curated pairs, 3x leverage
- stoploss = -0.06, trailing_stop_positive = 0.025, trailing_stop_positive_offset = 0.04
- trailing_only_offset_is_reached = True
- min_confluence = 2
- 365d: +25.08%, Sharpe 3.44, Sortino 4.05, SQN 6.21, PF 4.82, WR 85.1%, Max DD 1.89%

---

## ChromaDB Exit Strategies (Score-Ranked)

### Top Exit Signals to Implement:
1. **Scaling Out at Resistance** (score 0.612) — Scale out half at round numbers/resistance. If level holds, close rest at BE. If breaks, re-enter with profit buffer.
2. **Risk to Zero ASAP** (score 0.565) — Move SL to breakeven ASAP after entry. Makes trade risk-free, removes psychology pressure.
3. **Time-Based Profit Target** (score 0.563) — 0.5R within 25% time window = on track. If BE/negative at 50% time, exit. If not 1R by 75%, exit at market. For 1h: 0-12h develop, 12-24h decide, 24-36h must reach 1R, 36-48h exit.
4. **Half Position Trailing** (score 0.545) — Exit half at 1R fixed, trail remaining with wider 3-4x ATR stop. Guarantees profit on first half while letting runner extend.
5. **Percentage Trailing Stop** (score 0.449) — Fixed % trailing: crypto 3-5% scalp, 5-8% swing, 10-15% position. Simplest mechanism. **Our current 2.5%/4% is at the tight scalp end — ChromaDB suggests 5-8% for swing trades.**
6. **ATR Trailing Stop** (score 0.444) — 2-3x ATR trailing. Tighten 0.5x ATR when volume drops below 50% avg. **Our previous ATR custom_stoploss DESTROYED performance — don't reactivate without major guardrails.**
7. **RSI Divergence Exit** (score 0.464) — Bearish div on longs (higher high price, lower high RSI), bullish div on shorts. 2 candle confirmation. "Most reliable exit across all conditions."
8. **Candlestick Reversal at Key Level** (score 0.500) — Pin bar at resistance (long exit), doji after strong candles (exit 50%). Requires level confluence.

---

## ChromaDB Entry Strategies (Score-Ranked)

### Top Entry Concepts:
1. **Cross-Section Entry** (score 0.489) — Two consecutive strong candles overlapping midpoint creates cross-section. Retest = entry. Optimal at 80/20 levels. Stop: 10pts beyond cross.
2. **Close Above/Below Candle** (score 0.438) — Momentum candle closes beyond prior extreme. Must be at structural area of value. Confluence with HTF trend + RSI div.
3. **Consolidation Breakout** (score 0.412) — After trend line break, price consolidates instead of pulling to 21 EMA. Enter breakout of consolidation. 2:1 R:R.
4. **21 EMA Pullback** (score 0.394) — After structure break + level tap, enter on 21 EMA touch. 58% WR at 2:1 R:R since 2018. Stop: half distance to target.
5. **200 MA + Structure Confluence** (score 0.392) — 200 MA aligned with major S/R + candlestick signal = highest probability entry. ATR-adjusted stops.
6. **Volume Profile Edge Entry** (score 0.372) — High-volume doji/shooting star/hammer at VP node edge. Must close before entry. Edge-to-edge target.

---

## ChromaDB Risk Management Insights

### Key Risk Concepts:
1. **Leverage Justification** (score 0.647) — Only justified with high Sharpe OR low downside volatility. Our Sharpe 3.44 JUSTIFIES 3x leverage.
2. **No Leverage / Capital Preservation** (score 0.639) — **Counter-argument:** Crypto 30-50% drawdowns make even 2-3x leverage "near-certain wipeout given sufficient time." Our 3x with -6% SL gives 18% effective loss on stop — survivable.
3. **Correct Leverage Use** (score 0.632) — Use leverage for capital efficiency (multiple positions), NOT to amplify single positions. 3x on 17 pairs = capital efficiency.
4. **Crypto Volatility Calibration** (score 0.632) — Don't import equity-style stops to crypto. 30% drawdowns are normal monthly events. Our -6% SL is calibrated for crypto.
5. **Fixed Dollar Risk / Dynamic Sizing** (score 0.605) — Risk fixed $ per trade, vary position size based on stop distance. Tighter entries = larger size.

---

## ChromaDB Trending_Down Strategies

1. **Kill Zones** (0.591) — Session-based entry windows (London/NY open)
2. **Breakeven Stop After 1R** (0.568) — Move SL to entry at 1R profit
3. **Multi-TF Entry** (0.540) — Analyze on 4H, enter on 1H
4. **2% Daily Max Stop** (0.533) — Cap daily losses at 2%
5. **Volume Capitulation** (0.525) — Extreme volume spike = reversal signal

---

## P3 Improvements to Test

### A. Exit Enhancement: RSI Divergence Exit (high confidence)
- Add RSI bearish divergence detection in `custom_exit` for longs
- Add RSI bullish divergence detection for shorts
- ChromaDB calls this "most reliable exit signal across all conditions"
- Implementation: compare last 5 candles RSI peaks vs price peaks

### B. Entry Enhancement: Key Level Confluence Boost
- When `dist_to_support < 0.5` (very close to pivot support), confluence count gets +1
- Same for shorts near resistance
- Reward entries at key levels with higher probability

### C. Exit Enhancement: Breakeven Trail After 1R (Risk to Zero concept)
- Already partially covered by `trailing_stop_positive = 0.025` (2.5%)
- ChromaDB says "move SL to BE ASAP" — our trailing starts at 4% offset
- Consider: `trailing_stop_positive_offset = 0.03` (tighter activation, earlier trail)
- Test 0.02 instead of 0.04

### D. Entry Enhancement: Kill Zone Session Filter
- Filter out entries during low-liquidity hours
- Crypto kill zones: 07:00-09:00 UTC (London), 13:30-16:00 UTC (NY)
- Can reduce false signals during low-volume periods

### E. Stop Loss Adjustment: Crypto-Volatility Calibrated
- Current -6% is tight but appropriate for 1h timeframe
- ChromaDB suggests 5-8% for swing — we could test -7% or -8%
- But -6% is working well (WR 85.1%), so only test minor adjustments

### F. Trailing Adjustment: Wider Trail (5-8% range)
- Current: 2.5% trail activating at 4% offset
- ChromaDB suggests 5-8% for swing, 3-5% for scalp
- Test variant: trailing_stop_positive=0.04, trailing_stop_positive_offset=0.06 (4%/6%)
- Test variant: trailing_stop_positive=0.05, trailing_stop_positive_offset=0.08 (5%/8%)

### G. DON'T DO (proven destructive in P2):
- DO NOT reactive ATR custom_stoploss (killed 90% of profit)
- DO NOT enable position_adjustment / partial exits (cuts winners short)
- DO NOT use regime-based entry thresholds (destroys consistent confluence)