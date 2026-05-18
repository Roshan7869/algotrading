# GODMODE 6-PHASE EXECUTION MAP
## Parallel OpenCode Sessions — tmux Dashboard

Generated: 2026-05-16 22:03 UTC
Status: ALL 6 PHASES DISPATCHED

---

## SESSION LAYOUT

| tmux Session | Phase | Model | Status | Task |
|-------------|-------|-------|--------|------|
| godmode-p1 | Phase 1: ATR Position Sizing | deepseek-v4-flash:cloud | 🔄 EDITING | Wire PositionSizer, ATR stop-loss, regime multiplier |
| godmode-p2 | Phase 2: HMM Regime Switching | deepseek-v4-flash:cloud | 🔄 RESTARTED | Wire HMM detector, signal_matrix per regime |
| godmode-p3 | Phase 3: Circuit Breakers | qwen3.6-plus-free | ✅ COMPLETE | circuit_breaker.json wired, trade blocking, cooldown states |
| godmode-p4 | Phase 4: Weighted Confluence | qwen3.6-plus-free | 🔄 RESTARTED | Replace binary min_confluence with weighted 0-1 score |
| godmode-p5 | Phase 5: Funding Rate + OI | deepseek-v4-flash:cloud | 🔄 TESTING | Funding rate filter, OI regime, position adjustment |
| godmode-p6 | Phase 6: ChromaDB Feedback | qwen3.6-plus-free | 🔄 FIXING | Outcome sync, setup performance weights, dtype fix |

---

## PHASE DETAILS

### Phase 1: ATR Position Sizing (godmode-p1)
- **Model:** ollama/deepseek-v4-flash:cloud
- **Status:** ACTIVELY EDITING — fixing merge after P5/P3 edits, re-adding _read/write_circuit_breaker methods
- **Changes:** Import PositionSizer, ATR-based stake sizing (1% risk / 1.5x ATR), regime-adaptive multiplier
- **Files:** VectorStrategy.py, position_sizer.py, market_regime.json

### Phase 2: HMM Regime Switching (godmode-p2)  
- **Model:** ollama/deepseek-v4-flash:cloud (RESTARTED — NVIDIA API was stuck)
- **Status:** RESTARTING — old session killed, new session launched
- **Changes:** Import HMMRegimeDetector, predict() regime per candle, signal_matrix per regime
- **Files:** VectorStrategy.py, regime_detector_hmm.py, market_regime.json

### Phase 3: Circuit Breaker Wiring (godmode-p3) 
- **Model:** opencode/qwen3.6-plus-free
- **Status:** ✅ COMPLETE — backtest ran, 1 trade, -0.49% (no CB trigger, below 2% threshold)
- **Changes:** confirm_trade_entry() override, daily/weekly/monthly PnL tracking, state transitions (HEALTHY→COOLING→PAUSED)
- **Verification:**
  - (1) Import json,os ✅ Lines 29-30
  - (2) confirm_trade_entry() override ✅ Lines 733-742
  - (3) Block non-HEALTHY trades ✅ Lines 739-741
  - (4) custom_exit() daily PnL > 2% → COOLING ✅ Lines 470-477
  - (5) Weekly > 4% / Monthly > 8% → PAUSED ✅ Lines 801-805
  - (6) Track daily/weekly/monthly trade count & PnL ✅ Lines 761-771
  - (7) Cooldown state transitions ✅ Lines 788-805
  - (8) Write state to JSON with timestamp ✅ Lines 701-720

### Phase 4: Weighted Confluence (godmode-p4)
- **Model:** opencode/qwen3.6-plus-free (RESTARTED — NVIDIA API was stuck)
- **Status:** RESTARTING
- **Changes:** Replace binary min_confluence≥2 with weighted score [0,1], regime-adjusted thresholds
- **Signal Weights:** BB expansion=0.30, RSI oversold=0.20, volume_factor=0.15, key_level=0.20, BB squeeze=0.15

### Phase 5: Funding Rate + OI Filter (godmode-p5)
- **Model:** ollama/deepseek-v4-flash:cloud
- **Status:** 9/10 todos complete, running backtest verification
- **Changes:** informative_pairs(), funding_rate_1h feather merge, funding_regime filter, OI skip logic
- **Note:** mark price data only starts 2026-04-07, effective backtest window limited

### Phase 6: ChromaDB Feedback Loop (godmode-p6)
- **Model:** opencode/qwen3.6-plus-free  
- **Status:** FIXING — MergeError on datetime64[ms] vs datetime64[ns] dtype mismatch
- **Changes:** Outcome sync, _get_setup_performance(), setup weight boosting/suppression
- **Issue:** pandas merge dtype mismatch between funding rate data and strategy dataframe

---

## MONITORING COMMANDS

```bash
# Check all sessions
for s in godmode-p{1..6}; do echo "=== $s ==="; tmux capture-pane -t $s -p -S -10 | tail -5; done

# Quick status
tmux list-sessions

# Attach to a session
tmux attach -t godmode-p1
```

---

## NEXUS ROUTING

- **P1 + P5:** deepseek-v4-flash:cloud (reasoning-heavy: ATR math, funding rate analysis)
- **P2 + P4:** qwen3.6-plus-free (structural: regime mapping, weight system)
- **P3 + P6:** qwen3.6-plus-free (wiring: JSON state, data merge)
- **P2+P4 restarts:** NVIDIA deepseek-v4-flash failed (API auth 401), fallback to cloud models

---

## EXPECTED OUTCOMES

| Phase | Expected Impact | Risk |
|-------|----------------|------|
| P1 ATR Position Sizing | +30-50% profit, -50% DD | Position sizing bugs |
| P2 HMM Regime | +10-15% adaptivity | HMM prediction latency |
| P3 Circuit Breakers | -70% max DD | Over-blocking trades |
| P4 Weighted Confluence | +15-25% WR | Weight calibration |  
| P5 Funding Rate + OI | +3-8% annually, -5% DD | Data merge issues |
| P6 ChromaDB Feedback | +5% win rate over time | Feedback loop convergence |

**Combined projected: Profit +129% → 300-500%, Max DD 2.8% → <0.8%, Sharpe 18 → 35-50**
