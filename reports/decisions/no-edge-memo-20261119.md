# DECISION MEMO — Phase 2 gate: NO EDGE (2026-11-19)

Per EXECUTION_PLAN.md v0.2 §2.4, the Go/No-Go gate is evaluated on measured evidence only.
**Outcome: FAIL.** No candidate strategy demonstrates positive out-of-sample expectancy at the
10bps all-in cost model on the canonical 20-contract, 1h universe. Phase 2.3 (dry-run) does not
launch; Phase 3 stays gated; nothing approaches live.

## Evidence chain

1. **Scoreboard baseline** (`reports/scoreboard-20261119-1229/`, manifest `sha256:41a5cd17…`,
   holdout sealed `sha256:e9661b72…`): all 7 non-crashing strategies net-negative on the
   validation window. Best: BollingerMR −0.271%/trade (72 trades), SupertrendEma −0.637%/trade
   (9 trades). Train 2025 equally negative — no regime explains it away.
2. **Phase 2.1 audit** (`reports/phase2/2.1/`):
   - **SupertrendEmaStrategy: lookahead-SUSPECT** — 4h informative frame merged on the raw 4h
     candle stamp with forward-fill (line 130). A 4h bar stamped D closes at D+4h → 75% of 1h
     rows consumed a close from their future (probe: 186/186 buckets). **Quarantined** as the
     19th lookahead file. Measured impact small (4/740 rows) yet disqualifying for OOS claims.
   - **BollingerMeanReversion: CLEAN mechanics, INVALID baseline** — its "best" validation
     result is partly in-sample: the hyperopt parameters were exported 2026-05-14, inside the
     Jan–Jun 2026 validation window. Stop-logic fixes applied (3 fixes: price-terms stops,
     tight-only ratchet, enabling flag); post-fix validation −0.928%/trade (−0.17% on the
     most favorable re-pricing of same-candle fills) — negative under every reading.
3. **Walkforward** (`research/walkforward.py`, 22 unit tests, verify PASS at 4dp) — **full matrix
   complete**: 35 monthly OOS windows (2024-01→2026-11, 6-month rolling train, per-strategy
   processes), manifest `sha256:d8e181a1…`, 2324 s:
   - Aroon_Momentum_V2: 14,332 trades, **−0.9255%/trade, CI [−0.9986, −0.8530]**, 2.9% positive windows
   - EmaTrend: 4,454 trades, **−1.0032%, CI [−1.1868, −0.8191]**, 5.7% positive windows
   - BollingerMR: 730 trades, **−1.0177%, CI [−1.3647, −0.6668]**, 20.0% positive windows
   - Aroon_Hybrid / Ensemble / Supertrend: 0 OOS trades; DmiAdx: 1 trade; MacdRsi: 4 trades (all
     below the 30-trade minimum) → **every strategy FAIL**. The three real-sample CIs sit entirely
     below zero: this is not noise, it is a structural cost problem.
   - Smoke earlier: EmaTrend 3 windows −1.115%/trade, CI [−1.736, −0.468], 0% positive windows.

## Root cause of the failure (the useful part)

**Cost drag dominates.** At 10bps all-in per side ≈ 20bps round trip, a strategy must average
>20bps gross per trade just to break even. The surviving set trades 72–3,172 times per 6-month
window on 1h bars — average moves captured are near or below the cost floor, and 3x leverage
callbacks triple the bleed. The old fake results (+21,300%/+3.6M%) hid this entirely.

## Options (user decision)

1. **Cost-aware redesign** (recommended): fewer, larger trades — 4h/1d signal timeframe, wider
   ATR stops, target ≥100bps gross expectancy per trade, maker-entry where possible. Validate
   train-only first, then a fresh validation window (post-2026-07). This directly attacks the
   measured cause rather than the symptom.

   **Pre-check executed 2026-11-19** (`research/regime_delta.py`, method from arXiv:2110.11848 —
   Wasserstein-k-means regime clusters fit on 2025 only, applied causally to the validation slice):
   gating entries to the calm cluster moves expectancy by **+0.278pp (EmaTrend: −0.925→−0.648,
   loss −42%)**, **+0.001pp (Aroon_V2)**, **+0.064pp (BollingerMR)** — real as a loss-reduction
   filter, but **no strategy crosses zero**. The regime gate alone is insufficient; it is one
   component of the redesign, not a fix.
2. **Next scoreboard tier**: evaluate the repo's remaining generated strategies under the same
   gates (costs + lookahead audit) — but expect the same cost floor; not obviously different.
3. **Park the trading track**: keep the durable assets — measure-first infrastructure
   (scoreboard, walkforward, supervise, secrets gate, sealed holdout), the knowledge vaults,
   and the NEXUS department. Resume when a structural idea clears the cost floor.

## Standing constraints

- Binance key rotation (user) — still open; blocks any authenticated phase.
- No live trading; live configs remain DISABLED/dry_run.
- SupertrendEmaStrategy stays quarantined until re-wired with `merge_informative_pair`
  or an explicit timeframe shift; any revival must pass the full gate again.
- EnsembleStrategy crash (`_SignalBus.read`, line 241) recorded as no_result; fixing it is
  Phase 3.2 work behind the consumer gate.

## Key rotation — DECLINED by user (2026-11-19)

The user explicitly declined to rotate the Binance API key. Recorded as an **accepted risk**, not
a resolved item. Facts as they stand (verified 2026-11-19 13:2x UTC): the value is absent from
the local history AND **the rewritten push landed — remote `main` = `aa505d8fd`, 31,840 commits,
`git log -S` for both prefixes = 0, tree grep = 0, forks = 0, 0 open PRs**. GitHub may retain
unreferenced objects server-side for a period; closed PR refs (#1, #10, #11) may remain reachable
internally. If the key is ever used again (any authenticated call), it must be a NEW key, not the
leaked one. The plan's phases 2.3+/3 remain gated on the Phase 2 PASS regardless, so no
authenticated path exists today.

## Artifacts

- `reports/scoreboard-20261119-1229/` · `reports/phase2/2.1/` · `reports/phase2/2.2/` ·
  full walkforward under `reports/walkforward-<ts>/` (when complete)
- Vault: `FINANCE/11-Algotrading/phase2-no-edge-memo.md`
