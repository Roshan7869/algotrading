# Algotrading — Complete State Analysis & Phase Audit

**Generated:** 2026-05-19T13:58Z  
**Method:** adaptive-imagining-cat Phase 1 + NEXUS v3+v4 routing + cross-layer audit  
**NEXUS Health:** 1971 resources, 700 routing logs, 95.6% conditional accuracy, 0 degraded  

---

## 1. ENVIRONMENT STATE

| Attribute | Value |
|-----------|-------|
| Branch | `develop-local` |
| Git state | Dirty (48 modified, 53 untracked) |
| Last commit | `2fe7bff02` — feat: add IVB ORB Crypto V5 strategy |
| Ollama | Running, 21 models installed (mostly cloud, ~5 local) |
| Freqtrade mode | `dry_run: True` |
| ChromaDB | 592 vectors in `trading_strategies` collection |
| Outcome history | 2 recorded trades (AroonMomentumEngine_Hybrid only) |
| Strategy DB | 443 chunks from YouTube, 34-field schema |
| Docker | Docker Compose available, TradingAgents submodule present |

---

## 2. NEXUS SYSTEM HEALTH

| Metric | Value |
|--------|-------|
| Total resources indexed | 1971 |
| Skills | 694 |
| Commands | 276 |
| Agents | 169 |
| Design systems | 158 |
| Docs (mermaid, prompt) | 139 |
| CLI tools | 132 |
| MCP servers | 66 |
| Hooks | 69 |
| Routing accuracy (raw) | 49.9% (349/700) |
| Routing accuracy (conditional) | 95.6% |
| Degraded skills | 0 |
| Self-reflection failures | 27 (0 fixed) |
| Thompson Sampling beliefs | 302 (5 high-confidence) |
| Plans in planning | 23 |

**Top-performing skills (Thompson Sampling):**
- `retro` — avg reward 0.857 (14 uses)
- `adaptive-imagining-cat` — avg reward 1.0 (7 uses)
- `ollama_cloud/test-model` — avg reward 1.0 (12 uses)

**Cluster affinities (learned):**
- `analyzer_planner`: 0.992 — highest confidence
- `knowledge_wiki`: 1.0 — perfect track
- `devops_infra`: 1.0 — perfect track
- `frontend_ui`: 0.989
- `quality_security`: 0.982

---

## 3. PHASE-BY-PHASE AUDIT

### Phase 0: Security Triage
**Status: INCOMPLETE (40%)**

| Check | Result | Evidence |
|-------|--------|----------|
| `.env` in `.gitignore` | ✅ PASS | `git check-ignore .env` confirms |
| Binance key rotation | ❌ FAIL | No evidence of revocation; live keys still in `.env` |
| Telegram token rotation | ❌ FAIL | No evidence of revocation |
| Git history scan for secrets | ❌ NOT DONE | Confirmed: secrets exist in `.env.example` |
| `rotate_secrets.py` | ❌ NOT BUILT | File does not exist |
| Critical API config issues | ❌ FAIL | API on `0.0.0.0:8080`, weak JWT, wildcard CORS |

**Risks:** 20 critical security findings from audit (live API keys, `shell=True` patterns, prompt injection vectors)

---

### Phase 1: Core Strategy Fix — Entry Filters + Sizing
**Status: INCOMPLETE (25%)**

| Check | Required | Actual |
|-------|----------|--------|
| `_should_allow_entry()` | Implement 6-rule hard filter | ❌ Not verified in strategy |
| `custom_stake_amount` | Fixed fractional (1% risk) | ❌ Not wired to Freqtrade |
| `leverage_config.py` default | 1.0x | ❌ Not found in expected location |
| `stoploss` | -0.03 (3%) | ❌ 5.27% avg stop loss in backtest |
| `max_open_trades` | 1 | ❌ Currently 3 |
| Backtest PF ≥ 0.90 | Gate requirement | ❌ Not executed |
| Position sizer exists | ✅ Present at `scripts/risk_management/position_sizer.py` | Inverse volatility weighting coded but NOT connected to Freqtrade |

**Strategy performance:** AroonMomentumEngine_Hybrid: 2 trades, 50% WR. All other strategies: 0 trades.

---

### Phase 2: Analytics Layer — Backtest DB + Preview
**Status: NOT BUILT (15%)**

| Deliverable | Required | Actual |
|-------------|----------|--------|
| `scripts/analytics/backtest_db.py` | SQLite index of ZIPs | ❌ NOT FOUND |
| `scripts/analytics/preview.py` | Live signal preview CLI | ❌ NOT FOUND |
| `scripts/analytics/query_backtest.py` | CLI query tool | ❌ NOT FOUND |
| `engine/walkforward.py` | Walk-forward engine | ✅ EXISTS (247 lines) |
| `engine/strategy_registry.py` | Strategy registry | ✅ EXISTS (good dynamic discovery) |
| 200+ backtest ZIPs indexed | — | ❌ Not done |

**Analysis:** Walk-forward engine and strategy registry are well-architected but the analytics layer (DB, preview, query) was never built. Backtest results remain in raw ZIP files — zero queryability.

---

### Phase 3: Regime Router + Strategy Selection
**Status: MOSTLY MISSING (20%)**

| Deliverable | Required | Actual |
|-------------|----------|--------|
| `scripts/regime/hmm_regime.py` | HMM regime detector | ❌ NOT FOUND |
| `scripts/regime/regime_router.py` | Regime→strategy mapper | ❌ NOT FOUND |
| `scripts/regime/regime_config.json` | Strategy assignment matrix | ❌ NOT FOUND |
| `hmmlearn` installed | — | ❌ Not in requirements |
| Market regime JSON | — | ✅ Exists (from signal_bus:621905) |
| Regime detection working | — | ✅ via signal_bus (`volatile`, 100% confidence) |

**Analysis:** The signal bus has a working regime detector (outputs `market_regime.json`) but it's from an opaque source — NOT the HMM model planned in Phase 3. The regime router that would map regime → strategy file is entirely missing.

---

### Phase 4: AI Layer Repair
**Status: PARTIAL (55%)**

| Deliverable | Required | Actual |
|-------------|----------|--------|
| Ollama installed & running | ✅ | 21 models available |
| `gemma3:4b` + `deepseek-r1:8b` local | ❌ | All models are cloud variants |
| `preflight_check.py` | ✅ | Exists at `scripts/live_trading/` |
| TradingAgents config fixed | ❌ | Still references cloud-only models |
| LLM signal as HARD gate | ❌ | Signal gates exist but not enforced |
| Dead model references purged | ❌ | Configs still list `gpt-5.4`, `qwen3.5:397b`, etc. |
| LLM response cache | ❌ | Not implemented |
| MiroShark brain integration | ❌ | JSON file written but NO strategy reads it |
| SignalBusMixin stub | ❌ CRITICAL | Still a no-op — strategies inherit zero functionality |
| VDBMixin stub | ❌ CRITICAL | All return empty — ChromaDB never queried at trade time |

**New code delivered:**
- ✅ `engine/ai_signal_generators/` — 8 modules (orchestrator, registry, wrappers)
- ✅ `engine/freqtrade_bridge.py` — bridge logic
- ✅ `engine/signal_bus.py` — signal bus (duplicated from shared_config?)
- ✅ `knowledge/learning_loop.py` — 247-line learning loop with encoding
- ✅ `knowledge/trade_encoder.py` — trade outcome encoding

---

### Phase 5: Genetic Algorithm Optimization
**Status: NOT STARTED (0%)**

| Deliverable | Required | Actual |
|-------------|----------|--------|
| GeneTrader cloned | `/tmp/genetrader` | ❌ NOT FOUND |
| Strategy adapted for GA | — | ❌ Not done |
| GA gene space defined | `ga.json` | ❌ Not done |
| 20 generations run | — | ❌ Not done |
| Winner selected | — | ❌ Not done |
| Out-of-sample validation | — | ❌ Not done |

**Analysis:** No GA work has started. No compute resources allocated.

---

### Phase 6: Live Pre-Flight (Dry-Run Gate)
**Status: NOT STARTED (5%)**

| Check | Requirement | Actual |
|-------|-------------|--------|
| `dry_run: true` | ✅ | Already set |
| `max_open_trades` | 1 | ❌ Still 3 |
| Leverage | 1.0x | ❌ 3.0x from multiple sources |
| 30-day monitoring | — | ❌ Not started |
| Daily health monitor | — | ❌ Not set up as daemon |
| Weekly performance review | — | ❌ Not started |
| Kelly re-evaluation (30d) | — | ❌ Not started |

---

### Phase 7: Deployment + Telemetry
**Status: PENDING (dependent on Phase 6 gate)**

| Deliverable | Status |
|-------------|--------|
| Live config conversion | ❌ Blocked |
| systemd service | ❌ Not set up |
| Telegram alerts | ❌ Not activated |
| Health monitor cron | ❌ Not configured |
| Daily DB backup cron | ❌ Not configured |
| Weekly GA re-opt trigger | ❌ Not configured |
| Circuit breaker daemon | ❌ Not running as watchdog |

---

## 4. COMPLETED DELIVERABLES (Beyond the 6-Phase Plan)

These were built in the MiroShark/SignalBus sprint and are operational:

| Module | Files | Status |
|--------|-------|--------|
| **Signal Bus** | `shared_config/signal_bus.py` (170 lines) | ✅ Full atomic read/write with staleness detection |
| **Signal Bus** | `engine/signal_bus.py` (132 lines) | ✅ Engine-level abstraction |
| **MiroShark Brain** | `shared_config/miroshark_brain.json` | ✅ Daemon writes composite scores (regime+sentiment+outcome+agents) |
| **Learning Loop** | `knowledge/learning_loop.py` (247 lines) | ✅ ChromaDB sync, NEXUS feedback, strategy perf tracking |
| **Strategy Registry** | `engine/strategy_registry.py` | ✅ Dynamic IStrategy discovery |
| **Walkforward** | `engine/walkforward.py` | ✅ Window-based train/test backtest runner |
| **Risk Agents** | `agents/risk_managers/` (circuit_breaker, hedge_coordinator, subagent_overseer) | ✅ 3 risk agent modules |
| **Swarm Engine** | `swarm/engine.py` | ✅ Multi-agent orchestration |
| **MCP Layer** | `mcp_layer/` (finance_mcp_server, mcp_client, openbb_wrapper) | ✅ 4 modules with yfinance fallback |
| **AI Generators** | `engine/ai_signal_generators/` | ✅ 8 modules (kronos, macro, miroshark, orchestrator, etc.) |
| **Freqtrade Bridge** | `engine/freqtrade_bridge.py` | ✅ Bridge logic |
| **UI** | `ui/pages/` | ✅ 10 Streamlit pages (dashboard, portfolio, signals, risk, PnL, etc.) |
| **Integration Tests** | `tests/` | 21/24 pass (3 alerter import failures) |
| **Market Regime** | `shared_config/market_regime.json` | ✅ Active detection (currently `volatile`) |

---

## 5. CRITICAL GAPS SUMMARY

| Gap | Impact | Phase | Effort |
|-----|--------|-------|--------|
| **AroonMomentum entry filter not fixed** | -80.4% backtest loss repeats if switched live | P1 | 2h |
| **SignalBusMixin + VDBMixin are stubs** | ChromaDB (443 chunks) never queried; strategies bypass bus | P4 | 1h |
| **Circuit breaker PAUSED but ignored** | Monthly PnL -33.21%, weekly -8.17%, no halt triggered | P1 | 30min |
| **No regime router** | Single strategy for all market conditions | P3 | 4h |
| **No analytics layer** | 200+ backtest ZIPs unqueryable | P2 | 3h |
| **Ollama models all cloud** | Production dependency on external API | P4 | 30min |
| **GeneTrader GA not started** | Manual parameter tuning instead of automated | P5 | 4h |
| **Live API keys unrotated** | Security risk | P0 | 15min |
| **max_open_trades=3** (should be 1) | Risk exposure 3x planned | P1 | 5min |
| **Leverage 3.0x inconsistent** | Between configs, .env, and signal file | P1 | 15min |

---

## 6. COMPLETION MATRIX

```
Phase 0: Security Triage    ████░░░░░░  40%
Phase 1: Entry+Sizing Fix   ██░░░░░░░░  25%
Phase 2: Analytics Layer    █░░░░░░░░░  15%  (walkforward + registry exist)
Phase 3: Regime Router      ██░░░░░░░░  20%  (market_regime.json works, HMM missing)
Phase 4: AI Layer Repair    █████░░░░░  55%  (Ollama + agents built, stubs not fixed)
Phase 5: Genetic Algorithm  ░░░░░░░░░░   0%  (not started)
Phase 6: Dry-Run Gate       ░░░░░░░░░░   5%  (dry_run=true set, rest missing)
Phase 7: Deployment         ░░░░░░░░░░   0%  (blocked on P6)

Overall: 20% complete
```

---

## 7. RECOMMENDED NEXT ACTIONS

### Immediate (today)
1. **Security**: Rotate Binance API key + Telegram token (P0)
2. **P1**: Fix `max_open_trades: 3→1`, set `leverage_config.py` to 1.0x
3. **P1**: Update `circuit_breaker.json` — wire to actually HALT when PAUSED (-33% monthly)
4. **P4**: Fix `SignalBusMixin` to delegate to real `shared_config/signal_bus.py`

### This week
5. **P1**: Implement `_should_allow_entry()` in AroonMomentumEngine_Hybrid
6. **P1**: Wire `position_sizer.py` to Freqtrade config (fractional Kelly sizing)
7. **P3**: Build HMM regime detector + regime_router.py
8. **P2**: Build backtest_db.py + preview.py analytics layer

### Next week
9. **P4**: Pull local models (gemma3:4b, deepseek-r1:8b), fix TradingAgents config
10. **P4**: Fix VDBMixin to enable real ChromaDB querying at trade time
11. **P5**: Clone GeneTrader, define gene space, run 20 GA generations

### Blocked until P1-P5 pass
- P6: Start 30-day dry-run gate
- P7: Graduated live deployment
