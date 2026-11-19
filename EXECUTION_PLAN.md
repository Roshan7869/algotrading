# EXECUTION PLAN — fix the root issues (v0.2, 2026-11-19)

Supersedes v0.1 (which the goldfish review REJECTED). Review: `GOLDFISH-REVIEW-EXECUTION_PLAN.md`.
Evidence: `D:\nexus-data\audits\algotrading\`. Every number below was measured on this machine;
counts are re-derived at execution time, never inherited.

## 1. Root causes

| # | Root cause | Evidence (measured) |
|---|---|---|
| R1 | Trust was never enforced by code | 5 conflicting "verified" numbers; +3,632,254% artifact ranked #1; **18 files** quarantined for lookahead (17 flagged + IVB_ORB) |
| R2 | Enforcement layers decorative | breaker stub returned constants (fixed 11-19); `risk_gate` still has no order-path call site; breaker `--check` is one-shot |
| R3 | Accumulation over composition | 152 configs, 9 leverage sources (3.0→18), 356 MB duplicate subtree, 217 boilerplate docs, empty gitlink |
| R4 | Integrations exist but are incompletely wired | engine/* imports resolve internally but fail on undeclared deps (redis, fcntl); nexus/bridge and agents/* DO import engine modules; swarm is canned |
| R5 | Docs drift from reality | May-2026 sprint; /home/roshan paths; wrong KB claims |
| R6 | No trade record | No plain tradesv3.sqlite; a **tracked `tradesv3.dryrun.sqlite` with 0 rows** (+shm/wal, corrupt WAL) exists; agent journal = 6 blocked decisions (2026-05-06) |

Diagnosis unchanged: the project optimized for the appearance of a trading system instead of its
two constituents — reproducible measurement and enforced risk.

## 2. Principles (binding)

1. Enforcement before edge. 2. Delete more than you add. 3. Reproducibility contract (SHA +
   data manifest + config path + fee model on every stored number; metrics compared at 4 dp on
   the same machine, never "byte-identical" across machines). 4. Paper before money.
   5. CPU-only, script-only.
6. **Attic = decision quarantine, not storage**: moving files also `git rm --cached` + .gitignore
   them (they leave the tracked tree), and object purging is a scheduled, backed-up step.

## 3. Phases

### Phase 0 — close the safety baseline (≈2-3 days)
- 0.1 **Finish push, then purge ALL refs.** The rewritten upload is in flight. After it lands:
  (a) delete remote branches still carrying pre-scrub history (`develop-local`, dependabot/*) via
  `gh api -X DELETE`; (b) list open PRs/forks and record them (PRs closed → delete refs; forks
  are out of reach — rotation covers, documented); (c) locally rewrite-or-delete every remaining
  ref, then `git gc --prune=now`; (d) **history-wide proof**: `git log --all -S` for both tokens
  AND a blob scan over `git rev-list --all --objects -- <leaked paths>` = 0 hits; (e) fresh clone
  + `git log --all --format=%H | xargs -n50 git grep` spot protocol documented.
  [orchestrator; push job already running]
- 0.2 **Rotate the Binance key** (user). **BLOCKS Phase 2.3 dry-run launch and all Phase 3 work.**
  Backtests/scoreboard do not require it.
- 0.3 **Supervised risk enforcement.** New `scripts/supervise.py`: launches a freqtrade dry-run
  session, polls the breaker every 5 min (`circuit_breaker.py --check`), and **stops the bot**
  (REST stop / process signal) on PAUSED or UNKNOWN; exits when the session ends. Breaker
  `--check` also runs as a preflight in every start script. Acceptance: with a mocked balance
  feeding −4% then −8% sequences, supervise stops the bot within one poll and writes PAUSED;
  demonstrated in a log.
- 0.4 **Secret gate with allowlist.** Pre-commit/pre-push hook: flags 64-char tokens and
  `api_key|secret|token\s*[:=]\s*<value>` assignments **except** `${ENV_VAR}` placeholders;
  compatible with the existing `.pre-commit-config.yaml`. Acceptance: planted test string is
  blocked; every current config with `${FREQTRADE_*}` passes.
- 0.5 **Delete dead trade DBs**: `tradesv3.dryrun.sqlite`(+shm/wal, 0 rows, corrupt WAL) removed
  from tracking and disk; a corrupt WAL must never masquerade as a paper record.

### Phase 1 — trust reset (≈5-7 days)
- 1.1 **The Attic.** Move + `git rm --cached` + gitignore: ALL result JSONs — including the ones
  v0.1 missed: `batch_results*`, `godmode_*`, `eden_*`, `generated_results_*`, `all_results_8y*`,
  `omni_results_300d*`, `analysis_8y_spot.json`, `kronos_results_*`, `strategy_rankings.json`;
  `Algo @ 2/` (356 MB); `.claude/` (217 files); upstream freqtrade docs beyond README;
  `notebooks/*`; UTF-16 txt artifacts; `config_archive/`, `config_examples/`; `.git-rewrite/`
  leftovers. Licensing note in `attic/README.md` (GPL-3 freqtrade tree retained, unmodified).
  Acceptance: `git ls-files | wc -l` and tracked-size target stated in the attic README (target:
  tracked tree ≤ 150 MB); working tree ≤ 600 MB; every mover listed with a one-line reason.
  **P1.5 object purge** (after attic verification, backup bundle first): history-rewrite attic
  paths out + `git gc --prune=now`; repo pack target documented (best effort — pack size is
  reported, not promised).
- 1.2 **Config consolidation.** Canonical set = the three that EXIST today:
  `user_data/config_backtest.json` (futures), `user_data/config_spot.json` (spot),
  `user_data/config_dryrun.json` (dry-run) — each gains explicit `db_url`, stake,
  max_open_trades, stoploss, `leverage` cap, purpose header line. Everything else cached-removed
  to attic. **Leverage truth**: all 8 surviving strategies define their own `leverage()`
  callback (verified) — so ONE table (`docs/leverage-matrix.md`) lists each strategy's leverage
  and the config cap; the claim "one leverage value" becomes "one documented table + one cap",
  which is what freqtrade actually consumes. New `scripts/validate_configs.py`: every canonical
  config parses, required keys present, api_server = 127.0.0.1 + env placeholders, no
  `dry_run: false`. Acceptance: validator green; exactly 3 tracked `user_data/config_*.json`.
- 1.3 **Data refresh with connectivity preflight.** First prove the feed works: download 1 pair
  × 1 day from Binance; if geo-blocked, try Bybit/Gate/OKX and record which venue works. Then
  refresh the canonical universe 2026-05-16 → today. Gap gate: per pair, expected = candles
  between first and last bar for that pair's listing window; gap% = missing/expected;
  acceptance = **no pair with >1% gaps and ≥95% of the canonical universe covered**.
- 1.4 **Scoreboard (centerpiece).** `scripts/scoreboard.py` (NEW): 8 surviving strategies × the
  20-pair canonical universe (futures data) with THREE-WAY split — train ≤2025-12-31,
  **validation 2026-01-01→2026-06-30 (selection)**, **holdout 2026-07-01→run-date (untouched
  until 2.4)**. Fees + slippage in. Output `reports/scoreboard-<date>/` JSON + MD with the
  reproducibility header (git SHA, data manifest with row counts, config path, fee model) and a
  manifest hash — re-runs must match at 4 dp and manifest hash; timestamps excluded from hashes.
  Universe sized at runtime (measured today: 338 feathers total, 205 futures files, 40 futures
  1h pairs, 13 spot 1h pairs — recomputed at run).
  Acceptance: scoreboard regenerated twice matches at 4 dp; holdout columns sealed (separate
  file not used by selection).
- 1.5 Object purge + fresh-clone verification of P1.1 (bundle backup kept until verified).

### Phase 2 — one honest candidate, or honest failure (≈1 week code + 30 days wall-clock per attempt)
- 2.1 Select top-2 **by validation-set expectancy** (holdout still sealed). Verify no lookahead;
  fix stop logic in those two files ONLY (price-terms stops, tight-only ratchet, leverage-aware);
  re-run scoreboard; if either drops out of contention after fixes, move to the next candidate.
- 2.2 `research/walkforward.py` (NEW) with executable acceptance: rolling 6-month train /
  1-month test across the canonical universe; output must report per-window expectancy AND an
  aggregate **bootstrap 95% CI**; gate: aggregate OOS expectancy > 0 with CI lower bound > 0,
  else the script reports FAIL loudly. "Honest header" = the reproducibility header from 1.4 —
  same fields, same hash scheme.
- 2.3 **Dry-run month** on the SAME 20-pair universe (fixes the v0.1 mismatch), via
  `scripts/supervise.py` (breaker wired), writing to `tradesv3.dryrun.sqlite` (the filename
  freqtrade actually uses without db_url — verified). Journal: daily note in
  `FINANCE/12-Research/journal-<date>.md` **plus a repo-side weekly export**
  `reports/dryrun/week-<n>.csv` so the record is verifiable from the repo alone.
  Acceptance: DB exists with ≥50 closed trades; supervise log shows zero unhandled stop
  failures; journal ≥ 28 daily notes; weekly CSVs present.
- 2.4 **Go/No-Go with statistics, not sign.** Evaluate the dry run: expectancy net of fees with
  bootstrap 95% CI; PASS = CI lower bound > 0 **and** dry-run expectancy ≥ 50% of the
  validation-set expectancy (sanity vs scoreboard). FAIL → archive strategy, loop 2.1 with the
  next candidate (+30 days each). Decision memo with numbers committed to `reports/decisions/`.
  Holdout is opened exactly once here for the chosen strategy; its metrics are reported beside
  validation and dry-run — if holdout contradicts validation, FAIL regardless.

### Phase 3 — integrations, only after Phase 2 PASS (user opt-in; ≈3-4 days)
- 3.1 Optional and gated: TradingAgents consumer. Build `signal_v1` only here (moved behind the
  anti-goal gate — v0.1 violated its own rule). Needs the user's LLM key; freshness checks on
  `_timestamp`; 30-day signal validation; no order path.
- 3.2 **Module consumer map first.** `grep -rn 'from engine|import engine'` (already shows
  engine internal imports, nexus/bridge, agents/*) → table of module → importers → dependency
  status. Archive only zero-importer modules; fix deps (replace redis with file-based bus,
  fcntl guard) only for modules with named consumers. Nothing gets archived that breaks an
  import path without its consumer being archived in the same commit.
- 3.3 Flowsurface: archive until a charting need is proven (Rust build deferred, no toolchain).
- 3.4 `scripts/daily_report.py` (cron-able, exits): yesterday's dry-run stats → vault note.

### Phase 4 — operations & knowledge (ongoing)
- 4.1 Docs collapse: README rewrite; AGENTS.md fix (paths, counts); retire old audits/plans to
  attic — **enumerate at execution time** (measured today: 7 `*AUDIT*.md` at root; `plans/`
  holds no plan docs — the earlier "6+7" was wrong). Keep: SETUP_LOCAL, this plan, runbook,
  scoreboard, leverage-matrix.
- 4.2 KB maintenance: after any strategy change → ingest + normalize. Coverage target defined
  by an executable measure: fraction of chunks whose keywords/title mention futures
  (`scripts/kb_coverage.py`, NEW) — baseline measured first, target = 3× baseline, reported as
  numbers, never a promise of "20%".
- 4.3 `make check` (NEW): list-strategies (expect 8), validate_configs, secret-hook self-test,
  scoreboard smoke (1 strategy, 1 month). Weekly; quarterly full re-audit.

## 4. Anti-goals
1. No new strategies before the Phase 2 gate — signal_v1 explicitly lives in Phase 3.
2. No integration without a named consumer + test (module map proves it).
3. No config without a purpose line; cap 3 canonical configs.
4. No number in docs without the reproducibility header.
5. No live money without: Phase 2 PASS + supervise/breaker demonstrated + journal running +
   explicit user arming. This plan never arms anything.
6. No attic growth without `attic/README.md` entry and cached-removal.

## 5. Timeline (with retries priced in)
- Phase 0: 2-3 days (plus push wall-clock).
- Phase 1: 5-7 days.
- Phase 2 attempt: ~1 week code + 30 days dry-run. **Each additional candidate = +30-37 days.**
- Phase 3: 3-4 days (parallel with a dry-run if one is active).
- Honest range: **best case 6-8 weeks (first candidate passes); typical 10-13 weeks (one retry);
  fail case = same cost, with a written "no edge found" memo and the scoreboard as the asset.**

## 6. Risks & failure modes (expanded)
- **Exchange connectivity blocked** → 1.3 preflight decides (Binance → Bybit/Gate/OKX); if all
  blocked, Phase 2.3 is impossible → plan converts to backtest-only and says so in the decision
  memo instead of pretending.
- **Force-push/branch-protection/PRs/forks**: 0.1 protocol; forks out of reach → rotation is the
  fix, stated in the memo. Bundle `pre_rewrite_backup.bundle` kept until fresh-clone verification.
- **Selection leakage**: three-way split; holdout opened once; holdout contradiction = FAIL.
- **Noise at 50 trades**: gate uses bootstrap CI + relative sanity vs validation expectancy.
- **Discipline drift** (new strategies/tools instead of the dry-run month): anti-goals + weekly
  make check + vault journal.
- **TradingAgents cost creep**: Phase 3 only; LLM opinions never enter the order path.

## 7. Definition of done
A stranger can clone the repo, run `make check`, run `scripts/scoreboard.py`, and reproduce the
documented numbers at 4 dp with matching manifests; the holdout was opened once and is reported;
the repo contains one strategy with validation + holdout + 4-week supervised paper evidence (or
a written failure memo), a working risk supervisor, a secrets hook that demonstrably blocks, and
no aspirational module without a consumer.

## Appendix — review resolution log (v0.1 → v0.2)
F1 feed assumption → 1.3 preflight + §6. F2 push/purge refs → 0.1. F3 external journal → 2.3
repo CSV export. F4 licensing → 1.1 attic note. F5 signal_v1 contradiction → moved to 3.1.
F6 attic/size mechanics → principle 6 + 1.1 + P1.5. F7 blocking scope → 0.2 wording (blocks
2.3+). F8 leverage() reality → 1.2 leverage-matrix. F9 universe mismatch → 2.3 same 20 pairs.
F10 retries → §5. F11 count reconciliation → R1 (18 files). F12 history-wide secret proof →
0.1(d-e) (verified: bf5775c94/a9b56205c still match locally via non-main refs). F13 holdout
leakage → three-way split (1.4/2.4). F14 statistical gate → 2.4 CI. F15 breaker --check
one-shot → supervise.py (0.3). F16 hook allowlist → 0.4. F17 db filename → 2.3. F18
byte-identical → principle 3 (4 dp + manifest). F19 gap denominator → 1.3. F20 walkforward
acceptance → 2.2. F21 adjectives → counted throughout. F22 coverage baseline → 4.2 executable
measure. F23 scope creep → KB/walkforward/signal_v1 marked optional/gated. F24 attic list →
1.1 expanded. F25 import graph → 3.2 map-first (verified imports exist). F26 counts → runtime
discovery (verified: 338/205/40/13 — critic's 130/22 were wrong). F27 missing configs → 1.2
uses the three that exist. F28 empty tracked DB → 0.5 + R6 wording. F29 inventory → 4.1
enumerate at execution. F30 deliverables-as-state → all NEW files marked.

## Outcome log

### 2026-11-19 — Phase 2 gate: **FAIL (no edge)**
Executed 2.1+2.2. SupertrendEma quarantined (lookahead: 4h merge on raw stamp; 19 files total).
BollingerMR baseline invalidated (hyperopt params 2026-05-14 overlap validation 2026H1);
post-stop-fix −0.93%/trade. Walkforward smoke: −1.115%/trade, CI [−1.74%, −0.47%], 0% positive
windows → loud FAIL. **2.3 dry-run does not launch; Phase 3 stays gated.** Decision memo:
`reports/decisions/no-edge-memo-20261119.md`. Root cause: cost drag (20bps round trip vs
1h trade frequency) × 3x leverage. Next: cost-aware redesign (user decision).

### 2026-11-19 — key rotation declined by user
The user declined rotating the Binance key — recorded as an accepted risk in the memo (§Key
rotation). No authenticated path exists in the plan until a Phase 2 PASS, so nothing today uses
that credential family.

### 2026-11-19 — Phase 0.1 COMPLETE (push landed + verified)
Rewritten history pushed; remote `main` = local HEAD (`aa505d8fd`), 31,840 commits, single branch,
0 open PRs, 0 forks. Secret-value proof: `git log origin/main -S` both prefixes = 0 hits; tree
grep = 0. Bundle backups retained (`pre_rewrite_backup.bundle`, `pre_purge_backup_20261119.bundle`).

### 2026-11-19 — Phase 4.1 / 4.2 / 4.3 (partial — AGENTS.md blocked)
4.1: README rewritten with the honest FAIL status; 48 old docs → `attic/docs-history/`
(MOVED.md tracked, 73 entries incl. superseded refs); `.claude-flow/` session dumps attic'd.
**AGENTS.md edit DENIED by the agent-instruction file protection** — file untouched; proposed
content saved at `reports/phase4/docs/AGENTS_MD_PROPOSED.md` pending explicit user approval.
Stale `/home/roshan` refs remain only in AGENTS.md + old analysis scripts + editor tool configs.
4.2/4.3: `scripts/make_check.py` PASS 27.55 s (7 loadable / 19 quarantined none loadable;
configs PASS; secrets 0/1514; smoke ok); `scripts/kb_coverage.py` baseline 10.13% (62/612 chunks),
3× target 30.39%; `start_local.sh` +22-line fail-closed breaker preflight.
