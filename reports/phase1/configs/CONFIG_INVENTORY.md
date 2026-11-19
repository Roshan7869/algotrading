# CONFIG INVENTORY — Phase 1.2

**Measured:** `git rev-parse HEAD` = `7977650755f7178924b4fbcd18dee2b8e75ea426`, working tree on
2026-11-19. **Method:** every JSON/py/sh/yml file outside `.venv`, `attic`, `TradingAgents`,
`.git`, `strategy_db`, `backtest_results` was scanned for each config basename; `.md` references
were recorded separately and never counted as consumers.

**Counting unit.** "Tracked configs" = `git ls-files 'user_data/config*.json'` → **112 before**,
**3 after** (working tree; the git *index* still lists 112 because this lane may not run `git rm` —
cached removal is the orchestrator's step per `EXECUTION_PLAN.md` principle 6).

## A. Families (the whole config landscape)

| Family | Files | Referenced by (code) | Canonical replacement | Action |
|---|---|---|---|---|
| `user_data/config_backtest.json` | 1 | `research/harness.py`, `ui/pages/8_backtest.py` | **itself (canonical)** | keep + edited |
| `user_data/config_spot.json` | 1 | `batch_runner_8y_spot.py`, `batch_runner_generated.py`, `research/harness.py`, `run_all_backtest_8yr.py`, `run_kronos_batch.py` | **itself (canonical)** | keep + edited |
| `user_data/config_dryrun.json` | 1 | `run_eden_hedge_backtest.py`, `run_eden_leverage.py` | **itself (canonical)** | keep + edited |
| `user_data/config_backtest_*.json` (per-experiment leverage/pair variants) | 31 | `scripts/disable_telegram_in_backtests.py`, `queue_backtest.py`, `test_single_backtest.py`, `scripts/backtesting/Run-*` | `config_backtest.json` | **moved** |
| `user_data/config_godmode_*.json` | 3 | `batch_runner_generated.py`, `godmode_batch_30d.py`, `godmode_batch_300d.py` | `config_backtest.json` | **moved**; consumers are dead batch runners |
| `user_data/config_live_*.json`, `config_live_real.json.DISABLED/.DANGEROUS` | 5 | `run_wsl.sh`, `start_trading.sh`, `scripts/trading_orchestrator.py`, `scripts/config_loader.py`, `scripts/live_trading/*`, `scripts/validation/test_configs.py`, `scripts/test_fault_tolerance.py`, `send_*.py` | `config_dryrun.json` | **moved**; entrypoints rewired, live-family helpers left fail-fast |
| `user_data/config_aroon*.json`, `config_ivb_orb_v4_extended.json` | 5 | `scripts/backtesting/Run-7Day-*.ps1`, `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | **moved** |
| `user_data/config_{base,runtime,api,market_ready,unified}.json` | 5 | `scripts/Run-Trading.ps1`, `scripts/analytics/walk_forward.py`, `scripts/regime/regime_router.py`, `scripts/circuit_breaker.py`, `docker-compose*.yml`, `scripts/agents/agent_runner.py`, `scripts/validation/validate_backtest_ready.py` | `config_dryrun.json` | **moved**; refs rewired |
| `user_data/config_{all_40,coindcx,solana,multi_backtest_365d,vector_backtest,backtest_2021,backtest_30d}.json` | 7 | `scripts/auto_optimize.py`, `user_data/scripts/cvd_download_batch.py` (comment) | `config_backtest.json` / `config_spot.json` | **moved** |
| `user_data/config.json` + `temp_backtest_config.json` | 2 | `config/paths.py`, `scripts/circuit_breaker.py`, `scripts/ws_client.py` (all rewired); `freqtrade/constants.py` `DEFAULT_CONFIG` (generic name, not this file) | `config_dryrun.json` | **moved** |
| `user_data/config_archive/` | 60 | `scripts/disable_telegram_in_backtests.py`, `run_wsl.sh`, `scripts/auto_optimize.py`, `scripts/Run-Trading.ps1`, `docker-compose.unified.yml` | per-name canonical | **moved whole dir** |
| `config_examples/` (upstream freqtrade examples) | 4 | `tests/test_configuration.py`, `tests/freqai/conftest.py`, `freqtrade/templates/FreqaiExampleHybridStrategy.py` (docstring) | — | **moved whole dir**; 2 test modules now need the fixtures back (risk R1) |
| `user_data/strategies/leverage_config.py` | 1 | none — `get_leverage()` has **0 call sites**; mentioned only in prose strings (`AroonMomentumEngine_Hybrid.py:78`, two `.ps1` banners) | — | **keep** (Python module, not a config; dead code, documented) |
| `shared_config/leverage_signal.json` | 1 | `AroonMomentumEngine_Hybrid.py`, `AroonMomentumEngine_V2.py`, `miroshark/brain.py`, `scripts/dynamic_leverage.py`, `scripts/health_monitor_v2.py` | — | **keep** (runtime signal; inert without `SHARED_CONFIG_DIR`) |
| `shared_config/*.json` (17 others) | 17 | engine/agents/scripts (signal bus, regime, health) | — | **keep** (runtime state, not bot config) |
| `HEdge/configs/*.json` | 17 | `HEdge/scripts/run_all_backtests.sh` | — | **untouched** (separate experiment tree) |
| `strat_optimisation/configs/**` | 9 | `strat_optimisation/scripts/run_all_backtests.sh`, 3 archived strategy files | — | **untouched** (separate experiment tree) |
| `tests/**/*config*.json` | 9 | freqtrade upstream tests, CI | — | **untouched** (fixtures) |
| `scripts/regime/regime_config.json` | 1 | `scripts/regime/regime_router.py` | — | **untouched** (router config, not a bot config) |

Totals: **116 files moved** (60 archive + 4 examples + 52 in `user_data/` root: 49 tracked
`config*.json`, 2 untracked `config_live_real.json.DISABLED/.DANGEROUS`, and the tracked generated
`temp_backtest_config.json`).

## B. Every moved `user_data/` + `config_examples/` file, and who referenced it

`refs rewired` = every code reference now points at a canonical config (verified by
`scripts/validate_configs.py` + `py_compile`/`bash -n`/`yaml.safe_load`).
`refs left (legacy consumer)` = the referencing file is a legacy research runner that is itself
superseded (Phase 1.4 scoreboard replaces it); it now fails fast with "config not found" instead of
silently running a stale leverage variant.

| file | referenced by (code) | canonical replacement | action |
|---|---|---|---|
| `config_examples/config_binance.example.json` | — | `— (upstream example)` | moved; test fixture refs left (see risks) |
| `config_examples/config_freqai.example.json` | `freqtrade/templates/FreqaiExampleHybridStrategy.py`, `tests/freqai/conftest.py` | `— (upstream example)` | moved; test fixture refs left (see risks) |
| `config_examples/config_full.example.json` | `tests/test_configuration.py` | `— (upstream example)` | moved; test fixture refs left (see risks) |
| `config_examples/config_kraken.example.json` | — | `— (upstream example)` | moved; test fixture refs left (see risks) |
| `user_data/config.json` | `.github/workflows/ci.yml`, `.github/workflows/docker-build.yml`, `config/paths.py` (+42) | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_all_40.json` | `user_data/scripts/cvd_download_batch.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_api.json` | `scripts/circuit_breaker.py` | `config_dryrun.json` | moved; refs rewired |
| `user_data/config_archive/config_api.json` | `scripts/circuit_breaker.py` | `config_dryrun.json` | moved; refs rewired |
| `user_data/config_archive/config_aroon_300day_backtest.json` | `scripts/backtesting/Run-7Day-Backtest-18x.ps1`, `scripts/backtesting/Run-7Day-Backtest-6x.ps1`, `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_aroon_300day_backtest_9x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_aroon_momentum_engine.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_aroonmacd_optimized.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_2021.json` | — | `config_spot.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_20tokens_shorts.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_300d_12x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_300d_6x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_300d_9x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_30d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_6x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_9x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_9x_top_tokens.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_backtest_godmode_p1.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p2.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p2_reval.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3_p3a_rsi_divergence_exit.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3_p3b_tighter_trail.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3_p3c_wider_trail.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3_p3d_kill_zone_filter.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3_p3e_key_level_boost.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3d_forced.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3e_hyperopt.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3e_p2pairs.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_godmode_p3f.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_p3e_hyperopt_10d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_backtest_xrp_sol_300d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_bos_topgainer_ATOM_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_bos_topgainer_NEAR_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_bos_topgainer_STORJ_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_bos_topgainer_XRP_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_bos_topgainer_ZEC_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_coindcx.json` | — | `config_spot.json` | moved; no code ref |
| `user_data/config_archive/config_cvd_7.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_cvd_all.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_dryrun_wsl_10x.json` | `run_wsl.sh`, `scripts/disable_telegram_in_backtests.py` | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_eden_7d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_godmode_17p_fixed50.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_godmode_30p.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_ivb_orb_crypto.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_ivb_orb_v2.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_ivb_orb_v3.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_ivb_orb_v4_extended.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_multi_30d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_multi_7d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_multi_backtest_365d.json` | `scripts/auto_optimize.py` | `config_backtest.json` | moved; refs rewired |
| `user_data/config_archive/config_p3e_topgainer_ATOM_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_p3e_topgainer_NEAR_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_p3e_topgainer_STORJ_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_p3e_topgainer_XRP_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_p3e_topgainer_ZEC_USDT_USDT.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_pairs_eth_sol.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_pairs_op_arb.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_pairs_sui_ton.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_runtime.json` | `scripts/Run-Trading.ps1` | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_archive/config_sep2021.json` | — | `config_spot.json` | moved; no code ref |
| `user_data/config_archive/config_solana.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_archive/config_unified.json` | `docker-compose.unified.yml` | `config_dryrun.json` | moved; refs rewired |
| `user_data/config_archive/config_vector_backtest.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_aroon_300day_backtest.json` | `scripts/backtesting/Run-7Day-Backtest-18x.ps1`, `scripts/backtesting/Run-7Day-Backtest-6x.ps1`, `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_aroon_300day_backtest_9x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_aroon_momentum_engine.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_aroonmacd_optimized.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_100.json` | `scripts/disable_telegram_in_backtests.py`, `test_single_backtest.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_2021.json` | — | `config_spot.json` | moved; no code ref |
| `user_data/config_backtest_20tokens_shorts.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_300d_10x.json` | `run_wsl.sh`, `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_300d_12x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_300d_6x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_300d_9x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_300day_STANDARD.json` | `queue_backtest.py`, `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_30d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_6x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_9x.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_9x_top_tokens.json` | `scripts/disable_telegram_in_backtests.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_backtest_godmode_p1.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p2.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p2_reval.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3_p3a_rsi_divergence_exit.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3_p3b_tighter_trail.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3_p3c_wider_trail.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3_p3d_kill_zone_filter.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3_p3e_key_level_boost.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3d_forced.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3e_hyperopt.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3e_p2pairs.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_godmode_p3f.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_p3e_hyperopt_10d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_backtest_xrp_sol_300d.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_base.json` | `scripts/Run-Trading.ps1`, `scripts/analytics/walk_forward.py`, `scripts/regime/regime_router.py` | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_coindcx.json` | — | `config_spot.json` | moved; no code ref |
| `user_data/config_dryrun_wsl_10x.json` | `run_wsl.sh`, `scripts/disable_telegram_in_backtests.py` | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_godmode_17p.json` | `batch_runner_generated.py`, `godmode_batch_300d.py`, `godmode_batch_30d.py` | `config_backtest.json` | moved; refs left (legacy consumer) |
| `user_data/config_godmode_17p_fixed50.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_godmode_30p.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_ivb_orb_v4_extended.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_live_analysis.json` | `queue_backtest.py`, `scripts/disable_telegram_in_backtests.py`, `scripts/orchestrate.py` | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_live_trading_10x.json` | `run_wsl.sh`, `scripts/backtesting/Run-24h-Backtest.ps1`, `scripts/backtesting/Run-48h-Backtest.ps1` (+6) | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_live_trading_6x.json` | `scripts/disable_telegram_in_backtests.py`, `scripts/test_fault_tolerance.py`, `scripts/trading_orchestrator.py` (+2) | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_market_ready.json` | `docker-compose.yml`, `scripts/agents/agent_runner.py`, `scripts/validation/validate_backtest_ready.py` | `config_dryrun.json` | moved; refs rewired |
| `user_data/config_multi_backtest_365d.json` | `scripts/auto_optimize.py` | `config_backtest.json` | moved; refs rewired |
| `user_data/config_runtime.json` | `scripts/Run-Trading.ps1` | `config_dryrun.json` | moved; refs left (legacy consumer) |
| `user_data/config_solana.json` | — | `config_backtest.json` | moved; no code ref |
| `user_data/config_unified.json` | `docker-compose.unified.yml` | `config_dryrun.json` | moved; refs rewired |
| `user_data/config_vector_backtest.json` | — | `config_backtest.json` | moved; no code ref |

## B2. Untracked configs also moved (not in the table above because they are not tracked)

| file | reason | canonical replacement |
|---|---|---|
| `user_data/config_live_real.json.DISABLED` | live-family config, disabled by filename; `dry_run: true`, no keys, 0 literal 64-hex strings (measured) | `config_dryrun.json` |
| `user_data/config_live_real.json.DANGEROUS` | same, second copy; `dry_run: true`, no keys, 0 literal 64-hex strings | `config_dryrun.json` |

Moved to `attic/configs/user_data/` unchanged. Neither is tracked, so they do not affect the tracked
count; both are recorded in `attic/configs/MOVED.md`.

## C. References deliberately left in place (and why)

| Referencing file | Points at | Why left |
|---|---|---|
| `scripts/disable_telegram_in_backtests.py` | 16 legacy config paths | The script's only job is patching throwaway configs; it is itself a candidate for the attic. It warns and skips missing files (`[WARN] Config not found`), so it cannot corrupt anything. |
| `scripts/backtesting/Run-7Day-Backtest-{6,18}x.ps1`, `Run-{24,48}h-Backtest.ps1` | `config_aroon_300day_backtest.json`, `config_live_trading_10x.json` | Historical one-off runners pinned to specific leverage/date experiments; their numbers are not reproducible artifacts. |
| `scripts/Run-Trading.ps1` | `config_base.json`, `config_runtime.json` | **Already dead**: it hardcodes `$ProjectRoot = "c:\Users\USER\Desktop\Algotrading"` (wrong machine), so it cannot run before or after the move. |
| `scripts/config_loader.py`, `scripts/live_trading/{preflight_check,live_market_scanner,start_paper_trading}.py`, `scripts/validation/test_configs.py`, `scripts/test_fault_tolerance.py`, `send_backtest_results.py`, `send_telegram_report.py` | `config_live_trading_{10x,6x}.json` | These *are* the live-trading path that the standing rules forbid running. Leaving them fail-fast is safer than repointing a live preflight at a dry-run config (which would make "live" checks pass on paper numbers). |
| `batch_runner_generated.py`, `godmode_batch_{30d,300d}.py`, `run_eden_*.py`, `run_all_backtest_8yr.py`, `run_kronos_batch.py`, `batch_runner_8y_spot.py` | legacy per-sweep configs | Dead research runners superseded by `scripts/scoreboard.py` (Phase 1.4). They point at canonical `config_spot.json`/`config_dryrun.json` where they already did. |
| `user_data/scripts/cvd_download_batch.py` | `config_all_40.json` in a **comment** only | No path is read; the pair list is inline. |
| `.github/workflows/ci.yml` | `cp tests/testdata/config.tests.json user_data/config.json` | Upstream CI *creates* the file at run time; it does not require it to be tracked. |
| `scripts/supervise.py:267` | the string "config.json" in a comment | Comment only. |
| `freqtrade/**` (`DEFAULT_CONFIG = "config.json"`, `deploy_config.py`, `arguments.py`, many tests) | generic default filename | Not a reference to the moved file; `freqtrade trade` without `-c` now has no default config — intentional (every runbook passes `-c`). |
| `tests/test_configuration.py:44`, `tests/freqai/conftest.py` | `config_examples/config_full.example.json`, `config_freqai.example.json` | **Broken by the move** — see risk R1 in the phase report. |

## D. What "referenced by live code path" meant for the decisions

A config was treated as **protected** (not moved without a rewire) only if a file that can execute
today reads its path. Every such config was either (a) canonical already, or (b) moved **with** the
referencing file edited in the same batch. Configs whose only readers are dead runners, upstream
fixtures, or comments were moved without touching the reader, and each such case is listed in
section C.
