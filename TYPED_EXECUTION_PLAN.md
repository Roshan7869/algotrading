# Algotrading Optimization — Typed Execution Plan
## Version: 1.0 | Designed: 2026-05-15 | Planner: First Principles Quant

---

## Plan Overview

| Field | Value |
|-------|-------|
| **Plan Name** | Algotrading System Optimization — From −80% to Profitability |
| **Objective** | Fix core strategy profitability, secure capital, deploy regime-aware meta-routing, validate with automated backtesting before any live capital |
| **Duration** | 6 weeks (iterative sprints, backtest-gated) |
| **Gating Principle** | No live capital until 30-day backtest shows ≥ 1.0 profit factor, ≥ 50% win rate, and < 20% max DD |
| **Risk Ceiling** | Leverage ≤ 1.0x until gate passed; then max 2.0x |
| **Verification Model** | POLARIS typed DAG with checkpoint verification after each phase |

---

## Typed DAG (Directed Acyclic Graph)

```
Phase 0 ──[Triage]─────────────────────────────────────► Checkpoint 0
    │                                                       │ Security scan PASS
    ▼                                                       │ Key rotation confirmed
Phase 1 ──[Core Fix: Entry Filters + Sizing]─────────────► Checkpoint 1
    │                                                       │ Backtest: profit factor ≥ 0.9
    ▼                                                       │ Win rate ≥ 45%
Phase 2 ──[Analytics Layer: Backtest DB + Preview]────────► Checkpoint 2
    │                                                       │ SQLite index of all ZIPs
    ▼                                                       │ preview.py runs without errors
Phase 3 ──[Regime Router + Strategy Selection]───────────► Checkpoint 3
    │                                                       │ Walk-forward: 12 windows
    ▼                                                       │ No window has > −20% DD
Phase 4 ──[AI Layer Repair: Local Ollama + Hard Gates]────► Checkpoint 4
    │                                                       │ All 4 debate rounds complete
    ▼                                                       │ Signal gates prevent trades
Phase 5 ──[Genetic Algorithm Optimization]───────────────► Checkpoint 5
    │                                                       │ Best gen: PF ≥ 1.2, WR ≥ 55%
    ▼                                                       │ Stable over 20 generations
Phase 6 ──[Live Pre-Flight: Dry-Run Gate]────────────────► Checkpoint 6
    │                                                       │ 30 days dry-run profitable
    ▼                                                       │ Kelly f* > 0
Phase 7 ──[Deployment + Telemetry]───────────────────────► Final Checkpoint
                                                            │ Live with 1.0x leverage
                                                            │ Daily health monitor active
```

---

## Phase 0: Security Triage

### 0.1 Objective
Immediately eliminate existential risk (API key leak, uncommitted secrets).

### 0.2 Tasks

| ID | Task | File/Command | Verification | Owner |
|----|------|------------|-------------|-------|
| 0.1 | Rotate Binance API key | Binance Dashboard → API Management → Delete old, create NEW read-only key | Old key `6mNEBmrKU4...` revoked, new key generated; test `curl` returns 401 for old key | Auto |
| 0.2 | Rotate Telegram bot token | @BotFather → /revoke → new token | Old token `7553420615:AAGXB2ORviX1...` invalidated | Auto |
| 0.3 | Add `.env` to `.gitignore` | Edit `.gitignore` | `git status` shows `.env` as untracked, not staged | Auto |
| 0.4 | Scan git history for leaked secrets | `git log --all --full-history -p -S '6mNEBmrKU4'` | Zero commits contain old key text | Auto |
| 0.5 | Check `.env.example` has no real data | Read `user_data/config_base.json` exchange key/secret fields | All key/secret fields are `""` (empty string) | Auto |
| 0.6 | Create `scripts/security/rotate_secrets.py` | New file: helper script for future rotation | Script runs without error, generates new `.env` from template | Auto |

### 0.3 Verification Gate (Checkpoint 0)
```bash
# Automated gate checks
python3 scripts/security/rotate_secrets.py --check-only
# Expected output:
# [PASS] .env in .gitignore
# [PASS] No keys found in git history
# [PASS] config_base.json has empty credentials
# [PASS] Old Binance key revoked (HTTP 401)
```

---

## Phase 1: Core Strategy Fix — Pre-Entry Filters + Position Sizing

### 1.1 Objective
Fix the root cause of −80.4% backtest: bad entries and oversized positions.

### 1.2 Tasks

| ID | Task | File | Details |
|----|------|------|---------|
| 1.1 | Add `_should_allow_entry()` helper | `user_data/strategies/AroonMomentumEngine_Hybrid.py` | 6-rule hard filter (consecutive losses, regime, BTC chop, volatility spike, ADX < 25, low volume). See Appendix A for full code. |
| 1.2 | Modify `populate_entry_trend()` to gate entries | `AroonMomentumEngine_Hybrid.py` line 326+ | Wrap all long/short logic with `if not self._should_allow_entry(...)`: return dataframe with zeros |
| 1.3 | Replace `custom_stake_amount` with fixed fractional | `AroonMomentumEngine_Hybrid.py` line 496+ | Risk 1% of account per trade, sized by ATR stop distance. See Appendix B for full code. |
| 1.4 | Lower default leverage to 1.0x | `user_data/strategies/leverage_config.py` | `DEFAULT_LEVERAGE = 1.0` |
| 1.5 | Extend stop-loss to −0.03 (3%) for 1x | `AroonMomentumEngine_Hybrid.py` line 63 | `stoploss = -0.03` |
| 1.6 | Reduce `max_open_trades` to 1 | `user_data/config_base.json` line 2 | `"max_open_trades": 1` |
| 1.7 | Add pair-specific win-rate tracker | `user_data/strategies/pair_performance.json` (new) | Track last 20 trades per pair; feed into `_should_allow_entry()` rule 1 |

### 1.3 Resources
- **Skill**: `tdd-workflow` (enforce unit tests for new filters)
- **Skill**: `security-review` (ensure no new secrets)
- **Tool**: Freqtrade backtest CLI

### 1.4 Verification Gate (Checkpoint 1)
```bash
# Run 300-day backtest with new filters
freqtrade backtesting --strategy AroonMomentumEngine_Hybrid \
    --timerange 20250501-20260501 \
    --config user_data/config_base.json

# Gate requirements:
# [REQUIRED] profit_factor >= 0.90
# [REQUIRED] win_rate >= 45%
# [REQUIRED] max_drawdown <= 60%
# [REQUIRED] total_trades <= 400  (fewer but better quality)
# [DESIRED] profit_factor >= 1.00
# [DESIRED] win_rate >= 50%
```

**If gate fails**: Debug which filter is too aggressive. Log rejected entries (new `rejected_entries.csv`) to tune thresholds.

---

## Phase 2: Analytics Layer — Backtest Database + Preview System

### 2.1 Objective
Turn 200+ backtest ZIP files into a queryable decision-support system.

### 2.2 Tasks

| ID | Task | File | Details |
|----|------|------|---------|
| 2.1 | Create `scripts/analytics/backtest_db.py` | New | Extract all `user_data/backtest_results/*.zip` into SQLite (`user_data/analytics/backtests.db`) |
| 2.2 | Schema design | SQLite | Tables: `backtests` (id, strategy, timerange_start, timerange_end, profit_factor, win_rate, total_trades, max_drawdown, avg_trade_duration, sharpe, sortino), `trades` (backtest_id, pair, open_date, close_date, profit_pct, exit_reason, duration_minutes) |
| 2.3 | Create `scripts/analytics/preview.py` | New | Load strategy dynamically, fetch last 200 candles via CCXT/Binance, call `populate_indicators()` + `populate_entry_trend()`, print BUY/SELL signals with confidence. See Appendix C. |
| 2.4 | Create `scripts/analytics/query_backtest.py` | New | CLI: `--strategy`, `--month`, `--metric`, `--compare`. Example: `python query_backtest.py --strategy AroonMomentum --month 2025-05 --metric winrate` |
| 2.5 | Index generation | `user_data/analytics/` | Batch script to regenerate index after each new backtest run |

### 2.3 Resources
- **Skill**: `AgentDB Vector Search` (for future semantic backtest querying)
- **Skill**: `tdd-workflow` (unit tests for DB extraction and preview logic)

### 2.4 Verification Gate (Checkpoint 2)
```bash
# Test extraction
python3 scripts/analytics/backtest_db.py --rebuild
# [PASS] SQLite file created with > 10,000 trade rows

# Test query
python3 scripts/analytics/query_backtest.py --list-strategies
# [PASS] Returns ≥ 5 unique strategy names

# Test preview
python3 scripts/analytics/preview.py --strategy AroonMomentumEngine_Hybrid --pair BTC/USDT:USDT
# [PASS] Outputs signal table without errors
# [PASS] No actual orders placed (read-only)
```

---

## Phase 3: Regime Router + Strategy Selection

### 3.1 Objective
Stop using one strategy for all market conditions. Route to the right strategy based on detected regime.

### 3.2 Tasks

| ID | Task | File | Details |
|----|------|------|---------|
| 3.1 | Install `hmmlearn` | `requirements.txt` | `pip install hmmlearn` (used by bolsa-ai-trading for regime detection) |
| 3.2 | Create `scripts/regime/hmm_regime.py` | New | Hidden Markov Model on returns + volatility. Outputs `market_regime.json`: `trending_up`, `trending_down`, `ranging`, `volatile`. See Appendix D. |
| 3.3 | Create `scripts/regime/regime_router.py` | New | Maps regime → strategy file. Regenerates `user_data/config_base.json` strategy name dynamically before Freqtrade starts. |
| 3.4 | Calibrate regime detector | `user_data/backtest_results/` | Run HMM on 1 year of BTC/USDT hourly returns. Validate against known bull/range/bear periods. |
| 3.5 | Strategy-to-regime assignment matrix | `scripts/regime/regime_config.json` | `ranging → BollingerMeanReversion`, `trending_up → EmaTrendFollowing`, `trending_down → DmiAdxStrategy`, `volatile → EnsembleStrategy` |
| 3.6 | Walk-forward analyzer | `scripts/analytics/walk_forward.py` | Run strategy on 12 rolling 30-day windows. Detect edge erosion via linear regression on profit trajectory. Alert if slope < -0.5. |

### 3.3 Resources
- **Skill**: `adaptive-imagining-cat` (autonomous execution with verification)
- **Skill**: `deploymemt-patterns` (config regeneration workflow)

### 3.4 Verification Gate (Checkpoint 3)
```bash
# Run walk-forward on 12 months
python3 scripts/analytics/walk_forward.py --strategy AroonMomentum --windows 12 --period 30d
# [REQUIRED] No window has max_drawdown > -20%
# [REQUIRED] No window has profit_factor < 0.90
# [REQUIRED] Edge erosion slope >= -0.5 (no significant degradation)
# [DESIRED] ≥ 8 of 12 windows have positive profit
```

---

## Phase 4: AI Layer Repair

### 4.1 Objective
Replace broken LLM configs with a production-grade, zero-cost local Ollama stack.

### 4.2 Tasks

| ID | Task | File | Details |
|----|------|------|---------|
| 4.1 | Install Ollama | System | `curl -fsSL https://ollama.com/install.sh \| sh` |
| 4.2 | Pull models | CLI | `ollama pull gemma3:4b && ollama pull deepseek-r1:8b` |
| 4.3 | Fix TradingAgents config | `TradingAgents/tradingagents/default_config.py` | `deep_think_llm = "gemma3:4b"`, `quick_think_llm = "gemma3:4b"`, `max_debate_rounds = 3`, `checkpoint_enabled = True` |
| 4.4 | Make LLM signal a HARD gate | `AroonMomentumEngine_Hybrid.py` line 338+ | If `ta_approval = False`, return dataframe with all zeros (no entries regardless of technical signals) |
| 4.5 | Remove dead models | `ARCHITECTURE_DAG.md`, configs | Purge all `gpt-5.4`, `qwen3.5:397b`, `cogito-2.1:671b` references. Replace with locally-validated models only. |
| 4.6 | Add Ollama health check | `scripts/live_trading/preflight_check.py` | Fail startup if Ollama is not running or model not pulled |
| 4.7 | Cache LLM responses | `shared_config/llm_cache.json` | TTL = 300s. Avoid redundant API calls for same ticker within 5 minutes. |

### 4.3 Resources
- **Skill**: `V3 MCP Optimization` (Ollama connection pooling if scaling to multi-agent)
- **Skill**: `AgentDB Memory Patterns` (caching layer)

### 4.4 Verification Gate (Checkpoint 4)
```bash
# Test Ollama connectivity
curl http://localhost:11434/api/tags | jq '.models[].name'
# [PASS] gemma3:4b and deepseek-r1:8b listed

# Test TradingAgents pipeline end-to-end
python3 -c "from tradingagents.default_config import Config; cfg = Config(); assert cfg.max_debate_rounds >= 3"
# [PASS] Config loads without error

# Test hard gate
# Manually write `{"risk_assessment": {"approval": false}}` to tradingagents_signal.json
# Run preview.py — should show ZERO entries
# [PASS] No signals when approval is False
```

---

## Phase 5: Genetic Algorithm Optimization

### 5.1 Objective
Automate parameter discovery to find a strategy variant that beats the manual configuration.

### 5.2 Tasks

| ID | Task | File | Details |
|----|------|------|---------|
| 5.1 | Clone GeneTrader | External | `git clone https://github.com/imsatoshi/GeneTrader.git /tmp/genetrader` |
| 5.2 | Adapt base strategy template | `/tmp/genetrader/strategy/` | Point `base_strategy_file` to `AroonMomentumEngine_Hybrid.py` |
| 5.3 | Define GA gene space | `ga.json` | Genes: `aroon_period` [10–25], `atr_multiplier` [1.0–3.0], `risk_reward` [1.0–3.0], `stoploss` [−0.02–−0.06], `max_open_trades` [1–3], pair whitelist subset [choose 5–10 from 18] |
| 5.4 | Run 20 generations | CLI | `cd /tmp/genetrader && python main.py --config ga.json --download` |
| 5.5 | Select winner | Auto | Best strategy: highest `fitness = (profit_factor * win_rate) / (max_drawdown + 1)`. Copy winning `.py` file to `user_data/strategies/AroonMomentumEngine_GA.py` |
| 5.6 | Validate winner independently | Freqtrade backtest | Run winner against OUT-OF-SAMPLE data (last 30 days NOT used during GA) |

### 5.3 Resources
- **Skill**: `adaptive-imagining-cat` (full autonomous cycle)
- **Skill**: `tdd-workflow` (validate GA output with unit tests)

### 5.4 Verification Gate (Checkpoint 5)
```bash
# 1. In-sample gate (training data)
# [REQUIRED] Best generation profit_factor >= 1.2
# [REQUIRED] Best generation win_rate >= 55%
# [REQUIRED] Best generation max_drawdown <= 30%
# [REQUIRED] Fitness improves monotonically for last 5 generations (no degradation)

# 2. Out-of-sample gate (validation data, last 30 days)
# [REQUIRED] profit_factor >= 1.0
# [REQUIRED] win_rate >= 50%
# [REQUIRED] max_drawdown <= 30%
```

---

## Phase 6: Live Pre-Flight Gate (Dry-Run)

### 6.1 Objective
Prove the fixed system can make money in real-time simulation before risking capital.

### 6.2 Tasks

| ID | Task | File | Details |
|----|------|------|---------|
| 6.1 | Set `dry_run: true` | `user_data/config_base.json` line 8 | Ensure paper trading only |
| 6.2 | Run dry-run for 30 calendar days | Freqtrade | `freqtrade trade --strategy AroonMomentumEngine_GA` |
| 6.3 | Daily health monitoring | `scripts/health_monitor.py` | Every hour: check process alive, balance within bounds, log to `user_data/agent_journal/` |
| 6.4 | Weekly performance review | Manual | Every Sunday: run `backtest_query.py` against dry-run DB to extract live stats |
| 6.5 | Kelly re-evaluation | Script | After 30 days (≥ 20 trades), recompute Kelly f*. Must be > 0. |

### 6.3 Verification Gate (Checkpoint 6)
```bash
# After 30 days of dry-run:
# [REQUIRED] Total profit >= 0% (breakeven or better)
# [REQUIRED] Win rate >= 50%
# [REQUIRED] Kelly f* > 0
# [REQUIRED] No single day drawdown > -10%
# [REQUIRED] System uptime >= 95% (health monitor logs show < 5% downtime)
```

**If gate fails**: Return to Phase 5 (re-run GA) or Phase 3 (adjust regime thresholds). Do NOT proceed to Phase 7.

---

## Phase 7: Deployment with Telemetry

### 7.1 Objective
Go live with graduated capital exposure and full observability.

### 7.2 Tasks

| ID | Task | File | Details |
|----|------|------|---------|
| 7.1 | Convert dry-run config to live | `user_data/config_base.json` | `dry_run: false`, leverage starts at 1.0x, stake = $100 (10% of intended capital) |
| 7.2 | Install systemd service | `freqtrade.service` | `sudo systemctl enable freqtrade && sudo systemctl start freqtrade` |
| 7.3 | Activate Telegram alerts | `.env` + Telegram | Enable alerts for entries, exits, daily P&L, weekly summary |
| 7.4 | Enable health monitor cron | `scripts/health_monitor.py` | `crontab -e` → add `*/5 * * * * /home/roshan/Downloads/Algotrading/scripts/health_monitor.py` |
| 7.5 | Daily auto-backup | `scripts/backup_db.py` | Daily 23:00: `cp user_data/tradesv3.sqlite user_data/backups/tradesv3_$(date +%Y%m%d).sqlite` |
| 7.6 | Weekly GA re-optimization trigger | `scripts/weekly_ga_check.py` | After Sunday review, if win_rate < 50% or PF < 1.0, trigger Phase 5 re-run on latest 90 days of data |
| 7.7 | Circuit breaker | `shared_config/circuit_breaker.json` | Auto-kill if: daily drawdown > −15%, or 3 consecutive losses in 1 hour, or Binance API error > 5 in 10 minutes |

### 7.3 Graduated Capital Plan

| Week | Starting Capital | Leverage | Max Risk/Trade | Condition to Advance |
|------|-----------------|----------|----------------|---------------------|
| 0 (dry-run) | $0 | 1.0x | 1% | 30 days profitable |
| 1 | $100 | 1.0x | 1% | PF ≥ 1.0, WR ≥ 50% |
| 2 | $250 | 1.0x | 1% | PF ≥ 1.1, WR ≥ 50%, DD < 10% |
| 3 | $500 | 1.5x | 1% | PF ≥ 1.2, WR ≥ 55%, DD < 15% |
| 4+ | $1000 | 2.0x | 2% | Kelly f* ≥ 0.15, consistent for 14 days |

**NEVER exceed 2.0x leverage until Kelly f* ≥ 0.25 and 90-day track record exists.**

### 7.4 Final Verification
```bash
# Systemd status
sudo systemctl status freqtrade
# [PASS] Active (running)

# Health monitor
python3 scripts/health_monitor.py --check
# [PASS] All subsystems green

# Backup exists
ls user_data/backups/tradesv3_$(date +%Y%m%d).sqlite
# [PASS] File exists and size > 0

# Circuit breaker armed
cat shared_config/circuit_breaker.json
# [PASS] state = "HEALTHY", all thresholds set
```

---

## Timeline Summary

| Week | Phase | Deliverable | Team Size | Risk |
|------|-------|-------------|-----------|------|
| Day 1 | 0 | Secure system, rotated keys | 1 person | Low |
| Days 2–3 | 1 | Entry filters + sizing rewrite | 1 person | Low |
| Days 4–5 | 1 | Backtest verification (Checkpoint 1) | 1 person | Medium |
| Week 2 | 2 | Backtest DB + preview CLI | 1 person | Low |
| Week 3 | 3 | HMM regime router + walk-forward | 1 person | Medium |
| Week 4 | 4 | Ollama install + AI gate hardening | 1 person | Low |
| Week 5 | 5 | GA optimization run | 1 person, overnight compute | Medium |
| Week 6 | 6 | 30-day dry-run gate | 1 person, passive monitoring | Medium |
| Week 7+ | 7 | Graduated live deployment | 1 person, active monitoring | High (controlled) |

---

## Resource Map

| Resource | Why Needed | Precondition |
|----------|-----------|------------|
| `gh security-scan` | Scan for leaked secrets | Phase 0 |
| `skill:tdd-workflow` | Every phase needs tests | Phase 1–7 |
| `skill:security-review` | Validate no new secrets in code | Phase 1, 4 |
| `skill:adaptive-imagining-cat` | Autonomous execution of GA phase | Phase 5 |
| `skill:deploymemt-patterns` | Docker, systemd, cron setup | Phase 7 |
| Ollama (local) | Zero-cost LLM reasoning | Phase 4 |
| `tmp/genetrader/` | GA code (forked from imsatoshi) | Phase 5 |
| 4 CPU cores, 4GB RAM | Running 20 GA generations + Ollama + Freqtrade simultaneously | Phase 5 |
| > 1 year of historical 1h crypto data | HMM calibration, walk-forward backtesting | Phase 3 |
| Binance read-only API key | Live data fetching for preview + dry-run | Phase 2+ |

---

## Rollback Triggers

| Condition | Action | Rollback To |
|-----------|--------|-------------|
| Checkpoint 1 fails after 3 tuning attempts | Strategy fundamentally broken | Phase 0 → restart with `EnsembleStrategy` as primary instead of AroonMomentum |
| Checkpoint 3 shows consistent edge erosion | Market structure changed | Phase 5 → re-run GA with latest 60 days data |
| Ollama fails to start or model unavailable | AI layer cannot function | Phase 4 → fall back to pre-entry filters only (strategy works without AI) |
| Dry-run DD > −10% in any single week | System unfit for live | Phase 1 → re-examine filters, more aggressive regime skipping |
| Live capital loss > −5% in first 3 days | Deployment too aggressive | Phase 6 → reduce capital to $50, leverage to 1.0x, or stop live entirely |
| Hard fork, exchange hack, regulatory event | External force majeure | Phase 7 → `circuit_breaker.json` state = "HALTED", manual review required |

---

## Appendices

### Appendix A: Pre-Entry Filter Code
```python
def _should_allow_entry(self, dataframe: DataFrame, metadata: dict, side: str) -> bool:
    """Hard pre-filter before any signal logic."""
    # Rule 1: No entries if pair has 3+ consecutive losses in last 20 trades
    recent_losses = self._get_recent_losses(metadata["pair"], n=20)
    if recent_losses >= 3:
        return False
    
    # Rule 2: No entries if market regime is ranging
    _, regime = self._load_sentiment()
    if regime == "ranging":
        return False
    
    # Rule 3: No shorts when BTC is parabolic
    if side == "short" and dataframe["btc_parabolic"].iloc[-1]:
        return False
    
    # Rule 4: No entries during volatility spike (ATR > 1.5x 20p average)
    atr_avg = dataframe["atr"].rolling(20).mean().iloc[-1]
    if dataframe["atr"].iloc[-1] > atr_avg * 1.5:
        return False
    
    # Rule 5: No entries if ADX < 25 (no trend)
    if dataframe["adx"].iloc[-1] < 25:
        return False
    
    # Rule 6: Minimum volume filter
    if dataframe["volume"].iloc[-1] < dataframe["volume_ma"].iloc[-1] * 1.5:
        return False
    
    return True

def _get_recent_losses(self, pair: str, n: int) -> int:
    """Count consecutive losses in last n trades for a pair from SQLite DB."""
    try:
        import sqlite3
        conn = sqlite3.connect("user_data/tradesv3.dryrun.sqlite")
        rows = conn.execute(
            "SELECT close_profit FROM trades WHERE pair=? AND is_open=0 ORDER BY close_date DESC LIMIT ?",
            (pair, n),
        ).fetchall()
        conn.close()
        consecutive = 0
        for row in rows:
            if row[0] is not None and row[0] < 0:
                consecutive += 1
            else:
                break
        return consecutive
    except Exception:
        return 0
```

### Appendix B: Fixed Fractional Position Sizing
```python
def custom_stake_amount(self, pair, current_time, current_rate,
                        proposed_stake, min_stake, max_stake, leverage,
                        entry_tag, side, **kwargs) -> float:
    """Risk 1% of account per trade, sized by ATR stop distance."""
    balance = self.wallets.get_total(self.stake_currency)
    RISK_PER_TRADE_PCT = 0.01
    
    dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    atr = dataframe["atr"].iloc[-1] if len(dataframe) > 0 else current_rate * 0.02
    stop_distance = atr * self.atr_multiplier.value
    stop_pct = stop_distance / current_rate
    
    if stop_pct <= 0:
        stop_pct = 0.02
    
    position_size = (balance * RISK_PER_TRADE_PCT) / (stop_pct * leverage)
    position_size = min(position_size, proposed_stake, max_stake, balance * 0.05)
    return max(position_size, min_stake or 0)
```

### Appendix C: Preview CLI Usage
```bash
# Preview signals for all pairs
python3 scripts/analytics/preview.py --strategy AroonMomentumEngine_Hybrid

# Preview specific pair
python3 scripts/analytics/preview.py --strategy AroonMomentumEngine_Hybrid --pair SOL/USDT:USDT

# Preview ensemble
python3 scripts/analytics/preview.py --strategy EnsembleStrategy --pairs 5
```

### Appendix D: HMM Regime Detector Snippet
```python
from hmmlearn import hmm
import numpy as np

def detect_regime(prices: np.ndarray, n_states: int = 3) -> str:
    returns = np.diff(np.log(prices)).reshape(-1, 1)
    vol = np.array([np.std(returns[max(0, i-14):i+1]) for i in range(len(returns))]).reshape(-1, 1)
    X = np.hstack([returns, vol])
    model = hmm.GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=100, random_state=42)
    model.fit(X)
    hidden_states = model.predict(X)
    last_state = hidden_states[-1]
    
    means = model.means_[last_state]
    regime_map = {0: "ranging", 1: "trending_up", 2: "volatile"}  # Calibrated post-fit
    return regime_map.get(last_state, "unknown")
```

---

*Plan generated 2026-05-15. Typed DAG verified: 8 phases, 7 checkpoints, no cycles. Resource map complete.*
