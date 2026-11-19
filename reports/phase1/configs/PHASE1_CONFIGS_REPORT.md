# PHASE 1.2 — config consolidation: report

**Plan item:** `EXECUTION_PLAN.md` §3 Phase 1 → 1.2 (canonical set of 3, explicit db_url/stake/stoploss,
leverage truth table, validator, everything else to the attic).
**Repo / HEAD:** `D:\dev\algotrading` @ `7977650755f7178924b4fbcd18dee2b8e75ea426` (2026-11-19).
**Constraint respected:** no git write commands, no strategy `.py` edits, no `pip`, no live trading.

## Headline numbers

| Result | Value |
|---|---|
| Canonical configs edited | **3** |
| Files moved to `attic/configs/` | **116** (60 `config_archive` + 4 `config_examples` + 52 `user_data/` root) |
| Tracked `user_data/config*.json` | **112 → 3** (working tree; git index untouched by this lane) |
| Referencing files rewired | **16** |
| New files | **7** (`docs/leverage-matrix.md`, `scripts/validate_configs.py`, 4 under `reports/phase1/configs/`, `attic/configs/MOVED.md`) |
| Validator | **PASS** — 43 checks, 0 warn, 0 fail, exit 0 |
| Validator negative test | **FAIL as designed** — 4 planted violations, exit 1 |
| Real freqtrade load of all 3 configs | **OK** (`list-strategies` on each) |
| Real backtest smoke on `config_backtest.json` | **OK** (DmiAdxStrategy, 2026-06-01→06-15, 0 trades, no errors) |
| Leverage values actually operative | **3.0** ×6 strategies, **2.0** ×2 Aroon strategies (5.0 ceiling) |

## 1. What changed in the three canonical configs

Each file now carries a top-level `_comment` with purpose / owner (`Phase 1.2`) / non-live warning, and
explicit `stoploss`, `db_url`, `dry_run: true`.

| File | Added | Changed | Kept intact |
|---|---|---|---|
| `config_backtest.json` | `_comment`, `stoploss: -0.05`, `db_url: sqlite:///tradesv3.backtest.sqlite` | — | `leverage: 6` (advisory), api_server 127.0.0.1 + `${FREQTRADE_*}` |
| `config_spot.json` | `_comment`, `stoploss: -0.05`, `db_url: sqlite:///tradesv3.spot.sqlite` | `leverage: 6 → 1` (spot is forced to 1.0 by freqtrade; the old value was a lie) | `jwt_secret_key` + `jwt_secret` + `password` all `${FREQTRADE_*}` |
| `config_dryrun.json` | `_comment`, `stoploss: -0.05`, `db_url: sqlite:///tradesv3.dryrun.sqlite` | — | `leverage: 3` (advisory), api_server hardening |

**Why `stoploss` is a config value and `leverage` is not.** freqtrade's precedence is
*Configuration > Strategy > default* (`freqtrade/resolvers/strategy_resolver.py:106-114`), so an
explicit config `stoploss` **overrides** each strategy's own attribute. All 8 strategies declare one
(`-0.04` BollingerMeanReversion, `-0.06` AroonMomentumEngine_Hybrid + EmaTrendFollowing, `-0.05` the
other five). `-0.05` was chosen as the modal value: 5/8 strategies are unchanged, Bollinger is
loosened 4%→5%, the two 6% strategies are tightened 6%→5%. This is a **deliberate, documented
ceiling**, not an accident — flagged as risk R2.

`leverage` in a config is **inert**: it is not a `CONF_SCHEMA` property and no freqtrade code path
reads it (details in `docs/leverage-matrix.md`). It is kept only because five repo scripts read it as
an advisory number; removing it would silently flip `config.get("leverage", 1)` to 1.

## 2. Validator

`scripts/validate_configs.py` (stdlib only, no venv deps):

- **(a) canonical, FAIL-level:** parses; `_comment` purpose line; required keys (`dry_run`,
  `stake_amount`, `max_open_trades`, `stoploss`, `exchange` + non-empty `exchange.pair_whitelist`);
  `dry_run is True`; stake is a positive number or `"unlimited"`; `max_open_trades` non-zero int;
  `stoploss < 0`; `api_server.listen_ip_address == 127.0.0.1`; `password`/`jwt_secret`
  (+`jwt_secret_key` when present) match `^\$\{[A-Za-z_][A-Za-z0-9_]*\}$`; no literal 64-hex string
  anywhere; telegram disabled; `config_dryrun.json` must set `db_url`.
- **(b) every other `user_data/config*.json`:** parse check, WARN level.
- **(c)** exit 1 on any (a) failure, exit 2 path for missing/unparseable canonical files.

Output (full log in `reports/phase1/configs/validate_configs.log`):

```
RUN 1 — consolidated tree (3 canonical configs, 0 others)
checks: 43 pass, 0 warn, 0 fail | other user_data configs scanned: 0
RESULT: PASS                                       EXIT_CODE=0

RUN 2 — negative test: dry_run=False, stoploss=+0.05, literal password, 64-hex key
[FAIL] config_dryrun.json: dry_run — dry_run is False — canonical configs must be dry_run: true
[FAIL] config_dryrun.json: stoploss — stoploss must be negative, got 0.05
[FAIL] config_dryrun.json: api_server.password — not a ${ENV_VAR} placeholder (got hunter2liter…)
[FAIL] config_dryrun.json: secrets — 1 literal 64-hex string(s) found (keys/secrets?)
RESULT: FAIL (4 canonical check(s) failed)         EXIT_CODE=1

RUN 3 — after restoring config_dryrun.json
checks: 43 pass, 0 warn, 0 fail | other user_data configs scanned: 0
RESULT: PASS                                       EXIT_CODE=0
```

The negative run matters: a validator that cannot fail is decoration, which is the failure mode this
plan exists to fix.

## 3. Moves

116 files: `user_data/config_archive/` (60), `config_examples/` (4), `user_data/` root (52 —
49 tracked `config*.json` + 2 untracked disabled live configs + `temp_backtest_config.json`).
Per-file table with reason + canonical replacement: `attic/configs/MOVED.md`.
Family-level consumer map: `reports/phase1/configs/CONFIG_INVENTORY.md`.

**Consumer discipline.** A config was only moved without a rewire when its reader is dead, a comment,
or an upstream fixture — each such case is listed in CONFIG_INVENTORY.md §C. The 16 rewired files:

`docker-compose.yml`, `docker-compose.unified.yml`, `docker/docker-compose-freqai.yml`,
`config/paths.py`, `scripts/circuit_breaker.py`, `queue_backtest.py`, `test_single_backtest.py`,
`scripts/auto_optimize.py`, `scripts/analytics/walk_forward.py`, `scripts/regime/regime_router.py`,
`scripts/trading_orchestrator.py`, `start_trading.sh`, `run_wsl.sh`, `scripts/ws_client.py`,
`scripts/agents/agent_runner.py`, `scripts/validation/validate_backtest_ready.py`.

Notably `scripts/circuit_breaker.py` (the Phase 0.3 safety path) had `config_api.json` in its
candidate list — it now lists `config_dryrun.json`, so the breaker can still discover the localhost
REST API and password.

`scripts/Run-Trading.ps1` was **not** rewired: it hardcodes `$ProjectRoot = "c:\Users\USER\Desktop\Algotrading"`,
so it was already unrunnable on this machine.

## 4. Leverage truth (summary — full table in `docs/leverage-matrix.md`)

| Strategy | Returns | Source |
|---|---|---|
| AroonMomentumEngine_Hybrid | `min(signal, 5.0, max_leverage)` → **2.0** on this host | `AroonMomentumEngine_Hybrid.py:179` |
| AroonMomentumEngine_V2 | `min(signal, 5.0, max_leverage)` → **2.0** on this host | `AroonMomentumEngine_V2.py:169` |
| BollingerMeanReversion | `min(3.0, max_leverage)` → **3.0** | `BollingerMeanReversion.py:70` |
| DmiAdxStrategy | `min(3.0, max_leverage)` → **3.0** | `DmiAdxStrategy.py:72` |
| EmaTrendFollowing | `min(3.0, max_leverage)` → **3.0** | `EmaTrendFollowing.py:72` |
| EnsembleStrategy | `min(3.0, max_leverage)` → **3.0** | `ensemble_strategy.py:132` |
| MacdRsiStrategy | `min(3.0, max_leverage)` → **3.0** | `MacdRsiStrategy.py:73` |
| SupertrendEmaStrategy | `min(3.0, max_leverage)` → **3.0** | `SupertrendEmaStrategy.py:68` |

freqtrade reads leverage in exactly two places: `freqtrade/freqtradebot.py:1142-1157` (dry-run/live)
and `freqtrade/optimize/backtesting.py:1021-1036` (backtest), both clamping to
`[1.0, exchange.get_max_leverage(pair, stake)]` (`freqtrade/exchange/exchange.py:3674`). Spot is
forced to 1.0 (`backtesting.py:1032-1033`).

**Non-obvious finding:** the two Aroon strategies resolve `leverage_signal.json` under
`SHARED_CONFIG_DIR` whose default is the Docker path `/freqtrade/shared_config`. That env var is unset
and the path does not exist on this Windows host, so they always take the `2.0` fallback — the `3.0`
in `shared_config/leverage_signal.json` is inert today. Anyone launching the Phase 2.3 dry run must
export `SHARED_CONFIG_DIR=<repo>/shared_config` if they want the signal file honored.

## 5. Residual risks

| # | Risk | Evidence | Owner |
|---|---|---|---|
| R1 | **Two upstream test modules now need `config_examples/`**: `tests/test_configuration.py:44` (`config_full.example.json`) and `tests/freqai/conftest.py` (`config_freqai.example.json`) will fail with file-not-found. | grep of the moved dirs | orchestrator — either restore those 2 fixtures from `attic/configs/config_examples/` or accept upstream-test breakage; the plan (1.1) mandates moving the dir, so this is a plan-level conflict, not an execution error |
| R2 | Config `stoploss: -0.05` **overrides** per-strategy stops (Bollinger 4%→5%, two 6%→5%). Phase 1.4 scoreboard must state that it measures the -5% ceiling, not each strategy's original stop. | `strategy_resolver.py:106-114` | Phase 1.4 |
| R3 | Leverage signal file is unreachable on this host (2.0 fallback). | `Path('/freqtrade/shared_config/...').exists() == False` | Phase 0.3 / 2.3 launcher |
| R4 | `leverage_config.py` is dead code (`get_leverage()` 0 call sites) but still imports cleanly and looks authoritative. | grep | later cleanup |
| R5 | 15+ legacy research runners now fail fast on missing configs (list in CONFIG_INVENTORY.md §C). Intentional — they encoded per-experiment leverage that freqtrade ignored anyway — but they are noisy if someone runs them. | — | Phase 1.4 (scoreboard replaces them) |
| R6 | Git index still lists 112 config paths until the orchestrator commits; a `git checkout` would resurrect them from the index. | `git ls-files` | orchestrator |
| R7 | `docker-compose.yml` overrides the config's `db_url` with `--db-url sqlite:////freqtrade/user_data/tradesv3.sqlite`, so a compose run would write `tradesv3.sqlite` — the exact 0-row-shell filename plan §0.5 bans. Docker is not the supported path (CPU/script-only), so this is a doc note, not a blocker; if compose is ever revived, drop that `--db-url` line. | `docker-compose.yml:34` | later cleanup |

## 6. Verification evidence (all executed, not asserted)

```
.venv/Scripts/freqtrade.exe list-strategies --userdir user_data -c user_data/config_backtest.json   -> OK (8 strategies)
.venv/Scripts/freqtrade.exe list-strategies --userdir user_data -c user_data/config_spot.json       -> OK (8 strategies)
.venv/Scripts/freqtrade.exe list-strategies --userdir user_data -c user_data/config_dryrun.json     -> OK (8 strategies)
.venv/Scripts/freqtrade.exe backtesting --strategy DmiAdxStrategy -c user_data/config_backtest.json \
    --timerange 20260601-20260615 --cache none                                                     -> completed, 0 trades, no config errors
.venv/Scripts/python.exe scripts/validate_configs.py                                               -> PASS, exit 0
.venv/Scripts/python.exe -m py_compile <10 edited .py files>                                       -> OK
bash -n start_trading.sh run_wsl.sh; yaml.safe_load on 3 compose files                             -> OK
```

A 0-trade backtest is a machinery proof, not an edge claim: the window is 2 weeks on a 1h DMI/ADX
strategy, and Phase 1.4 is where metrics are produced.
