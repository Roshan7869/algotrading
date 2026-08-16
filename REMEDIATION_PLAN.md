# Algotrading Remediation — Typed Execution Plan

**Goal:** Fix all 13 critical issues from NEXUS multi-dimensional audit (score 47→75+)  
**Created:** 2026-05-22  
**Method:** NEXUS Planning Protocol (adaptive-imagining-cat + POLARIS DAG)  
**Estimated Phases:** 6  
**Estimated Duration:** 2-3 sessions (checkpoint between phases)

---

## Dependency Graph

```
Level 0 (parallel):
  P0-T1  Fix UI dashboard crash
  P0-T2  Fix learning loop unsafe default
  P0-T3  Add circuit breaker to crontab
  P0-T4  Fix strategy live entries (decision gate)

Level 1 (after P0):
  P1-T1  Start Redis + Freqtrade + orchestrator
  P1-T2  Add order validation to freqtrade_bridge
  P1-T3  Enable exchange stoplosses

Level 2 (after P1):
  P2-T1  Add @st.cache_data to UI
  P2-T2  Add charts to PnL Analytics + Dashboard
  P2-T3  Wire Backtest + Settings save buttons

Level 3 (after P2):
  P3-T1  Consolidate configs (96 → < 10)
  P3-T2  Rename SignalBus classes
  P3-T3  Extract core contracts to break circular deps

Level 4 (after P3):
  P4-T1  Run full test suite
  P4-T2  Verify dashboard loads without crash
  P4-T3  Verify system health (Redis, Freqtrade, circuit breaker)

Level 5 (after P4):
  P5-T1  Write VERIFICATION_REPORT.md
  P5-T2  Update AGENTS.md with new state
  P5-T3  Audit: plan vs execution matrix
```

---

## Phases

### Phase 0 — Critical Safety Fixes (Independent, Run in Parallel)

**Type:** implement  
**Guardrails:** Must not break existing tests. Must preserve dry_run default.

#### P0-T1: Fix Dashboard Crash
- **File:** `ui/pages/1_dashboard.py` lines 50-52
- **Bug:** `risk_events` is a list comprehension, then `.items()` is called on it
- **Fix:** Change `risk_events = [a for a in ...]` to `risk_events = {k: v for k, v in ...}` OR iterate the list directly
- **Verification:** Dashboard page loads without `AttributeError`
- **Tokens:** ~500

#### P0-T2: Fix Learning Loop Unsafe Default
- **File:** `knowledge/learning_loop.py` lines 181-183
- **Bug:** `_aggregate_win_rate()` returns `0.5` when `total_trades == 0` (unknown setup = approved)
- **Fix:** Return `0.0` when no historical data exists. Unknown setups should be blocked by default.
- **Verification:** `test_learning_loop.py` still passes (may need test update)
- **Tokens:** ~800

#### P0-T3: Add Circuit Breaker to Crontab
- **File:** `scripts/live_trading/preflight_check.py` (reference), user crontab
- **Bug:** `quantdinger_risk_gate.py` computes accurate risk but is not in crontab. Circuit breaker JSON is 70h stale.
- **Fix:** Add cron entry: `*/5 * * * * cd /home/roshan/Downloads/Algotrading && source .venv/bin/activate && python agents/risk_managers/quantdinger_risk_gate.py >> /tmp/circuit_breaker.log 2>&1`
- **Verification:** `circuit_breaker.json` updates every 5 minutes
- **Tokens:** ~300

#### P0-T4: Strategy Live Mode Decision Gate
- **File:** `user_data/strategies/AroonMomentumEngine_Hybrid.py` lines 497-570, `user_data/config_live_real.json`
- **Bug:** Strategy zeros all entries in live mode BUT config claims `dry_run: false` + `leverage: 10`. Dangerous mismatch.
- **Fix Options:**
  - **Option A (Recommended):** Create `config_signal_alerts.json` with `dry_run: true`, remove `config_live_real.json`, document strategy as "signal alerts only"
  - **Option B:** Enable live entries in strategy (remove the `if runmode == "live": return 0` guard) + add preflight validation
- **Decision Required:** See Question Gate below
- **Tokens:** ~1,000

---

### Phase 1 — Execution Pipeline (After P0)

**Type:** implement  
**Guardrails:** Must verify Redis is running before Freqtrade starts. Must check dry_run in all configs.

#### P1-T1: Start Redis + Freqtrade + Orchestrator
- **Files:** `start_trading.sh`, `start_local.sh`, `docker-compose.yml`
- **Actions:**
  1. Start Redis: `redis-server --daemonize yes`
  2. Verify: `redis-cli ping` returns PONG
  3. Start Freqtrade dry-run: `freqtrade trade --config user_data/config_market_ready.json --strategy AroonMomentumEngine_Hybrid`
  4. Verify: `ps aux | grep freqtrade` shows process
  5. Add orchestrator cron or systemd service
- **Verification:** System processes running, Redis responsive
- **Tokens:** ~1,200

#### P1-T2: Add Order Validation to Freqtrade Bridge
- **File:** `engine/freqtrade_bridge.py`
- **Bug:** Bridge publishes signals to Redis without validating pair, amount, price
- **Fix:** Add validation function:
  - `pair` must be in exchange whitelist
  - `amount` > min_order_size
  - `price` > 0 and within reasonable bounds
  - Exchange connectivity check before publish
- **Verification:** Invalid signals are rejected with error, not published
- **Tokens:** ~1,500

#### P1-T3: Enable Exchange Stoplosses
- **Files:** `user_data/strategies/AroonMomentumEngine_Hybrid.py`, `user_data/config*.json`
- **Bug:** All strategies set `stoploss_on_exchange: False`. At 10x leverage, bot-loop delay = catastrophic.
- **Fix:** Set `stoploss_on_exchange: True` in all futures configs. Add exchange-native stoploss order types.
- **Verification:** Configs contain `stoploss_on_exchange: true`
- **Tokens:** ~800

---

### Phase 2 — UI/UX Improvements (After P1)

**Type:** implement  
**Guardrails:** Must use existing plotly dep. Must not break Streamlit theming.

#### P2-T1: Add @st.cache_data to UI
- **Files:** All `ui/pages/*.py`, `ui/data_layer.py`
- **Fix:** Wrap all JSON-reading functions with `@st.cache_data(ttl=60)` to prevent disk I/O on every interaction
- **Verification:** Slider movement does not re-read all JSON files
- **Tokens:** ~1,000

#### P2-T2: Add Charts to PnL Analytics + Dashboard
- **Files:** `ui/pages/5_pnl_analytics.py`, `ui/pages/1_dashboard.py`
- **Fix:** Add plotly charts:
  - Equity curve (cumulative PnL over time)
  - Drawdown chart
  - Win rate by strategy (bar chart)
  - Trade distribution (histogram)
- **Verification:** Charts render with real data from `outcome_history.json`
- **Tokens:** ~2,000

#### P2-T3: Wire Backtest + Settings Save Buttons
- **Files:** `ui/pages/8_backtest.py`, `ui/pages/9_settings.py`
- **Fix:**
  - Backtest: Add callback that shells out to `freqtrade backtesting` with progress spinner
  - Settings: Add callback that writes to `shared_config/*.json` and validates inputs
- **Verification:** Buttons execute actions and show results
- **Tokens:** ~1,500

---

### Phase 3 — Structural Improvements (After P2)

**Type:** refactor  
**Guardrails:** Must preserve all existing behavior. Must update imports across codebase.

#### P3-T1: Consolidate Configs (96 → < 10)
- **Files:** `user_data/config*.json`, `config_examples/`
- **Plan:**
  1. Define 3 base configs: `config_base.json` (common), `config_dryrun.json` (development), `config_production.json` (signal alerts)
  2. Move strategy-specific overlays to `user_data/strategies/<name>.json`
  3. Delete 5 confirmed duplicates + 80+ unused configs
  4. Update all scripts to use new config paths
- **Verification:** `find user_data -name 'config*.json' | wc -l` returns < 15
- **Tokens:** ~3,000

#### P3-T2: Rename SignalBus Classes
- **Files:** `shared_config/signal_bus.py`, `engine/signal_bus.py`, all imports
- **Fix:**
  - `shared_config.signal_bus.SignalBus` → `shared_config.signal_bus.AtomicFileBus`
  - `engine.signal_bus.SignalBus` → `engine.signal_bus.RedisSignalBus`
- **Verification:** All imports updated, no naming ambiguity
- **Tokens:** ~1,500

#### P3-T3: Extract Core Contracts
- **New dir:** `core/` or `contracts/`
- **Files to extract:**
  - `Signal` dataclass (from `engine/ai_signal_generators/base.py`)
  - `TradeDecision` + `RiskTier` (from `agents/risk_managers/circuit_breaker.py`)
  - `StrategyInfo` (from `engine/strategy_registry.py`)
- **Goal:** `engine/`, `agents/`, `knowledge/` all depend on `core/` only. `core/` has zero dependencies.
- **Verification:** No circular imports when doing eager top-level imports
- **Tokens:** ~2,500

---

### Phase 4 — Verification (After P3)

**Type:** test  
**Guardrails:** All tests must pass. Dashboard must load. System must be warm.

#### P4-T1: Run Full Test Suite
- **Command:** `pytest tests/ -x -q --tb=short` (with xdist disabled if needed)
- **Target:** All 146 tests pass, including learning loop (9/9)
- **Tokens:** ~500

#### P4-T2: Verify Dashboard Loads
- **Command:** `streamlit run ui/app.py --server.port 8501 &`
- **Check:** No crash on Dashboard page. Charts render. Data loads.
- **Tokens:** ~300

#### P4-T3: Verify System Health
- **Checks:**
  - `redis-cli ping` → PONG
  - `ps aux | grep freqtrade` → process running
  - `cat shared_config/circuit_breaker.json` → updated within last 10 min
  - `python -c "from knowledge.learning_loop import LearningLoop; l=LearningLoop(); print(l.enabled)"` → True
- **Tokens:** ~300

---

### Phase 5 — Documentation & Audit (After P4)

**Type:** audit  
**Guardrails:** AGENTS.md must be updated. Report must be factual.

#### P5-T1: Write Verification Report
- **File:** `VERIFICATION_REPORT.md`
- **Content:** What was fixed, how it was verified, remaining gaps
- **Tokens:** ~800

#### P5-T2: Update AGENTS.md
- **File:** `AGENTS.md`
- **Updates:**
  - Config count (96 → < 15)
  - System status (cold → warm)
  - Known issues (remove fixed ones)
  - Test status
- **Tokens:** ~500

#### P5-T3: Plan vs Execution Audit
- **Matrix:** Compare planned vs actual fixes, token usage, time spent
- **Tokens:** ~500

---

## Resource Mapping

| Phase | Primary Cluster | Skills | Agents | Confidence |
|-------|-----------------|--------|--------|------------|
| P0 | analyzer_planner + quality_security | investigate, tdd-workflow | researcher, code-reviewer | HIGH |
| P1 | backend_api + devops_infra | backend-patterns, ship | database-admin | HIGH |
| P2 | frontend_ui | frontend-ui-engineering, design-html | designer | HIGH |
| P3 | architect | autopilot, sparc-methodology | architect, specification | MEDIUM |
| P4 | quality_security | qa, e2e-testing | qa-engineer, tdd-guide | HIGH |
| P5 | knowledge_wiki | document-release, learn | — | MEDIUM |

---

## Question Gate (User Decision Required)

### Q1: Strategy Live Mode — Which Path?

**Option A (Signal Alerts Only — Recommended):**
- Keep strategy blocking live entries
- Create `config_signal_alerts.json` with `dry_run: true`
- Delete `config_live_real.json`
- Document: "This system sends Telegram alerts, operator manually confirms via /forcelong"

**Option B (Enable Autonomous Live Trading):**
- Remove the live-mode entry block from strategy
- Keep `config_live_real.json` but add: preflight check as mandatory gate, smaller position sizing (1x not 10x), force_entry_enable: false
- Document: "Autonomous trading enabled with circuit breaker enforcement"

**Please specify A or B.**

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Config consolidation breaks scripts | Medium | High | Keep old configs in `config_archive/` for 1 week |
| SignalBus rename breaks imports | Low | High | Use `grep` to find all imports, update atomically |
| Redis still fails to start | Low | High | Add Docker compose fallback profile |
| Streamlit charts fail with stale data | Low | Medium | Add empty-state handling |
| Context window exhaustion | Medium | Medium | Checkpoint after every phase |

---

## Checkpoint Schedule

| After Phase | Checkpoint File |
|-------------|----------------|
| P0 | `/tmp/nexus-plan-p0.json` |
| P1 | `/tmp/nexus-plan-p1.json` |
| P2 | `/tmp/nexus-plan-p2.json` |
| P3 | `/tmp/nexus-plan-p3.json` |
| P4 | `/tmp/nexus-plan-p4.json` |
| P5 | `/tmp/nexus-plan-complete.json` |

---

## Approval Gate

**Before any code changes, you must approve this plan.**

**To approve:** Type `go` or `approve`
**To modify:** Type `modify` + what to change
**To scope down:** Type `p0 only` to execute only Phase 0 (critical fixes)
**To abort:** Type `abort`

---

*Plan generated by NEXUS v4 adaptive-imagining-cat protocol. 6 phases, 15 tasks, 6 checkpoint gates.*
