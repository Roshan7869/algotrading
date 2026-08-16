# Phase 1: Hybrid Search — BM25 + Vector Fusion

## First Principles Root Cause Analysis

### Core Question
*Why does pure semantic search fail for trading strategy retrieval?*

### Decomposition to First Principles

**Principle 1: Language is dual-natured**
- Semantic meaning (dense vectors) captures *concepts* and *relationships*
- Lexical matching (keyword) captures *specific terminology* and *exact phrasing*
- Trading strategies use highly specific jargon (FVG = Fair Value Gap, CVD = Cumulative Volume Delta, LVN = Low Volume Node, OTE = Optimal Trade Entry) that:
  - Appear in < 0.001% of general-purpose training data
  - Have precise definitions that semantic models blur
  - Are often acronyms where word-piece tokenization destroys meaning

**Principle 2: Cosine similarity in high-dimensional space is a weak signal**
- In 384-dimensional space, all vectors converge toward the same expected cosine similarity (~0.6-0.7 for random pairs)
- For a query like "FVG liquidity grab long entry", the embedding flattens all 4 concepts into one 384-dim vector
- A strategy chunk about "liquidity grab" but discussing CVD instead of FVG may score 0.73 vs the correct 0.78 — too close to distinguish reliably
- **Root cause**: Dense-only retrieval treats *degree of relevance* as a single float, when relevance is actually *multi-faceted* (topic match + term match + context match)

**Principle 3: Information retrieval is a recall-precision trade-off**
- Dense retrieval maximizes recall (finds conceptually related items) at the cost of precision (may miss exact matches)
- Keyword retrieval (BM25) maximizes precision (finds exact terms) at the cost of recall (misses paraphrases)
- Pure dense retrieval in trading RAG means: query "stop loss placement after FVG" returns chunks about "general stop loss" and "FVG" separately, but NOT "stop loss after FVG" specifically
- **Root cause**: The retrieval system has no mechanism to *require* co-occurrence of query terms

### Root Cause Statement

> **Pure semantic (dense) retrieval fails for trading strategy RAG because trading knowledge is dense with domain-specific terminology that general-purpose embedding models cannot represent precisely, and the single-stage cosine similarity ranking conflates multiple independent axes of relevance into one scalar.**

### Measured Evidence
- Current system: pure ChromaDB query_texts with n_results=5
- No fallback if top-5 are all irrelevant
- Metadata filters help but only for known fields (setup_type, market_condition)
- The existing `where_document` keyword filter is a literal substring match (fragile)

---

## Current State Analysis

| Component | Status | Limitation |
|-----------|--------|------------|
| ChromaDB query_texts | ✅ Working | Dense-only, no lexical fallback |
| Metadata filtering | ✅ Working | Only filters on structured fields |
| where_document $contains | ⚠️ Present | Substring-only, no ranking, no tokenization |
| BM25 | ❌ Missing | Not imported or used |
| RRF (Reciprocal Rank Fusion) | ❌ Missing | No mechanism to merge result sets |
| Query expansion | ❌ Missing | No automated abbreviation expansion (FVG → Fair Value Gap) |

---

## Typed Execution Plan

### DAG

```
Phase 1.1 ──[Add rank_bm25 dependency + BM25 index builder]────► Checkpoint 1.1
    │                                                              │ bm25.index built from all chunks
    ▼                                                              │ tokenized_corpus has n=592 entries
Phase 1.2 ──[Implement hybrid_search() in query pipeline]─────────► Checkpoint 1.2
    │                                                              │ hybrid_search returns results
    ▼                                                              │ scores normalized to [0,1]
Phase 1.3 ──[Add RRF fusion + score normalization]────────────────► Checkpoint 1.3
    │                                                              │ RRF merges ChromaDB + BM25
    ▼                                                              │ k=60 constant in range [1,100]
Phase 1.4 ──[Add abbreviation expansion (FVG → FVG, Fair Value Gap)]► Checkpoint 1.4
    │                                                              │ Expander maps acronyms
    ▼                                                              │ Both forms searched
Phase 1.5 ──[Backward compatibility + fallback logic]─────────────► Checkpoint 1.5
    │                                                              │ pure_dense fallback works
    ▼                                                              │ no exceptions on empty corpus
Phase 1.6 ──[Audit: benchmark recall@5, precision@5 against test set]► Done
                                                                   │ delta > +15% recall
```

### Phase 1.1 — BM25 Index Builder

**File**: `strategy_db/query.py` (new method in existing class)

**Implementation**:
```python
from rank_bm25 import BM25Okapi
import re

class StrategyDB:
    def _build_bm25_index(self):
        corpus = [
            self._tokenize(chunk.chunk_text + " " + chunk.setup_name + " " + chunk.entry_condition)
            for chunk in self.all_chunks
        ]
        self.bm25 = BM25Okapi(corpus)

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return text.split()
```

**Build triggers**: On init, on re-index, on `rebuild_index()`

### Phase 1.2 — Hybrid Search Function

```python
def hybrid_search(
    self,
    query: str,
    top_k: int = 10,
    alpha: float = 0.7,           # weight for dense score (0=pure BM25, 1=pure dense)
    dense_top_k: int = 20,        # over-retrieve for dense
    bm25_top_k: int = 20,         # over-retrieve for BM25
    where_filter: dict = None,
    abbreviation_expand: bool = True,
) -> list[dict]:
```

**Algorithm**:
1. Tokenize query → BM25 scores for all corpus documents
2. Run ChromaDB query_texts → dense scores for top-k candidates
3. Normalize both score sets to [0, 1] using min-max within each set
4. For documents in BM25 only → dense_score = 0; for dense only → bm25_score = 0
5. Fuse: `final_score = alpha * dense_score + (1-alpha) * bm25_score`
6. Sort by final_score, return top_k

### Phase 1.3 — RRF Fusion (Alternative to weighted sum)

```python
def rrf_fusion(
    self,
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion: RRF_score(d) = sum(1 / (k + rank_i(d)))"""
    scores = {}
    for rank, doc in enumerate(dense_results):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, doc in enumerate(bm25_results):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [self.get_by_id(doc_id) for doc_id, _ in ranked]
```

**Why RRF over weighted sum**: RRF is parameter-free (k=60 is near-universal optimal), rank-based (not score-based, so doesn't require score normalization), and proven in TREC competitions to outperform weighted fusion.

### Phase 1.4 — Abbreviation Expansion Dictionary

```python
ABBREVIATIONS = {
    "FVG": ["Fair Value Gap"],
    "CVD": ["Cumulative Volume Delta"],
    "LVN": ["Low Volume Node"],
    "HVN": ["High Volume Node"],
    "OB": ["Order Block"],
    "OTE": ["Optimal Trade Entry"],
    "ICT": ["Inner Circle Trader"],
    "SMC": ["Smart Money Concept"],
    "MSS": ["Market Structure Shift"],
    "CHoCH": ["Change of Character"],
    "BOS": ["Break of Structure"],
    "FTA": ["Fair Trade Area"],
    "TPR": ["Trading Price Range"],
    "DP": ["Discount Price", "Discount Array"],
    "SP": ["Premium Price", "Premium Array"],
    "LIQ": ["Liquidity"],
    "SSL": ["Sell Side Liquidity"],
    "BSL": ["Buy Side Liquidity"],
}
```

Apply: expand query tokens, run separate search for expanded forms, merge results.

### Phase 1.5 — Fallback Logic

```python
def query(self, text, top_k=5, **kwargs):
    try:
        return self.hybrid_search(text, top_k=top_k, **kwargs)
    except (ImportError, AttributeError):
        # rank_bm25 not installed or index not built
        return self.pure_dense_search(text, top_k=top_k, **kwargs)
```

---

## Audit Benchmarks

### Pre-Phase Baseline (measure BEFORE changes)

| Metric | Measurement Method | Current Value | Target |
|--------|-------------------|---------------|--------|
| Recall@5 | % of top-5 results containing at least 1 relevant doc (manual eval on 50 queries) | ~65% | >85% |
| Precision@5 | % of top-5 results that are relevant | ~40% | >60% |
| Zero-term-match rate | % of queries returning 0 results for exact acronym | ~100% on trading acronyms | 0% |
| Query latency (p50) | `time query()` over 100 queries | ~80ms | <150ms (allowable increase for dual search) |

### Post-Phase Verification Matrix

| Check | Tool | Pass Criteria |
|-------|------|---------------|
| BM25 index built | Assert `len(bm25.documents)` == 592 | All chunks indexed |
| Hybrid search returns 10 results | Unit test with known query | len(results) == 10 |
| RRF gives higher rank to dual-match docs | Unit test: query "FVG stop loss". Doc with both terms ranks #1 vs doc with only "stop loss" | Dual-match doc always above single-match |
| Abbreviation expansion works | Query "FVG" returns results with "Fair Value Gap" | >0 results for expanded form |
| Pure dense fallback on BM25 import error | Mock ImportError | Falls back without exception |
| Backward compatible | `search()` same signature as before | No caller changes needed |
| No new dependencies conflict | `pip check` | No version conflicts |

---

## Verification Protocol (Block-Level)

### Block 1: Unit Tests

```bash
python3 -m pytest strategy_db/tests/test_hybrid_search.py -v
```

Minimum 5 test cases:
1. `test_bm25_index_build` — index created, correct size, tokenizes correctly
2. `test_hybrid_search_returns_results` — known query returns expected count
3. `test_rrf_prefers_dual_match` — dual-match ranked above single-match
4. `test_abbreviation_expansion` — "FVG" expands and finds "Fair Value Gap"
5. `test_fallback_pure_dense` — mock failure falls back gracefully

### Block 2: Integration Test

```python
# Test against real ChromaDB + real chunks
db = StrategyDB()
results = db.hybrid_search("FVG liquidity grab entry", top_k=5)
assert len(results) == 5
# The top result should contain FVG-related text
assert "FVG" in results[0].chunk_text or "Fair Value" in results[0].chunk_text
```

### Block 3: Performance Regression

```bash
# Run query loop 100 times, measure p95 latency
python3 -c "
from strategy_db.query import StrategyDB
import time
db = StrategyDB()
queries = ['FVG entry', 'stop loss placement', 'trend following breakout', 'liquidity grab', 'risk management']
times = []
for q in queries * 20:
    t0 = time.time()
    db.hybrid_search(q)
    times.append(time.time() - t0)
times.sort()
print(f'p50: {times[50]:.3f}s, p95: {times[95]:.3f}s')
"
assert p95 < 0.200  # 200ms max
```

### Block 4: Recall/Precision Benchmark

Run a 50-query evaluation set with known ground-truth relevant documents. Measured improvement must be >= 15 percentage points in Recall@5.

```bash
python3 strategy_db/tests/eval_hybrid_search.py --queries eval_queries.json --ground_truth ground_truth.json
```

---

## Rollback Plan

If any verification block fails:
1. Set `enable_hybrid_search: false` in config (reverts to pure dense)
2. Fix the failing block
3. Re-verify
4. Re-enable

## Estimated Effort

| Task | Time | Dependencies |
|------|------|-------------|
| Phase 1.1 — BM25 index | 20 min | rank_bm25 pip install |
| Phase 1.2 — hybrid_search | 30 min | Phase 1.1 |
| Phase 1.3 — RRF fusion | 15 min | Phase 1.2 |
| Phase 1.4 — Abbreviation expansion | 15 min | Phase 1.2 |
| Phase 1.5 — Fallback | 10 min | Phase 1.2 |
| Phase 1.6 — Audit | 30 min | All above |
| **Total** | **2h** | |

---

## Success Criteria

- [ ] BM25 index built from all 592 chunks
- [ ] `hybrid_search()` returns results for acronym-only queries (previously returned 0)
- [ ] RRF fusion ranks dual-match documents above single-match
- [ ] Recall@5 improves by >= 15 percentage points
- [ ] P95 latency < 200ms (pure dense was ~80ms, hybrid overhead ~2x acceptable)
- [ ] No regressions in existing query paths
- [ ] All tests pass
