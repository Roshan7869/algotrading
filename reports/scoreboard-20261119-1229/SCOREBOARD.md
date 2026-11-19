# Phase 1.4 — strategy scoreboard

## Reproducibility header

| Field | Value |
|---|---|
| git SHA | `db692ceaa85275c3d24920e8b8ee8509c1987f40` |
| generated (UTC) | 2026-11-19T12:29:50Z |
| freqtrade | freqtrade 2026.5-dev-db692ceaa |
| config | `user_data/config_backtest.json` |
| config sha256 | `sha256:26e14c8c2f8c419eca3266f0fefd3be92a3c2f77b8599fa6fde8c5dc9a532b2a` |
| **fee_model** | **10bps all-in (fee + slippage proxy)** |
| timeframe | 1h |
| manifest hash | `sha256:41a5cd176213ffae4ca4b58b5b899b8805effbc11de564c914f24b42872a626f` |
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

| Strategy | Trades | Profit % | Profit USDT | Win % | Exp/trade USDT | Exp/trade % | MaxDD % | Sharpe | PF | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| AroonMomentumEngine_Hybrid | 0 | 0.00 | 0.00 | 0.0 | 0.00 | 0.000 | 0.00 | 0.00 | 0.00 | no_trades |
| AroonMomentumEngine_V2 | 3172 | -99.92 | -9,991.55 | 41.1 | -3.15 | -0.869 | 99.93 | -17.63 | 0.61 | ok |
| BollingerMeanReversion | 251 | -7.97 | -797.16 | 54.2 | -3.18 | -0.069 | 20.03 | -0.33 | 0.95 | ok |
| DmiAdxStrategy | 0 | 0.00 | 0.00 | 0.0 | 0.00 | 0.000 | 0.00 | 0.00 | 0.00 | no_trades |
| EmaTrendFollowing | 1290 | -98.09 | -9,808.90 | 36.0 | -7.60 | -1.155 | 98.62 | -6.77 | 0.74 | ok |
| EnsembleStrategy | 0 | — | — | — | — | — | — | — | — | no_result |
| MacdRsiStrategy | 1 | -1.38 | -138.29 | 0.0 | -138.29 | -5.582 | 1.38 | -100.00 | 0.00 | ok |
| SupertrendEmaStrategy | 18 | -6.22 | -621.75 | 38.9 | -34.54 | -1.376 | 12.62 | -0.24 | 0.59 | ok |

Per-pair breakdown: see `results.json` (`per_pair` on each entry).

## validation

| Strategy | Trades | Profit % | Profit USDT | Win % | Exp/trade USDT | Exp/trade % | MaxDD % | Sharpe | PF | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| AroonMomentumEngine_Hybrid | 0 | 0.00 | 0.00 | 0.0 | 0.00 | 0.000 | 0.00 | 0.00 | 0.00 | no_trades |
| AroonMomentumEngine_V2 | 1998 | -99.06 | -9,905.51 | 41.1 | -4.96 | -0.902 | 99.24 | -28.79 | 0.58 | ok |
| BollingerMeanReversion | 72 | -5.66 | -566.24 | 51.4 | -7.86 | -0.271 | 22.64 | -0.48 | 0.87 | ok |
| DmiAdxStrategy | 0 | 0.00 | 0.00 | 0.0 | 0.00 | 0.000 | 0.00 | 0.00 | 0.00 | no_trades |
| EmaTrendFollowing | 522 | -71.70 | -7,170.35 | 39.5 | -13.74 | -0.884 | 79.99 | -7.67 | 0.72 | ok |
| EnsembleStrategy | 0 | — | — | — | — | — | — | — | — | no_result |
| MacdRsiStrategy | 2 | -2.75 | -274.82 | 0.0 | -137.41 | -5.595 | 2.75 | -24.32 | 0.00 | ok |
| SupertrendEmaStrategy | 9 | -1.44 | -144.33 | 55.6 | -16.04 | -0.637 | 2.75 | -0.14 | 0.74 | ok |

Per-pair breakdown: see `results.json` (`per_pair` on each entry).

## holdout — SEALED

Holdout metrics are **not** in this file and not in `results.json`; they live
only in `HOLDOUT_SEALED.json`. Opening requires `--open-holdout` (Phase 2.4).

Sealed file: `HOLDOUT_SEALED.json` — 8 strategy rows, hash of scope `sha256:e9661b72f9090f3536407988e92b604ced4d5b0181dafe21d630ae2c17cd96b8`.

## Notes

- Ranking for Phase 2.1 uses **validation** expectancy only; train is reported for drift.
- A pair whose window has fewer than 100 candles is reported as insufficient.
- Reproduce: `python scripts/scoreboard.py --stage all`; compare with `--verify <dir1> <dir2>` (4 dp).
