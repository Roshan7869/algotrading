# MOVED — docs history (Phase 4.1)


On 2026-11-19 the root-level audits, state analyses, old plans and stale operational guides were
moved here. They describe the **pre-remediation** system. They are kept for the audit trail, not as
evidence: nothing below satisfies the reproducibility contract (git SHA + data manifest + config path
+ cost model), and several contain numbers that the lookahead audit and the 10 bps cost model
invalidated.

**Gitignore note.** `attic/` is gitignored per `attic/README.md` (`attic/*` in `.gitignore`, with
`README.md` and the `*.md` index files exempted). To keep this file visible, `.gitignore` now carries
the same three-line exemption used for `attic/configs/`:

```
!attic/docs-history/
attic/docs-history/*
!attic/docs-history/MOVED.md
```

The moved files themselves stay ignored, i.e. they leave the tracked tree on the next commit. Because
Phase 4.1 ran under a **no-git-write** rule, `git rm --cached` was **not** executed here: git will see
63 deletions and one added `MOVED.md` at commit time. The blobs remain in history until the scheduled
P1.5 object purge (backup bundle first) — same status as the rest of `attic/`.

**Layout:** root files are flat in this directory; `plans/` keeps its tree under `plans/`;
`.opencode/plans/` files are under `opencode-plans/`.

## What was moved (63 files)

| file | reason | superseded by |
|---|---|---|
| `ALGOTRADING_AUDIT_REPORT.md` | Pre-remediation 8-layer audit (2026-05-19); describes 49+ configs and the retired signal-bus stack. | EXECUTION_PLAN.md §1 (R1-R6) + reports/phase0/PHASE0_REPORT.md |
| `ALGOTRADING_STATE_ANALYSIS.md` | Pre-remediation state/grades snapshot (2026-05-07). | reports/phase1/ + reports/phase2/ (measured evidence) |
| `ALPHA_ARENA_RESEARCH.md` | Research note backing the retired GODMODE plan. | reports/decisions/no-edge-memo-20261119.md (Alpha Arena premise did not survive costs) |
| `ARCHITECTURAL_AUDIT.md` | Audit written against `/home/roshan/Downloads/Algotrading`; modules since archived. | README.md repo map + reports/phase2/2.1/LOOKAHEAD_AUDIT.md |
| `ARCHITECTURE_DAG.md` | 9-layer DAG (swarm/agents/Redis) of the retired stack. | README.md repo map |
| `AUDIT_REPORT_2026-05-19.md` | Audit claiming 13 live agents / 19 models; not reproducible in this tree. | reports/phase0/ + reports/phase1/ |
| `AUDIT_REPORT_300_AGENT.md` | Scan of 82 strategy files / 80 configs that no longer exist. | reports/phase1/ + reports/phase2/ |
| `BLOOMBERG_TERMINAL_RESEARCH.md` | Speculative terminal-stack research; never implemented. | none (never implemented) |
| `CLAUDE.md` | Ruflo boilerplate from another project, not this repo's agent guide. | AGENTS.md |
| `CROSS_PROJECT_INTELLIGENCE.md` | Analysis of 6 external repos for a retired roadmap. | EXECUTION_PLAN.md §2 (principles) |
| `DEPLOYMENT_CHECKLIST.md` | Live-trading checklist claiming 'READY FOR PAPER TRADING' for a deleted strategy — actively misleading. | README.md 'Guardrails' + scripts/validate_configs.py |
| `FINCEPT_INTEGRATION_DAG.md` | Integration proposal (2026-05-22) never implemented; Phase 3 is gated. | EXECUTION_PLAN.md §3 Phase 3 (gated) |
| `GODMODE_300D_MASTER_REPORT.md` | Backtest report anchored on quarantined strategies; contains the +3.6M% artifact. | reports/scoreboard-20261119-1229/SCOREBOARD.md |
| `GODMODE_30D_RESULTS.md` | 30-day rankings topped by the unlimited-stake P3E artifact. | reports/scoreboard-20261119-1229/SCOREBOARD.md |
| `GODMODE_6PHASE_EXECUTION_MAP.md` | tmux dispatch board for abandoned parallel sessions. | none (abandoned dispatch log) |
| `GODMODE_ARCHITECTURE_STATE.md` | 'Complete audit' premised on the +129.7% P3F edge, which the cost model invalidated. | reports/phase2/2.1/ + README.md repo map |
| `GODMODE_BACKTEST_ANALYSIS.md` | Narrative backtest log for retired strategy files. | reports/phase2/2.1/PHASE2_1_REPORT.md |
| `GODMODE_CHROMADB_GAP_ANALYSIS.md` | Maps KB chunks onto the quarantined P3E strategy. | reports/phase2/2.1/LOOKAHEAD_AUDIT.md |
| `GODMODE_HONEST_TRUTH.md` | Asserts P3E/P3F are 'production-ready' — exactly what the lookahead audit invalidated. | reports/decisions/no-edge-memo-20261119.md |
| `GODMODE_P3_CHROMADB_INSIGHTS.md` | Point-in-time regime snapshot from a retired pipeline. | reports/scoreboard-20261119-1229/ (reproducible stage metrics) |
| `GODMODE_P3_FINAL_REPORT.md` | 'Final verified' report without manifest, cost model or holdout. | reports/scoreboard-20261119-1229/ + reports/walkforward-20261119-1311/ |
| `GODMODE_P3_REPORT.md` | Variant-test report for the retired P3 family. | reports/phase2/2.1/PHASE2_1_REPORT.md |
| `GODMODE_P3_VERIFIED_REPORT.md` | Re-validation predating the reproducibility contract. | reports/scoreboard-20261119-1229/ |
| `GODMODE_RESEARCH_PLAN.md` | Aspirational 'prop firm' plan; no consumer, Phase 3 gated. | EXECUTION_PLAN.md §3 Phase 3 (gated; no signal work before gate) |
| `INTEGRATION_PLAN.md` | Premised on 20,484 files / 127 strategies that Phase 1 deleted. | EXECUTION_PLAN.md §3 Phase 3.2 (module-consumer map) |
| `INTEGRATION_SURFACE.md` | 690-line plugin map for the never-built Fincept integration. | freqtrade upstream docs + EXECUTION_PLAN.md §3 Phase 3.2 |
| `MASTER_BACKTEST_REPORT_2018_2026.md` | 8-year table topped by the +2,425% unlimited-stake artifact. | reports/scoreboard-20261119-1229/SCOREBOARD.md |
| `MIROSHARK_REMEDIATION_PLAN.md` | 1,070-line plan for a canned swarm; layers archived in Phase 1. | EXECUTION_PLAN.md §3 Phase 3.2 (consumer-gated) |
| `MoondevRED_Engine_DeepDive.md` | Audit of the duplicate subtree now in `attic/Algo @ 2/`. | none (subtree itself is in attic/Algo @ 2/) |
| `NEXUS_MULTIDIMENSIONAL_AUDIT_2026-05-22.md` | 47/100 audit of the pre-remediation tree. | EXECUTION_PLAN.md §1 (root causes re-derived from measurement) |
| `OPTIMIZATION_MASTERPLAN.md` | 2026-05-15 masterplan replaced by EXECUTION_PLAN.md v0.2. | EXECUTION_PLAN.md |
| `OPTIMIZATION_ROADMAP.md` | 2026-05-15 roadmap, listed as 'Primary' in the old AGENTS.md; dead plan. | EXECUTION_PLAN.md |
| `QUICK_START.md` | Telegram/Docker quick start for a stack that no longer runs here. | SETUP_LOCAL.md + README.md 'Quickstart' |
| `RAG_AUDIT_REPORT.md` | Audit of the retired RAG plan (`plans/rag_optimisation/`). | none (RAG plan retired with plans/rag_optimisation/) |
| `REALTIME_INTELLIGENCE_ARCHITECTURE.md` | Design-only regime/outcome loop; never wired. | EXECUTION_PLAN.md §3 Phase 3 (gated) |
| `REMEDIATION_PLAN.md` | 2026-05-22 plan superseded by EXECUTION_PLAN.md v0.2. | EXECUTION_PLAN.md |
| `STATE_ANALYSIS_AUDIT.md` | Pre-remediation working-tree snapshot; every count has changed. | reports/phase1/ + reports/phase2/ |
| `STRATEGIC_PIPELINE_SUMMARY.md` | Config de-dup summary (2026-05-07) superseded by Phase 1.2. | attic/configs/MOVED.md + reports/phase1/configs/ |
| `TYPED_EXECUTION_PLAN.md` | 2026-05-15 8-phase plan; named in Phase 4.1 as retired. | EXECUTION_PLAN.md |
| `TYPED_EXECUTION_PLAN_v2.md` | 2026-05-15 v2 plan; baseline claim has no manifest. | EXECUTION_PLAN.md |
| `Trading_RESEARCH_PREVIEW_SYSTEM.md` | TRAP design for unbuilt tooling. | scripts/scoreboard.py + research/walkforward.py |
| `VERIFICATION_REPORT.md` | 'ALL PHASES COMPLETE' claim that is false in this tree. | reports/phase0/PHASE0_REPORT.md |
| `WSL_README.md` | WSL/Docker instructions superseded by native-Windows SETUP_LOCAL.md. | SETUP_LOCAL.md (native Windows) |
| `nexus_routing_research.md` | Research about NEXUS routing, not this repo's measurement path. | none (NEXUS is a separate system) |
| `trade_analysis_report.md` | Generated 35-trade artifact (analyze_trades.py output), pre-remediation. | reports/scoreboard-20261119-1229/ (regenerate with analyze_trades.py if needed) |
| `plans/flowsurface_integration_graphify.md` | Retired plan doc: flowsurface_integration_graphify.md | EXECUTION_PLAN.md §3 Phase 3.3 (archived until a charting need is proven) |
| `plans/rag_optimisation/01_hybrid_search.md` | Retired plan doc: 01_hybrid_search.md | none (plan retired) |
| `plans/rag_optimisation/02_cross_encoder_rerank.md` | Retired plan doc: 02_cross_encoder_rerank.md | none (plan retired) |
| `plans/rag_optimisation/03_multi_layer_cache.md` | Retired plan doc: 03_multi_layer_cache.md | none (plan retired) |
| `plans/rag_optimisation/04_embedding_finetuning.md` | Retired plan doc: 04_embedding_finetuning.md | none (plan retired) |
| `plans/rag_optimisation/05_monitoring_eval.md` | Retired plan doc: 05_monitoring_eval.md | none (plan retired) |
| `plans/rag_optimisation/06_production_serving.md` | Retired plan doc: 06_production_serving.md | none (plan retired) |
| `plans/rag_optimisation/README.md` | Retired plan doc: README.md | none (plan retired) |
| `.opencode/plans/ALGOTRADING_FULL_GRAPH_PLAN.md` | Graphify plan for the whole repo; tooling never adopted. | EXECUTION_PLAN.md |
| `.opencode/plans/GRAPHIFY_EXECUTION_PLAN.md` | Format doc for the abandoned graphify system. | EXECUTION_PLAN.md |
| `.opencode/plans/INTEGRATION_PIPELINE_PLAN.md` | Integration plan targeting archived modules. | EXECUTION_PLAN.md §3 Phase 3.2 |
| `.opencode/plans/NEXUS_MCP_EXECUTION_PLAN.md` | Plan to wire NEXUS MCP into this repo; not implemented. | none (NEXUS is a separate system) |
| `.opencode/plans/TEMPLATE.md` | Template for the retired graphify plan format. | none (graphify plan format retired) |
| `.opencode/plans/UNIFIED_ARCHITECTURE_PLAN.md` | Unified 9-layer architecture plan; premise retired. | README.md repo map |
| `.opencode/plans/dual_engine_rust_python.md` | Rust+Python dual-engine proposal; no toolchain, no code. | none (no Rust toolchain) |
| `.opencode/plans/indicator-classification.md` | Indicator taxonomy for an unbuilt overlay UI. | none (UI work never built) |
| `.opencode/plans/indicator-overlay-system.md` | Overlay system spec for unbuilt UI work. | none (UI work never built) |
| `.opencode/plans/pro-level-indicators.md` | 'Pro-level indicators' spec for unbuilt UI work. | none (UI work never built) |

**Count:** 63 files moved (45 root, 8 `plans/`, 10 `.opencode/plans/`).

## What was kept at the root, and why

| file | why it stays |
|---|---|
| `README.md` | Rewritten this phase: identity, honest status, tool quickstart, repo map, reproducibility contract. |
| `AGENTS.md` | Agent entry point. **Still stale** — the runtime blocks writes to agent-instruction files without user consent, so its `/home/roshan/...` paths and 58/36/28 counts remain until the user approves the rewrite (proposed text: `reports/phase4/docs/AGENTS_MD_PROPOSED.md`). |
| `EXECUTION_PLAN.md` | Governing plan; out of scope for edits per Phase 4.1. |
| `GOLDFISH-REVIEW-EXECUTION_PLAN.md` | Review that produced v0.2; referenced by the plan. |
| `SETUP_LOCAL.md` | Only accurate machine-setup doc; out of scope for edits per Phase 4.1. |
| `CONTRIBUTING.md` | Upstream freqtrade guide, not history. Kept because `.github/PULL_REQUEST_TEMPLATE.md` links to it and Phase 4.1 may not edit that template. |

Also kept outside the root, for the same reason: `reports/**/*.md` (current evidence),
`docs/leverage-matrix.md` (referenced by `scripts/scoreboard.py`), `.githooks/README.md` (hook
install instructions), `.github/*.md` (templates), `flowsurface_src/README.md`, `ft_client/README.md`
(component readmes).

## What did NOT move, although it looks like history

- `attic/README.md` and `attic/configs/` — attic rules and the Phase 1.2 config inventory; out of scope.
- `reports/phase0`, `reports/phase1`, `reports/phase2`, `reports/decisions` — these are the *current*
  remediation evidence, not the pre-remediation past.
- `reports/scoreboard-*`, `reports/walkforward-*` — generated measurement records, including the
  canonical scoreboard run and the sealed holdout.

