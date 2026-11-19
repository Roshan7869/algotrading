# Phase 4.1 — documentation inventory

Repo: `D:\dev\algotrading`. Enumerated on disk on 2026-11-19 (no inherited counts).
Scope: every `*.md` in the repo root, `plans/`, and the plan/report dirs found during the sweep. 
`reports/` and `docs/` were reviewed as report dirs and kept (see section D).

**Totals:** 51 root `*.md` -> 6 kept, 45 atticked. 8 `plans/*.md` -> 0 kept, 8 atticked. 
10 `.opencode/plans/*.md` -> 0 kept, 10 atticked. **63 files moved** to `attic/docs-history/`.

Rule applied: a file survives only if it is README/AGENTS, the governing plan + its review, the setup doc, 
or is referenced by `scripts/` or a config. Everything describing the pre-remediation system is history.

## A. Repo root (51 files)

| file | what it actually is | keep or attic | reason |
|---|---|---|---|
| `README.md` | Project front page (currently upstream freqtrade boilerplate: badges, exchange matrix, Telegram/Docker install) | KEEP — rewritten | Replaced with project-specific README: identity, honest status, tool quickstart, repo map, reproducibility contract |
| `AGENTS.md` | Agent-facing doc index + ChromaDB query instructions; all paths point at /home/roshan/Downloads/Algotrading and counts are pre-remediation (443 chunks, 10 docs) | KEEP — rewritten | Kept as the agent entry point; paths/counts/commands corrected to this machine and this repo state |
| `EXECUTION_PLAN.md` | Governing remediation plan v0.2 (root causes R1-R6, phases 0-4, anti-goals, outcome log incl. Phase 2 FAIL) | KEEP | The plan of record; out of scope for edits per Phase 4.1 |
| `GOLDFISH-REVIEW-EXECUTION_PLAN.md` | Adversarial review of plan v0.1 (30 findings, verdict REJECT) that produced v0.2 | KEEP | Referenced from EXECUTION_PLAN.md line 3; the audit trail for why v0.2 exists |
| `SETUP_LOCAL.md` | Verified Windows setup: .venv, deps, data inventory, do-not-run list, research harness | KEEP | Current, machine-specific, and the only accurate setup doc; out of scope for edits |
| `ALGOTRADING_AUDIT_REPORT.md` | 2026-05-19 layer-by-layer audit of the pre-remediation system (49+ configs, 3.0x hardcoded default, shared_config signal files) | ATTIC | Describes the retired architecture; counts and paths no longer exist. Superseded by reports/phase0 + reports/phase1 + EXECUTION_PLAN.md |
| `ALGOTRADING_STATE_ANALYSIS.md` | 2026-05-07 state analysis with letter grades (security F, production readiness D), 94 tests, 9 configs | ATTIC | Pre-remediation snapshot; grades and counts are stale and contradict measured state |
| `ALPHA_ARENA_RESEARCH.md` | 2026-05-16 research note on Nof1 Alpha Arena (6 LLMs, $10k each) used to justify the GODMODE plan | ATTIC | Research input to a retired plan; no code or measurement in this repo depends on it |
| `ARCHITECTURAL_AUDIT.md` | 2026-05-22 full architecture audit written against /home/roshan/Downloads/Algotrading | ATTIC | Wrong absolute paths and describes archived modules (MiroShark, swarm, 5+ signal generators) |
| `ARCHITECTURE_DAG.md` | 9-layer DAG (swarm, agents, signal bus, Redis/Postgres infra) of the pre-remediation stack | ATTIC | Most layers are archived or have no consumer; the current architecture is freqtrade + scripts/ + research/ |
| `AUDIT_REPORT_2026-05-19.md` | 8-layer audit claiming 13 live agents / 19 models / HMM regime detection | ATTIC | Claims are not reproducible in the current tree (agents archived, swarm canned) |
| `AUDIT_REPORT_300_AGENT.md` | 2026-05-18 '300-agent' scan over 82 strategy files, 80 configs, 6 sub-projects | ATTIC | Scanned a tree that no longer exists; numbers were never re-derived |
| `BLOOMBERG_TERMINAL_RESEARCH.md` | 2026-05-18 compendium of OpenBB et al. for a terminal stack that was never built | ATTIC | Speculative research with no implementation and no consumer |
| `CLAUDE.md` | Ruflo Claude Code configuration boilerplate (send-message coordination, /src /tests layout rules) from another project | ATTIC | Not this repo's agent guide; the file layout it mandates does not exist here. AGENTS.md is the agent entry point |
| `CONTRIBUTING.md` | Upstream freqtrade contribution guide (PR against freqtrade develop, upstream CI) | KEEP | Not history, and a tracked file links to it (`.github/PULL_REQUEST_TEMPLATE.md`); moving it would create a dangling link. Upstream boilerplate retained per GPL-fork convention |
| `CROSS_PROJECT_INTELLIGENCE.md` | 2026-05-15 analysis of 6 external repos (Kronos, QuantDinger, AI-Trader, neural-trader, MoondevRED, strategy DB) | ATTIC | Reference material for a retired roadmap; cloned sources are gone |
| `DEPLOYMENT_CHECKLIST.md` | 2026-02-02 live-trading checklist asserting 'READY FOR PAPER TRADING' for AroonMomentumEngine_Shorts_v2_Optimized.py | ATTIC | Actively misleading: the strategy file does not exist, no paper record exists, and live trading is prohibited. Highest-risk stale doc |
| `FINCEPT_INTEGRATION_DAG.md` | 2026-05-22 proposal mapping FinceptTerminal components (options pricing, etc.) into this repo | ATTIC | Never implemented; Phase 3 is gated and requires a named consumer first |
| `GODMODE_300D_MASTER_REPORT.md` | 300-day backtest report claiming P3F +129.7% and a +3.6M% compounding artifact | ATTIC | Results belong to quarantined/deleted strategies and the unlimited-stake artifact; contradicts the measured no-edge result |
| `GODMODE_30D_RESULTS.md` | 30-day ranking table topped by P3E_HYPEROPT +179% (unlimited stake) | ATTIC | Same artifact class; 17-pair/3x setup retired |
| `GODMODE_6PHASE_EXECUTION_MAP.md` | tmux dispatch board for 6 parallel OpenCode sessions (ATR sizing, HMM, etc.) | ATTIC | Session log for work that was abandoned; no surviving consumer |
| `GODMODE_ARCHITECTURE_STATE.md` | 591-line 'complete system audit' anchored on the +129.7% P3F champion | ATTIC | Premise (P3F edge) is false under the 10bps cost model |
| `GODMODE_BACKTEST_ANALYSIS.md` | VectorStrategy Phase 2 report ('OpenCode changes WRECKED performance') | ATTIC | Narrative backtest log for retired strategy files |
| `GODMODE_CHROMADB_GAP_ANALYSIS.md` | Maps 592 ChromaDB chunks onto VectorStrategy_P3E_KEY_LEVEL_BOOST | ATTIC | Strategy file is quarantined; KB coverage was never the binding constraint |
| `GODMODE_HONEST_TRUTH.md` | '592 vectors vs reality' table claiming 2 production-ready strategies out of 20 | ATTIC | Its 'production-ready' claim (P3E/P3F) is exactly what the lookahead audit and cost model invalidated |
| `GODMODE_P3_CHROMADB_INSIGHTS.md` | 2026-05-16 market-regime snapshot (trending_down 97.17%) and regime win-rate table | ATTIC | Point-in-time snapshot of a retired pipeline; not reproducible |
| `GODMODE_P3_FINAL_REPORT.md` | Phase 3+ 'final verified' report for the ChromaDB -> backtest -> hyperopt pipeline | ATTIC | 'Verified' is unsupported under the current reproducibility contract (no manifest, no cost model) |
| `GODMODE_P3_REPORT.md` | Phase 3 variant-testing report (P3A-D) against the P2 champion | ATTIC | Retired strategy family; superseded by reports/phase2/2.1 |
| `GODMODE_P3_VERIFIED_REPORT.md` | Phase 3+ re-validation of P2* baseline | ATTIC | Same retired family; verification standard predates the manifest/holdout contract |
| `GODMODE_RESEARCH_PLAN.md` | 'Alpha Arena to prop firm' research plan (multi-alpha, regime-adaptive) | ATTIC | Aspirational plan with no implemented consumer; Phase 3+ is gated |
| `INTEGRATION_PLAN.md` | Plan to unify '20,484 Python files / 127 strategies / 124 scripts' into a dashboard | ATTIC | Describes mass that Phase 1 deleted; the plan's premise is gone |
| `INTEGRATION_SURFACE.md` | 690-line map of plugin points for bolting new components onto freqtrade | ATTIC | Written for the Fincept integration that was never built; freqtrade's own interface docs cover the surviving surface |
| `MASTER_BACKTEST_REPORT_2018_2026.md` | 8-year backtest table topped by VectorStrategy_P3E_HYPEROPT +2,425% | ATTIC | Artifact of unlimited-stake compounding on a quarantined strategy |
| `MIROSHARK_REMEDIATION_PLAN.md` | 1,070-line plan to rebuild a 5-layer MiroShark prediction engine | ATTIC | Swarm is canned and the plan's layers were archived in Phase 1 |
| `MoondevRED_Engine_DeepDive.md` | Audit of the vendored MoondevRED engine under 'Algo @ 2/' | ATTIC | The audited subtree is in attic/ (356 MB duplicate); paths are /home/roshan |
| `NEXUS_MULTIDIMENSIONAL_AUDIT_2026-05-22.md` | NEXUS audit scoring the system 47/100 across 4 dimensions | ATTIC | Score and findings target the pre-remediation tree; its remediation plan is also retired |
| `OPTIMIZATION_MASTERPLAN.md` | 2026-05-15 first-principles masterplan (-80.4% DD diagnosis, external research synthesis) | ATTIC | Diagnosis was correct but the action plan was replaced by EXECUTION_PLAN.md v0.2 |
| `OPTIMIZATION_ROADMAP.md` | 2026-05-15 5-phase roadmap; listed as 'Primary' in the old AGENTS.md index | ATTIC | Superseded by EXECUTION_PLAN.md; keeping it invites agents to follow a dead plan |
| `QUICK_START.md` | 'Post-fix' quick start about a Telegram bot conflict, Docker containers and 16 patched configs | ATTIC | Operational advice for a stack that no longer runs here; superseded by SETUP_LOCAL.md |
| `RAG_AUDIT_REPORT.md` | Audit of the 6-phase RAG optimisation plan (plans/rag_optimisation/) | ATTIC | The plan and its 6 phase docs are retired with it; no consumer in the current tree |
| `REALTIME_INTELLIGENCE_ARCHITECTURE.md` | Design doc for regime-adaptive ChromaDB retrieval feeding trade outcomes back | ATTIC | Design only; the regime/outcome loop was never wired and is not part of the current gate |
| `REMEDIATION_PLAN.md` | 2026-05-22 typed plan to fix 13 NEXUS audit issues (score 47 -> 75+) | ATTIC | Superseded by EXECUTION_PLAN.md v0.2 (different root causes, measured evidence) |
| `STATE_ANALYSIS_AUDIT.md` | 2026-05-19 complete state analysis (branch develop-local, 48 modified files, 1971 NEXUS resources) | ATTIC | Pre-remediation working-tree snapshot; every count has changed |
| `STRATEGIC_PIPELINE_SUMMARY.md` | 2026-05-07 summary of a config de-duplication pass (15 configs, 7 redundant) | ATTIC | Superseded by Phase 1.2 config consolidation (3 canonical configs, attic/configs/MOVED.md) |
| `TYPED_EXECUTION_PLAN.md` | 2026-05-15 8-phase typed DAG plan (-80% to profitability, 6 weeks, 7 checkpoints) | ATTIC | Named in Phase 4.1 as a retired plan; its gates were never executed and EXECUTION_PLAN.md replaced it |
| `TYPED_EXECUTION_PLAN_v2.md` | 2026-05-15 v2 plan: turn ChromaDB into a live adaptive intelligence layer | ATTIC | Same retired plan family; baseline claim (+53.47%) has no manifest |
| `Trading_RESEARCH_PREVIEW_SYSTEM.md` | TRAP system design (preview/estimate/backtest_query/walk_forward/dashboard) | ATTIC | Design doc for unbuilt tooling; the measurement tools that do exist are scripts/scoreboard.py and research/walkforward.py |
| `VERIFICATION_REPORT.md` | 2026-05-07 'ALL PHASES COMPLETE' verification of Docker/MiroFish work | ATTIC | False in the current tree (no MiroFish, no unified compose); misleading completion claim |
| `WSL_README.md` | WSL2 + Docker Desktop run instructions | ATTIC | Superseded by native-Windows SETUP_LOCAL.md; the Docker path is no longer used |
| `nexus_routing_research.md` | 2026-05-15 NEXUS routing research (AnyTool/ScaleMCP/ToolkenGPT comparison, 1686 resources) | ATTIC | Research note about a different system (NEXUS), not this repo's measurement path |
| `trade_analysis_report.md` | 35-trade performance table for AroonMomentumEngine_Hybrid (65.7% WR, +144.16 USDT) | ATTIC | Output artifact of analyze_trades.py, generated pre-remediation; not a validated result (no manifest, no cost model) |

## B. `plans/` (8 files)

`plans/` contains no governing plan — the plan of record is `EXECUTION_PLAN.md` at the root. 
These are the FlowSurface and RAG-optimisation plans, both retired.

| file | what it actually is | keep or attic | reason |
|---|---|---|---|
| `plans/flowsurface_integration_graphify.md` | Graphify-style integration plan for the Rust/Tauri FlowSurface charting app | ATTIC | Phase 3.3 defers FlowSurface until a charting need is proven; no Rust toolchain installed |
| `plans/rag_optimisation/README.md` | Index for the 6-phase RAG optimisation plan | ATTIC | Plan retired with RAG_AUDIT_REPORT.md; no consumer |
| `plans/rag_optimisation/01_hybrid_search.md` | Phase 1: BM25 + vector hybrid search | ATTIC | Depends on rank_bm25, which is not installed; plan abandoned |
| `plans/rag_optimisation/02_cross_encoder_rerank.md` | Phase 2: cross-encoder reranking | ATTIC | Requires a model download that never happened |
| `plans/rag_optimisation/03_multi_layer_cache.md` | Phase 3: multi-layer retrieval cache | ATTIC | No consumer; retrieval stack not on the measurement path |
| `plans/rag_optimisation/04_embedding_finetuning.md` | Phase 4: embedding fine-tuning | ATTIC | No dataset, no consumer |
| `plans/rag_optimisation/05_monitoring_eval.md` | Phase 5: retrieval monitoring/eval | ATTIC | No consumer |
| `plans/rag_optimisation/06_production_serving.md` | Phase 6: production serving of the retrieval stack | ATTIC | No serving path exists in this repo |

## C. `.opencode/plans/` (10 files, found during the sweep)

Not in the original Phase 4.1 text, but this is the repo's only other plan directory and every file in it 
describes pre-remediation work. Retired with the rest; flagged in `POLISH_REPORT.md`.

| file | what it actually is | keep or attic | reason |
|---|---|---|---|
| `.opencode/plans/ALGOTRADING_FULL_GRAPH_PLAN.md` | Full-repo graphify plan (typed DAG of every module) | ATTIC | Graphify tooling was never adopted; plan predates remediation |
| `.opencode/plans/GRAPHIFY_EXECUTION_PLAN.md` | 4-layer typed-DAG execution format for graphify work | ATTIC | Format doc for the abandoned graphify system |
| `.opencode/plans/INTEGRATION_PIPELINE_PLAN.md` | Integration pipeline plan (agents/signals/UI) | ATTIC | Targets archived modules |
| `.opencode/plans/NEXUS_MCP_EXECUTION_PLAN.md` | Plan to wire NEXUS MCP tools into this repo | ATTIC | Not implemented; NEXUS is a separate system |
| `.opencode/plans/UNIFIED_ARCHITECTURE_PLAN.md` | Unified architecture plan for the 9-layer stack | ATTIC | Premise (9-layer stack) retired in Phase 1 |
| `.opencode/plans/dual_engine_rust_python.md` | Rust+Python dual-engine proposal | ATTIC | No Rust toolchain, no implementation |
| `.opencode/plans/indicator-classification.md` | Taxonomy of indicators for an overlay system | ATTIC | Spec for unbuilt UI work |
| `.opencode/plans/indicator-overlay-system.md` | Indicator overlay system spec | ATTIC | Spec for unbuilt UI work; UI pages were broken and are not on the path |
| `.opencode/plans/pro-level-indicators.md` | 'Pro-level indicators' feature plan | ATTIC | Spec for unbuilt UI work |
| `.opencode/plans/TEMPLATE.md` | Template for the graphify typed-DAG plan format | ATTIC | Template for the retired graphify plan system |
## D. Other markdown reviewed and kept (not moved)

| path | why it stays |
|---|---|
| `reports/decisions/no-edge-memo-20261119.md` | Phase 2 gate decision of record (FAIL). README and AGENTS.md cite it. |
| `reports/phase0/PHASE0_REPORT.md` | Current remediation evidence (safety baseline). |
| `reports/phase1/**/*.md` | Current evidence: config consolidation, data refresh + gap scan, scoreboard report. |
| `reports/phase2/**/*.md` | Current evidence: lookahead audit, stop fixes, walkforward reports. |
| `reports/scoreboard-*/SCOREBOARD.md` | Generated measurement output; the sealed-holdout records. `scoreboard-20261119-1229/` is the canonical run. |
| `reports/walkforward-*/WALKFORWARD.md` | Generated walkforward output incl. the loud FAIL. |
| `docs/leverage-matrix.md` | The one documented leverage table (Phase 1.2 deliverable), referenced by `scripts/scoreboard.py`. |
| `.githooks/README.md` | Install/verify instructions for the Phase 0.4 secret gate. |
| `.github/*.md` | Issue/PR templates for the upstream fork; harmless, no stale claims. |
| `flowsurface_src/README.md`, `ft_client/README.md` | Component readmes for vendored code; not project docs. |
| `attic/README.md` | Attic rules; explicitly out of scope for edits. |

## E. Verification

- Move set checked against `git ls-files "*.md"` (root) on 2026-11-19: 51 tracked root files, all accounted for above.
- No moved file is referenced by `scripts/`, `Makefile`, `user_data/config_*.json`, or `.githooks/` (grep before moving).
  `CONTRIBUTING.md` was initially moved and then restored: `.github/PULL_REQUEST_TEMPLATE.md` links to it, and Phase 4.1
  may not edit that template.
  `trade_analysis_report.md` is written by `analyze_trades.py` (an output path, not an input) and is regenerated on demand.
- `README.md`, `AGENTS.md`, `EXECUTION_PLAN.md`, `GOLDFISH-REVIEW-EXECUTION_PLAN.md`, `SETUP_LOCAL.md` remain at the root.

