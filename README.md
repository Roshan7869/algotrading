# Algotrading — measurement-first strategy research on a freqtrade fork

A personal research platform for one question: **does a rule-based crypto strategy still make money
after realistic costs?** It is a fork of [freqtrade](https://www.freqtrade.io) (GPL-3, engine tree
retained unmodified) plus a small measurement layer: a scoreboard with a sealed holdout, a
walk-forward validator with a bootstrap gate, a risk supervisor, and a secret gate.

It is not a product, not a signal service, and not a trading system. Nothing in this repo is
authorised to touch money, and the current answer to the question above is **no**.

## Status — 2026-11-19

> **Phase 2 gate: FAILED. No strategy shows a positive out-of-sample expectancy at 10 bps all-in
> per side (≈20 bps round trip). Phase 2.3 dry-run does not launch; Phase 3 stays gated; no live
> trading.** Decision of record:
> [`reports/decisions/no-edge-memo-20261119.md`](reports/decisions/no-edge-memo-20261119.md).

| Fact | State | Evidence |
|---|---|---|
| Phase 2 gate | **FAIL** — cost drag dominates at 1h trade frequency | `reports/decisions/no-edge-memo-20261119.md` |
| Live trading | **none**; live config families are gone/disabled, the only runnable config is dry-run | `scripts/validate_configs.py` rejects `dry_run: false` |
| Loadable strategies | **7** | `freqtrade list-strategies --userdir user_data`, run 2026-11-19 |
| Quarantined for lookahead | **19** files | `user_data/strategies/_archived/lookahead_20261119/`; audit in `reports/phase2/2.1/LOOKAHEAD_AUDIT.md` |
| Canonical configs | **3** — futures backtest, spot, dry-run | `reports/phase1/configs/PHASE1_CONFIGS_REPORT.md` |
| Data | 20 USDT-M perpetual pairs, 1h, through 2026-11-19 | `reports/phase1/data/DATA_REFRESH.md` (manifest `sha256:e8485279…`) |

### What was actually measured

- **Scoreboard** — 8 strategies × 20 pairs, 10 bps per side, three-way split with a sealed holdout:
  every non-crashing strategy is net-negative on the validation window; best is BollingerMeanReversion
  at −0.271 %/trade (72 trades). Train 2025 is equally negative.
  → [`reports/scoreboard-20261119-1229/SCOREBOARD.md`](reports/scoreboard-20261119-1229/SCOREBOARD.md)
  (manifest `sha256:41a5cd17…`).
- **Walk-forward** — rolling 6-month train / 1-month test, 10,000-resample bootstrap:
  EmaTrendFollowing −1.115 %/trade, 95 % CI [−1.736 %, −0.468 %], 0 % positive windows → loud
  `WALKFORWARD FAIL`, exit 1.
  → [`reports/walkforward-20261119-1311/WALKFORWARD.md`](reports/walkforward-20261119-1311/WALKFORWARD.md)
- **Root cause** (measured, not guessed): a strategy must clear ~20 bps round-trip before it earns
  anything; the surviving set trades 72–3,172 times per 6-month window on 1h bars, and the 3×
  leverage callbacks triple the bleed. The pre-remediation "+21,300 % / +3.6 M %" numbers were
  artifacts of unlimited stake on strategies that are now quarantined.

Next step is a **user decision**, listed in the memo: cost-aware redesign (4h/1d signals, ≥100 bps
target gross expectancy, maker entries), or park the trading track and keep the measurement assets.

## Quickstart

Prerequisites: Windows, the repo-local `.venv` built per [`SETUP_LOCAL.md`](SETUP_LOCAL.md)
(Python 3.13, freqtrade installed editable). Run everything from the repo root. `python` below means
`.venv\Scripts\python.exe`; on this host a bare `python` may resolve to a different interpreter.

```bat
REM 0. Sanity: which strategies actually load (expect 7, all OK)
.venv\Scripts\python.exe -m freqtrade list-strategies --userdir user_data
```

**1. Validate the canonical configs** — parse, required keys, loopback API, env placeholders, no
`dry_run: false`:

```bat
.venv\Scripts\python.exe scripts\validate_configs.py
REM PASS -> "checks: 43 pass, 0 warn, 0 fail | RESULT: PASS" (exit 0)
```

**2. Secret gate** (Phase 0.4). Scan the whole tree, then enable the hooks once per clone:

```bat
.venv\Scripts\python.exe scripts\secrets_scan.py --all
git config core.hooksPath .githooks
git config --get core.hooksPath
```

`pre-commit` scans added lines only; `pre-push` scans the whole tree. See
[`.githooks/README.md`](.githooks/README.md).

**3. Scoreboard** — the centrepiece. Three stages (`train` ≤2025-12-31, `validation` 2026-01-01→06-30
= selection, `holdout` 2026-07-01→run date = **sealed**), 20-pair futures universe, fees + slippage
proxy in, reproducibility header + manifest hash out.

```bat
REM smoke first: one strategy, two pairs, validation stage only (~minutes)
.venv\Scripts\python.exe scripts\scoreboard.py --stage validation --limit 2 ^
    --strategies EmaTrendFollowing --outdir reports\scoreboard-smoke

REM full run: all stages x 7 strategies x 20 pairs (hours; writes reports\scoreboard-<ts>\)
.venv\Scripts\python.exe scripts\scoreboard.py --stage all

REM reproducibility: run the same smoke again into a second dir, then compare at 4 dp
.venv\Scripts\python.exe scripts\scoreboard.py --stage validation --limit 2 ^
    --strategies EmaTrendFollowing --outdir reports\scoreboard-smoke-rerun
.venv\Scripts\python.exe scripts\scoreboard.py --verify reports\scoreboard-smoke reports\scoreboard-smoke-rerun
```

`--open-holdout` unseals the holdout into the report. That is a **Phase 2.4, once-only** action
(plan §2.4); do not use it for exploration.

**4. Walk-forward** — rolling train/test, per-window expectancy and an aggregate bootstrap 95 % CI;
the gate is CI lower bound > 0 with ≥30 trades. It exits 1 and prints `WALKFORWARD FAIL` when the
edge is not there — that is the tool working.

```bat
REM smoke: 3 monthly windows on one strategy
.venv\Scripts\python.exe research\walkforward.py --strategy EmaTrendFollowing ^
    --start 20250801 --end 20251101 --limit 5

REM full: 2024-01 -> run date, default strategy set, writes reports\walkforward-<ts>\
.venv\Scripts\python.exe research\walkforward.py
```

**5. Supervisor preflight** — checks that the circuit breaker is readable and not PAUSED before any
session start; it fails closed:

```bat
.venv\Scripts\python.exe scripts\supervise.py --preflight
REM today: state=UNKNOWN, should_stop=true, exit 1 — no balance source is wired, so it refuses.
REM That is correct behaviour, not a bug. Wiring a balance feed is Phase 2.3 work (gated).
```

`scripts\supervise.py --config user_data\config_dryrun.json` is the session launcher: it polls the
breaker every 5 min and stops the bot via REST/process signal on PAUSED or UNKNOWN. **Do not run it
against anything but the dry-run config.**

## Repo map

| Path | What lives there |
|---|---|
| `freqtrade/` | Upstream freqtrade engine (GPL-3), editable install. Treat as vendored; strategy work does not modify the engine. |
| `user_data/strategies/` | The 7 loadable strategies. `leverage_config.py`, `signal_bus_mixin.py`, `vdb_mixin.py`, `kronos_indicators.py` are helper modules, not strategies. |
| `user_data/strategies/_archived/lookahead_20261119/` | 19 files quarantined for lookahead / invalid baselines. Evidence: `reports/phase2/2.1/LOOKAHEAD_AUDIT.md`. Not in the scoreboard. |
| `user_data/config_backtest.json` | Canonical futures backtest config (purpose header, explicit stake/stoploss/db_url). |
| `user_data/config_spot.json` | Canonical spot config (leverage forced to 1.0 by freqtrade). |
| `user_data/config_dryrun.json` | Canonical dry-run config. The only config a session may use, and only when a phase authorises it. |
| `user_data/data/binance/` | Feather data: spot `1h` pairs and `futures/` (1h/4h/1m/5m + funding/mark). The 20-pair 1h futures set is canonical. |
| `research/` | `walkforward.py` (bootstrap gate), `harness.py` (KB + vault research brief). |
| `scripts/` | `scoreboard.py`, `supervise.py`, `circuit_breaker.py`, `validate_configs.py`, `secrets_scan.py` are the trusted set. The rest is legacy and not on the measurement path. |
| `reports/` | Evidence, not documentation: `phase0/`, `phase1/`, `phase2/`, `scoreboard-<ts>/`, `walkforward-<ts>/`, `decisions/`. |
| `docs/` | [`leverage-matrix.md`](docs/leverage-matrix.md) — the one table of where leverage actually comes from. |
| `attic/` | Decision quarantine. `attic/results/`, `configs/`, `docs-upstream/` etc. are gitignored except `README.md` and the `*.md` indexes; nothing here is evidence. |
| `reports/phase4/docs/` | This phase's docs work: `INVENTORY.md`, `POLISH_REPORT.md`. |
| `EXECUTION_PLAN.md` | The governing plan: root causes R1–R6, phases 0–4, anti-goals, outcome log. |
| `GOLDFISH-REVIEW-EXECUTION_PLAN.md` | The adversarial review that rejected plan v0.1 and produced v0.2. |

## Reproducibility contract

A number is only usable in a decision if it can be re-derived. Every stored result therefore carries,
in its `MANIFEST.json` and report header:

1. **git SHA** of the tree that produced it, and the freqtrade version string.
2. **Data manifest** — file list with row counts and first/last timestamps, hashed (`manifest_hash`).
3. **Config path + config sha256** — the exact JSON that was run.
4. **Fee/cost model**, stated explicitly (`--fee 0.001` per side = 10 bps fee + slippage proxy; the
   backtester has no native slippage model).
5. **Stage boundaries**, strategy/universe lists, and a schema version.

Comparisons are made **at 4 dp on the same machine**, with timestamps excluded from hashes — never
"byte-identical across machines". `scripts/scoreboard.py --verify A B` enforces this: it compares
`manifest_hash` and every scalar at 4 dp and exits non-zero on any mismatch.

Corollaries enforced in code, not by convention: the holdout is written to a separate file that
selection never reads; the walkforward gate refuses to pass without ≥30 trades and a positive CI
lower bound; `validate_configs.py` rejects `dry_run: false`.

## Documentation

Start with [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md). Phase state as of 2026-11-19:

| Phase | Scope | State |
|---|---|---|
| 0 | Safety baseline: secrets purge, risk supervisor, secret gate, dead DB removal | done (key rotation declined by the user — accepted risk, see memo) |
| 1 | Trust reset: attic, 3 configs, data refresh, scoreboard with sealed holdout | done |
| 2 | One honest candidate or honest failure: lookahead audit, stop fixes, walkforward, dry-run, Go/No-Go | **FAIL at 2.4 — no edge; 2.3 never launched** |
| 3 | Integrations (TradingAgents, module-consumer map, FlowSurface, daily report) | gated on Phase 2 PASS |
| 4 | Operations: docs collapse (this), KB maintenance, `make check` (specified in the plan, not built yet) | in progress |

Supporting docs: [`SETUP_LOCAL.md`](SETUP_LOCAL.md) (machine setup, verified),
[`docs/leverage-matrix.md`](docs/leverage-matrix.md) (leverage sources per strategy),
[`reports/decisions/no-edge-memo-20261119.md`](reports/decisions/no-edge-memo-20261119.md) (failure
memo), [`attic/docs-history/MOVED.md`](attic/docs-history/MOVED.md) (what was retired and why).

## Guardrails

- **No live money.** No config with `dry_run: false` is valid; the validator fails on one. Arming
  live trading requires Phase 2 PASS + a demonstrated supervisor + a running journal + explicit user
  action, and this repo never arms anything.
- **Holdout discipline.** The holdout is opened once (Phase 2.4) and reported beside validation. If
  it contradicts validation, the answer is FAIL.
- **No new strategies before the gate.** Signal work lives in Phase 3 and stays out of the order path.
- **Attic is quarantine, not storage.** A file moves there with a `MOVED.md` reason; it does not come
  back without passing the current gate.
- **A number without a report path is an opinion.** Docs cite `reports/…`; if a claim has no
  artifact, it does not belong in a doc.
