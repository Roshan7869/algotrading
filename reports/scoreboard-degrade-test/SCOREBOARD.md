# Phase 1.4 — strategy scoreboard

## Reproducibility header

| Field | Value |
|---|---|
| git SHA | `bc9157a2a39066554bc6fe59395daadd45945c62` |
| generated (UTC) | 2026-11-19T12:21:55Z |
| freqtrade | freqtrade 2026.5-dev-bc9157a2a |
| config | `user_data/config_backtest.json` |
| config sha256 | `sha256:6714efeaa4b23c9162dd463819729816d2feb691916f93469419b9a95fc962cb` |
| **fee_model** | **10bps all-in (fee + slippage proxy)** |
| timeframe | 1h |
| manifest hash | `sha256:cd322e8c78fa3722319c6fa81e30951a1552adcfc71d9914ab8330435807baec` |
| strategies | 1 |
| universe | 1 pairs |

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

`BTC/USDT:USDT`

**Unresolved (no substitute available)**: ETH/USDT:USDT, SOL/USDT:USDT, XRP/USDT:USDT, DOGE/USDT:USDT, BNB/USDT:USDT, ADA/USDT:USDT, AVAX/USDT:USDT, LINK/USDT:USDT, DOT/USDT:USDT, LTC/USDT:USDT, TRX/USDT:USDT, ATOM/USDT:USDT, NEAR/USDT:USDT, APT/USDT:USDT, ARB/USDT:USDT, OP/USDT:USDT, SUI/USDT:USDT, INJ/USDT:USDT, SEI/USDT:USDT

### Data coverage per stage

| Pair | file rows | train | validation | holdout |
|---|---|---|---|---|
| BTC/USDT:USDT | 58591 | 8760 | 3240 | 0 *(insufficient)* |

## train

_not run_

## validation

_not run_

## holdout — SEALED

Holdout metrics are **not** in this file and not in `results.json`; they live
only in `HOLDOUT_SEALED.json`. Opening requires `--open-holdout` (Phase 2.4).

Sealed file: `HOLDOUT_SEALED.json` — 1 strategy rows, hash of scope `sha256:6076762049a299262efda941e5662b10f26364d7b6537571c8ef8db0ebade863`.

## Notes

- Ranking for Phase 2.1 uses **validation** expectancy only; train is reported for drift.
- A pair whose window has fewer than 100 candles is reported as insufficient.
- Reproduce: `python scripts/scoreboard.py --stage all`; compare with `--verify <dir1> <dir2>` (4 dp).
