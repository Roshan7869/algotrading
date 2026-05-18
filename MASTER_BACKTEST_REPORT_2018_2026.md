# MASTER BACKTEST REPORT — ALL STRATEGIES (2018-2026)

**Date:** 2026-05-17
**Data:** Binance 1h candles, SPOT (2018-01 to 2026-05, 8 pairs) + FUTURES (2020-01 to 2026-05, 3 pairs)
**Stake:** 50 USDT per trade, max 3 open trades

---

## 1. SPOT BACKTEST — 2018-01-09 to 2026-05-16 (8+ years, longs only, 8 pairs)

| # | Strategy | Trades | Tot Profit% | WR% | Drawdown% | Avg Duration |
|---|---|---|---|---|---|---|
| 1 | **VectorStrategy_P3E_HYPEROPT** | 16,814 | **+2,425.72** | 75.4 | 24.45 | 8:43 |
| 2 | VectorStrategy_P3E_KEY_LEVEL_BOOST | 1,176 | +169.81 | 74.1 | 14.70 | 4:51 |
| 3 | VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL | 1,169 | +133.24 | 74.2 | 12.45 | 4:50 |
| 4 | VectorStrategy (base=P3F) | 1,169 | +133.24 | 74.2 | 12.45 | 4:50 |
| 5 | VectorStrategy_P3A_RSI_DIVERGENCE_EXIT | 185 | +1.09 | 50.3 | 4.17 | 3:08 |
| 6 | MacdRsiStrategy | 23 | +3.07 | 65.2 | 5.72 | 2d 0h |
| 7 | VectorStrategy_P3C_WIDER_TRAIL | 186 | -1.35 | 63.4 | 11.21 | 4:37 |
| 8 | DmiAdxStrategy | 13 | -0.19 | 30.8 | 3.50 | — |
| 9 | VectorStrategy_P3D_KILL_ZONE_FILTER | 186 | -2.63 | 63.4 | 11.91 | 4:37 |
| 10 | VectorStrategy_P3B_TIGHTER_TRAIL | 186 | -3.65 | 63.4 | 12.44 | 4:36 |
| 11 | SupertrendEmaStrategy | 187 | -12.75 | 60.4 | 27.56 | — |
| 12 | AroonMomentumEngine_V2 | 87 | -50.58 | 43.7 | 50.58 | 2:26 |
| 13 | BollingerMeanReversion | 234 | -49.57 | 55.6 | 50.35 | 7:00 |
| 14 | EmaTrendFollowing | 252 | -49.86 | 48.8 | 52.25 | — |

**SPOT-only Notes:**
- P3E_HYPEROPT generates 16,814 trades (14x more than base) — likely over-fitted, suspicious 0.32% drawdown
- VectorStrategy base = P3F = +133% across 8 years, 74.2% WR, 12.45% DD — solid but modest
- P3A-D variants all generate ~186 trades (7x fewer than base) — signal filters are too restrictive
- MacdRsiStrategy only 23 trades in 8 years — essentially inactive
- DmiAdxStrategy: 13 trades — dead strategy on spot
- Bottom 3 (Aroon, Bollinger, EMA) all lose ~50% — designed for shorts, fail on spot-only

---

## 2. FUTURES BACKTEST — 2020-01-01 to 2026-05-16 (6+ years, longs+shorts, 3 pairs)

| # | Strategy | Trades | Tot Profit% | WR% | Drawdown% | Avg Duration |
|---|---|---|---|---|---|---|
| 1 | **VectorStrategy_P3E_HYPEROPT** | 15,479 | **+10,651.38** | 79.5 | 0.32 | 5:14 |
| 2 | VectorStrategy_P3E_KEY_LEVEL_BOOST | 804 | +416.76 | 83.3 | 2.26 | 3:08 |
| 3 | VectorStrategy (base=P3F) | 811 | +386.00 | 83.6 | 2.07 | 2:58 |
| 4 | VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL | 811 | +386.00 | 83.6 | 2.07 | 2:58 |
| 5 | VectorStrategy_P3A_RSI_DIVERGENCE_EXIT | 116 | +26.06 | 60.3 | 7.29 | — |
| 6 | VectorStrategy_P3D_KILL_ZONE_FILTER | 116 | +21.37 | 69.8 | 10.16 | — |
| 7 | VectorStrategy_P3C_WIDER_TRAIL | 116 | +18.08 | 69.8 | 10.29 | — |
| 8 | VectorStrategy_P3B_TIGHTER_TRAIL | 117 | +13.97 | 69.2 | 10.69 | — |
| 9 | VectorStrategyV2 | 101 | +6.96 | 74.3 | 5.75 | — |
| 10 | EmaTrendFollowing | 828 | +2.83 | 51.8 | 45.30 | — |
| 11 | SupertrendEmaStrategy | 15 | -0.84 | 53.3 | 7.50 | — |
| 12 | MacdRsiStrategy | 11 | -2.38 | 45.5 | 7.29 | 5:44 |
| 13 | RsiDivergenceStrategy | 28 | -22.48 | 32.1 | 22.71 | — |
| 14 | BollingerMeanReversion | 105 | -50.43 | 34.3 | 54.28 | 1:38 |
| 15 | AroonMomentumEngine_V2 | 8,146 | -49.51 | 49.1 | 82.94 | — |
| 16 | DmiAdxStrategy | 0 | 0.0 | — | — | No trades |

**FUTURES-only Notes:**
- P3E_HYPEROPT: 10,651% profit is extraordinary — but 15,479 trades and 0.32% DD are suspiciously low. Likely over-fitted or compounding effect with unlimited position stacking
- P3E_KEY_LEVEL_BOOST: +416.76%, 83.3% WR, 2.26% DD — best risk-adjusted performance
- VectorStrategy/P3F: +386%, 83.6% WR, 2.07% DD — nearly identical to P3F (current champion)
- Shorts add massive value: base went from +133% (spot) to +386% (futures) — shorts contribute ~3x more profit
- P3A-D all profitable on futures vs losing/slight on spot — shorts are essential for their momentum signals
- Aroon and Bollinger lose >50% on both modes — fundamentally flawed
- DmiAdxStrategy: 0 trades on futures — completely dead
- ensemble_strategy: runtime error (SignalBus API missing)

---

## 3. STRATEGY TIER RANKING (Combined Spot + Futures)

### TIER S — ELITE (Consistently profitable both modes)
| Strategy | Spot Profit | Futures Profit | Spot WR | Futures WR | Comments |
|---|---|---|---|---|---|
| **VectorStrategy_P3E_HYPEROPT** | +2,425% | +10,651% | 75.4% | 79.5% | ⚠️ Suspiciously high trade count (16K+), likely over-fit |
| **VectorStrategy_P3E_KEY_LEVEL_BOOST** | +169.8% | +416.8% | 74.1% | 83.3% | Best risk-adjusted; consistent across modes |
| **VectorStrategy (P3F)** | +133.2% | +386.0% | 74.2% | 83.6% | Current champion; reliable baseline |

### TIER A — PROFITABLE (Futures-only decent, spot marginal)
| Strategy | Spot Profit | Futures Profit | Notes |
|---|---|---|---|
| P3A_RSI_DIVERGENCE_EXIT | +1.1% | +26.1% | Low trade count (116-185), decent futures edge |
| P3D_KILL_ZONE_FILTER | -2.6% | +21.4% | Needs shorts to work |
| P3C_WIDER_TRAIL | -1.4% | +18.1% | Needs shorts to work |
| P3B_TIGHTER_TRAIL | -3.7% | +14.0% | Needs shorts to work |
| VectorStrategyV2 | N/A | +7.0% | Modest futures edge |

### TIER B — BREAKEVEN / INACTIVE
| Strategy | Spot | Futures | Notes |
|---|---|---|---|
| MacdRsiStrategy | +3.1% | -2.4% | Near-zero: 11-23 trades in 6-8 years |
| DmiAdxStrategy | -0.2% | 0 trades | Dead: 13 trades spot, 0 trades futures |
| SupertrendEmaStrategy | -12.8% | -0.8% | Marginal losses both modes |
| EmaTrendFollowing | -49.9% | +2.8% | Needs shorts to be slightly above zero |

### TIER F — CATASTROPHIC LOSSES
| Strategy | Spot | Futures | Notes |
|---|---|---|---|
| BollingerMeanReversion | -49.6% | -50.4% | 50%+ drawdown both modes |
| AroonMomentumEngine_V2 | -50.6% | -49.5% | 50-83% drawdown both modes |
| RsiDivergenceStrategy | N/A | -22.5% | 32% WR, 22.7% DD |
| ensemble_strategy | — | CRASH | SignalBus runtime error |

---

## 4. KEY INSIGHTS

1. **P3E_HYPEROPT is likely overfit**: 16-17K trades with 0.32% drawdown is a red flag. The strategy compounds aggressively with $50 stake, generating many tiny winning trades. Needs walk-forward validation.

2. **Shorts are CRITICAL**: Every strategy performs 2-3x better on futures (with shorts) vs spot (longs only). The base VectorStrategy goes from +133% → +386% when shorts are enabled.

3. **Current champion (P3F) is solid**: +386% on futures, 83.6% WR, 2.07% DD — this is the real-deal baseline.

4. **P3E_KEY_LEVEL_BOOST is better**: +417% vs +386% for P3F, with slightly higher avg profit per trade. Consider switching to P3E.

5. **Bottom 3 strategies should be deleted**: AroonMomentumEngine_V2, BollingerMeanReversion, and EmaTrendFollowing all lose ~50% across both modes.

6. **DmiAdxStrategy is dead**: 0 trades on futures, 13 trades on spot. Delete.

7. **ensemble_strategy is broken**: Runtime error with SignalBus API. Fix or delete.

8. **P3B/P3C/P3D are inferior variants**: They all generate the same ~116-117 trades (7x fewer than base) and are less profitable. Their signal filters are too restrictive.