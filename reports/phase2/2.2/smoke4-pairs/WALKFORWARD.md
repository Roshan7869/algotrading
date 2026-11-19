# Phase 2.2 — walk-forward validation

## FAIL

### WALKFORWARD FAIL: no OOS edge at 10bps

Failing strategies: EmaTrendFollowing

Gate rule: PASS iff bootstrap 95% CI lower bound of the aggregate out-of-sample expectancy per trade is > 0 AND n_trades >= 30 AND n_windows_with_trades >= 2

## Reproducibility header

| Field | Value |
|---|---|
| git SHA | `9fd8eca2b2793bd7d79452ab92c8376671673746` |
| generated (UTC) | 2026-11-19T13:09:06Z |
| freqtrade | freqtrade 2026.5-dev-9fd8eca2b |
| config | `user_data/config_backtest.json` |
| config sha256 | `sha256:26e14c8c2f8c419eca3266f0fefd3be92a3c2f77b8599fa6fde8c5dc9a532b2a` |
| **fee_model** | **10bps all-in (fee + slippage proxy)** |
| timeframe | 1h |
| run mode | per-strategy (one freqtrade process per strategy+window) |
| manifest hash | `sha256:a96e5b21771878997a0bcbf9482d6fa5c5f58bb5bcd3c18135584be654e9c9de` |
| strategies | 1 — `EmaTrendFollowing` |
| universe | 2 pairs |
| bootstrap | 10000 resamples, seed 42, unit=trade |

## Windows

- span (tests): `20240101` → `20240131` (`--end` mode: explicit)
- train 6 month(s) rolling immediately before each test window
- test 1 month(s); END exclusive in freqtrade timeranges
- windows run: **1**; insufficient-data windows: **0**

## Aggregate out-of-sample results

| Strategy | Trades | Windows | Exp/trade % | CI low % | CI high % | Positive win % | Mean window profit % | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| EmaTrendFollowing | 15 | 1 | -2.4260 | -4.9316 | 0.6201 | 0.0 | -8.744 | FAIL |

`Exp/trade %` is the mean per-trade return (leverage-adjusted, net of the 10 bps all-in fee) over every concatenated test-window trade; `CI low/high` is the percentile bootstrap of that mean.

## Per-window detail

| Window | Test timerange | Pairs | EmaTrendFollowing |
|---|---|---:|---:|
| 2024-01 | `20240101-20240201` | 1 | -8.74 (15) |

Cells are `profit % (trades)` for the test month. `0` = backtest ran, no trades. `—` = no result (process failure). Full metrics per window: `windows.json`; per-trade records: `trades/<strategy>.csv`.

## Data sufficiency

- windows skipped for insufficient data: **0**
- pair-window skips (listed late / no candles in window): **1** across 1 windows — the window still ran with the remaining pairs.
  - 2024-01: HYPE

## Known limits

- The trade-level bootstrap assumes trades are independent. They are not: trades inside one month share a regime. `window_bootstrap` in `walkforward.json` resamples windows instead and is the pessimistic companion number.
- Each window starts from a fresh 10,000 USDT wallet with `max_open_trades: 4`, so per-window profit % is not a compounded portfolio return; the gate is on expectancy per trade, which is the scale-free quantity.
- The train window is only reported, never fitted: these strategies have no hyperopt step, so 'train' here means 'the history that preceded the test month', and it is useful mainly to see whether the pair list was tradable at the time.
- Backtests fill at candle prices with a 10 bps all-in proxy; slippage is not modelled beyond that proxy, and no funding cost beyond freqtrade's funding_fees column is charged in this run.
- Each strategy runs in its own process. freqtrade's `--strategy-list` shares startup candles across strategies and changes results (measured: 13 vs 15 trades, expectancy sign flip, same window), so `--batch` numbers are only comparable against the same batch.

## Reproduce

```
python research/walkforward.py --strategy EmaTrendFollowing --start 20240101 --end 20240131 --train-months 6 --test-months 1
python research/walkforward.py --verify <dirA> <dirB>   # 4 dp + manifest hash
```
