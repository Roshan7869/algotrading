# attic/configs/MOVED.md — Phase 1.2 config consolidation

Every file below was moved **by filesystem `mv` only** (`git rm --cached` + `.gitignore` is the
orchestrator's step, per `EXECUTION_PLAN.md` principle 6 — this lane runs no git commands).

Canonical set that remains in `user_data/`: `config_backtest.json` (futures backtest),
`config_spot.json` (spot backtest), `config_dryrun.json` (dry-run).

| # | moved file | reason | canonical replacement |
|---|---|---|---|
| 1 | `config_examples/config_binance.example.json` | upstream freqtrade example configs; documentation only, no runtime consumer | `user_data/config_backtest.json` |
| 2 | `config_examples/config_freqai.example.json` | upstream freqtrade example configs; documentation only, no runtime consumer | `user_data/config_backtest.json` |
| 3 | `config_examples/config_full.example.json` | upstream freqtrade example configs; documentation only, no runtime consumer | `user_data/config_backtest.json` |
| 4 | `config_examples/config_kraken.example.json` | upstream freqtrade example configs; documentation only, no runtime consumer | `user_data/config_backtest.json` |
| 5 | `user_data/config.json` | superseded variant; no canonical role | `user_data/config_backtest.json` |
| 6 | `user_data/config_all_40.json` | superseded variant; no canonical role | `user_data/config_backtest.json` |
| 7 | `user_data/config_api.json` | superseded variant; no canonical role | `user_data/config_dryrun.json` |
| 8 | `user_data/config_archive/config_api.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_dryrun.json` |
| 9 | `user_data/config_archive/config_aroon_300day_backtest.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 10 | `user_data/config_archive/config_aroon_300day_backtest_9x.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 11 | `user_data/config_archive/config_aroon_momentum_engine.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 12 | `user_data/config_archive/config_aroonmacd_optimized.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 13 | `user_data/config_archive/config_backtest_2021.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_spot.json` |
| 14 | `user_data/config_archive/config_backtest_20tokens_shorts.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 15 | `user_data/config_archive/config_backtest_300d_12x.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 16 | `user_data/config_archive/config_backtest_300d_6x.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 17 | `user_data/config_archive/config_backtest_300d_9x.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 18 | `user_data/config_archive/config_backtest_30d.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 19 | `user_data/config_archive/config_backtest_6x.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 20 | `user_data/config_archive/config_backtest_9x.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 21 | `user_data/config_archive/config_backtest_9x_top_tokens.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 22 | `user_data/config_archive/config_backtest_godmode_p1.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 23 | `user_data/config_archive/config_backtest_godmode_p2.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 24 | `user_data/config_archive/config_backtest_godmode_p2_reval.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 25 | `user_data/config_archive/config_backtest_godmode_p3_p3a_rsi_divergence_exit.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 26 | `user_data/config_archive/config_backtest_godmode_p3_p3b_tighter_trail.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 27 | `user_data/config_archive/config_backtest_godmode_p3_p3c_wider_trail.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 28 | `user_data/config_archive/config_backtest_godmode_p3_p3d_kill_zone_filter.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 29 | `user_data/config_archive/config_backtest_godmode_p3_p3e_key_level_boost.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 30 | `user_data/config_archive/config_backtest_godmode_p3d_forced.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 31 | `user_data/config_archive/config_backtest_godmode_p3e_hyperopt.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 32 | `user_data/config_archive/config_backtest_godmode_p3e_p2pairs.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 33 | `user_data/config_archive/config_backtest_godmode_p3f.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 34 | `user_data/config_archive/config_backtest_p3e_hyperopt_10d.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 35 | `user_data/config_archive/config_backtest_xrp_sol_300d.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 36 | `user_data/config_archive/config_bos_topgainer_ATOM_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 37 | `user_data/config_archive/config_bos_topgainer_NEAR_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 38 | `user_data/config_archive/config_bos_topgainer_STORJ_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 39 | `user_data/config_archive/config_bos_topgainer_XRP_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 40 | `user_data/config_archive/config_bos_topgainer_ZEC_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 41 | `user_data/config_archive/config_coindcx.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_spot.json` |
| 42 | `user_data/config_archive/config_cvd_7.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 43 | `user_data/config_archive/config_cvd_all.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 44 | `user_data/config_archive/config_dryrun_wsl_10x.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_dryrun.json` |
| 45 | `user_data/config_archive/config_eden_7d.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 46 | `user_data/config_archive/config_godmode_17p_fixed50.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 47 | `user_data/config_archive/config_godmode_30p.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 48 | `user_data/config_archive/config_ivb_orb_crypto.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 49 | `user_data/config_archive/config_ivb_orb_v2.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 50 | `user_data/config_archive/config_ivb_orb_v3.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 51 | `user_data/config_archive/config_ivb_orb_v4_extended.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 52 | `user_data/config_archive/config_multi_30d.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 53 | `user_data/config_archive/config_multi_7d.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 54 | `user_data/config_archive/config_multi_backtest_365d.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 55 | `user_data/config_archive/config_p3e_topgainer_ATOM_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 56 | `user_data/config_archive/config_p3e_topgainer_NEAR_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 57 | `user_data/config_archive/config_p3e_topgainer_STORJ_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 58 | `user_data/config_archive/config_p3e_topgainer_XRP_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 59 | `user_data/config_archive/config_p3e_topgainer_ZEC_USDT_USDT.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 60 | `user_data/config_archive/config_pairs_eth_sol.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 61 | `user_data/config_archive/config_pairs_op_arb.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 62 | `user_data/config_archive/config_pairs_sui_ton.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 63 | `user_data/config_archive/config_runtime.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_dryrun.json` |
| 64 | `user_data/config_archive/config_sep2021.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_spot.json` |
| 65 | `user_data/config_archive/config_solana.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 66 | `user_data/config_archive/config_unified.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_dryrun.json` |
| 67 | `user_data/config_archive/config_vector_backtest.json` | archived experiment config (already self-declared archive); no live consumer | `user_data/config_backtest.json` |
| 68 | `user_data/config_aroon_300day_backtest.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 69 | `user_data/config_aroon_300day_backtest_9x.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 70 | `user_data/config_aroon_momentum_engine.json` | superseded variant; no canonical role | `user_data/config_backtest.json` |
| 71 | `user_data/config_aroonmacd_optimized.json` | superseded variant; no canonical role | `user_data/config_backtest.json` |
| 72 | `user_data/config_backtest_100.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 73 | `user_data/config_backtest_2021.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_spot.json` |
| 74 | `user_data/config_backtest_20tokens_shorts.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 75 | `user_data/config_backtest_300d_10x.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 76 | `user_data/config_backtest_300d_12x.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 77 | `user_data/config_backtest_300d_6x.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 78 | `user_data/config_backtest_300d_9x.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 79 | `user_data/config_backtest_300day_STANDARD.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 80 | `user_data/config_backtest_30d.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 81 | `user_data/config_backtest_6x.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 82 | `user_data/config_backtest_9x.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 83 | `user_data/config_backtest_9x_top_tokens.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 84 | `user_data/config_backtest_godmode_p1.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 85 | `user_data/config_backtest_godmode_p2.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 86 | `user_data/config_backtest_godmode_p2_reval.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 87 | `user_data/config_backtest_godmode_p3_p3a_rsi_divergence_exit.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 88 | `user_data/config_backtest_godmode_p3_p3b_tighter_trail.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 89 | `user_data/config_backtest_godmode_p3_p3c_wider_trail.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 90 | `user_data/config_backtest_godmode_p3_p3d_kill_zone_filter.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 91 | `user_data/config_backtest_godmode_p3_p3e_key_level_boost.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 92 | `user_data/config_backtest_godmode_p3d_forced.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 93 | `user_data/config_backtest_godmode_p3e_hyperopt.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 94 | `user_data/config_backtest_godmode_p3e_p2pairs.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 95 | `user_data/config_backtest_godmode_p3f.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 96 | `user_data/config_backtest_p3e_hyperopt_10d.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 97 | `user_data/config_backtest_xrp_sol_300d.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 98 | `user_data/config_base.json` | generated-runtime / base config for a config factory script (now rewired) | `user_data/config_dryrun.json` |
| 99 | `user_data/config_coindcx.json` | superseded variant; no canonical role | `user_data/config_spot.json` |
| 100 | `user_data/config_dryrun_wsl_10x.json` | leverage-variant config; freqtrade ignores the config leverage key | `user_data/config_dryrun.json` |
| 101 | `user_data/config_godmode_17p.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 102 | `user_data/config_godmode_17p_fixed50.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 103 | `user_data/config_godmode_30p.json` | godmode research sweep config; consumer is a dead batch runner | `user_data/config_backtest.json` |
| 104 | `user_data/config_ivb_orb_v4_extended.json` | quarantined lookahead strategy's config | `user_data/config_backtest.json` |
| 105 | `user_data/config_live_analysis.json` | live-family config (never armed; all dry_run true); superseded by the canonical dry-run config | `user_data/config_dryrun.json` |
| 106 | `user_data/config_live_real.json.DANGEROUS` | live-family config (never armed; all dry_run true); superseded by the canonical dry-run config | `user_data/config_dryrun.json` |
| 107 | `user_data/config_live_real.json.DISABLED` | live-family config (never armed; all dry_run true); superseded by the canonical dry-run config | `user_data/config_dryrun.json` |
| 108 | `user_data/config_live_trading_10x.json` | live-family config (never armed; all dry_run true); superseded by the canonical dry-run config | `user_data/config_dryrun.json` |
| 109 | `user_data/config_live_trading_6x.json` | live-family config (never armed; all dry_run true); superseded by the canonical dry-run config | `user_data/config_dryrun.json` |
| 110 | `user_data/config_market_ready.json` | superseded variant; no canonical role | `user_data/config_dryrun.json` |
| 111 | `user_data/config_multi_backtest_365d.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 112 | `user_data/config_runtime.json` | generated-runtime / base config for a config factory script (now rewired) | `user_data/config_dryrun.json` |
| 113 | `user_data/config_solana.json` | superseded variant; no canonical role | `user_data/config_backtest.json` |
| 114 | `user_data/config_unified.json` | superseded variant; no canonical role | `user_data/config_dryrun.json` |
| 115 | `user_data/config_vector_backtest.json` | per-experiment leverage/pair variant; the variant number lived only in this filename | `user_data/config_backtest.json` |
| 116 | `user_data/temp_backtest_config.json` | tracked leftover of a throwaway generated config (1 pair, `leverage: 9`); regenerated on demand, never a chosen config | `user_data/config_backtest.json` |

**Total moved: 116 files** (`config_archive/`: 60, `config_examples/`: 4, `user_data/` root: 52 —
49 tracked `config*.json` + 2 untracked `config_live_real.json.DISABLED/.DANGEROUS` +
`temp_backtest_config.json`, a tracked generated single-pair artifact with `leverage: 9`).

`temp_backtest_config.json` was created by `queue_backtest.py` / `test_single_backtest.py` as a
throwaway output path (both now write to the canonical configs' inputs and still generate it at run
time); a stale tracked copy was never a config anyone chose.

## Not moved

| file | why it stays |
|---|---|
| `user_data/strategies/leverage_config.py` | Python module, not a config; **zero callers** (`get_leverage()` has no call site). Kept because a strategy docstring string and two `.ps1` banners mention it; archiving it is a cleanup for whoever retires those scripts. |
| `shared_config/leverage_signal.json` | runtime signal written by `signal_bus`, read by the two Aroon strategies' `leverage()`. Not a freqtrade config. |
| `shared_config/*.json` (regime, signals, health) | live runtime state, not bot config. |
| `tests/testdata/*.json`, `tests/config_test_comments.json` | test fixtures. |
| `HEdge/configs/*.json`, `strat_optimisation/configs/*.json` | separate experiment trees with their own `run_all_backtests.sh` consumers — outside `user_data/`, not part of the bot's config set. |

