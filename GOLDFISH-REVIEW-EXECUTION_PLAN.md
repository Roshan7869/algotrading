# GOLDFISH REVIEW — EXECUTION_PLAN.md (v0.1)

Reviewer: isolated adversarial subagent (no conversation context), 2026-11-19.
Method: read the draft only; verified repo claims against live files.

## Verdict: REJECT

30 findings — BLOCKER: F1 (dry-run feed assumption), F5 (signal_v1 violates anti-goal 1),
F6 (attic cannot shrink repo as specified), F12 (fresh-clone grep misses history),
F13 (test-set selection leakage).

## Top-3 changes demanded
1. History-wide secret proof + purge PR refs/forks/branches (not a working-tree grep).
2. Fix measurement design: third untouched holdout + numeric gate with CI/min trades.
3. Make size/sequencing physically true: cached-removal + scheduled purge, or drop the size
   target; move signal_v1 behind the Phase 2 gate.

## Disposition

All 30 findings folded into v0.2 (resolution log in the plan's appendix). Two reviewer counts
were re-measured and corrected against the repo: spot 1h pairs = **13** (reviewer said 22),
futures feather files = **205** (reviewer said 130); both now discovered at runtime.

## Reviewer's own BLOCKER quote (for the audit trail)

> "§0.1's acceptance — verify `git grep` on a fresh clone returns 0 hits — tests the working tree
> at HEAD, not history... `git log --all -S'BINANCE_API_SECRET'` still matches bf5775c94 and
> a9b56205c across 31,849 revisions. The safety gate can pass without the leak being closed."

Verified independently on 2026-11-19: TRUE — the secret remains reachable via non-main refs in
the local clone; the remote `develop-local` branch still carries pre-scrub history. v0.2 Phase
0.1 now purges all refs and proves cleanliness history-wide before anything closes.

Full findings JSON: `D:\nexus-data\audits\algotrading\goldfish_review_execution_plan.json`
(copied from the reviewer's return).
