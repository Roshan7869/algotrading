# Algotrading Project: Layer-by-Layer Audit Report

**Date:** 2026-05-19
**Scope:** 8-layer functionality + integration gap analysis

---

## 1. Configuration Layer

### What Exists
- `shared_config/` — 7 JSON signal files (sentiment, regime, circuit breaker, leverage, outcome, miroshark brain, tradingagents)
- `env_file` (.env.example) with API keys
- 49+ JSON strategy configs in `user_data/`
- `leverage_config.py` — hardcoded 3.0x default
- `config_market_ready.json`, `config_unified.json`

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| Leverage: 3 sources, 1 value | **CRITICAL** | `leverage_config.py` (hardcoded 3.0x), `leverage_signal.json` (3.0x), `.env` (3.0x) — all say the same thing, but no single source of truth. If any diverges, no alert. |
| Config path fragmentation | **MAJOR** | Strategies resolve `SHARED_CONFIG_DIR` via env var but fall back to different hardcoded paths: some use `shared_config/` (relative), some `/freqtrade/shared_config` (container). |
| No schema validation | **MAJOR** | JSON configs have no Pydantic/JSON Schema — malformed JSON silently returns defaults. |
| 3 naming conventions | **MINOR** | `HEdge/`, `shared_config/`, `user_data/strategies/*.json` — no unified config registry. |

---

## 2. Strategy Layer

### What Exists
- **90+ strategy files** in `user_data/strategies/`
- **6-strategy ensemble** (EnsembleStrategy) with voting
- **9 VectorOmni variants** (VectorOmniStrategy v1-v9, VectorStrategy)
- **52 generated strategies** in `generated_strategies/`
- **4 Kronos variants** (kronos_v1, v2, v3, v4)
- **AroonMomentumEngine_Hybrid** — the default active strategy
- **SignalBusMixin, VDBMixin** — intended integration base classes

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| SignalBusMixin is stub | **CRITICAL** | `signal_bus_mixin.py` has `pass` for `publish_signal()`, `get_signal()`, `has_signal()`. Strategies inherit it but gain zero functionality. |
| VDBMixin is stub | **CRITICAL** | `vdb_mixin.py` has all methods returning empty — `query_vdb()` returns `[]`, `record_outcome()` is `pass`, `_vdb_is_available()` returns `False`. ChromaDB (443 chunks) is never queried during trading. |
| Generated strategies orphaned | **CRITICAL** | 52 generated strategies, 5 with failed generations (C013, C024, N003, N006, N011) — none integrated into the ensemble or traded actively. |
| VectorOmni variant bloat | **MAJOR** | 9 VectorOmni variants exist without clear lineage, benchmarking hierarchy, or pruning criteria. No evidence which (if any) is actively traded. |
| Duplicate kronos_indicators.py | **MAJOR** | Two identical copies: `strategies/kronos_indicators.py` and `kronos_chromadb/kronos_indicators.py` — drift risk. |
| No strategy registry | **MINOR** | Strategies discovered by filesystem — no single registry, version, or active flag. |

### Data Flow
```
ensemble_strategy.py → _load_signal_bus() → get_bus().read() → JSON files
                    → populate_entry_trend() → votes from 6 indicator strategies
                    → VDBMixin._vdb_is_available() → ALWAYS FALSE
                    → circuit_breaker.json check in bot_loop_start() → only KILL signal
```

---

## 3. AI / Signal Layer

### What Exists
- **TradingAgents**: Multi-LLM LangGraph system (5 analyst types, CEO manager, CRO manager, 3 risk debaters, B3 bonus scorer)
- **MiroShark brain**: Composite scoring model (regime + sentiment + outcome + agents + circuit_breaker)
- **MiroFish**: Swarm intelligence system (separate repo at `../MiroFish`)
- **SignalBus** (`shared_config/signal_bus.py`): Atomic read/write with staleness detection — **actually works**
- **7 active signal files** being written by daemon processes

### Signal File Freshness (as of 2026-05-18/19)
| File | Written By | Status |
|------|-----------|--------|
| `circuit_breaker.json` | `VectorStrategy` | **PAUSED** state |
| `sentiment_signal.json` | `signal_bus:234409` | Fresh (18:30) |
| `market_regime.json` | `signal_bus:259375` | Fresh (20:50) |
| `miroshark_brain.json` | `signal_bus:161894` | Fresh (18:48) |
| `outcome_feedback.json` | `signal_bus:234410` | Fresh (18:30) |
| `tradingagents_signal.json` | `signal_bus:343553` | 4 days old |
| `leverage_signal.json` | `signal_bus:343553` | 5 days old |

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| signal_bus_mixin.py vs. real signal_bus.py | **CRITICAL** | The mixin in `strategies/` is a no-op stub. But `shared_config/signal_bus.py` has a fully functional atomic SignalBus. The mixin should delegate to the real bus — it doesn't. |
| Strategies bypass the bus abstraction | **MAJOR** | Ensemble reads JSON directly via `get_bus().read()`. AroonMomentumEngine strategies read filesystem directly. No unified signal consumption API. |
| Circuit breaker: PAUSED but ignored | **CRITICAL** | `circuit_breaker.json` shows `state: "PAUSED"`, monthly PnL: **-33.21%**, weekly: **-8.17%**. The ensemble checks for KILL signal — but PAUSE triggers no halt. Trading may be continuing at -33% drawdown. |
| MiroShark brain no integration | **MAJOR** | `miroshark_brain.json` has composite scores but **no strategy reads it**. MiroShark runs as separate daemon with no integration path. |
| TradingAgents: scorer only, not gate | **MAJOR** | `tradingagents_signal.json` rating "Buy" feeds into ensemble threshold bonus (-1 vote requirement). It is NOT a trading gate — does not override decisions. |
| MiroFish not integrated | **MINOR** | MiroFish analyst exists in TradingAgents but no MiroFish-specific signal read path. Docker compose references `../MiroFish` but it's a separate repo. |
| AI-Trader / Neural-Trader / QuantDinger missing | **MAJOR** | Mentioned in documentation as existing systems — no code found on disk. QuantDinger has only `quantdinger_risk_gate.py` (5-tier risk classification script). |

---

## 4. Risk Management Layer

### What Exists
- **HEdge system**: 9 strategies under `HEdge/strategies/` (fixed fractional, risk-to-zero, half-Kelly, anti-martingale, scale-out, consecutive-loss-protect, win-rate-adaptive, champion, meta 7-in-1)
- **Circuit breaker** (`circuit_breaker.json`) — state machine (HEALTHY/PAUSED/KILL)
- **QuantDinger 5-tier risk gate** (`quantdinger_risk_gate.py`) — standalone script
- **Leverage config** (`leverage_config.py`) — hardcoded 3.0x
- **Trailing stop** via `trailing_stop = True` and ATR-based dynamic stoploss in ensemble
- **Stoploss**: -5% default, -10% in HEdge

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| HEdge strategies run independently | **CRITICAL** | 9 HEdge strategies are separate freqtrade configurations — they don't share positions, coordinate exits, or have unified risk. Up to 9 * independent max_open_trades = extreme concentration risk. |
| HedgeMeta7in1: 14 max trades at 10x | **CRITICAL** | HedgeMeta7in1 allows 14 max open trades at 10x leverage — highest risk in the system. Combined with other HEdge variants, total exposure is unbounded across them. |
| Circuit breaker: PAUSE is advisory | **CRITICAL** | QuantDinger risk gate writes circuit_breaker.json with SAFE/CAUTION/RESTRICT/HALT/LIQUIDATE tiers. But the ensemble only reads KILL state. PAUSE/RESTRICT/CAUTION have no enforcement. |
| No system-level max drawdown | **MAJOR** | Each strategy has its own stoploss but there's no global max-drawdown limit that halts all trading (e.g., "stop all if total PnL < -20%"). |
| Dynamic leverage = static 3.0x | **MAJOR** | leverage_config.py returns hardcoded 3.0x. leverage_signal.json also says 3.0x. No dynamic adjustment (e.g., Kelly-based sizing). |
| QuantDinger not wired | **MAJOR** | `quantdinger_risk_gate.py` has proper 5-tier risk → circuit_breaker integration, but it's a standalone CLI script. Not scheduled as a daemon. Not in docker-compose. |

---

## 5. Execution Layer

### What Exists
- **Freqtrade** core trading engine (stable image)
- **docker-compose.yml** — basic freqtrade container (default)
- **docker-compose.unified.yml** — full stack (freqtrade + mirofish + redis + postgres + tradingagents)
- **systemd service** (`freqtrade.service`) with watchdog
- **Dry-run mode** (default)

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| docker-compose.unified.yml is not default | **MAJOR** | The unified stack (with signal daemons, redis, postgres) is in a separate file. Default `docker-compose.yml` runs freqtrade alone — no signal producers. |
| No health checks between services | **MAJOR** | Docker compose has `depends_on` but no health checks. If tradingagents or mirofish fail, freqtrade continues trading with stale signals. |
| Systemd references global freqtrade | **MINOR** | Systemd service points to `/usr/bin/freqtrade` but the project has local freqtrade fork in `freqtrade/` directory. |
| No signal_bus daemon restart policy | **MINOR** | Signal bus writer processes run outside docker (pid-based) — no restart on crash. |
| No monitoring/alerting | **MAJOR** | No service health monitoring. No alert on stale signals (>max_age). No PnL or drawdown alerts. |

---

## 6. Data Layer

### What Exists
- **ChromaDB** — 443 strategy chunks from YouTube, indexed with all-MiniLM-L6-v2
- **SQLite DB** (`tradesv3.dryrun.sqlite`) — freqtrade internal trade storage
- **strategy_db/** — ChromaDB ingestion and CLI bridge (`gcode_bridge.py`)
- **Backtest results** — JSON files in `user_data/backtest_results/`
- **strategy_rankings.json**

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| ChromaDB never queried during trading | **CRITICAL** | `vdb_mixin.py` is a stub — all strategies inherit `_vdb_is_available() → False`. The 443 strategy chunks exist but provide zero runtime value. |
| No strategy_db MCP server | **MAJOR** | CLI bridge (`gcode_bridge.py`) works manually but MCP server is "planned" — no programmatic access from agents. |
| Backtest results: no unified analytics | **MAJOR** | Backtest results exist as JSON files but there's no pipeline that aggregates them, compares strategies, or feeds results into strategy selection. |
| No persistent trade analytics DB | **MAJOR** | `outcome_feedback.json` has summary stats but no per-trade queryable history. SQLite is freqtrade's internal format. |
| strategy_rankings.json: undocumented criteria | **MINOR** | Ranking exists but criteria/methodology not documented. |

---

## 7. Agent / Orchestration Layer

### What Exists
- **NEXUS v3** — 1097 indexed resources, FAISS + ISO embeddings, 5 learning layers (Thompson Sampling + Self-Reflection + Cluster Affinity)
- **RuFlo v3.6.27** — swarm orchestration
- **Claude .claude/** — 29 skills, 22 agents, 9 commands
- **Coach bridge** — 65 tests, 7 tables, 6 skills, 5 MCP tools (fully shipped)
- **31 algotrading skills** in NEXUS DB (resource table, not on disk)

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| 31 algotrading skills in DB but not on disk | **CRITICAL** | NEXUS recognizes `trading` project and has 31 algotrading skill records. But none have materialized `.md` skill files — cannot be loaded by agents. |
| No NEXUS↔Freqtrade integration | **CRITICAL** | NEXUS has zero ability to interact with the live trading engine. No MCP tools for: start/stop trades, read positions, execute backtests, adjust configs. |
| AGENTS.md references NEXUS but no direct integration | **MAJOR** | AGENTS.md mentions NEXUS v3 routing as if integrated, but the actual trading pipeline doesn't touch NEXUS at all. |
| No trade outcome → NEXUS learning feedback | **MAJOR** | `outcome_feedback.json` has win rates per regime. NEXUS has Thompson Sampling beliefs and Self-Reflection. But trade outcomes never feed into NEXUS learning pipeline. |
| RuFlo swarm initialized but unused | **MAJOR** | RuFlo registered via hooks, swarm initialized, but never used for actual trading coordination. |
| No trading-specific Claude agents | **MINOR** | 29 skills + 22 agents in .claude/ but none are trading-specific (e.g., "backtest agent", "risk monitor agent", "signal evaluator"). |

---

## 8. Deployment Layer

### What Exists
- **Docker**: 5 compose files, 8 Dockerfiles
- **CI/CD**: GitHub Actions workflows
- **Scripts**: `setup.sh`, `run_wsl.sh`, `Run-Trading.ps1`

### Gaps
| Gap | Severity | Detail |
|-----|----------|--------|
| 19 Docker definitions — fragmentation | **MAJOR** | 5 compose files + 8 Dockerfiles spread across root, `docker/`, `TradingAgents/`, `.github/`. No single source of truth. |
| 3 deployment entry points | **MAJOR** | `run_wsl.sh` (6 options), `Run-Trading.ps1` (3 modes), `docker compose up` — inconsistent behavior. |
| .env.example references GPT-4o, key is placeholder | **MAJOR** | OPENAI_API_KEY is `sk-your-key-here`. No documented process for secret provisioning. |
| No staging/prod separation | **MAJOR** | No environment distinction. Dry-run and live share the same configs — risk of accidental live trading. |
| No automated rollback | **MAJOR** | No strategy to roll back to previous version on failure or excessive drawdown. |

---

## Cross-Cutting Integration Summary

```
                    Signal Bus Leak
                    ───────────────
  shared_config/signal_bus.py (REAL)    ←── daemons write here
          │
          ├──→ ensemble_strategy.py reads via get_bus().read()    (OK)
          ├──→ AroonMomentumEngine_Hybrid reads filesystem directly (DUPLICATE)
          └──→ signal_bus_mixin.py (STUB)                         (DEAD CODE)


                    VDB Leak
                    ────────
  ChromaDB (443 chunks)             ←── ingestion pipeline writes here
          │
          ├──→ strategy_db/gcode_bridge.py (CLI only, no MCP)    (MANUAL)
          └──→ vdb_mixin.py (STUB)                               (DEAD CODE)


                    No Orchestrated Loop
                    ────────────────────
  Freqtrade (execution)  ←── signals?  ──→  TradingAgents (AI)
       │                                            │
       │                                   MiroShark (composite)
       │                                            │
       └──── risk? ──── HEdge (9 strategies) ───────┘
                                   │
                     No shared position tracking
                    No coordinated risk limits


                    No Feedback Loop
                    ─────────────────
  Trade outcomes (SQLite + outcome_feedback.json)
          │
          ├──→ NOT fed back to NEXUS learning (Thompson beliefs)
          ├──→ NOT fed into strategy optimization
          └──→ NOT fed into VDB (ChromaDB)

                    Legend
                    ──────
  CRITICAL: Active risk of financial loss
  MAJOR:    Significant integration gap, missing feature
  MINOR:    Cleanup/consolidation needed
```

---

## Priority Remediation Recommendations

### Tier 1: Active Financial Risk (Fix Immediately)
1. **Circuit breaker: enforce PAUSE state** — `ensemble_strategy.py:bot_loop_start()` currently only halts on KILL. Add PAUSE enforcement. Monthly drawdown is -33.21%.
2. **HedgeMeta7in1: cap max trades** — 14 trades at 10x leverage is extreme concentration risk. Reduce or coordinate across HEdge strategies.
3. **SignalBusMixin: wire to real SignalBus** — Replace `pass` stubs with delegation to `shared_config/signal_bus.py`. Every strategy should use the same bus.

### Tier 2: Critical Integration Gaps (Fix This Week)
4. **Wire QuantDinger risk gate as daemon** — Add `quantdinger_risk_gate.py` as a periodic service (docker or cron) that actually enforces risk tiers.
5. **System-level max drawdown** — Add global PnL monitor that halts all trading if aggregate drawdown exceeds threshold (e.g., -20%).
6. **Stale signal detection** — Alert if `tradingagents_signal.json` or `market_regime.json` exceed `max_age`. Currently no freshness monitoring.

### Tier 3: Architecture (Fix This Sprint)
7. **VDBMixin: enable ChromaDB queries** — Wire `vdb_mixin.py` to the real ChromaDB. The 443 strategy chunks are wasted otherwise.
8. **NEXUS↔Freqtrade bridge** — Create MCP tools (`trade_status`, `execute_backtest`, `adjust_config`) so NEXUS can interact with the trading engine.
9. **Trade outcomes → NEXUS learning** — Pipe `outcome_feedback.json` into NEXUS Thompson Sampling beliefs and Self-Reflection.

### Tier 4: Consolidation (Fix When Possible)
10. **Merge 5 docker-compose files** → single unified file with profiles.
11. **Prune dead strategies** — VectorOmni variants (keep 1-2), generated strategies (integrate top ones, archive rest), duplicate kronos_indicators.py.
12. **Strategy DB MCP server** — Turn `gcode_bridge.py` CLI into proper MCP server for programmatic ChromaDB access.
13. **Materialize 31 algotrading skills** in NEXUS — Currently DB records only, no skill files on disk.
