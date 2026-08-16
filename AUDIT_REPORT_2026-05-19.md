# ALGOTRADING — COMPREHENSIVE MULTI-LAYER AUDIT REPORT

**Date:** 2026-05-19 | **Project:** Algotrading | **Scope:** Full 8-layer audit

---

## EXECUTIVE BRIEFING

The **Algotrading** project is a sophisticated multi-agent algorithmic trading system integrating Freqtrade, LangGraph-based LLM agents (TradingAgents), swarm intelligence (MiroFish/Shark), ChromaDB vector strategy DB, and a filesystem-based signal bus. It runs 13 live agents across 19 models in a 9-layer architecture with HMM regime detection, circuit breakers, and ATR-based position sizing.

**Total findings across all 8 audit layers:**

| Team | Domain | CRITICAL | HIGH | MEDIUM | LOW |
|------|--------|----------|------|--------|-----|
| 🔴 Red | Security & Compliance | **3** | 7 | 9 | 5 |
| 🏗️ Blue | Architecture & DDD | **2** | 6 | 7 | 2 |
| 🟢 Green | Backend & API | **3** | 7 | 12 | 4 |
| 🟠 Orange | DevOps & Infra | **3** | 5 | 5 | 3 |
| 🟣 Purple | Frontend & UI | 0 | 2 | 2 | 2 |
| 🌀 Cyan | QA & Testing | **3** | 4 | 5 | 4 |
| 🟡 Yellow | Documentation | 1 | **6** | 6 | 3 |
| 🎀 Pink | Trading Strategy | **5** | 6 | 6 | 5 |
| **TOTAL** | **All Layers** | **20** | **43** | **52** | **28** |

---

## 🔴 TEAM RED — SECURITY & COMPLIANCE (CSO)

### CRITICAL

| # | Finding | File | Action Required |
|---|---------|------|----------------|
| C-1 | **Live Binance API keys** exposed in `.env` (DRY_RUN=true but real creds) | `.env:22-27` | **ROTATE IMMEDIATELY** — revoke keys at Binance, purge from git history |
| C-2 | **Telegram bot token** committed in `.env.example` (not placeholders) | `.env.example:10` | Revoke token via @BotFather, use `git filter-repo` to purge history |
| C-3 | **Hardcoded API creds**: API server bound to `0.0.0.0:8080`, weak JWT secret (`freqtrade-secret-key-change-me`), wildcard CORS (`*`), OpenAPI enabled | `config_api.json` | Set `listen_ip_address: 127.0.0.1`, generate random JWT, remove `enable_openapi` |

### HIGH
- Command injection via `shell=True` in `queue_backtest.py`, `godmode_batch_30d.py`
- Prompt injection in LLM agents (`bull_researcher.py`, `agent_utils.py`)
- Plaintext trading signals in `shared_config/*.json` (leaks PnL, positions)
- Weak Postgres default password (`freqtrade`), Redis without auth
- Telegram token in URL query string

---

## 🏗️ TEAM BLUE — ARCHITECTURE & DDD

### CRITICAL

| # | Finding | File | Action Required |
|---|---------|------|----------------|
| C-1 | **No dependency inversion** — All layers import concrete implementations. yfinance imported directly at module-level in `trading_graph.py:10` | `trading_graph.py`, `dataflows/interface.py` | Introduce abstract `IDataVendor` interface |
| C-2 | **Star imports** — `from tradingagents.agents import *` creates implicit coupling to 20+ symbols | `setup.py:7`, `trading_graph.py:18` | Replace with explicit imports |

### HIGH
- Two **competing agent systems**: `TradingAgents/` (LangGraph) vs `scripts/agents/` (Ollama) — fork in place
- **49 JSON configs** with duplicated `pair_whitelist`, `leverage` values — no single source of truth
- `SignalBusMixin` and `VDBMixin` are **no-op stubs** used by live strategies
- **50+ auto-generated strategy files** in `generated/` never pruned
- Global mutable state in `dataflows/config.py`
- Leverage specified inconsistently: 6x in .env, 3x in `config_unified.json`

---

## 🟢 TEAM GREEN — BACKEND & API

### CRITICAL

| # | Finding | File | Action Required |
|---|---------|------|----------------|
| C-1 | **f-string SQL injection** in migrations — all `text(f"...")` calls | `migrations.py` | Use SQLAlchemy schema API or adopt Alembic |
| C-2 | **Shared mutable state** in `ApiBG` without synchronization | `webserver_bgwork.py` | Add `threading.Lock()` around all shared state |
| C-3 | **Event loop conflict** in backtest background task | `api_backtest.py:51` | Use `loop.run_in_executor()` |

### HIGH
- N+1 queries on trade listing (lazy `include_orders=True`)
- Missing index on `trades.is_open`
- JWT secret defaults (`"super-secret"`, `"somethingRandom"`)
- No rate limiting on any endpoint (incl `/token/login`)
- Transaction management anti-pattern: `Trade.commit()` inside `Order.update_orders()`
- WebSocket token passed as query parameter

---

## 🟠 TEAM ORANGE — DEVOPS & INFRASTRUCTURE

### CRITICAL

| # | Finding | File | Action Required |
|---|---------|------|----------------|
| C-1 | **No HEALTHCHECK** in any of 9 Dockerfiles | All Dockerfiles | Add `HEALTHCHECK CMD curl --fail http://localhost:8080/api/v1/ping` |
| C-2 | **Secrets in plaintext** via `.env` bind-mounted into containers | `docker-compose.unified.yml` | Use Docker secrets or vault |
| C-3 | **No database backup strategy** — PostgreSQL/SQLite trade data has zero protection | `docker-compose.unified.yml` | Add `pg_dump` cron job + offsite backup |

### HIGH
- Postgres default password `freqtrade` if env var unset
- TradingAgents mounts entire source code (production anti-pattern)
- Root containers in `Dockerfile.custom`, `Dockerfile.jupyter`
- `.dockerignore` does not exclude `.env` or secret files
- `ollama/ollama:latest` not pinned to version

---

## 🟣 TEAM PURPLE — FRONTEND & UI

**This project has no frontend application.** The freqtrade web UI (React SPA) is not installed — only the fallback page exists.

### HIGH
| # | Finding | Action Required |
|---|---------|----------------|
| H1 | Web UI not installed — users hitting the API server URL see a fallback | Run `freqtrade install-ui` |
| H2 | Accent color typo in `mkdocs.yml:75`: `"tear"` should be `"teal"` | Fix typo |

---

## 🌀 TEAM CYAN — QA & TESTING

### CRITICAL

| # | Finding | File | Action Required |
|---|---------|------|----------------|
| C-1 | **Strategy DB has zero tests** — ChromaDB, gcode_bridge, ingest completely untested | `strategy_db/` | Add unit tests, target 70% coverage |
| C-2 | **No end-to-end test** connecting Strategy DB → TradingAgents → freqtrade | Project-wide | Create integration test |
| C-3 | **No coverage threshold** in CI — Codecov reports but does not enforce minimum | `.coveragerc` | Add `--cov-fail-under=50` |

### HIGH
- Async code virtually untested (1 `@pytest.mark.asyncio` test only)
- TradingAgents integration tests absent (LLM calls not mocked for integration)
- `MagicMock()` without `spec` in shared fixtures allows contract drift
- Cross-test state pollution via shared `np.random.seed(42)`

---

## 🟡 TEAM YELLOW — DOCUMENTATION

### CRITICAL
| # | Finding | Action Required |
|---|---------|----------------|
| 1 | **Root README is stock Freqtrade** — does not describe the actual Algotrading project | Rewrite with architecture, stack, quickstart |

### HIGH
- No incident response/runbook document
- Duplicate deployment checklists (`DEPLOYMENT_CHECKLIST.md` root vs `docs/`)
- No Algotrading-specific API documentation
- No docstring enforcement in CI (pre-commit has no pydocstyle)
- `QUICK_START.md` references stale state (Windows paths, past fixes)
- 12+ unindexed Godmode research documents

---

## 🎀 TEAM PINK — TRADING STRATEGY & RISK

### CRITICAL

| # | Finding | File | Action Required |
|---|---------|------|----------------|
| C-1 | **Hardcoded 10x leverage** with no dynamic adjustment — all strategies | All strategies' `leverage()` | Cap leverage inversely to ATR, use MiroShark signal |
| C-2 | **No on-exchange stop-loss** — `stoploss_on_exchange: False` everywhere | All HEdge strategies | Set to `True`, add liquidation check `liquidation_price * 1.02` |
| C-3 | **Circuit breaker PAUSED state ignored** by MiroShark brain (scores as `UNKNOWN=1.0`) | `shared_config/circuit_breaker.json`, `brain.py` | Unify schema, check for ANY non-HEALTHY state |
| C-4 | **RSI uses SMA instead of Wilder's EMA** — all 30+ strategies wrong | `hedge_01*.py:126-133` | Use `ta.RSI()` from TA-Lib |
| C-5 | **Walk-forward parser assigns win_rate = loss count** — overfitting detection broken | `walk_forward_validate.py:61` | Fix: `win_rate = wins / (wins + losses) * 100` |

### HIGH
- No Kelly Criterion in live position sizing (only post-hoc analysis)
- Inverse vol position sizer has math error (`max_positions` cancels out)
- No take-profit logic in most strategies (rely on `minimal_roi` + trailing only)
- Strategy DB auto-generated code produces **non-trading stubs** (empty entry/exit logic)
- Hyperopt slippage mismatch: 0.05% vs actual 5%
- VaR-95 computed on percentage (0.1) instead of dollar exposure (100x understatement)

---

## EMERGENCY ACTION ITEMS (Top 5)

1. **ROTATE ALL SECRETS** — Binance API keys, Telegram bot token are live and exposed in git
2. **FIX CIRCUIT BREAKER** — It's PAUSED with -33% monthly PnL but the brain ignores it
3. **FIX WALK-FORWARD VALIDATOR** — win_rate = loss_count breaks all overfitting detection
4. **ADD ON-EXCHANGE STOP-LOSS** — 10x leverage with in-process SL = liquidation risk
5. **FIX RSI CALCULATION** — SMA not Wilder's EMA affects ALL 30+ strategies

---

## REPORT LOCATIONS

Full detailed reports from each audit team are available in the session history above:
- 🔴 Security: 3 CRITICAL, 7 HIGH, 9 MEDIUM, 5 LOW
- 🏗️ Architecture: 2 CRITICAL, 6 HIGH, 7 MEDIUM, 2 LOW
- 🟢 Backend: 3 CRITICAL, 7 HIGH, 12 MEDIUM, 4 LOW
- 🟠 DevOps: 3 CRITICAL, 5 HIGH, 5 MEDIUM, 3 LOW
- 🟣 Frontend: 0 CRITICAL, 2 HIGH, 2 MEDIUM, 2 LOW
- 🌀 QA: 3 CRITICAL, 4 HIGH, 5 MEDIUM, 4 LOW
- 🟡 Docs: 1 CRITICAL, 6 HIGH, 6 MEDIUM, 3 LOW
- 🎀 Trading: 5 CRITICAL, 6 HIGH, 6 MEDIUM, 5 LOW

**Grand Total: 20 CRITICAL, 43 HIGH, 52 MEDIUM, 28 LOW**
