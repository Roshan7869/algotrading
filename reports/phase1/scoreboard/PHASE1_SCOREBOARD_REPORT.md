# Phase 1.4 — scoreboard: build + smoke report

Generated 2026-11-19 (UTC). Evidence: `reports/phase1/scoreboard/SMOKE.log`, output dirs
`reports/scoreboard-smoke-A`, `-smoke-B`, `-fullrun`, `-matrix-smoke`, `-degrade-test`.

## 1. What was built

`scripts/scoreboard.py` (new, single file, stdlib + pyarrow/pandas only) — a reproducible
strategy scoreboard over the 8 surviving strategies and the fixed 20-pair futures universe.

| Piece | Implementation |
|---|---|
| CLI | `--stage train\|validation\|holdout\|all`, `--open-holdout`, `--strategies`, `--pairs`, `--limit N`, `--userdir`, plus `--config`, `--data-dir`, `--outdir`, `--timerange` (smoke override), `--no-batch`, `--max-run-seconds`, `--verify DIR1 DIR2` |
| Backtest invocation | `.venv/Scripts/freqtrade.exe backtesting --strategy <Class> -c user_data/config_backtest.json --userdir user_data --timerange <stage> --fee 0.001 --cache none --export trades --backtest-directory <tmp> --timeframe 1h -p <pairs…>` |
| Result parsing | the archive's JSON (`strategy[<name>]`) — scalars plus `results_per_pair` (the `TOTAL` row is dropped) |
| Metrics | trades (long/short), `profit_abs`, `profit_pct`, `winrate_pct`, `expectancy_abs` (USDT/trade), `expectancy_pct`, `max_drawdown_pct`/`_abs`, `sharpe`, `sortino`, `calmar`, `profit_factor`, `cagr_pct`, `pairs_in_report`/`pairs_traded`, `per_pair[]` |
| Outputs | `MANIFEST.json`, `SCOREBOARD.md`, `results.json`, `UNIVERSE.json`, `HOLDOUT_SEALED.json` (only when the holdout stage runs), `logs/<stage>__<strategy>.log`, `raw/<stage>/` |
| Reproducibility | `manifest_hash` = sha256 over a canonical payload that includes the **config content hash** (`config_sha256`, because a path alone cannot prove which config ran); `--verify` compares `manifest_hash` and every scalar in `results.json` at 4 dp and prints PASS/FAIL (exit 0/1) |

`--export-filename` is **deprecated** for backtesting in freqtrade 2026.5-dev; the installed
`backtesting --help` names `--backtest-directory` (alias `--export-directory`) as the supported
flag, and the archive is named after that directory. The script uses the supported flag.

## 2. Three-way split (constants block with rationale)

| Stage | Window (inclusive) | freqtrade timerange | Role |
|---|---|---|---|
| train | 2025-01-01 → 2025-12-31 | `20250101-20260101` | in-sample history, drift reference only |
| validation | 2026-01-01 → 2026-06-30 | `20260101-20260701` | **the only window Phase 2.1 may select on** |
| holdout | 2026-07-01 → run date | `20260701-<run date + 1d>` | sealed; Phase 2.4 opens it once |

freqtrade's `--timerange` END is exclusive, so the exclusive constants are what execute while the
inclusive dates are what the docs say. Selection leakage is prevented structurally: holdout
entries are assembled in a separate block and written only to `HOLDOUT_SEALED.json`;
`results.json`, `SCOREBOARD.md`, `UNIVERSE.json` and `MANIFEST.json` never carry holdout metrics
unless `--open-holdout` is passed. The sealed file also stores `sealed_hash` (sha256 of the
holdout rows), so a later reader can tell whether the numbers changed.

## 3. Cost model

`fee_model: 10bps all-in (fee + slippage proxy)` — emitted verbatim in every output.
`--fee 0.001` is charged by freqtrade on entry **and** exit, i.e. 10 bps per side-equivalent
covering exchange taker fee plus a slippage allowance. freqtrade's backtester has no native
slippage parameter; folding it into the fee is the honest proxy, and it is labelled as a proxy in
every artifact.

## 4. Loading set (verified, not inherited)

`.venv/Scripts/freqtrade.exe list-strategies --userdir user_data` → 8 strategies, all `OK`:

```
AroonMomentumEngine_Hybrid  AroonMomentumEngine_V2  BollingerMeanReversion  DmiAdxStrategy
EmaTrendFollowing           EnsembleStrategy        MacdRsiStrategy         SupertrendEmaStrategy
```

`ensemble_strategy.py` defines class **`EnsembleStrategy`** (filename ≠ class name) — the script's
default list uses the class name, which is what `--strategy` accepts. The 18 lookahead strategies
in `user_data/strategies/_archived/lookahead_20261119/` do not appear (freqtrade does not load
subdirectories).

## 5. Universe

Canonical constant, emitted to `UNIVERSE.json`, reused by Phase 2's dry-run config:

```
BTC ETH SOL XRP DOGE BNB ADA AVAX LINK DOT LTC TRX ATOM NEAR APT ARB OP SUI INJ SEI  (…/USDT:USDT)
```

Resolution is per-run against `user_data/data/binance/futures/*-1h-futures.feather`; missing pairs
are replaced from a **frozen** `SUBSTITUTE_ORDER` pool (not "whatever is on disk") and the
substitution is recorded in `MANIFEST.json`, `SCOREBOARD.md` and `UNIVERSE.json`.

* At 17:18Z three canonical pairs had no usable file: **SEI (absent), BNB and INJ (only from
  2026-05-16)**.
* The parallel data-refresh lane back-filled all three before the runs; at 17:50Z the resolution
  was **20/20 available, 0 substitutions, 0 unresolved** (every pair: 8760 train / 4344 validation
  / 3396 holdout 1h candles, last candle 2026-11-19 09:00Z).
* The substitution path itself is proven in `SMOKE.log` Appendix A (data dir holding only BTC, ETH,
  BCH → SOL substituted by BCH, 17 unresolved, no crash).

Consequence for the earlier premise "data ends 2026-05": the holdout window is **populated** as of
this run. The "insufficient data" path was still exercised explicitly against a fixture truncated
at 2026-05-16 — it reports `status: insufficient_data` and skips the backtest instead of crashing.

## 6. Smoke evidence (exact commands and numbers)

```
$ .venv/Scripts/python.exe scripts/scoreboard.py --stage train --limit 2 \
    --strategies EmaTrendFollowing --timerange 20251001-20251120 --outdir reports/scoreboard-smoke-A
$ .venv/Scripts/python.exe scripts/scoreboard.py --stage train --limit 2 \
    --strategies EmaTrendFollowing --timerange 20251001-20251120 --outdir reports/scoreboard-smoke-B
$ .venv/Scripts/python.exe scripts/scoreboard.py --verify reports/scoreboard-smoke-A reports/scoreboard-smoke-B
```

| Field | Value (both runs identical) |
|---|---|
| timerange | 20251001-20251120 (7 weeks, BTC + ETH, 1 strategy) |
| trades | 20 (20 long / 0 short) |
| profit | +132.053331 USDT = +1.320533 % |
| win rate | 60.0 % |
| expectancy | +6.602667 USDT/trade = +0.305033 %/trade |
| max drawdown | 5.320937 % (569.418576 USDT) |
| Sharpe | 0.394234 |
| profit factor | 1.113753 |
| config_sha256 | `sha256:6714efeaa4b23c9162dd463819729816d2feb691916f93469419b9a95fc962cb` |
| manifest_hash | `sha256:9200ac0a3b2691dd83133fc92006e682539a56792d9bf3dffa189a9a47bf0f35` |
| verify | **PASS** — manifest_hash MATCH, 54 scalar fields MATCH at 4 dp, exit 0 |
| negative control | a copy of run B with `profit_pct` perturbed by +0.0001 → **FAIL**, exit 1 (`SMOKE.log` Appendix B) |
| wall clock | 8 s / 8 s |

Additional runs recorded in the same log:

| Run | Command shape | Result |
|---|---|---|
| Full universe, 1 strategy, 3 stages | `--stage all --strategies EmaTrendFollowing` | 20 pairs × 3 stages, 72 s wall (train 30.8 s / validation 17.7 s / holdout 20.3 s); train **1286 trades, −9 806.58 USDT, −98.07 %**, validation **514 trades, −6 901.43 USDT, −69.01 %**; holdout sealed (1 entry in `HOLDOUT_SEALED.json`, 0 holdout metrics in `results.json`, 0 metric rows in the SCOREBOARD holdout section) |
| 8-strategy matrix smoke | `--stage validation --timerange 20260101-20260201` | 20 pairs × 8 strategies, 98 s wall, 7/8 strategies produced results |
| Graceful degradation | `--stage holdout` against a data dir truncated at 2026-05-16 | `status: insufficient_data`, no crash |

## 7. Findings that matter for Phase 2

1. **`EnsembleStrategy` is broken at this HEAD** — `populate_entry_trend` →
   `_load_signal_bus()` → `AttributeError: '_SignalBus' object has no attribute 'read'`
   (`user_data/strategies/ensemble_strategy.py:241`). `list-strategies` reports `OK` because only
   imports are checked. The scoreboard records `status: no_result` and continues; the strategy
   cannot be scored until its own file is fixed (out of scope here — anti-goal: no strategy edits).
   This crash is also why `--strategy-list` batch mode aborts and the script falls back to
   per-strategy processes; `--no-batch` skips the wasted attempt.
2. **The cost model is not cosmetic.** Under 10 bps all-in and the config's leverage cap of 6,
   EmaTrendFollowing goes from whatever the old result JSONs claimed to −98.07 % (train) and
   −69.01 % (validation) across the 20-pair portfolio. Any Phase 2 candidate has to clear fees,
   not just signal quality.
3. `AroonMomentumEngine_Hybrid` and `DmiAdxStrategy` produced **0 trades** in the 1-month matrix
   smoke — not an error (status `no_trades`), but it means a 1-month window is too short to score
   them; the full train/validation windows are the meaningful ones.

## 8. Runtime estimate for the full matrix (8 × 20 × 3)

Measured: 20 pairs × 3 stages × 1 strategy = **68.8 s** of backtests (train 30.8 s, validation
17.7 s, holdout 20.3 s).

```
8 strategies × 68.8 s            = 550 s  (~9 min)
+ one failed batch attempt       =  21 s   (auto-disabled after the first failure)
+ EnsembleStrategy failing fast  =   7 s
  ------------------------------------------
  full 8 × 20 × 3 wall clock     ≈ 10 min (allow 10-13 with machine load)
```

That is small enough to run the full matrix as part of `make check`'s quarterly variant, and it is
the reason no per-strategy sharding was added.

## 9. Known limits

* **The full 8 × 20 × 3 matrix was not run** — deliberate, per the task's timebox. Only the runs in
  §6 exist; every other number here is a timing extrapolation, labelled as such.
* **Batch mode is currently poisoned by `EnsembleStrategy`.** One crashing strategy aborts the
  whole `--strategy-list` process; the fallback keeps the run correct but costs one wasted attempt
  per invocation (auto-disabled after the first failure).
* **Metrics are portfolio-level** (max 4 open trades, leverage from each strategy's `leverage()`
  callback capped at 6 by the config). `per_pair[]` rows are that pair's contribution to the shared
  wallet, not an independent single-pair backtest.
* **Fee is a proxy for slippage**, labelled as such; it does not model spread, funding, or
  market impact. Futures funding is not charged by the backtester.
* **Reproducibility is scoped**: `manifest_hash` covers the windows actually scored, so a data
  refresh that appends candles outside those windows does not change it. A refresh that rewrites
  candles *inside* a scored window does change it — correctly, because the results would change.
  The hash also includes the git SHA, so any new commit invalidates a comparison (4 dp equality of
  `results.json` still holds if the code and data are unchanged).
* **Data is live during this work**: the refresh lane rewrote several feather files between runs
  (BNB 4 490 → 59 369 rows within ~30 minutes). The smoke window was chosen in the past
  (2025-10/11) so appends could not influence it; that is why the two runs match exactly.
* The `--limit` smoke flag limits **pairs**, not strategies; use `--strategies` for that.

## 10. Files created / modified

| Path | Status |
|---|---|
| `scripts/scoreboard.py` | new |
| `reports/phase1/scoreboard/SMOKE.log` | new (full evidence, sections 0-8 + Appendix A) |
| `reports/phase1/scoreboard/PHASE1_SCOREBOARD_REPORT.md` | new (this file) |
| `reports/scoreboard-smoke-A/`, `-smoke-B/` | new (reproducibility pair, 90 KB each) |
| `reports/scoreboard-fullrun/` | new (20 pairs × 3 stages × 1 strategy) |
| `reports/scoreboard-matrix-smoke/` | new (20 pairs × 8 strategies × 1 month) |
| `reports/scoreboard-degrade-test/` | new (insufficient-data fixture) |

Nothing else was touched: no config edits, no strategy edits, no git writes, no live trading.
