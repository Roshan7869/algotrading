# Phase 2.2 — walk-forward validation: build + smoke evidence

Date: 2026-11-19 · git `9fd8eca2b2793bd7d79452ab92c8376671673746` · freqtrade `2026.5-dev-9fd8eca2b`
Owner: Phase 2.2 (`EXECUTION_PLAN.md`). Evidence dir: `reports/phase2/2.2/`.

**Bottom line: the tool is built and runs. Every smoke FAILS the gate with real numbers
(no out-of-sample edge survives 10 bps), and the failure is loud: banner + exit code 1.**
The full 8-strategy matrix was **not** run — that is the orchestrator's job (§5).

---

## 1. What was built

| File | Purpose |
|---|---|
| `research/walkforward.py` (new) | rolling train/test windows, per-window backtests, trade-concatenated bootstrap 95% CI, loud PASS/FAIL gate, `--verify` |
| `tests/phase2/test_walkforward.py` (new) | 22 stdlib-unittest cases: window arithmetic, bootstrap determinism, gate logic, skip paths, verify contract |
| `reports/phase2/2.2/*` (new) | smoke outputs (WALKFORWARD.md / walkforward.json / windows.json / MANIFEST.json / trades CSV / raw zips+logs) |

### Reuse (not reinvention)

`research/walkforward.py` imports `scripts/scoreboard.py` as a module and calls its
`run_backtest()`, `parse_result_zip()`, `extract_metrics()`, `build_command()`, `git_sha()`,
`file_sha256()`, `sha256_of()`, `_walk_numbers()`, `VERIFY_ROUND_DP`, `EMPTY_METRICS`,
`FEE_MODEL`, `MIN_STAGE_CANDLES`, and the universe resolver. Fee handling is therefore literally
the scoreboard code path (`--fee 0.001`, `--cache none`, same config, same `--timeframe`), and the
fee string emitted is the scoreboard's verbatim:
`fee_model: 10bps all-in (fee + slippage proxy)`.

The only new logic is: the window loop, per-window pair availability, trade-level aggregation, the
bootstrap, the gate, and the report/manifest.

### CLI (as specified, plus operators)

```
python research/walkforward.py
  --strategy <Class> [--strategy ...]      # default: all 8 loading strategies
  --strategies <Class> [...]               # alias, same thing
  --pairs ... | --universe-json <file>     # default reports/scoreboard-20261119-1229/UNIVERSE.json
  --train-months 6 --test-months 1
  --start 20240101 --end RUN_DATE          # default end = run date (UTC)
  --userdir user_data --config user_data/config_backtest.json --data-dir <dir>
  --fee 0.001                              # all-in per side; label auto-derives for other values
  --bootstrap-resamples 10000 --seed 42 --min-trades 30
  --limit N --outdir DIR --max-run-seconds 600 --batch --allow-fail
  --verify DIR_A DIR_B                     # 4 dp + manifest hash, same contract as scoreboard
```

**Window semantics (documented deviation, deliberate).** `--start`/`--end` bound the **test**
span; the train window rolls immediately before each test month. Implemented literally ("first
test = start + train"), the prescribed smoke `--start 20250801 --end 20251101 --train-months 3`
yields **zero** windows — a smoke that proves nothing. With test-span semantics it yields 3 real
windows (2025-08, 2025-09, 2025-10). A clipped tail window shorter than 7 days is dropped and
recorded (`2025-11` in the smoke: `20251101-20251102`).

### Gate (loud, at the top of the report and on stdout)

```
PASS  iff bootstrap 95% CI lower bound of aggregate OOS expectancy per trade > 0
      AND n_trades >= 30 AND n_windows_with_trades >= 2
FAIL  -> "WALKFORWARD FAIL: no OOS edge at 10bps" + per-strategy reasons + exit 1
        (--allow-fail keeps the banner and exits 0 for CI wiring)
```

The extra sample-size conditions are strictly conservative additions: a 1-trade "CI" is a point,
and one lucky month is not a walk-forward result. Zero-trade windows count as non-positive in
`pct_positive_windows`.

### Outputs per run

`WALKFORWARD.md` (verdict at the top, reproducibility header: git SHA, freqtrade version, config +
config sha256, fee model, timeframe, run mode, manifest hash, bootstrap params; windows table;
aggregate table; per-window matrix; data-sufficiency section; known limits; reproduce block),
`walkforward.json` (stable ordering: strategies alphabetical, windows by index; numbers at 6 dp,
compared at 4 dp), `windows.json` (per-window per-strategy full metrics + pair lists + skips),
`MANIFEST.json` (hash scope: git SHA, config sha, fee, timeframe, **run mode**, strategy list,
universe, window list, bootstrap params, gate rule, per-pair test-row counts per window; excludes
timestamps/paths/runtime/metrics), `trades/<strategy>.csv` (every OOS trade, so the bootstrap can
be re-derived from the artifact), `raw/<window>__<strategy>/` zips + `logs/`.

---

## 2. Smoke evidence (real numbers, nothing synthetic)

### 2.1 Prescribed smoke — 1 strategy, 3 months, 3-month train

```
.venv/Scripts/python.exe research/walkforward.py --strategies EmaTrendFollowing \
  --train-months 3 --test-months 1 --start 20250801 --end 20251101 \
  --outdir reports/phase2/2.2/smoke1
```

| | |
|---|---|
| windows run | **3** (2025-08, 2025-09, 2025-10), 0 insufficient |
| trades | **300** |
| aggregate OOS expectancy / trade | **-1.1152 %** |
| **bootstrap 95% CI** | **[-1.7358 %, -0.4677 %]** (10 000 resamples, seed 42) |
| pct positive windows | 0.0 % |
| gate | **FAIL** — `ci_low=-0.017358 <= 0` |
| exit code | **1** |
| wall time | 26.0 s (7.6 / 8.8 / 9.1 s per window) |
| manifest hash | `sha256:0bd598e40479a1fd2992955eb9f30b85bddcbed79d01d78db0df71f2eb7040f3` |

Per window: 2025-08 `-33.62 % (87 trades)`, 2025-09 `-26.88 % (114)`, 2025-10 `-14.84 % (99)`.
Consistent in sign and magnitude with the scoreboard's validation stage for this strategy
(`-71.70 %` over 2026H1, `-0.884 %`/trade) — regime-consistent, not a tooling artifact.

**Reproducibility:** the same command run again into `smoke1-rerun` and compared:

```
python research/walkforward.py --verify reports/phase2/2.2/smoke1 reports/phase2/2.2/smoke1-rerun
  manifest_hash: MATCH (sha256:0bd598e4...)
  results: MATCH at 4 dp (74 scalar fields)
PASS
```

The same smoke was also run **without `--outdir`**, so the default path convention is exercised:
`reports/walkforward-20261119-1311/` (31.6 s, 3 windows). `--verify` against `smoke1` also reports
`manifest_hash: MATCH` and `results: MATCH at 4 dp` — reproducibility holds across output dirs and
across runs twenty minutes apart, not just within one directory.

### 2.2 Broader smoke — 2 strategies, 4 months

```
--strategies BollingerMeanReversion SupertrendEmaStrategy --train-months 3 --test-months 1
--start 20250701 --end 20251101 --outdir reports/phase2/2.2/smoke2
```

| Strategy | Trades | Windows | Exp/trade % | CI low % | CI high % | Pos. win % | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| BollingerMeanReversion | 96 | 4 | -0.6193 | -1.5531 | **+0.3289** | 25.0 | FAIL |
| SupertrendEmaStrategy | 2 | 4 | +0.5093 | -5.5910 | +6.6096 | 25.0 | FAIL (n=2 < 30) |

65.9 s total (~16.5 s/window). Bollinger's CI **includes zero** — the point estimate is negative
and its interval is wide, which is exactly the "sign is not evidence" case the gate exists for.
Supertrend trades twice in four months; no CI over 2 trades can pass.

### 2.3 Crash containment — EnsembleStrategy (known `_SignalBus.read` AttributeError)

```
--strategies EnsembleStrategy --train-months 3 --test-months 1 --start 20250901 --end 20251101
```

Both windows: `no_result` (rc=1, AttributeError at `ensemble_strategy.py:241` captured in the log
tail), the strategy is put on the skip list after 2 process failures, **the run completes** and
reports `n_trades=0 -> FAIL (no out-of-sample trades)`. Exit 1, 12.9 s. The strategy was not
touched: it is treated as no-result, per the Phase 2 contract.

### 2.4 Late-listed pair — skipped per window, no crash

```
--strategies EmaTrendFollowing --pairs BTC/USDT:USDT HYPE/USDT:USDT --start 20240101 --end 20240131
```

`pairs=1` for the window, `HYPE` recorded under *pair-window skips* ("test_rows=0 < 100"), the
window still ran (15 trades, CI [-4.93 %, +0.62 %]), `--allow-fail` → **exit 0**. 4.9 s.

### 2.5 Unit tests

```
.venv/Scripts/python.exe -m unittest tests.phase2.test_walkforward -v
Ran 22 tests in 0.090s — OK
```

Covers: window arithmetic (`start+train` for the smoke = 3 windows, tail drop, 35 windows for the
default span, no train/test overlap), bootstrap determinism under seed 42 and CI bracketing,
gate PASS on a synthetic positive edge / FAIL on negative / FAIL on < 30 trades / FAIL when all
windows are no-result / FAIL with a single trading window, the scoreboard fee-string and
`--fee`→`build_command` path, per-window pair skipping, and `--verify` (match at 4 dp, mismatch on
a 5th-dp change, mismatch on manifest hash).

### 2.6 Measured cost of one window (basis for the estimate)

| Configuration | Window cost | Notes |
|---|---:|---|
| 1 strategy | 7.6–9.1 s | smoke1 |
| 2 strategies | ~16.5 s | smoke2 |
| 8 strategies (7 loading + 1 crashing) | **67.5 s** | `scale-8x1`, 2025-10 window, 20 pairs |
| 7 strategies, batch mode | 27.4 s | `scale-7x1` — see §3, not the default |

---

## 3. Finding that changed the default: batch mode is not a measurement mode

While probing, the same window (2025-10, 20 pairs) gave **different results for the same
strategy depending on whether it ran alone or inside `--strategy-list`**:

| Run | Trades | Exp/trade % |
|---|---:|---:|
| `BollingerMeanReversion` alone | 13 | **-1.2501** |
| `BollingerMeanReversion` in a 7-strategy batch | 15 | **+0.5664** |

The month's sign flips. freqtrade shares the loaded data/startup-candle window across
`--strategy-list` members, so each strategy's warm-up — and therefore its first signals — changes
with batch membership. A validation number that depends on which other strategies were in the
process is not a measurement, so **the default is one process per (strategy, window)**;
`--batch` remains available for speed when only relative ranking inside a fixed set matters.
`run_mode` is recorded in the manifest and **inside the manifest hash**, so a batched run can never
be mistaken for an isolated one.

---

## 4. Known limits (also emitted in every WALKFORWARD.md)

1. **Trade-level bootstrap assumes independent trades.** Trades within a month share a regime. The
   gate uses the specified trade-level interval; `window_bootstrap` (resample windows) is reported
   beside it as the pessimistic companion. In smoke1 it agrees: `[-1.83 %, -0.57 %]`.
2. **Per-window profit % is not a portfolio return** — each window restarts at 10 000 USDT with
   `max_open_trades: 4` and unlimited stake, so windows are not compounded. The gate is on
   expectancy per trade, which is scale-free.
3. **"Train" is measured, not fitted.** None of these strategies has a hyperopt step; the train
   window is reported so the reader can see whether the pair list was tradable, not to fit
   parameters.
4. **Cost model is a proxy**: 10 bps per side covers fee + slippage; the backtester models no
   native slippage, and only freqtrade's own `funding_fees` column charges funding.
5. **Test-span semantics** (§1) is a deliberate reading of the plan text; it is stated in the
   module docstring and in every report.
6. **A run longer than 120 s triggers the guardrail**: subsequent windows are capped to 10 pairs
   and the degradation is written into `MANIFEST.json` (`degraded`) and WALKFORWARD.md. It did not
   trigger in any smoke (max 67.5 s).
7. The gate is a *necessary* condition, not a promise: a PASS on 30 trades of a
   leveraged 1h strategy is still a small sample, which is why Phase 2.4 adds the dry-run leg.

---

## 5. Full-run estimate (measured, not guessed)

Default span `20240101 → 2026-11-19` = **35 windows** (2024-01 … 2026-11, last one partial).

| Matrix | Measured per window | 35 windows |
|---|---:|---:|
| 8 strategies (as specified) | 67.5 s | **≈ 39 min** (67.5 × 35 = 2 363 s) |
| 2 strategies (Phase 2.1 top-2) | 16.5 s | **≈ 10 min** |
| 8 strategies, `--batch` | 27.4 s | ≈ 16 min, **not comparable to isolated runs** (§3) |

Recommendation for the orchestrator: run the 8-strategy matrix unbatched once
(`python research/walkforward.py --outdir reports/walkforward-<ts>`), budget 40 minutes, and use
`--allow-fail` only when the exit code is not the signal — the FAIL banner and
`walkforward.json.gate` carry the verdict either way.

Total measured backtest execution for this child task: ~4.2 minutes of freqtrade runs
(26 + 26 + 31.6 + 66 + 13 + 5 + 68 + 3 s), well inside the 20-minute timebox.
