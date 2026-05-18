# HEdge — ChromaDB-Powered Hedge Strategies

A dedicated collection of **9 hedge strategies** built from your local ChromaDB risk management principles, designed for freqtrade futures trading with 50/50 long-short capital split.

## Architecture

```
HEdge/
├── README.md                          ← this file
├── deploy.py                          ← copy strategies to user_data/strategies/
├── build_configs.py                   ← generate freqtrade config JSONs
├── strategies/
│   ├── hedge_01_fixed_fractional.py   ← Fixed Fractional 1% position sizing
│   ├── hedge_02_risk_to_zero.py       ← Breakeven stop at +3% move
│   ├── hedge_03_half_kelly.py         ← ½ Kelly Criterion sizing
│   ├── hedge_04_consec_loss_protect.py← Drawdown circuit breaker on losing streaks
│   ├── hedge_05_scale_out.py          ← 50%-30%-20% partial profit taking
│   ├── hedge_06_anti_martingale.py    ← Increase size on win streaks
│   ├── hedge_07_win_rate_adaptive.py  ← Dual-direction sizing (win/loss streaks)
│   ├── hedge_meta_7in1.py             ← Combined ensemble of all 7 principles
│   └── hedge_champion_p3f.py          ← P3F/P3E champion + tighter trail
├── configs/
│   └── config_hedge_*.json            ← 9 freqtrade configs (one per strategy)
└── scripts/
    └── run_all_backtests.sh           ← Backtest runner (sequential or tmux)
```

## Common Parameters (All Strategies)

| Parameter | Value |
|-----------|-------|
| Capital split | 50% long, 50% short |
| Leverage | 10x |
| Stop Loss | -10% (base; overridden by adaptive sizing) |
| Profit Target | +30% (with scale-outs where applicable) |
| Max open trades | 14 (7 long + 7 short) |
| Timeframe | 1h |
| Exchange | Binance Futures |
| Pairs | P2★ (17 pairs: NEAR, VET, ENA, ONDO, DOT, LINK, WLD, ARB, AVAX, SHIB, OP, KAS, SUI, DOGE, ALGO, TRX, XLM) |

## Strategy Descriptions

### 1. Fixed Fractional 1% (`hedge_01_fixed_fractional.py`)
**ChromaDB source:** "Fixed Fractional Position Sizing" (risk_management category)
- Risks exactly 1% of account per trade
- Position size = (balance × 0.01) / (entry_price × stop_loss_percent)
- Conservative baseline — most predictable risk profile
- Best for: high-volatility regimes where you want flat risk per trade

### 2. Risk to Zero ASAP (`hedge_02_risk_to_zero.py`)
**ChromaDB source:** "Risk to Zero ASAP" (risk_management category, score 0.689)
- Activates breakeven stop once position is +3% in profit
- After breakeven, trails stop with 0.5% offset
- Free trade after hitting +3% — no downside remaining
- Best for: capturing extended moves while eliminating all risk early

### 3. Half-Kelly (`hedge_03_half_kelly.py`)
**ChromaDB source:** "Kelly Criterion Fractional Position Sizing" (position_sizing category)
- Uses ½ Kelly fraction (≈24.7% of bankroll at 40% win rate, 2:1 R:R)
- Optimal growth with reduced volatility vs full Kelly
- Dynamic sizing based on win rate and realized R:R from last 50 trades
- Best for: maximizing long-term geometric growth, swing trading

### 4. Consecutive Loss Protection (`hedge_04_consec_loss_protect.py`)
**ChromaDB source:** "Consecutive Loss Protection" pattern synthesized from:
- "Risk Management: Maximum Consecutive Losses" (score 0.601)
- "Stop-Loss and Risk Management: Avoiding the 5-Loss Trap"
- Reduces position size 25% after 3 consecutive losses, 50% after 5, stops after 7
- Reset counter on any win
- Best for: protecting against drawdown spirals in choppy markets

### 5. Scale Out 50-30-20 (`hedge_05_scale_out.py`)
**ChromaDB source:** "Scale-Out Strategy 50-30-20" (trade_management category)
- Exits 50% at +10%, 30% at +20%, lets 20% run with trailing stop (0.03 offset)
- Locked-in profits reduce psychological pressure on runner
- Weighted average exit ≈ +15% if all targets hit
- Best for: trending markets where you want to capture most of the move

### 6. Anti-Martingale (`hedge_06_anti_martingale.py`)
**ChromaDB source:** "Anti-Martingale Risk Scaling" pattern from risk management principles
- Increases position size 50% after each win (cap at 4% of wallet)
- Resets to base 1% on any loss
- Rides hot streaks, cuts quickly on cold streaks
- Best for: high-win-rate strategies in trending conditions

### 7. Win Rate Adaptive (`hedge_07_win_rate_adaptive.py`)
**ChromaDB source:** "Win Rate Adaptive Position Sizing" (position_sizing category)
- Tracks rolling 50-trade win rate
- +25% sizing after 3 consecutive wins, +50% after 5 wins
- -25% sizing after 2 consecutive losses, -50% after 3 losses
- Adjusts signal sensitivity threshold based on win rate zone
- Best for: self-correcting systems that adapt to changing market conditions

### 8. Meta 7-in-1 (`hedge_meta_7in1.py`)
**ChromaDB source:** All 7 principles combined in layered hierarchy
- Layer 1: Win Rate Adaptive → sets signal sensitivity
- Layer 2: Anti-Martingale → adjusts sizing multiplier
- Layer 3: Consecutive Loss Protection → circuit breaker override
- Layer 4: Half-Kelly → caps maximum position size
- Layer 5: Fixed Fractional → ensures minimum risk control floor
- Layer 6: Risk to Zero ASAP → moves stop to breakeven
- Layer 7: Scale Out → partial exits at profit targets
- Each layer can be toggled independently (configurable)
- Best for: maximum robustness across all market conditions

### 9. Champion P3F (`hedge_champion_p3f.py`)
**ChromaDB + Project Champions:** Based on VectorStrategy P3F/P3E
- P3E_KEY_LEVEL_BOOST: **+934%** return, 84.1% win rate, 0.93% max DD (6yr)
- P3F_KEY_LEVEL_TIGHT_TRAIL: **+901%** return, 84.8% win rate, 0.96% max DD
- 5 signal categories: squeeze_breakout, mean_reversion, ema_alignment, expansion, key_level
- +1 key_level_boost confluence when very close to support/resistance
- Minimum 2/5 signal confluence for entry
- Tighter trail at +3% (offset 0.03 was 0.04) — Risk to Zero ASAP style
- Best for: proven champion mechanics with hedge-specific overlays

## Getting Started

### 1. Deploy strategies to freqtrade

```bash
cd /home/roshan/Downloads/Algotrading/HEdge
python3 deploy.py
```

### 2. Generate config files

```bash
python3 build_configs.py
```

### 3. Run backtests

**Sequential:**
```bash
bash scripts/run_all_backtests.sh
```

**Parallel (tmux):**
```bash
bash scripts/run_all_backtests.sh --tmux
```

**Single strategy backtest:**
```bash
freqtrade backtesting \
  --config configs/config_hedge_champion_p3f.json \
  --timerange 20250101- \
  --timeframe 1h \
  --export signals \
  --breakdown month
```

## ChromaDB Sources

All strategies reference risk management principles from your local vector database:

```bash
# Query source principles
python3 strategy_db/gcode_bridge.py query "risk management position sizing"
python3 strategy_db/gcode_bridge.py query "fixed fractional kelly criterion"
python3 strategy_db/gcode_bridge.py query "consecutive loss protection anti-martingale"
```

## Performance Expectations

| Strategy | Win Rate (est.) | Avg R:R | Drawdown (est.) |
|----------|----------------|---------|-----------------|
| Fixed Fractional | moderate | low | lowest |
| Risk to Zero | moderate | moderate | low |
| Half-Kelly | moderate-high | high | moderate |
| Consec Loss Protect | moderate | moderate | low |
| Scale Out | moderate | moderate-high | low |
| Anti-Martingale | high (streaks) | moderate | moderate |
| Win Rate Adaptive | high | moderate-high | low-moderate |
| Meta 7-in-1 | **varies** | **varies** | **lowest combined** |
| Champion P3F | **high (~84%)** | **high (~2:1)** | **very low (<1%)** |

## Files

| File | Lines | Size | Purpose |
|------|-------|------|---------|
| `hedge_01_fixed_fractional.py` | 136 | 5,441 B | Base conservative sizing |
| `hedge_02_risk_to_zero.py` | 140 | 5,531 B | Breakeven + trail protection |
| `hedge_03_half_kelly.py` | 148 | 5,843 B | Optimal growth sizing |
| `hedge_04_consec_loss_protect.py` | 149 | 5,895 B | Streak-based circuit breaker |
| `hedge_05_scale_out.py` | 141 | 5,605 B | Partial profit taking |
| `hedge_06_anti_martingale.py` | 133 | 5,183 B | Win streak riding |
| `hedge_07_win_rate_adaptive.py` | 151 | 5,917 B | Adaptive dual-direction sizing |
| `hedge_meta_7in1.py` | 252 | 9,601 B | Combined ensemble of all 7 |
| `hedge_champion_p3f.py` | 329 | 12,844 B | P3F champion + tighter trail |
| `deploy.py` | 64 | 1,921 B | Deploy script |
| `build_configs.py` | 71 | 2,802 B | Config builder |
| `run_all_backtests.sh` | 79 | 2,347 B | Backtest runner |
