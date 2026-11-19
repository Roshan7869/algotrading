# PROPOSED AGENTS.md — not active, requires user approval

The runtime refused the direct write to `AGENTS.md` ("protected agent-instruction file … user has NOT
consented"). Phase 4.1 therefore could not fix the live file. This is the exact replacement text,
ready to be applied by the user (or by an agent after consent). Until it is applied, `AGENTS.md`
still points at `/home/roshan/Downloads/Algotrading` and still advertises the pre-remediation counts
(58/36/28 strategies), which is why `stale_paths_remaining` is not zero.

To apply: replace the whole content of `D:\dev\algotrading\AGENTS.md` with the block below
(everything after the `---` line).

---

# AGENTS.md — entry point for AI agents

Read this before touching anything. It replaces the old documentation index (which pointed at
`/home/roshan/Downloads/Algotrading` and listed pre-remediation counts that no longer exist).

## What this repo is

A personal, measurement-first trading **research** platform on a freqtrade fork. One question:
does a rule-based crypto strategy survive realistic costs? The answer, as of 2026-11-19, is no —
and the repo's job is to keep that answer honest rather than to produce a strategy.

- Host: Windows 11, repo at `D:\dev\algotrading`. The agent shell is bash (git-bash); native tools
  need `C:/...` style paths, bash builtins accept `/d/dev/algotrading`.
- Python: **`.venv/Scripts/python.exe`** (Python 3.13, freqtrade installed editable). A bare
  `python`/`python3` on this host is a different interpreter — do not use it for repo work.
- Setup details: `SETUP_LOCAL.md`. Governing plan: `EXECUTION_PLAN.md`.

## Current state — re-verify, never inherit

| Fact | Value | How to check |
|---|---|---|
| Phase 2 gate | **FAILED — no edge at 10 bps all-in per side** | `reports/decisions/no-edge-memo-20261119.md` |
| Live trading | none, prohibited | `scripts/validate_configs.py` rejects `dry_run: false` |
| Loadable strategies | **7** | `.venv/Scripts/python.exe -m freqtrade list-strategies --userdir user_data` |
| Quarantined for lookahead | **19** files | `user_data/strategies/_archived/lookahead_20261119/` + `reports/phase2/2.1/LOOKAHEAD_AUDIT.md` |
| Canonical configs | **3**: `config_backtest.json` (futures), `config_spot.json`, `config_dryrun.json` | `ls user_data/config_*.json` |
| Data | 20 USDT-M perpetual pairs, 1h, through 2026-11-19 | `reports/phase1/data/DATA_REFRESH.md` |
| Docs of record | `README.md`, this file, `EXECUTION_PLAN.md`, `GOLDFISH-REVIEW-EXECUTION_PLAN.md`, `SETUP_LOCAL.md` | root listing |

If a document disagrees with the table above, the document is stale. Counts are re-derived at
execution time; nothing is inherited from prose.

## Hard rules

1. **Never start trading.** Do not run `freqtrade trade`, `scripts/supervise.py --config …`, or any
   launcher against a live or dry-run config unless the user explicitly asks *and* a plan phase
   authorises it (Phase 2.3 is gated and did not launch). No config with `dry_run: false` may exist.
2. **Never open the holdout.** `scripts/scoreboard.py --open-holdout` is a once-only Phase 2.4
   action. Exploration uses `train`/`validation` only.
3. **No new strategies** and no strategy edits before the Phase 2 gate is passed, except the
   narrowly-scoped fixes a plan item names.
4. **No secrets in the tree.** Keys come from env placeholders (`${FREQTRADE_*}`); scan with
   `.venv/Scripts/python.exe scripts/secrets_scan.py --all` before proposing any commit. The hooks
   live in `.githooks/` and are enabled per clone (`git config core.hooksPath .githooks`).
5. **Do not edit the record.** `EXECUTION_PLAN.md`, `GOLDFISH-REVIEW-EXECUTION_PLAN.md` and
   `SETUP_LOCAL.md` are the audit trail; change them only when the user asks. Append outcomes, never
   rewrite history.
6. **`attic/` is quarantine, not storage.** Nothing comes out without passing the current gate. Do
   not cite attic content as evidence.
7. **A number without an artifact is an opinion.** Every claim needs git SHA + data manifest +
   config path + cost model, pointing at a path under `reports/`.

## Commands that work (verified 2026-11-19)

```bat
REM strategy inventory -> 7 rows, all OK
.venv\Scripts\python.exe -m freqtrade list-strategies --userdir user_data

REM canonical configs -> "43 pass, 0 warn, 0 fail | RESULT: PASS", exit 0
.venv\Scripts\python.exe scripts\validate_configs.py

REM secret gate -> silent, exit 0
.venv\Scripts\python.exe scripts\secrets_scan.py --all

REM scoreboard smoke -> reports\scoreboard-smoke\ with MANIFEST.json + SCOREBOARD.md
.venv\Scripts\python.exe scripts\scoreboard.py --stage validation --limit 2 --strategies EmaTrendFollowing --outdir reports\scoreboard-smoke

REM reproducibility check -> PASS only if manifest_hash matches and numbers match at 4 dp
.venv\Scripts\python.exe scripts\scoreboard.py --verify reports\scoreboard-smoke reports\scoreboard-smoke-rerun

REM walkforward smoke -> exits 1 with "WALKFORWARD FAIL" when there is no edge (expected today)
.venv\Scripts\python.exe research\walkforward.py --strategy EmaTrendFollowing --start 20250801 --end 20251101 --limit 5

REM supervisor preflight -> state=UNKNOWN, should_stop=true, exit 1 (fail-closed, no balance source)
.venv\Scripts\python.exe scripts\supervise.py --preflight
```

In bash the binary is `./.venv/Scripts/python.exe`; forward-slash arguments work for native tools.

## Repo map (short)

- `freqtrade/` — vendored upstream engine (GPL-3). Strategy work does not modify it.
- `user_data/strategies/` — 7 loadable strategies; helper modules (`leverage_config.py`,
  `signal_bus_mixin.py`, `vdb_mixin.py`, `kronos_indicators.py`) are not strategies.
- `user_data/strategies/_archived/lookahead_20261119/` — quarantined; not measured.
- `user_data/config_backtest.json` / `config_spot.json` / `config_dryrun.json` — the only valid configs.
- `user_data/data/binance/{,futures/}` — feather data; the 20-pair 1h futures set is canonical.
- `research/walkforward.py` — rolling train/test + bootstrap 95 % CI gate (loud FAIL).
- `scripts/scoreboard.py` — three-way split, sealed holdout, manifest hash, `--verify`.
- `scripts/supervise.py` — breaker poller + REST/process stop; `--preflight` fails closed.
- `scripts/circuit_breaker.py` — drawdown breaker consumed by the supervisor.
- `scripts/validate_configs.py`, `scripts/secrets_scan.py`, `.githooks/` — enforcement gates.
- `reports/` — evidence: `phase0/`, `phase1/`, `phase2/`, `scoreboard-<ts>/`, `walkforward-<ts>/`,
  `decisions/`. New phase evidence goes under `reports/phase<N>/…`.
- `docs/leverage-matrix.md` — per-strategy leverage sources (8 rows; written before
  `SupertrendEmaStrategy` was quarantined, so 7 rows are current).
- `attic/` — quarantine. `attic/docs-history/MOVED.md` lists the retired audits/plans and why.

## Legacy — do not treat as current

- `Makefile` targets (`run`, `full`, `dev`, `dashboard`) are docker-compose era. **`make check` does
  not exist yet** (Phase 4.3). Do not cite it, do not run `make run`.
- Most of `scripts/` is legacy (TPO, MiroFish, orchestrate, refresh_*). The trusted set is listed
  above; anything else has no consumer or no test.
- `strategy_db/`, `agents/`, `engine/`, `shared_config/`, `ui/` are pre-remediation components kept
  only because a consumer has not been formally archived. They are not on the measurement path.
- Docs describing the retired system were moved to `attic/docs-history/` on 2026-11-19. If you find
  a root-level doc that is not one of the five listed above, it is a leftover — report it, do not
  follow it.

## When in doubt

Stop and ask. The failure mode this repo exists to prevent is an agent producing a confident number
that cannot be reproduced. A missing result is cheaper than a fabricated one.
