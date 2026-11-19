# Phase 2.2 — walk-forward validation

## FAIL

### WALKFORWARD FAIL: no OOS edge at 10bps

Failing strategies: AroonMomentumEngine_Hybrid, AroonMomentumEngine_V2, BollingerMeanReversion, DmiAdxStrategy, EmaTrendFollowing, EnsembleStrategy, MacdRsiStrategy, SupertrendEmaStrategy

Gate rule: PASS iff bootstrap 95% CI lower bound of the aggregate out-of-sample expectancy per trade is > 0 AND n_trades >= 30 AND n_windows_with_trades >= 2

## Reproducibility header

| Field | Value |
|---|---|
| git SHA | `ee24d04f3da193f2732da8a066d11cd0e9137e82` |
| generated (UTC) | 2026-11-19T13:13:33Z |
| freqtrade | freqtrade 2026.5-dev-ee24d04f3 |
| config | `user_data/config_backtest.json` |
| config sha256 | `sha256:26e14c8c2f8c419eca3266f0fefd3be92a3c2f77b8599fa6fde8c5dc9a532b2a` |
| **fee_model** | **10bps all-in (fee + slippage proxy)** |
| timeframe | 1h |
| run mode | per-strategy (one freqtrade process per strategy+window) |
| manifest hash | `sha256:d8e181a1b6a98a42440ad18f801fd8d7058fd9a335df5ebd4abbd7f24a21b2b2` |
| strategies | 8 — `AroonMomentumEngine_Hybrid`, `AroonMomentumEngine_V2`, `BollingerMeanReversion`, `DmiAdxStrategy`, `EmaTrendFollowing`, `EnsembleStrategy`, `MacdRsiStrategy`, `SupertrendEmaStrategy` |
| universe | 20 pairs |
| bootstrap | 10000 resamples, seed 42, unit=trade |

## Windows

- span (tests): `20240101` → `20261119` (`--end` mode: explicit)
- train 6 month(s) rolling immediately before each test window
- test 1 month(s); END exclusive in freqtrade timeranges
- windows run: **35**; insufficient-data windows: **0**
- partial (clipped at run date): 2026-11

## Aggregate out-of-sample results

| Strategy | Trades | Windows | Exp/trade % | CI low % | CI high % | Positive win % | Mean window profit % | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| AroonMomentumEngine_Hybrid | 0 | 35 | — | — | — | 0.0 | 0.000 | FAIL |
| AroonMomentumEngine_V2 | 14332 | 35 | -0.9255 | -0.9986 | -0.8530 | 2.9 | -53.095 | FAIL |
| BollingerMeanReversion | 730 | 35 | -1.0177 | -1.3647 | -0.6668 | 20.0 | -5.048 | FAIL |
| DmiAdxStrategy | 1 | 35 | -5.5799 | -5.5799 | -5.5799 | 0.0 | -0.039 | FAIL |
| EmaTrendFollowing | 4454 | 35 | -1.0032 | -1.1868 | -0.8191 | 5.7 | -26.236 | FAIL |
| EnsembleStrategy | 0 | 0 | — | — | — | — | — | FAIL |
| MacdRsiStrategy | 4 | 35 | -1.2669 | -5.6054 | 7.3835 | 2.9 | -0.035 | FAIL |
| SupertrendEmaStrategy | 0 | 0 | — | — | — | — | — | FAIL |

`Exp/trade %` is the mean per-trade return (leverage-adjusted, net of the 10 bps all-in fee) over every concatenated test-window trade; `CI low/high` is the percentile bootstrap of that mean.

## Per-window detail

| Window | Test timerange | Pairs | AroonMomentumEngine_Hybrid | AroonMomentumEngine_V2 | BollingerMeanReversion | DmiAdxStrategy | EmaTrendFollowing | EnsembleStrategy | MacdRsiStrategy | SupertrendEmaStrategy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-01 | `20240101-20240201` | 20 | 0 | -80.37 (507) | -13.28 (24) | -1.38 (1) | -51.43 (180) | — | 0 | — |
| 2024-02 | `20240201-20240301` | 20 | 0 | -41.94 (381) | 5.15 (23) | 0 | -15.40 (242) | — | 0 | — |
| 2024-03 | `20240301-20240401` | 20 | 0 | -92.88 (741) | -16.36 (45) | 0 | -67.33 (292) | — | 0 | — |
| 2024-04 | `20240401-20240501` | 20 | 0 | -86.18 (521) | -7.05 (7) | 0 | -29.71 (74) | — | 0 | — |
| 2024-05 | `20240501-20240601` | 20 | 0 | -59.87 (412) | -6.04 (25) | 0 | -20.67 (144) | — | 0 | — |
| 2024-06 | `20240601-20240701` | 20 | 0 | -61.53 (316) | -0.53 (2) | 0 | -4.23 (34) | — | 0 | — |
| 2024-07 | `20240701-20240801` | 20 | 0 | -41.02 (394) | 0.41 (21) | 0 | -30.75 (146) | — | 0 | — |
| 2024-08 | `20240801-20240901` | 20 | 0 | -80.88 (521) | -12.66 (25) | 0 | -31.69 (124) | — | 0 | — |
| 2024-09 | `20240901-20241001` | 20 | 0 | -23.56 (298) | 0.87 (25) | 0 | -11.12 (153) | — | 2.90 (1) | — |
| 2024-10 | `20241001-20241101` | 20 | 0 | -35.97 (291) | -9.83 (20) | 0 | -45.38 (145) | — | 0 | — |
| 2024-11 | `20241101-20241201` | 20 | 0 | -78.53 (808) | -23.51 (85) | 0 | -70.96 (466) | — | 0 | — |
| 2024-12 | `20241201-20250101` | 20 | 0 | -95.20 (709) | -8.71 (28) | 0 | -28.22 (111) | — | 0 | — |
| 2025-01 | `20250101-20250201` | 20 | 0 | -77.51 (500) | -20.80 (30) | 0 | -11.50 (149) | — | 0 | — |
| 2025-02 | `20250201-20250301` | 20 | 0 | -83.01 (549) | -1.28 (4) | 0 | -32.42 (51) | — | 0 | — |
| 2025-03 | `20250301-20250401` | 20 | 0 | -25.34 (509) | -0.81 (19) | 0 | -23.01 (83) | — | 0 | — |
| 2025-04 | `20250401-20250501` | 20 | 0 | -38.04 (410) | -2.21 (31) | 0 | -18.54 (135) | — | 0 | — |
| 2025-05 | `20250501-20250601` | 20 | 0 | -58.67 (406) | -1.61 (41) | 0 | -45.48 (178) | — | 0 | — |
| 2025-06 | `20250601-20250701` | 20 | 0 | -48.62 (308) | -5.45 (13) | 0 | -18.94 (83) | — | 0 | — |
| 2025-07 | `20250701-20250801` | 20 | 0 | -46.92 (405) | 1.44 (47) | 0 | -38.13 (231) | — | -1.38 (1) | — |
| 2025-08 | `20250801-20250901` | 20 | 0 | -55.94 (335) | -10.32 (25) | 0 | -33.62 (87) | — | 0 | — |
| 2025-09 | `20250901-20251001` | 20 | 0 | -34.61 (239) | -2.29 (11) | 0 | -26.88 (114) | — | 0 | — |
| 2025-10 | `20251001-20251101` | 20 | 0 | -75.35 (446) | -4.06 (13) | 0 | -14.84 (99) | — | 0 | — |
| 2025-11 | `20251101-20251201` | 20 | 0 | -81.41 (457) | 0 | 0 | -10.13 (21) | — | 0 | — |
| 2025-12 | `20251201-20260101` | 20 | 0 | -46.59 (354) | -1.34 (7) | 0 | -50.75 (75) | — | 0 | — |
| 2026-01 | `20260101-20260201` | 20 | 0 | -49.95 (291) | 8.09 (18) | 0 | -4.58 (104) | — | -2.75 (2) | — |
| 2026-02 | `20260201-20260301` | 20 | 0 | -80.83 (462) | -0.46 (6) | 0 | -21.48 (24) | — | 0 | — |
| 2026-03 | `20260301-20260401` | 20 | 0 | -30.70 (352) | -6.63 (12) | 0 | -30.35 (106) | — | 0 | — |
| 2026-04 | `20260401-20260501` | 20 | 0 | -5.06 (255) | -15.92 (22) | 0 | -45.91 (154) | — | 0 | — |
| 2026-05 | `20260501-20260601` | 20 | 0 | -25.80 (275) | -1.66 (9) | 0 | 4.57 (111) | — | 0 | — |
| 2026-06 | `20260601-20260701` | 20 | 0 | -77.53 (394) | 0.08 (5) | 0 | -10.67 (30) | — | 0 | — |
| 2026-07 | `20260701-20260801` | 20 | 0 | 4.51 (258) | 1.26 (14) | 0 | -33.57 (106) | — | 0 | — |
| 2026-08 | `20260801-20260901` | 20 | 0 | -15.27 (346) | -8.23 (24) | 0 | 14.98 (133) | — | 0 | — |
| 2026-09 | `20260901-20261001` | 20 | 0 | -9.39 (377) | -11.55 (48) | 0 | -23.32 (213) | — | 0 | — |
| 2026-10 | `20261001-20261101` | 20 | 0 | -69.27 (308) | -1.37 (1) | 0 | -29.16 (49) | — | 0 | — |
| 2026-11 | `20261101-20261120` | 20 | 0 | -49.11 (197) | 0 | 0 | -7.65 (7) | — | 0 | — |

Cells are `profit % (trades)` for the test month. `0` = backtest ran, no trades. `—` = no result (process failure). Full metrics per window: `windows.json`; per-trade records: `trades/<strategy>.csv`.

## Data sufficiency

- windows skipped for insufficient data: **0**
- pair-window skips: 0

## Known limits

- The trade-level bootstrap assumes trades are independent. They are not: trades inside one month share a regime. `window_bootstrap` in `walkforward.json` resamples windows instead and is the pessimistic companion number.
- Each window starts from a fresh 10,000 USDT wallet with `max_open_trades: 4`, so per-window profit % is not a compounded portfolio return; the gate is on expectancy per trade, which is the scale-free quantity.
- The train window is only reported, never fitted: these strategies have no hyperopt step, so 'train' here means 'the history that preceded the test month', and it is useful mainly to see whether the pair list was tradable at the time.
- Backtests fill at candle prices with a 10 bps all-in proxy; slippage is not modelled beyond that proxy, and no funding cost beyond freqtrade's funding_fees column is charged in this run.
- Each strategy runs in its own process. freqtrade's `--strategy-list` shares startup candles across strategies and changes results (measured: 13 vs 15 trades, expectancy sign flip, same window), so `--batch` numbers are only comparable against the same batch.

## Reproduce

```
python research/walkforward.py --strategy AroonMomentumEngine_Hybrid --start 20240101 --end 20261119 --train-months 6 --test-months 1
python research/walkforward.py --verify <dirA> <dirB>   # 4 dp + manifest hash
```
