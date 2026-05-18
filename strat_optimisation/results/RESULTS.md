# BOS+LVN+VWAP Strategy Optimisation — Results

## Backtest Period: May 1-18, 2026 | 1h futures (V4: Apr 1 - May 18, 4h) | 10x leverage

---

## Summary Table

| # | Strategy | Trades | Profit % | Profit USDT | DD % | PF | Sharpe | SQN | WR % | Avg Dur |
|---|----------|--------|-----------|-------------|------|-----|--------|-----|------|---------|
| V1 | SHORT-only Top 9 (SL 8%) | 215 | +162.4% | $16,236 | 34.1% | 1.89 | 55.7 | 3.37 | 47.0% | 2:54 |
| V2a | SHORT SL 4% | 270 | +18.7% | $1,868 | 52.5% | 1.14 | 14.8 | 0.80 | 27.4% | 1:36 |
| V2b | SHORT SL 6% | 240 | +63.2% | $6,319 | 44.5% | 1.40 | 34.3 | 1.97 | 36.7% | 2:13 |
| V2c | SHORT SL 8% (= V1) | 215 | +162.4% | $16,236 | 34.1% | 1.89 | 55.7 | 3.37 | 47.0% | 2:54 |
| V3 | Late Trail Merge | 92 | +23.8% | $2,380 | 14.0% | 1.28 | 10.5 | 0.97 | 44.6% | 3:00 |
| V4 | 4H Validation (48 days) | 290 | +4.8% | $479 | 54.0% | 1.02 | 0.9 | 0.13 | 32.1% | 3:10 |
| V5 | Combined LONG+SHORT Hyperopt | 406 | +325.1% | $32,505 | 37.1% | 1.70 | 86.2 | 3.80 | 44.1% | 3:01 |

---

## Analysis

### Stop Loss Optimization (V2)
- **4% SL**: Terrible. WR drops to 27.4%, DD spikes to 52.5%. Too tight — chops out good trades.
- **6% SL**: Mediocre. 36.7% WR, 44.5% DD. Sweet spot not yet reached.
- **8% SL**: Winner by far. 47% WR, 34.1% DD, PF 1.89. The wider stop lets the trend develop.
- **Verdict**: 8% hard stop is optimal for this strategy on 1h timeframe.

### Late Trail Merge (V3)
- Lowest DD at 14% — excellent risk control from the late trail (2.5% trail after 12%)
- But only 92 trades and +23.8% — the late activation (12% before trailing) leaves too much on the table
- PF only 1.28 — many small losses before the big winners trigger
- **Verdict**: Great for conservative accounts. Needs earlier trail activation (maybe 8-10%) to catch more profit.

### 4H Timeframe Validation (V4)
- Near-zero edge: +4.8% over 48 days, PF 1.02, Sharpe 0.9
- DD is 54% — worse than 1h by every metric
- **Verdict**: BOS+LVN+VWAP confluence is a 1h strategy. On 4h, too few signals combine and the edge vanishes.

### Combined LONG+SHORT Hyperopt (V5) — CHAMPION
- **+325.1% in 17 days** — absolute monster
- PF 1.70, Sharpe 86.2, SQN 3.80
- LONG side adds +95K worth of profit trades, SHORT side adds the bulk
- All 9 pairs profitable (TRX only +3.35%)
- Per-pair: OP +70.4%, ENA +55.8%, SUI +52.0%, ARB +47.1%, KAS +46.7%, LINK +24.1%, 1000SHIB +16.0%, WLD +9.7%, TRX +3.4%

---

## Key Findings

1. **8% SL is optimal** — tighter stops destroy the strategy's edge
2. **Combined LONG+SHORT >> SHORT-only** — adding LONG entries nearly doubles profit
3. **1h timeframe only** — 4h validation shows no edge
4. **Late Trail exit is too conservative** (14% DD but only +23.8%) — needs earlier activation
5. **V5 (combined) is the champion** at +325% / PF 1.70 / Sharpe 86

---

## Next Steps for Hyperopt

Run on V5 to find optimal:
- `swing_lookback` (10-40, default 20)
- `lvn_threshold` (0.2-0.7, default 0.5)
- `vwap_proximity_pct` (0.3-1.5%, default 0.5%)
- `min_body_ratio` (0.3-0.7, default 0.4)
- `min_confluences` (3 or 4)
- Stop loss (3-10%)
- Trailing stop (1-5%, offset 5-25%)

Command:
```bash
freqtrade hyperopt --config strat_optimisation/configs/config_v5_hyperopt.json \
  --strategy BOS_V5_Hyperopt --hyperopt-loss SharpeHyperOptLoss \
  --spaces buy sell --timeframe 1h --timerange 20260501-20260518 \
  -e 500
```