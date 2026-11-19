# Phase 1.4 — strategy scoreboard

## Reproducibility header

| Field | Value |
|---|---|
| git SHA | `bc9157a2a39066554bc6fe59395daadd45945c62` |
| generated (UTC) | 2026-11-19T12:18:47Z |
| freqtrade | freqtrade 2026.5-dev-bc9157a2a |
| config | `user_data/config_backtest.json` |
| config sha256 | `sha256:6714efeaa4b23c9162dd463819729816d2feb691916f93469419b9a95fc962cb` |
| **fee_model** | **10bps all-in (fee + slippage proxy)** |
| timeframe | 1h |
| manifest hash | `sha256:9200ac0a3b2691dd83133fc92006e682539a56792d9bf3dffa189a9a47bf0f35` |
| strategies | 1 |
| universe | 2 pairs |

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

`BTC/USDT:USDT`, `ETH/USDT:USDT`

### Data coverage per stage

| Pair | file rows | train | validation | holdout |
|---|---|---|---|---|
| BTC/USDT:USDT | 63091 | 8760 | 4344 | 3396 |
| ETH/USDT:USDT | 61181 | 8760 | 4344 | 3396 |

## train

| Strategy | Trades | Profit % | Profit USDT | Win % | Exp/trade USDT | Exp/trade % | MaxDD % | Sharpe | PF | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| EmaTrendFollowing | 20 | 1.32 | 132.05 | 60.0 | 6.60 | 0.305 | 5.32 | 0.39 | 1.11 | ok |

Per-pair breakdown: see `results.json` (`per_pair` on each entry).

## validation

_not run_

## holdout — SEALED

Holdout metrics are **not** in this file and not in `results.json`; they live
only in `HOLDOUT_SEALED.json`. Opening requires `--open-holdout` (Phase 2.4).

## Notes

- Ranking for Phase 2.1 uses **validation** expectancy only; train is reported for drift.
- A pair whose window has fewer than 100 candles is reported as insufficient.
- Reproduce: `python scripts/scoreboard.py --stage all`; compare with `--verify <dir1> <dir2>` (4 dp).
