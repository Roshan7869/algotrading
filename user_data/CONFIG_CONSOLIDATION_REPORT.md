# Config Consolidation Report

**Date:** 2026-05-22  
**Project:** /home/roshan/Downloads/Algotrading  
**Task:** Consolidate `user_data/config*.json` files into a manageable hierarchy (< 15 files)

---

## Summary

| Metric | Value |
|--------|-------|
| Configs before (user_data) | 73 |
| New overlays created | 1 (`config_dryrun.json`) |
| Duplicate groups found | 1 |
| Duplicate files | 2 (`config_ivb_orb_v2.json` == `config_ivb_orb_v3.json`) |
| Configs archived | 60 |
| Configs remaining (active) | **14** |
| Target (< 15) | **PASS** |

---

## Active Configs (14)

| File | Purpose | Script References |
|------|---------|-------------------|
| `config_base.json` | Common settings shared by all (DO NOT MODIFY) | `scripts/regime/regime_router.py` |
| `config.json` | Default / primary config | — |
| `config_backtest.json` | Backtest-specific overlay | `ui/pages/8_backtest.py` |
| `config_dryrun.json` | Development/dry-run overlay (dry_run: true, wallet: 1000, leverage: 3) | `run_wsl.sh` |
| `config_live_trading_10x.json` | Live trading / paper trading (primary) | `start_trading.sh`, `run_wsl.sh`, `scripts/live_trading/*.py`, `scripts/trading_orchestrator.py` |
| `config_live_trading_6x.json` | Live trading variant (6x leverage) | `send_backtest_results.py`, `send_telegram_report.py`, `scripts/disable_telegram_in_backtests.py`, `scripts/test_fault_tolerance.py`, `scripts/trading_orchestrator.py` |
| `config_live_analysis.json` | Live analysis / market scanner | `scripts/orchestrate.py` |
| `config_backtest_300d_10x.json` | 300-day backtest (10x leverage) | `run_wsl.sh`, `scripts/disable_telegram_in_backtests.py` |
| `config_backtest_300day_STANDARD.json` | Standard 300-day backtest | `queue_backtest.py` |
| `config_backtest_100.json` | Short 100-day backtest | `test_single_backtest.py` |
| `config_godmode_17p.json` | Godmode batch backtests | `godmode_batch_300d.py`, `godmode_batch_30d.py`, `batch_runner_generated.py` |
| `config_all_40.json` | CVD download batch (40 pairs) | `user_data/scripts/cvd_download_batch.py` |
| `config_market_ready.json` | Market-ready validation | `scripts/validation/validate_backtest_ready.py` |
| `config_spot.json` | Spot trading mode | `run_all_backtest_8yr.py`, `batch_runner_8y_spot.py`, `run_kronos_batch.py`, `batch_runner_generated.py` |

---

## Archived Configs (60)

All archived configs moved to `user_data/config_archive/`:

- `config_api.json`
- `config_aroon_300day_backtest_9x.json`
- `config_aroon_300day_backtest.json`
- `config_aroonmacd_optimized.json`
- `config_aroon_momentum_engine.json`
- `config_backtest_2021.json`
- `config_backtest_20tokens_shorts.json`
- `config_backtest_300d_12x.json`
- `config_backtest_300d_6x.json`
- `config_backtest_300d_9x.json`
- `config_backtest_30d.json`
- `config_backtest_6x.json`
- `config_backtest_9x.json`
- `config_backtest_9x_top_tokens.json`
- `config_backtest_godmode_p1.json`
- `config_backtest_godmode_p2.json`
- `config_backtest_godmode_p2_reval.json`
- `config_backtest_godmode_p3d_forced.json`
- `config_backtest_godmode_p3e_hyperopt.json`
- `config_backtest_godmode_p3e_p2pairs.json`
- `config_backtest_godmode_p3f.json`
- `config_backtest_godmode_p3_p3a_rsi_divergence_exit.json`
- `config_backtest_godmode_p3_p3b_tighter_trail.json`
- `config_backtest_godmode_p3_p3c_wider_trail.json`
- `config_backtest_godmode_p3_p3d_kill_zone_filter.json`
- `config_backtest_godmode_p3_p3e_key_level_boost.json`
- `config_backtest_p3e_hyperopt_10d.json`
- `config_backtest_xrp_sol_300d.json`
- `config_bos_topgainer_ATOM_USDT_USDT.json`
- `config_bos_topgainer_NEAR_USDT_USDT.json`
- `config_bos_topgainer_STORJ_USDT_USDT.json`
- `config_bos_topgainer_XRP_USDT_USDT.json`
- `config_bos_topgainer_ZEC_USDT_USDT.json`
- `config_coindcx.json`
- `config_cvd_7.json`
- `config_cvd_all.json`
- `config_dryrun_wsl_10x.json`
- `config_eden_7d.json`
- `config_godmode_17p_fixed50.json`
- `config_godmode_30p.json`
- `config_ivb_orb_crypto.json`
- `config_ivb_orb_v2.json`
- `config_ivb_orb_v3.json`
- `config_ivb_orb_v4_extended.json`
- `config_multi_30d.json`
- `config_multi_7d.json`
- `config_multi_backtest_365d.json`
- `config_p3e_topgainer_ATOM_USDT_USDT.json`
- `config_p3e_topgainer_NEAR_USDT_USDT.json`
- `config_p3e_topgainer_STORJ_USDT_USDT.json`
- `config_p3e_topgainer_XRP_USDT_USDT.json`
- `config_p3e_topgainer_ZEC_USDT_USDT.json`
- `config_pairs_eth_sol.json`
- `config_pairs_op_arb.json`
- `config_pairs_sui_ton.json`
- `config_runtime.json`
- `config_sep2021.json`
- `config_solana.json`
- `config_unified.json`
- `config_vector_backtest.json`

---

## Strat Optimisation Deduplication

The 5 identical configs in `strat_optimisation/configs/` were deduplicated:

- **Kept:** `config_v5_hyperopt.json`
- **Archived:** `config_v1_short_top9.json`, `config_v2_sl_optimizer.json`, `config_v3_late_trail.json`, `config_v4_4h.json`

References in `strat_optimisation/scripts/run_all_backtests.sh` updated to point to `config_v5_hyperopt.json`.

---

## Script Updates

The following scripts were updated to reference active configs:

| Script | Change |
|--------|--------|
| `run_wsl.sh` | `config_dryrun_wsl_10x.json` → `config_dryrun.json` |
| `scripts/disable_telegram_in_backtests.py` | Removed all archived configs from `CONFIGS_TO_DISABLE`; updated `CONFIGS_TO_KEEP_ENABLED` |
| `scripts/validation/test_configs.py` | Removed `config_live_real.json` references; updated `.gitignore` checks |
| `strat_optimisation/scripts/run_all_backtests.sh` | `config_v1-v4*.json` → `config_v5_hyperopt.json` |
| `user_data/strategies/AroonMomentumEngine_Hybrid.py` | `config_signal_alerts.json` → `config_dryrun.json`; `config_live_real.json` → `config_live_trading_10x.json` |
| `run_eden_hedge_backtest.py` | `config_eden_7d.json` → `config_dryrun.json` |
| `run_eden_leverage.py` | `config_eden_7d.json` → `config_dryrun.json` |
| `scripts/auto_optimize.py` | `config_multi_backtest_365d.json` → `config_backtest.json` |
| `user_data/strategies/bos_v5_hyperopt.py` | `config_bos_hyperopt.json` → `config_v5_hyperopt.json` |
| `user_data/strategies/ssrn-*/bos_v5_hyperopt*.py` (3 files) | `config_bos_hyperopt.json` → `config_v5_hyperopt.json` |
| `strat_optimisation/strategies/bos_v5_hyperopt.py` | `config_bos_hyperopt.json` → `config_v5_hyperopt.json` |

---

## Verification

- [x] All `.py` and `.sh` scripts validated with `python3 -m py_compile` / `bash -n`
- [x] Zero broken references to archived configs across the codebase
- [x] `config_base.json` was **not modified** (preserved as-is)
- [x] All archived configs retained in `user_data/config_archive/` (not permanently deleted)

---

## How to Restore an Archived Config

If you need to restore a config from the archive:

```bash
cd /home/roshan/Downloads/Algotrading
mv user_data/config_archive/<config_name>.json user_data/
```

---

*Report generated automatically by config consolidation script.*
