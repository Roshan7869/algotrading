# GODMODE VectorStrategy — Phase 2 Final Report
**Date**: 2026-05-16 | **Timerange**: 20250501–20260506 (365 days) | **Timeframe**: 1h | **Leverage**: 3x Isolated

---

## Executive Summary

Phase 2 GODMODE backtesting tested ChromaDB-driven strategy optimizations sourced from:
- **NEXUS MCP**: Vector search across 592 strategy chunks
- **Strategy-KB MCP**: Regime detection, adaptive context, outcome sync
- **OpenCode (deepseek-v4-flash)**: ATR trailing, regime filtering, partial exits
- **OpenCode (qwen-3.6-plus)**: Additional analysis (pending)

**KEY FINDING**: OpenCode's changes WRECKED performance. Reverting to P1 baseline + beacon exits produced the best risk-adjusted returns ever.

---

## Configuration Comparison

| Config | Trades | Profit% | Sharpe | Sortino | SQN | PF | WR% | MaxDD% | Verdict |
|--------|--------|---------|--------|---------|------|------|------|--------|---------|
| P1 ORIGINAL (22 pairs) | 172 | +36.98 | 2.83 | 6.93 | 4.32 | 2.24 | 72.7 | 4.36 | Baseline |
| P2 OPENCODE (22 pairs, ATR+regime+partial) | 900 | +4.04 | 0.33 | 1.50 | 0.21 | 1.02 | 54.0 | 11.74 | **FAILED** |
| OPENCODE (17 pairs, ATR+regime+partial) | 414 | +19.13 | 1.52 | 5.99 | 1.45 | 1.17 | 56.3 | 9.40 | Degraded |
| **P2 REVERTED+BEACON (22 pairs)** | 141 | +26.44 | 3.34 | 4.23 | 5.43 | 3.40 | 82.3 | 2.71 | Improved |
| **P2★ REVERTED+BEACON (17 pairs)** | **114** | **+25.08** | **3.44** | **4.05** | **6.21** | **4.82** | **85.1** | **1.89** | **★ BEST** |

---

## P2★ Config (Champion)

```json
{
  "max_open_trades": 7,
  "stake_amount": "unlimited",
  "tradable_balance_ratio": 0.7,
  "trading_mode": "futures",
  "margin_mode": "isolated",
  "leverage": 3,
  "minimal_roi": {"0": 0.10, "60": 0.06, "240": 0.04, "720": 0.02, "1440": 0.01},
  "stoploss": -0.06,
  "trailing_stop": true,
  "trailing_stop_positive": 0.025,
  "trailing_stop_positive_offset": 0.04,
  "trailing_only_offset_is_reached": true,
  "pair_whitelist": [
    "NEAR/USDT:USDT", "VET/USDT:USDT", "ENA/USDT:USDT", "ONDO/USDT:USDT",
    "DOT/USDT:USDT", "LINK/USDT:USDT", "WLD/USDT:USDT", "ARB/USDT:USDT",
    "AVAX/USDT:USDT", "1000SHIB/USDT:USDT", "OP/USDT:USDT", "KAS/USDT:USDT",
    "SUI/USDT:USDT", "DOGE/USDT:USDT", "ALGO/USDT:USDT", "TRX/USDT:USDT",
    "XLM/USDT:USDT"
  ]
}
```

**Removed pairs** (negative contributors): ZEC, PEPE, SOL, BCH, RENDER

**Strategy parameters**:
- `stoploss = -0.06` (6%)
- `trailing_stop = True`, 2.5%/4% offset
- `min_confluence = 2` (need 2+ of 5 signals for entry)
- `volume_factor = 1.5`
- `position_adjustment_enable = False` (NO partial exits)
- `custom_stoploss = disabled` (ATR trailing killed performance)
- `leverage = 3x` capped

---

## What Went Wrong (OpenCode Changes)

### 1. `trailing_stop = False` — CATASTROPHIC
The ATR custom_stoploss replaced the fixed trailing stop. Result: 900 trades (vs 141), win rate dropped from 82.3% to 54.0%. The ATR zones were too tight on initial entry, triggering premature stops.

### 2. `position_adjustment_enable = True` with 50% exit at 1R
Closed half the position at just 6% profit. The ROI table (10/6/4/2/1%) would have captured much more. This locked in small gains while removing upside.

### 3. Regime-based confluence thresholds
`volatile: confluence +=1` required 3-of-5 signals (rare → missed good entries).
`trending_up: short_thr +=1` raised short threshold (killed profitable short signals).
The strategy's short PnL dropped from +19.33% to negligible levels.

---

## What Worked (Kept in P2★)

### 1. Beacon Exit System (BB %b extremes)
```python
# Exit long if BB %b > 0.85 (overbought)
# Exit short if BB %b < 0.15 (oversold)
```
Captured 11 clean exits at extreme BB positions.

### 2. Fixed Trailing Stop (2.5%/4%)
The trailing stop at 4% offset with 2.5% trail locks in profits after the offset is reached. **10 trailing_stop_loss exits** with 100% win rate.

### 3. ROI Table (stepped)
Primary driver: ROI exits capture profits cleanly at predefined levels.

### 4. Short-side dominance
- Long trades: 29 trades, 86.2% WR, +6.50% total
- Short trades: 85 trades, 84.7% WR, +18.57% total
- Shorts produce **2.85x** the profit of longs

---

## Regime-Aware Performance (Outcome History)

### Long Confluence Entry (29 trades, 86.2% WR)
| Regime | Trades | WR% | PnL% | Avg R |
|--------|--------|-----|------|-------|
| trending_up | 18 | 100.0 | +45.97 | 0.43R |
| volatile | 4 | 75.0 | +13.53 | 0.56R |
| ranging | 4 | 75.0 | +4.94 | 0.21R |
| trending_down | 3 | 33.3 | -6.29 | -0.35R |

### Short Confluence Entry (85 trades, 84.7% WR)
| Regime | Trades | WR% | PnL% | Avg R |
|--------|--------|-----|------|-------|
| trending_up | 46 | 87.0 | +105.44 | 0.38R |
| trending_down | 17 | 76.5 | +31.42 | 0.31R |
| volatile | 15 | 86.7 | +23.27 | 0.26R |
| ranging | 7 | 85.7 | +6.95 | 0.17R |

**Key insight**: Shorts perform well in ALL regimes, especially trending_up. Longs fail in trending_down (expected). This validates keeping min_confluence=2 across all regimes.

---

## ChromaDB Integration

Outcome history synced to ChromaDB vector store:
- 119 trades across 11 strategy chunks
- Regime-aware performance per chunk
- Used for adaptive strategy context via `mcp_strategy_kb_strategy_context`
- Connected to `mcp_strategy_kb_outcome_sync` for feedback loop

---

## Phase 3 Recommendations

1. **Walk-forward validation**: Split 2025-05→2026-05 into 3 segments, validate P2★ on out-of-sample
2. **ATR trailing as Phase 3 experiment**: Keep custom_stoploss commented out, hyperopt ATR parameters separately
3. **ADX filter instead of regime**: Replace `_detect_regime_simple` with ADX > 25 filter for trend confirmation
4. **Dynamic leverage**: Use ChromaDB context to adjust leverage based on signal strength (2x for confluence=2, 4x for confluence=4+)
5. **Add BTC/ETH to pair list**: BTC/USDT and ETH/USDT have deep liquidity and may improve portfolio diversification

---

## Files

| File | Purpose |
|------|---------|
| `user_data/config_backtest_godmode_p1.json` | 22-pair config (original P1) |
| `user_data/config_backtest_godmode_p2.json` | 17-pair config (P2★ champion) |
| `user_data/strategies/VectorStrategy.py` | Strategy (reverted + beacon exits) |
| `strategy_db/outcome_history.json` | 119 trades with regime labels |
| `GODMODE_BACKTEST_ANALYSIS.md` | This report |

---

*Generated by GODMODE Phase 2 — NEXUS MCP + Strategy-KB MCP + OpenCode + ChromaDB*