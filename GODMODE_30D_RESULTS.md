# GODMODE 30-DAY BACKTEST RESULTS
Generated: 2026-05-16
Timerange: 2026-04-16 → 2026-05-16 (30 days)
Config: 17 pairs, 1h base, 3x leverage, futures

## RANKINGS (Profit%)

| Rank | Strategy                              | Trades | Profit%  | WR%   | DD%   | Sharpe(d) | Verdict          |
|------|---------------------------------------|--------|----------|-------|-------|-----------|------------------|
| 1    | P3E_HYPEROPT (unlimited stake)        | 758    | +179.15  | 80.6  | 4.68  | 16.18     | Compounding art. |
| 2    | P3E_KEY_LEVEL_BOOST                   | 60     | +6.71    | 86.7  | 0.70  | ~9.3      | STRONG           |
| 3    | P3F_KEY_LEVEL_TIGHT_TRAIL             | 60     | +6.28    | 86.7  | 0.70  | 9.27      | STRONG           |
| 4    | VectorStrategy baseline               | 11     | -0.44    | 72.7  | 0.80  | negative  | Flat/bleeding     |
| 5    | P3B_TIGHTER_TRAIL                     | 11     | -0.29    | 72.7  | 0.80  | negative  | Flat/bleeding     |
| 6    | P3A_RSI_DIVERGENCE_EXIT               | 11     | -0.57    | 63.6  | 0.80  | negative  | DESTRUCTIVE       |
| 7    | BollingerMeanReversion                 | 0      | 0.00     | 0     | 0     | —         | ZERO TRADES      |
| 8    | AroonMomentumEngine_V2                | 514    | -12.80*  | ~46   | 19.79 | -1.81     | DISASTER          |

*Note: AroonV2 from batch script parser — trades 514, WR likely 46.5% (239 wins/514)

## KEY 30d INSIGHTS

1. **P3E & P3F still dominate** — +6.7% and +6.3% in 30 days with 86.7% WR, <1% DD
2. **Only 60 trades in 30d** for P3E/P3F (2/day) vs 557 in 300d (1.9/day) — consistent 
3. **Baseline bleeding** — VectorStrategy has only 11 trades in 30d, -0.44%. Key level boost is essential.
4. **P3A still destructive** — drops WR from 72.7% to 63.6%, adds more losses
5. **AroonV2 still catastrophic** — over-trades massively with <50% WR
6. **P3E_HYPEROPT +179%** — unlimited stake compounding on 758 trades; unrealistic for production

## 30d vs 300d COMPARISON

| Strategy           | 300d Profit% | 30d Profit% | 300d WR% | 30d WR% | Trend      |
|--------------------|-------------|------------|---------|---------|-----------|
| P3F                | +129.70     | +6.28      | 88.5    | 86.7    | Consistent |
| P3E                | +129.05     | +6.71      | 86.9    | 86.7    | Consistent |
| Baseline           | +13.74      | -0.44      | 82.1    | 72.7    | Degrading  |
| P3A_RSI_DIV_EXIT   | +8.34       | -0.57      | 65.3    | 63.6    | Consistent bad |

## MIXIN STUBS CREATED

- `signal_bus_mixin.py` — unblocks 5 strategies (BollingerMeanReversion, EmaTrendFollowing, MacdRsiStrategy, RsiDivergenceStrategy, SupertrendEmaStrategy)
- `vdb_mixin.py` — unblocks 2 strategies (DmiAdxStrategy, ensemble_strategy)
- `shared_config/signal_bus.py` — unblocks ensemble_strategy shared bus
- All 7 previously broken strategies now import successfully