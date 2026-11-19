# Phase 1.4 — strategy scoreboard

## Reproducibility header

| Field | Value |
|---|---|
| git SHA | `bc9157a2a39066554bc6fe59395daadd45945c62` |
| generated (UTC) | 2026-11-19T12:20:17Z |
| freqtrade | freqtrade 2026.5-dev-bc9157a2a |
| config | `user_data/config_backtest.json` |
| config sha256 | `sha256:6714efeaa4b23c9162dd463819729816d2feb691916f93469419b9a95fc962cb` |
| **fee_model** | **10bps all-in (fee + slippage proxy)** |
| timeframe | 1h |
| manifest hash | `sha256:515bf99d6f6046ad8b635d3d9480094c6cd105441e9881902f1fa1b188063339` |
| strategies | 8 |
| universe | 20 pairs |

Cost model detail: `--fee 0.001` is charged on entry **and** exit, i.e. 10 bps per
side-equivalent covering exchange fee plus a slippage proxy (the backtester has no
native slippage model, so this is the honest proxy).

## Stage boundaries

| Stage | Window (inclusive) | freqtrade timerange | Role |
|---|---|---|---|
| train | 20250101 → 20251231 | `20250101-20260101` | in-sample history |
| validation | 20260101 → 20260630 | `20260101-20260701` | **SELECTION** |
| holdout | 20260701 → run_date | `20260701-RUN_DATE` | SEALED (Phase 2.4) |

## Universe

Canonical 20-pair futures universe; same list drives Phase 2's dry-run config.

`BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT`, `XRP/USDT:USDT`, `DOGE/USDT:USDT`, `BNB/USDT:USDT`, `ADA/USDT:USDT`, `AVAX/USDT:USDT`, `LINK/USDT:USDT`, `DOT/USDT:USDT`, `LTC/USDT:USDT`, `TRX/USDT:USDT`, `ATOM/USDT:USDT`, `NEAR/USDT:USDT`, `APT/USDT:USDT`, `ARB/USDT:USDT`, `OP/USDT:USDT`, `SUI/USDT:USDT`, `INJ/USDT:USDT`, `SEI/USDT:USDT`

### Data coverage per stage

| Pair | file rows | train | validation | holdout |
|---|---|---|---|---|
| BTC/USDT:USDT | 63091 | 8760 | 4344 | 3396 |
| ETH/USDT:USDT | 61181 | 8760 | 4344 | 3396 |
| SOL/USDT:USDT | 54173 | 8760 | 4344 | 3396 |
| XRP/USDT:USDT | 60220 | 8760 | 4344 | 3396 |
| DOGE/USDT:USDT | 55755 | 8760 | 4344 | 3396 |
| BNB/USDT:USDT | 59380 | 8760 | 4344 | 3396 |
| ADA/USDT:USDT | 59620 | 8760 | 4344 | 3396 |
| AVAX/USDT:USDT | 53957 | 8760 | 4344 | 3396 |
| LINK/USDT:USDT | 59956 | 8760 | 4344 | 3396 |
| DOT/USDT:USDT | 54725 | 8760 | 4344 | 3396 |
| LTC/USDT:USDT | 60148 | 8760 | 4344 | 3396 |
| TRX/USDT:USDT | 60004 | 8760 | 4344 | 3396 |
| ATOM/USDT:USDT | 59448 | 8760 | 4344 | 3396 |
| NEAR/USDT:USDT | 53428 | 8760 | 4344 | 3396 |
| APT/USDT:USDT | 35818 | 8760 | 4344 | 3396 |
| ARB/USDT:USDT | 32085 | 8760 | 4344 | 3396 |
| OP/USDT:USDT | 39166 | 8760 | 4344 | 3396 |
| SUI/USDT:USDT | 31100 | 8760 | 4344 | 3396 |
| INJ/USDT:USDT | 37330 | 8760 | 4344 | 3396 |
| SEI/USDT:USDT | 28570 | 8760 | 4344 | 3396 |

## train

_not run_

## validation

| Strategy | Trades | Profit % | Profit USDT | Win % | Exp/trade USDT | Exp/trade % | MaxDD % | Sharpe | PF | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| AroonMomentumEngine_Hybrid | 0 | 0.00 | 0.00 | 0.0 | 0.00 | 0.000 | 0.00 | 0.00 | 0.00 | no_trades |
| AroonMomentumEngine_V2 | 324 | -59.05 | -5,905.49 | 38.0 | -18.23 | -1.115 | 67.59 | -40.42 | 0.62 | ok |
| BollingerMeanReversion | 16 | 9.44 | 943.67 | 81.2 | 58.98 | 2.337 | 2.74 | 5.31 | 3.16 | ok |
| DmiAdxStrategy | 0 | 0.00 | 0.00 | 0.0 | 0.00 | 0.000 | 0.00 | 0.00 | 0.00 | no_trades |
| EmaTrendFollowing | 101 | -1.47 | -147.21 | 49.5 | -1.46 | 0.056 | 29.99 | -0.53 | 0.98 | ok |
| EnsembleStrategy | 0 | — | — | — | — | — | — | — | — | no_result |
| MacdRsiStrategy | 2 | -2.75 | -274.82 | 0.0 | -137.41 | -5.595 | 2.75 | -141.98 | 0.00 | ok |
| SupertrendEmaStrategy | 3 | -2.27 | -226.99 | 33.3 | -75.66 | -3.054 | 2.77 | -1.58 | 0.18 | ok |

Per-pair breakdown: see `results.json` (`per_pair` on each entry).

## holdout — SEALED

Holdout metrics are **not** in this file and not in `results.json`; they live
only in `HOLDOUT_SEALED.json`. Opening requires `--open-holdout` (Phase 2.4).

## Notes

- Ranking for Phase 2.1 uses **validation** expectancy only; train is reported for drift.
- A pair whose window has fewer than 100 candles is reported as insufficient.
- Reproduce: `python scripts/scoreboard.py --stage all`; compare with `--verify <dir1> <dir2>` (4 dp).
