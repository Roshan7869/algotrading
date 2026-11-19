# Phase 2.2 — walk-forward validation

## FAIL

### WALKFORWARD FAIL: no OOS edge at 10bps

Failing strategies: BollingerMeanReversion, SupertrendEmaStrategy

Gate rule: PASS iff bootstrap 95% CI lower bound of the aggregate out-of-sample expectancy per trade is > 0 AND n_trades >= 30 AND n_windows_with_trades >= 2

## Reproducibility header

| Field | Value |
|---|---|
| git SHA | `9fd8eca2b2793bd7d79452ab92c8376671673746` |
| generated (UTC) | 2026-11-19T13:01:38Z |
| freqtrade | freqtrade 2026.5-dev-9fd8eca2b |
| config | `user_data/config_backtest.json` |
| config sha256 | `sha256:26e14c8c2f8c419eca3266f0fefd3be92a3c2f77b8599fa6fde8c5dc9a532b2a` |
| **fee_model** | **10bps all-in (fee + slippage proxy)** |
| timeframe | 1h |
| run mode | per-strategy (one freqtrade process per strategy+window) |
| manifest hash | `sha256:557585ccca3a5013c44030bb248c21b071e019d5672d34f4058e8ae502599459` |
| strategies | 2 — `BollingerMeanReversion`, `SupertrendEmaStrategy` |
| universe | 20 pairs |
| bootstrap | 10000 resamples, seed 42, unit=trade |

## Windows

- span (tests): `20250701` → `20251101` (`--end` mode: explicit)
- train 3 month(s) rolling immediately before each test window
- test 1 month(s); END exclusive in freqtrade timeranges
- windows run: **4**; insufficient-data windows: **0**
- dropped tail window(s) (too short to measure): `2025-11` clipped tail window shorter than 7 days

## Aggregate out-of-sample results

| Strategy | Trades | Windows | Exp/trade % | CI low % | CI high % | Positive win % | Mean window profit % | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| BollingerMeanReversion | 96 | 4 | -0.6193 | -1.5531 | 0.3289 | 25.0 | -3.809 | FAIL |
| SupertrendEmaStrategy | 2 | 4 | 0.5093 | -5.5910 | 6.6096 | 25.0 | 0.063 | FAIL |

`Exp/trade %` is the mean per-trade return (leverage-adjusted, net of the 10 bps all-in fee) over every concatenated test-window trade; `CI low/high` is the percentile bootstrap of that mean.

## Per-window detail

| Window | Test timerange | Pairs | BollingerMeanReversion | SupertrendEmaStrategy |
|---|---|---:|---:|---:|
| 2025-07 | `20250701-20250801` | 20 | 1.44 (47) | 1.64 (1) |
| 2025-08 | `20250801-20250901` | 20 | -10.32 (25) | 0 |
| 2025-09 | `20250901-20251001` | 20 | -2.29 (11) | 0 |
| 2025-10 | `20251001-20251101` | 20 | -4.06 (13) | -1.39 (1) |

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
python research/walkforward.py --strategy BollingerMeanReversion --start 20250701 --end 20251101 --train-months 3 --test-months 1
python research/walkforward.py --verify <dirA> <dirB>   # 4 dp + manifest hash
```
