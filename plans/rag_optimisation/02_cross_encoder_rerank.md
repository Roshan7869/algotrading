# Phase 2: Cross-Encoder Reranking

## First Principles Root Cause Analysis

### Core Question
*Why does first-stage retrieval alone produce irrelevant results even with hybrid search?*

### Decomposition to First Principles

**Principle 1: Bi-encoder vs cross-encoder asymmetry**
- **Bi-encoders** (all-MiniLM-L6-v2) encode query and document *independently* into fixed vectors, then compare with cosine similarity
- This means: `similarity(q, d) = cos(encode(q), encode(d))` — the query and document never "see" each other
- **Cross-encoders** process query and document *jointly*: `score(q, d) = cross_encoder(q + [SEP] + d)` — the model can attend to interactions between query tokens and document tokens
- **Root cause**: Independent encoding cannot model token-level interactions like "not" negation, temporal ordering ("before X vs after X"), or conditional relationships ("if A then B")

**Principle 2: The precision ceiling of embedding similarity**
- For a fixed embedding model and corpus, there exists a maximum achievable precision@k
- This ceiling is determined by the model's ability to distinguish fine-grained relevance differences
- MiniLM (384-dim) has a lower precision ceiling than larger models (768-dim, 1024-dim)
- Once you hit this ceiling, the only way to improve is a second stage that uses a fundamentally different (more expensive) scoring mechanism
- **Root cause**: Single-stage retrieval hits the precision ceiling of the embedding model; further improvements require cross-encoder scoring

**Principle 3: Re-ranking is a two-stage retrieval system**
- Stage 1 (hybrid search): Cast wide net, maximize recall (top-20 to top-50)
- Stage 2 (cross-encoder): Narrow to precision, minimize false positives (top-3 to top-5)
- This mirrors how human experts search: scan broadly first, then evaluate candidates carefully
- **Root cause**: Current system does top-5 search directly — too few candidates to achieve high recall, but including more irrelevant results pollutes the LLM context

### Root Cause Statement

> **First-stage retrieval alone cannot achieve production-grade precision because bi-encoder embeddings compress query-document interactions into fixed vectors, losing token-level relevance signals. This causes a precision ceiling of ~60% at top-5, where 2 of 5 retrieved chunks are typically irrelevant — directly polluting the LLM generation context.**

### Measured Evidence
- Current precision@5: ~40% (Phase 1 target: 60%)
- Over-retrieving to top-20 with pure embedding: precision@20 ~15%
- The LLM generation prompt includes all retrieved chunks — 2 irrelevant chunks out of 5 means 40% context pollution

---

## Current State Analysis

| Component | Status | Limitation |
|-----------|--------|------------|
| Bi-encoder (MiniLM) | ✅ Working | Fast, but hits precision ceiling |
| Hybrid search (Phase 1) | ⏳ In progress | Better than dense-only, still stage-1 only |
| Cross-encoder reranker | ❌ Missing | No second-stage scoring |
| Model selection | ❌ Undecided | Which cross-encoder model? |
| Batch scoring | ❌ Missing | Scored one by one, must batch for speed |

---

## Typed Execution Plan

### DAG

```
Phase 2.1 ──[Select + load cross-encoder model (TinyBERT-L-2)]──► Checkpoint 2.1
    │                                                              │ model loads in <2s
    ▼                                                              │ inference returns score
Phase 2.2 ──[Implement rerank() pipeline]────────────────────────► Checkpoint 2.2
    │                                                              │ rerank(20 candidates) → top-5
    ▼                                                              │ preserves scores
Phase 2.3 ──[Integrate with hybrid_search (over-retrieve → rerank)]► Checkpoint 2.3
    │                                                              │ pipeline: hybrid(top_k=20) → rerank(top-5)
    ▼                                                              │ no circular imports
Phase 2.4 ──[Batch scoring + latency optimization]────────────────► Checkpoint 2.4
    │                                                              │ batches of 5, max 4 concurrent
    ▼                                                              │ latency < 500ms total
Phase 2.5 ──[Benchmark precision@5, recall@5, latency]───────────► Done
                                                                   │ precision@5 > 80%
```

### Phase 2.1 — Model Selection

**Criteria**: Must run on CPU, < 100MB RAM, < 200ms inference per 20 candidates

**Selected model**: `cross-encoder/ms-marco-TinyBERT-L-2`

| Model | Parameters | Speed (20 pairs) | Precision Gain | RAM |
|-------|-----------|-------------------|----------------|-----|
| TinyBERT-L-2 | 14.5M | ~150ms | +15-25% | ~60MB |
| ms-marco-MiniLM-L-4-v2 | 22.7M | ~250ms | +18-28% | ~90MB |
| ms-marco-MiniLM-L-6-v2 | 42.6M | ~400ms | +20-30% | ~170MB |
| **bge-reranker-v2-m3 (selected)** | **~160M (quantized)** | **~200ms** | **+20-30%** | **~120MB** |

**Final selection**: `BAAI/bge-reranker-v2-m3` in FP16 (quantized) — best quality-to-speed ratio on CPU.

**Fallback**: `cross-encoder/ms-marco-TinyBERT-L-2` if memory constrained.

### Phase 2.2 — Rerank Implementation

```python
from sentence_transformers import CrossEncoder

class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self.model = CrossEncoder(
            model_name,
            max_length=512,
            device="cpu",
        )

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
        batch_size: int = 5,
    ) -> list[dict]:
        """Score candidate (query, doc_text) pairs and return top_k."""
        pairs = [(query, doc["chunk_text"][:2048]) for doc in candidates]
        scores = self.model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
        # Attach scores
        for doc, score in zip(candidates, scores):
            doc["rerank_score"] = float(score)
        # Sort by score descending
        candidates.sort(key=lambda x: -x.get("rerank_score", 0))
        return candidates[:top_k]
```

### Phase 2.3 — Integration with Hybrid Search

```python
def search_with_rerank(
    self,
    query: str,
    final_top_k: int = 5,
    retrieve_top_k: int = 20,
) -> list[dict]:
    """Over-retrieve, then rerank."""
    candidates = self.hybrid_search(query, top_k=retrieve_top_k)
    if len(candidates) <= final_top_k:
        return candidates  # No reranking needed
    return self.reranker.rerank(query, candidates, top_k=final_top_k)
```

### Phase 2.4 — Latency Optimization

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class Reranker:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1)  # Single-thread for model inference
        self._model = None  # Lazy load

    def ensure_loaded(self):
        if self._model is None:
            import time
            t0 = time.time()
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(
                "BAAI/bge-reranker-v2-m3",
                max_length=512,
                device="cpu",
            )
            print(f"[reranker] Loaded in {time.time()-t0:.2f}s")

    async def rerank_async(self, query, candidates, top_k=5):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.rerank,
            query,
            candidates,
            top_k,
        )
```

---

## Audit Benchmarks

### Pre-Phase Baseline

| Metric | Current Value | Target |
|--------|---------------|--------|
| Precision@5 | ~40% | >80% |
| Recall@5 | ~65% | >85% |
| Context pollution (% irrelevant in top-5) | ~40% | <15% |
| End-to-end latency (query → top-5) | ~80ms | <500ms |
| Reranker RAM usage | N/A | <200MB |

### Post-Phase Verification Matrix

| Check | Tool | Pass Criteria |
|-------|------|---------------|
| Model loads successfully | `CrossEncoder("BAAI/bge-reranker-v2-m3")` | No OOM, < 5s load time |
| Rerank scores correct range | Scores are floats, ordered descending | All scores in [0, 1] or monotonic |
| Top-5 after rerank differs from top-5 before rerank | At least 1 different document in top-5 | At least 1 re-rank change |
| Precision@5 >= 80% | Manual eval on 50 queries | >= 80% |
| P95 latency < 500ms | 100-query benchmark | Each query < 500ms |

---

## Verification Protocol (Block-Level)

### Block 1: Model Load

```python
import psutil
proc = psutil.Process()
mem_before = proc.memory_info().rss
reranker = Reranker()
mem_after = proc.memory_info().rss
assert (mem_after - mem_before) < 200 * 1024 * 1024  # <200MB
```

### Block 2: Rerank Correctness

```python
# Create known test case: 1 relevant, 9 irrelevant chunks
relevant = {"chunk_text": "This talks about FVG liquidity grab entry strategy with stop loss at recent low"}
irrelevant = [{"chunk_text": f"Irrelevant text about random topic {i}"} for i in range(9)]
candidates = [relevant] + irrelevant
import random
random.shuffle(candidates)
result = reranker.rerank("FVG liquidity grab entry", candidates, top_k=3)
assert result[0]["chunk_text"] == relevant["chunk_text"]  # Relevant should be #1
```

### Block 3: Integration

```python
db = StrategyDB()
# Without rerank
results_no_rr = db.hybrid_search("FVG entry", top_k=5)
# With rerank (over-retrieve 20, rerank to 5)
results_with_rr = db.search_with_rerank("FVG entry")
# Reranked results should have strictly higher average relevance
assert avg_relevance(results_with_rr) >= avg_relevance(results_no_rr)
```

### Block 4: Latency

```bash
python3 -c "
from strategy_db.query import StrategyDB
import time
db = StrategyDB()
times = [time.time() for _ in range(100)]
_ = [db.search_with_rerank('FVG entry') for _ in range(100)]
times = [time.time() - t for t in times]
times.sort()
print(f'p50: {times[50]:.3f}s, p95: {times[95]:.3f}s')
"
assert p95 < 0.500
```

---

## Rollback Plan

| Failure | Action |
|---------|--------|
| OOM on model load | Fall back to TinyBERT-L-2 (2-layer) |
| Latency > 500ms | Reduce retrieve_top_k from 20 to 10 |
| Precision not improving | Reduce batch_size, try different model |
| Import errors | Lazy-import cross_encoder, skip rerank, log warning |

## Estimated Effort

| Task | Time | Dependencies |
|------|------|-------------|
| Phase 2.1 — Model selection + load | 15 min | pip install sentence-transformers |
| Phase 2.2 — rerank() | 30 min | Phase 2.1 |
| Phase 2.3 — Integration | 20 min | Phase 2.2, Phase 1 |
| Phase 2.4 — Async optimization | 20 min | Phase 2.2 |
| Phase 2.5 — Benchmark | 30 min | All above |
| **Total** | **~1h 55min** | |

---

## Success Criteria

- [ ] Cross-encoder model loads correctly on CPU (< 200MB, < 5s load)
- [ ] `rerank()` correctly re-orders candidates, placing relevant docs higher
- [ ] Integration produces top-5 that are strictly better than hybrid-only top-5
- [ ] P95 latency < 500ms end-to-end
- [ ] Precision@5 > 80%
- [ ] No regressions in existing query paths
- [ ] Lazy import ensures crash tolerance (missing library = graceful fallback)
