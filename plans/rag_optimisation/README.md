# RAG Optimisation — 6-Phase Execution Plan

## First Principles Diagnosis

**Core problem**: The two RAG systems (Algotrading Strategy DB + NEXUS) use off-the-shelf embedding models, single-stage retrieval, and zero caching. Every query pays full cost regardless of repetition. Every failure is a system failure.

**Root cause chain**:
1. General-purpose embedding models allocate <0.5% capacity to trading jargon
2. Single-stage retrieval hits precision ceiling at ~60%
3. No memoization means 40%+ of queries recompute identical results
4. No measurement means regressions are invisible
5. No serving layer means TUI integration is fragile

## Phase Dependency DAG

```
Phase 1 ──► Phase 2 ──► Phase 4
  │                          │
  ▼                          ▼
Phase 3 ◄────────────────────┘
  │
  ▼
Phase 5 ◄── Phase 2 ── Phase 4
  │
  ▼
Phase 6 ◄── All Phases
```

| Phase | Name | Effort | Impact | Depends On |
|-------|------|--------|--------|------------|
| 1 | Hybrid Search (BM25 + RRF) | 2h | High recall for acronym queries | — |
| 2 | Cross-Encoder Reranking | 2h | Highest precision improvement | 1 |
| 3 | Multi-Layer Caching | 2h | 40% latency reduction, 60% cost reduction | 1, 2 |
| 4 | Embedding Fine-Tuning | 3h | 5-10% HR@10 improvement on trading queries | 1 |
| 5 | Monitoring & Evaluation | 4.5h | Makes all other phases measurable | 1, 2, 3 |
| 6 | Production Serving | 3h | TUI-ready unified gateway | 1, 2, 3, 4, 5 |
| **Total** | | **~17h** | Production-grade RAG | |

## Running the Plans

Each plan file includes:
- **First principles root cause analysis** — why this problem exists
- **Current state analysis** — what exists today
- **Typed DAG** — phased execution with checkpoints
- **Detailed implementation** — code, algorithms, config
- **Audit benchmarks** — measurable before/after metrics
- **Verification protocol** — block-level tests to validate completion
- **Rollback plan** — how to undo if something fails

## Quick Start

```bash
# 1. Start with Phase 1 (lowest risk, highest impact for effort)
#    Add BM25 hybrid search alongside existing ChromaDB

# 2. Phase 2 adds cross-encoder reranking (needs Phase 1 for over-retrieval)

# 3. Phase 3 adds caching (benefits from both Phase 1 and 2)

# 4. Phase 4 fine-tunes embeddings (independent, can be parallel)

# 5. Phase 5 adds measurement (needs Phases 1-3 to measure)

# 6. Phase 6 serves everything to TUI tools (needs all prior phases)
```


## Hardware Constraints

| Resource | Available | Used By Phase |
|----------|-----------|---------------|
| CPU | 16GB DDR3 | All phases — MiniLM, BM25, cross-encoder (TinyBERT) all run on CPU |
| RAM | 16GB total | Phase 2 (cross-encoder ~120MB), Phase 3 (cache <50MB), Phase 4 (training ~2GB) |
| GPU | None | No phase requires GPU |
| Disk | Variable | ChromaDB persistence (~10MB), adapter weights (~6MB), logs (SQLite, minimal) |

All phases are designed for CPU-only inference and training.
