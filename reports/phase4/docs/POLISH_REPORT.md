# Phase 4.1 — docs collapse: polish report

Date: 2026-11-19 · Repo: `D:\dev\algotrading` · HEAD at start: `aa505d8fdc1cd40b2b621895c4e95c7d0a5dd5a6`
(no git write commands were run: no commit, no `git rm --cached`, no push).

## 1. Outcome in one table

| Item | Result |
|---|---|
| Root `*.md` before | 51 |
| Root `*.md` after | 6 — `README.md`, `AGENTS.md`, `EXECUTION_PLAN.md`, `GOLDFISH-REVIEW-EXECUTION_PLAN.md`, `SETUP_LOCAL.md`, `CONTRIBUTING.md` |
| Files moved to `attic/docs-history/` | **63** (45 root, 8 `plans/`, 10 `.opencode/plans/`) |
| Files rewritten | **`README.md`** (full replacement of the freqtrade boilerplate) |
| Files created | `reports/phase4/docs/INVENTORY.md`, `reports/phase4/docs/POLISH_REPORT.md`, `reports/phase4/docs/AGENTS_MD_PROPOSED.md`, `attic/docs-history/MOVED.md` |
| `AGENTS.md` | **NOT fixed — write blocked by the runtime** (protected agent-instruction file, consent required). Exact replacement text is in `AGENTS_MD_PROPOSED.md`. |
| Stale absolute paths in docs of record | 2, both in the un-editable `AGENTS.md` (§5) |
| Broken relative links in docs of record | 10, all in `AGENTS.md`; 0 everywhere else (§4) |

## 2. `README.md` — what it says now

Replaced the upstream freqtrade README (badges, exchange matrix, Docker quickstart, Telegram command
list, upstream contribution links) with a project README in six sections:

1. **Identity** — a personal measurement-first research platform on a freqtrade fork; explicitly not
   a product, signal service or trading system.
2. **Honest status banner** — Phase 2 gate **FAILED**, no edge at 10 bps all-in per side; Phase 2.3
   dry-run does not launch; no live trading; 7 loadable strategies after 19 lookahead quarantines;
   3 canonical configs; 20-pair 1h futures data through 2026-11-19. Each row points at its evidence
   path.
3. **What was measured** — scoreboard best −0.271 %/trade (BollingerMR, 72 trades) from
   `reports/scoreboard-20261119-1229/SCOREBOARD.md` (manifest `sha256:41a5cd17…`); walkforward
   −1.115 %/trade, CI [−1.736 %, −0.468 %], 0 % positive windows from
   `reports/walkforward-20261119-1311/WALKFORWARD.md`; the cost-drag root cause and the three user
   options from the no-edge memo.
4. **Quickstart for the four tools** — `scripts/scoreboard.py` (smoke, full, `--verify`),
   `research/walkforward.py` (smoke + full), `scripts/supervise.py --preflight`, and
   `scripts/validate_configs.py` + `scripts/secrets_scan.py` / `.githooks`. Each block states the
   expected exit code or output, including the honest note that `--preflight` currently exits 1 with
   `state=UNKNOWN` because no balance source is wired (fail-closed, not a bug).
5. **Repo map** — strategies / configs / data / `research/` / `scripts/` (trusted subset flagged) /
   `reports/` / `docs/` / `attic/` / phase evidence.
6. **Reproducibility contract + guardrails + doc pointers** — SHA, manifest hash, config sha256, fee
   model, stage bounds; 4 dp comparison rule; holdout opened once; no live money; no numbers without
   an artifact.

No marketing language, no forward-looking claims, no number without a `reports/…` path. The phase
table marks Phase 2 as FAIL and Phase 3 as gated.

Verified against live state while writing: `list-strategies` returned 7 OK rows;
`validate_configs.py` returned `43 pass, 0 warn, 0 fail | RESULT: PASS`; `secrets_scan.py --all`
returned exit 0; `supervise.py --preflight` returned `state=UNKNOWN`, `should_stop=true`, exit 1.

## 3. `AGENTS.md` — blocked, not skipped

`write_file` on `AGENTS.md` was refused by the runtime: *"write to protected agent-instruction
file(s) (AGENTS.md) was denied by the user … Do NOT retry it or attempt the same edit via another
path."* No patch/terminal workaround was attempted, per that instruction.

The live file is therefore unchanged and still contains:

- 10 links to files that are now in `attic/docs-history/` (`TYPED_EXECUTION_PLAN.md`,
  `OPTIMIZATION_ROADMAP.md`, `CROSS_PROJECT_INTELLIGENCE.md`, `OPTIMIZATION_MASTERPLAN.md`,
  `Trading_RESEARCH_PREVIEW_SYSTEM.md`, `MoondevRED_Engine_DeepDive.md`, `ARCHITECTURE_DAG.md`,
  `ALGOTRADING_STATE_ANALYSIS.md`, `STRATEGIC_PIPELINE_SUMMARY.md`, `VERIFICATION_REPORT.md`);
- 2 `cd /home/roshan/Downloads/Algotrading` instructions;
- pre-remediation counts (443 ChromaDB chunks, "10 documents", strategy numbers from the old index);
- no mention of the Phase 2 FAIL, the 7/19 strategy split, or the 3 canonical configs.

`reports/phase4/docs/AGENTS_MD_PROPOSED.md` holds the complete replacement (agent-facing purpose
kept: hard rules, verified commands with expected outputs, repo map, legacy warnings, escalation
rule). **Action needed:** apply it to `AGENTS.md` with user consent; after that the stale-path and
broken-link counts in this report drop to the values in §4/§5 minus the `AGENTS.md` column.

## 4. Link check

Every relative markdown link in the docs of record was resolved against disk (after the moves).

| Doc | Relative links | Broken |
|---|---:|---:|
| `README.md` | 11 | **0** |
| `AGENTS.md` | 10 | **10** (all point at atticked files; blocked write) |
| `EXECUTION_PLAN.md` | 0 | 0 |
| `GOLDFISH-REVIEW-EXECUTION_PLAN.md` | 0 | 0 |
| `SETUP_LOCAL.md` | 0 | 0 |
| `CONTRIBUTING.md` | 0 | 0 |
| `docs/leverage-matrix.md` | 0 | 0 |
| `attic/docs-history/MOVED.md` | 0 | 0 |
| `reports/phase4/docs/INVENTORY.md` | 0 | 0 |

One link was created and then removed during the work: moving `CONTRIBUTING.md` broke
`.github/PULL_REQUEST_TEMPLATE.md` (it links `CONTRIBUTING.md`). Since that template is outside
Phase 4.1's file ownership, `CONTRIBUTING.md` was restored to the root and reclassified KEEP
(upstream boilerplate, not history, inbound link exists). `INVENTORY.md` and `MOVED.md` reflect the
restore.

## 5. Stale-path grep

Command (docs of record only):

```bash
grep -rn --include="*.md" -E "/home/roshan|Downloads/Algotrading|/tmp/analysis" \
  README.md AGENTS.md EXECUTION_PLAN.md GOLDFISH-REVIEW-EXECUTION_PLAN.md SETUP_LOCAL.md \
  CONTRIBUTING.md docs/
```

Result: **3 hits — 2 actionable, 1 historical.**

| File | Line | Hit | Status |
|---|---:|---|---|
| `AGENTS.md` | 28 | `cd /home/roshan/Downloads/Algotrading` | **stale** — blocked write |
| `AGENTS.md` | 48 | `cd /home/roshan/Downloads/Algotrading` | **stale** — blocked write |
| `EXECUTION_PLAN.md` | 15 | "Docs drift from reality … `/home/roshan` paths" | historical diagnosis, not an instruction; file is do-not-touch |

Zero hits in `README.md`, `SETUP_LOCAL.md`, `GOLDFISH-REVIEW-EXECUTION_PLAN.md`, `CONTRIBUTING.md`
and `docs/`.

Wider sweep (whole tree, excluding `attic/`, `Algo @ 2/`, `.venv/`, `TradingAgents/`, `.git/`) found
5 more, all outside Phase 4.1's ownership and therefore **not touched**:

| File | Hits | What it is |
|---|---:|---|
| `HEdge/README.md` | 1 | component readme with a `cd /home/roshan/...` example |
| `HEdge/docs/BOS_FRVP_LVN_VWAP_Strategy_Study.md` | 1 | source PDF path in a study note |
| `user_data/CONFIG_CONSOLIDATION_REPORT.md` | 2 | pre-remediation config report inside `user_data/` (explicitly do-not-touch) |
| `user_kb/01_my_rules.md` | 1 | NEXUS path (`/home/roshan/nexus/`) in a personal rules note |

`reports/phase4/docs/INVENTORY.md` and `AGENTS_MD_PROPOSED.md` mention the old path descriptively
(they quote what was wrong); those are evidence, not instructions, and are excluded from the count.

## 6. Inventory and attic record

- `reports/phase4/docs/INVENTORY.md` — 51 root files + 8 `plans/` files + 10 `.opencode/plans/`
  files, each with what it actually is, keep/attic verdict and reason; plus section D listing the
  markdown deliberately kept outside the root (`reports/**`, `docs/leverage-matrix.md`,
  `.githooks/README.md`, `.github/*.md`, component readmes) so the sweep cannot be mistaken for
  "everything must move".
- `attic/docs-history/MOVED.md` — 63 rows: file, reason, superseded-by; the gitignore mechanics
  (`attic/*` ignores everything, `!attic/docs-history/` + `!attic/docs-history/MOVED.md` keeps the
  index visible); a note that `git rm --cached` was not run under the no-git-write rule, so the next
  commit records 63 deletions + 1 added `MOVED.md`; and the list of files kept at the root with
  reasons.
- Layout: root files flat in `attic/docs-history/`; `plans/` preserved under `plans/`;
  `.opencode/plans/` under `opencode-plans/`.

`.gitignore` was edited (3 lines, mirroring the existing `attic/configs/` exemption) because
otherwise `MOVED.md` would itself be invisible to git and the move would leave no tracked record.
No other file outside the owned set was modified.

## 7. Docs I could not fix

| Doc | Problem | Why not fixed |
|---|---|---|
| `AGENTS.md` | Stale `/home/roshan` paths, 10 broken links, old counts, no Phase 2 status | Runtime blocks writes to agent-instruction files without user consent; replacement ready in `AGENTS_MD_PROPOSED.md` |
| `EXECUTION_PLAN.md` | Line 15 contains `/home/roshan` (historical root-cause entry) | Do-not-touch per Phase 4.1 |
| `docs/leverage-matrix.md` | Lists 8 strategies incl. `SupertrendEmaStrategy`, quarantined 2026-11-19; its `git rev-parse HEAD` line (`7977650…`) is older than HEAD | Outside the owned file set. `README.md` and `AGENTS_MD_PROPOSED.md` state the 8-vs-7 caveat instead |
| `Makefile` | Still advertises docker-compose targets (`run`, `full`, `dev`) and has **no `check` target**, although Phase 4.3 specifies `make check` | Outside the owned file set; `README.md` does not cite `make check` as available, and `AGENTS_MD_PROPOSED.md` warns agents not to use the Makefile |
| `.github/PULL_REQUEST_TEMPLATE.md` | Upstream template pointing at `CONTRIBUTING.md` | Left intact; handled by restoring `CONTRIBUTING.md` instead of editing the template |
| `SETUP_LOCAL.md` | Says `list-strategies` shows "28 strategies" (line 18) — now 7 loadable, 19 quarantined | Do-not-touch per Phase 4.1. Flagged here and in `README.md` (which gives the measured count) |

## 8. Verification commands run

```bash
.venv/Scripts/python.exe -m freqtrade list-strategies --userdir user_data   # 7 rows, all OK
.venv/Scripts/python.exe scripts/validate_configs.py                        # PASS, 43 checks
.venv/Scripts/python.exe scripts/secrets_scan.py --all                      # exit 0
.venv/Scripts/python.exe scripts/supervise.py --preflight                   # UNKNOWN -> exit 1 (expected)
# link resolution over every relative markdown link in the docs of record   # see §4
# stale-path grep over docs of record and whole tree                        # see §5
```

The README's scoreboard smoke command was executed twice to prove the documented path works:
`--stage validation --limit 2 --strategies EmaTrendFollowing` into two separate output dirs.
Both runs produced `manifest_hash: sha256:5526ca6e…`; `--verify` reported **PASS**
(`manifest_hash: MATCH`, `results: MATCH at 4 dp (54 scalar fields)`). The output dirs were written
to the scratch area, not into `reports/`, so the repo gains no throwaway evidence.

No backtest other than that documented smoke, no dry-run, and no trading process was started at any
point in this phase.
