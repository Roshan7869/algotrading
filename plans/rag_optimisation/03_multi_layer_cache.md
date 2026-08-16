# Phase 3: Multi-Layer Caching

## First Principles Root Cause Analysis

### Core Question
*Why does every RAG query recompute work that's already been done?*

### Decomposition to First Principles

**Principle 1: Query repetition is a power-law distribution**
- In any RAG system with >1 user, the top 10% of queries account for 40-70% of all queries
- In a trading context: users ask "FVG entry rules" repeatedly because it's a common concept
- ChromaDB HNSW search recomputes the approximate nearest neighbors from scratch every time
- The exact same embedding computation, the exact same HNSW graph traversal, the exact same score normalization — repeated
- **Root cause**: No memoization of computation results that are deterministic and reusable across calls

**Principle 2: Deterministic operations should never be repeated**
- Embedding: `encode("FVG liquidity grab entry")` returns the *exact same vector* every time
- BM25 scoring: same query → same tokenized query → same corpus → same scores
- Cross-encoder: same (query, doc) pair → same score
- These are *pure functions* of their inputs: given the same input, the output is identical
- **Root cause**: The system treats every query as unique when most queries are semantically identical to previously answered queries

**Principle 3: Latency budgets are cumulative**
- Current pipeline: embed (~50ms) + ChromaDB search (~30ms) + rerank (~200ms) = ~280ms per query
- If 40% of queries hit cache: average latency drops to `0.4 * 1ms + 0.6 * 280ms = 168ms`
- That's a 40% latency reduction from caching alone
- **Root cause**: No distinction between "hot" (frequent) queries and "cold" (novel) queries — all queries pay the same latency cost

### Root Cause Statement

> **Every RAG query re-embeds the query text, re-searches the vector index, and optionally re-reranks results — even when identical or near-identical queries have been served before. For a system with 40% query repetition, this means 40% of compute and latency is wasted on work with precomputed results, adding unnecessary load to both the embedding model and the vector database.**

### Measured Evidence
- Current: `RuntimeVDBridge` has a simple TTL cache (300s) — but only caches the full result object, no embedding cache, no retrieval cache
- No LRU eviction — cache can grow unbounded
- No semantic caching — only exact string match
- Each query still pays full embedding cost

---

## Current State Analysis

| Component | Status | Limitation |
|-----------|--------|------------|
| RuntimeVDBridge TTL cache | ⚠️ Partial | 300s TTL, exact match only, no LRU |
| Embedding cache | ❌ Missing | Every query re-embeds at ~50ms each |
| Retrieval cache | ❌ Missing | ChromaDB search repeats for same query |
| Semantic cache (near-duplicate) | ❌ Missing | "FVG entry rules" ≠ "FVG entry rule" — no fuzzy match |
| Cache invalidation | ❌ Missing | No mechanism to clear on re-index |
| Cache monitoring | ❌ Missing | No hit-rate tracking |

---

## Typed Execution Plan

### DAG

```
Phase 3.1 ──[Embedding cache (LRU, maxsize=1024)]───────────────► Checkpoint 3.1
    │                                                              │ 1024 entries cached
    ▼                                                              │ cache hit returns in <1µs
Phase 3.2 ──[Retrieval cache (query_hash → chunk_ids, TTL)]──────► Checkpoint 3.2
    │                                                              │ keyed by (query, top_k, filters)
    ▼                                                              │ 512 entries, 60s TTL
Phase 3.3 ──[Semantic cache (cosine > 0.95 → cached answer)]────► Checkpoint 3.3
    │                                                              │ separate ChromaDB collection
    ▼                                                              │ max 100 cached queries
Phase 3.4 ──[Cache invalidation on re-index]────────────────────► Checkpoint 3.4
    │                                                              │ version tag in cache key
    ▼                                                              │ bump version → auto-invalidate
Phase 3.5 ──[Hit-rate monitoring + stats]────────────────────────► Checkpoint 3.5
    │                                                              │ hit_rate, size, evictions tracked
    ▼                                                              │ exposed via MCP tool
Phase 3.6 ──[Benchmark: latency, hit rate, cost reduction]───────► Done
                                                                   │ p95 latency < 100ms for hot queries
```

### Phase 3.1 — Embedding Cache

```python
from cachetools import LRUCache
import hashlib

class EmbeddingCache:
    def __init__(self, maxsize: int = 1024):
        self.cache = LRUCache(maxsize=maxsize)
        self.hits = 0
        self.misses = 0

    def _make_key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def get_or_compute(self, text: str, compute_fn):
        key = self._make_key(text)
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        result = compute_fn(text)
        self.cache[key] = result
        return result

    def invalidate(self):
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
```

### Phase 3.2 — Retrieval Cache

```python
from cachetools import TTLCache

class RetrievalCache:
    def __init__(self, maxsize: int = 512, ttl: int = 60):
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.hits = 0
        self.misses = 0

    def make_key(self, query: str, top_k: int, where_filter: str = "") -> str:
        key = f"{query}|{top_k}|{hashlib.md5(str(where_filter).encode()).hexdigest()}"
        return hashlib.md5(key.encode()).hexdigest()

    def get_or_search(self, query: str, top_k: int, where_filter: dict, search_fn):
        key = self.make_key(query, top_k, str(where_filter))
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        results = search_fn(query, top_k=top_k, where_filter=where_filter)
        self.cache[key] = results
        return results
```

### Phase 3.3 — Semantic Cache

```python
class SemanticCache:
    """
    Stores query → answer pairs in a small ChromaDB collection.
    New queries are first checked for near-duplicates (cosine > 0.95).
    If found, the cached answer is returned directly.
    """

    def __init__(self, embedder, threshold: float = 0.95, max_entries: int = 100):
        self.embedder = embedder  # MiniLM embedder
        self.threshold = threshold
        self.client = chromadb.Client()  # In-memory, small
        self.collection = self.client.get_or_create_collection(
            name="semantic_cache",
            metadata={"hnsw:space": "cosine"},
        )

    def lookup(self, query: str) -> dict | None:
        q_emb = self.embedder.encode([query]).tolist()
        results = self.collection.query(query_embeddings=q_emb, n_results=1)
        if results["distances"] and len(results["distances"][0]) > 0:
            distance = results["distances"][0][0]
            similarity = 1.0 - distance
            if similarity >= self.threshold:
                return {
                    "answer": results["metadatas"][0][0].get("answer"),
                    "source": "semantic_cache",
                    "similarity": similarity,
                }
        return None

    def store(self, query: str, answer: str):
        if self.collection.count() >= 100:
            return  # Don't grow unbounded
        q_emb = self.embedder.encode([query]).tolist()
        self.collection.add(
            embeddings=q_emb,
            metadatas=[{"answer": answer[:500], "query": query}],
            ids=[hashlib.md5(query.encode()).hexdigest()],
        )

    def invalidate(self):
        self.client.delete_collection("semantic_cache")
        self.collection = self.client.get_or_create_collection("semantic_cache")
```

### Phase 3.4 — Cache Invalidation

```python
class VersionedCache:
    """Cache with corpus version — bump version to invalidate all caches."""

    _corpus_version = 1

    @classmethod
    def bump_version(cls):
        cls._corpus_version += 1

    def _make_key(self, query: str) -> str:
        return hashlib.md5(
            f"{query}|v{self._corpus_version}".encode()
        ).hexdigest()
```

**Invalidation triggers**:
- `ingest.py` calls `VersionedCache.bump_version()` after re-indexing
- All caches automatically use new version → old entries never match
- TTL handles natural expiry for retrieval cache (60s max anyway)

### Phase 3.5 — Monitoring

```python
class CacheMonitor:
    def __init__(self):
        self.stats = {}

    def register(self, name: str, cache):
        self.stats[name] = cache

    def report(self) -> dict:
        return {
            name: {
                "hit_rate": cache.hit_rate,
                "size": len(cache.cache) if hasattr(cache, "cache") else 0,
                "maxsize": cache.maxsize if hasattr(cache, "maxsize") else "N/A",
                "hits": cache.hits,
                "misses": cache.misses,
            }
            for name, cache in self.stats.items()
        }
```

---

## Audit Benchmarks

### Pre-Phase Baseline

| Metric | Current Value | Target |
|--------|---------------|--------|
| Embedding cache hit rate | 0% (no cache) | >40% |
| Retrieval cache hit rate | 0% (no cache) | >30% |
| P95 latency (full pipeline) | ~280ms | <100ms for cached, <280ms for uncached |
| Memory for cache | 0MB (no cache) | <50MB (cached embeddings: ~1.5MB for 1024 × 384 floats) |
| Query throughput (queries/sec) | ~3.5 | >10 with caching |

### Post-Phase Verification Matrix

| Check | Tool | Pass Criteria |
|-------|------|---------------|
| Embedding cache returns cached result | Same query twice → second returns in <1µs | Latency drop from ~50ms to <1µs |
| Retrieval cache returns cached | Same query within TTL → cached results | No ChromaDB call made |
| Semantic cache matches near-duplicate | "FVG entry" → "FVG entry rules" (diff text, same meaning) | Similarity > 0.95 → cache hit |
| Cache invalidation works | bump_version → same query → cache miss | Full pipeline runs |
| Hit rate tracked | 100 queries, 40 repeats | hit_rate ≈ 0.40 |
| All caches evict correctly | Fill LRU beyond maxsize | Oldest entries evicted |
| Memory under limit | Monitor RSS after 1000 unique queries | < 50MB total cache |

---

## Verification Protocol (Block-Level)

### Block 1: Embedding Cache

```python
cache = EmbeddingCache(maxsize=10)
call_count = 0
def embed(text):
    nonlocal call_count
    call_count += 1
    return [0.1, 0.2, 0.3]

# First call should compute
result1 = cache.get_or_compute("test", embed)
assert call_count == 1

# Second call should hit cache
result2 = cache.get_or_compute("test", embed)
assert call_count == 1  # No second call
assert result1 == result2
```

### Block 2: Semantic Cache

```python
sc = SemanticCache(embedder)
sc.store("FVG entry rules", "Look for fair value gap...")

# Exact match
result = sc.lookup("FVG entry rules")
assert result is not None
assert result["source"] == "semantic_cache"

# Near-duplicate (same meaning, different words)
result = sc.lookup("FVG entry rule")  # singular
assert result is not None  # Should match with cosine > 0.95
```

### Block 3: Invalidation

```python
v1_key = VersionedCache()._make_key("test")
VersionedCache.bump_version()
v2_key = VersionedCache()._make_key("test")
assert v1_key != v2_key  # Different versions → different keys
```

### Block 4: Latency

```bash
python3 -c "
from strategy_db.query import StrategyDB
import time
db = StrategyDB()
# Cold query
t0 = time.time()
db.query('FVG entry')
cold = time.time() - t0
# Hot query (same)
t0 = time.time()
db.query('FVG entry')
hot = time.time() - t0
print(f'Cold: {cold:.4f}s, Hot: {hot:.4f}s')
assert hot < cold * 0.1  # Hot should be 10x faster
"
```

---

## Rollback Plan

| Failure | Action |
|---------|--------|
| Cache returns stale data | Bump corpus_version, short TTL (60s max) |
| OOM from cache growth | Reduce LRU maxsize, add memory guard |
| Semantic cache false positives | Raise threshold from 0.95 to 0.98 |
| Cache misses always (no benefit) | Disable semantic cache, keep embedding + retrieval |

## Estimated Effort

| Task | Time | Dependencies |
|------|------|-------------|
| Phase 3.1 — Embedding cache | 20 min | cachetools (stdlib compatible) |
| Phase 3.2 — Retrieval cache | 15 min | Phase 3.1 |
| Phase 3.3 — Semantic cache | 30 min | ChromaDB (already installed) |
| Phase 3.4 — Invalidation | 10 min | Phase 3.1-3.3 |
| Phase 3.5 — Monitoring | 15 min | Phase 3.1-3.4 |
| Phase 3.6 — Benchmark | 20 min | All above |
| **Total** | **~1h 50min** | |

---

## Success Criteria

- [ ] Embedding cache reduces embedding calls by >= 40% on repeated queries
- [ ] Retrieval cache returns cached results within TTL, bypassing ChromaDB
- [ ] Semantic cache matches near-duplicate queries with cosine > 0.95
- [ ] Cache invalidation on corpus version bump works correctly
- [ ] Cache hit rates are tracked and exposed via MCP tool
- [ ] Total cache memory < 50MB
- [ ] Hot queries return in < 100ms (vs ~280ms cold)
- [ ] No regressions in correctness (cache returns same results as uncached pipeline)
