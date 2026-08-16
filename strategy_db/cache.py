"""
Multi-Layer Caching for RAG Optimization (Phase 3).

Layers:
  1. EmbeddingCache  — LRU cache for embedding vectors (~1.5 MB)
  2. RetrievalCache  — TTL cache for full retrieval results (60 s)
  3. SemanticCache   — Near-duplicate query cache via cosine similarity
  4. VersionedCache  — Corpus-versioned cache key invalidation
  5. CacheMonitor    — Central registry with aggregate stats

Memory budget: <50 MB total (16 GB DDR3, no GPU).
"""

import hashlib
import json
from typing import Any, Callable

import chromadb
from cachetools import LRUCache, TTLCache


# ---------------------------------------------------------------------------
# 1. EmbeddingCache
# ---------------------------------------------------------------------------

class EmbeddingCache:
    """LRU cache for embedding vectors.

    Max 1024 entries (~1.5 MB for 384-dim float32).  Uses MD5 of the
    input text as the cache key so identical strings always collide.
    """

    def __init__(self, maxsize: int = 1024) -> None:
        self.cache: LRUCache = LRUCache(maxsize=maxsize)
        self.hits: int = 0
        self.misses: int = 0
        self.maxsize: int = maxsize

    @staticmethod
    def _make_key(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def get_or_compute(
        self, text: str, compute_fn: Callable[[str], Any]
    ) -> Any:
        """Return cached embedding or compute and cache it."""
        key = self._make_key(text)
        try:
            result = self.cache[key]
            self.hits += 1
            return result
        except KeyError:
            self.misses += 1
            result = compute_fn(text)
            self.cache[key] = result
            return result

    def invalidate(self) -> None:
        """Clear all cached embeddings and reset counters."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self.cache)


# ---------------------------------------------------------------------------
# 2. RetrievalCache
# ---------------------------------------------------------------------------

class RetrievalCache:
    """TTL cache for full retrieval results.

    512 entries with a 60-second TTL.  The cache key incorporates the
    query text, top-k, and a hash of the filter dict so different
    filter combinations don't collide.
    """

    def __init__(self, maxsize: int = 512, ttl: int = 60) -> None:
        self.cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.hits: int = 0
        self.misses: int = 0
        self.maxsize: int = maxsize
        self.ttl: int = ttl

    @staticmethod
    def make_key(
        query: str,
        top_k: int,
        where_filter: str = "",
    ) -> str:
        raw = f"{query}|{top_k}|{hashlib.md5(where_filter.encode()).hexdigest()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get_or_search(
        self,
        query: str,
        top_k: int,
        where_filter: dict[str, Any],
        search_fn: Callable[..., list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Return cached results or execute *search_fn* and cache."""
        key = self.make_key(query, top_k, str(where_filter))
        try:
            results = self.cache[key]
            self.hits += 1
            return results
        except KeyError:
            self.misses += 1
            results = search_fn(query, top_k=top_k, where_filter=where_filter)
            self.cache[key] = results
            return results

    def invalidate(self) -> None:
        """Clear the TTL cache and reset counters."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self.cache)


# ---------------------------------------------------------------------------
# 3. SemanticCache
# ---------------------------------------------------------------------------

class SemanticCache:
    """Near-duplicate query cache using cosine similarity.

    Stores query-to-answer pairs in a small in-memory ChromaDB
    collection.  A new query is answered from the cache only when its
    embedding is >= *threshold* similar to a previously-seen query.

    Max 100 cached queries.
    """

    def __init__(
        self,
        embedder: Any = None,
        threshold: float = 0.95,
        max_entries: int = 100,
    ) -> None:
        self.threshold: float = threshold
        self.max_entries: int = max_entries
        self.hits: int = 0
        self.misses: int = 0
        self._embedder: Any = embedder
        self._client: chromadb.Client | None = None
        self._collection: chromadb.Collection | None = None
        self._init_collection()

    def _init_collection(self) -> None:
        self._client = chromadb.Client()  # in-memory
        try:
            self._client.delete_collection("semantic_cache")
        except Exception:
            pass
        self._collection = self._client.create_collection(
            name="semantic_cache",
            metadata={"hnsw:space": "cosine"},
        )

    def set_embedder(self, embedder: Any) -> None:
        """Inject an embedder after construction (deferred wiring)."""
        self._embedder = embedder

    def lookup(self, query: str) -> dict[str, Any] | None:
        """Return cached results if a near-duplicate query exists."""
        if self._embedder is None or (
            self._collection is not None and self._collection.count() == 0
        ):
            self.misses += 1
            return None
        try:
            q_emb = self._embedder.encode([query])
            if hasattr(q_emb, "tolist"):
                q_emb = q_emb.tolist()
            results = self._collection.query(query_embeddings=q_emb, n_results=1)
            distances = results.get("distances")
            if distances and len(distances[0]) > 0:
                similarity = 1.0 - float(distances[0][0])
                if similarity >= self.threshold:
                    self.hits += 1
                    return {
                        "source": "semantic_cache",
                        "similarity": similarity,
                        "cached_results": results["metadatas"][0][0],
                    }
        except Exception:
            pass
        self.misses += 1
        return None

    def store(self, query: str, results: list[dict[str, Any]]) -> None:
        """Persist a query and its results into the cache."""
        if self._embedder is None or self._collection is None:
            return
        if self._collection.count() >= self.max_entries:
            return
        try:
            q_emb = self._embedder.encode([query])
            if hasattr(q_emb, "tolist"):
                q_emb = q_emb.tolist()
            summary = json.dumps([
                {
                    "id": r.get("id", ""),
                    "setup_name": r.get("setup_name", ""),
                    "score": r.get("score", 0.0),
                }
                for r in results[:5]
            ])
            self._collection.add(
                embeddings=q_emb,
                metadatas=[{"query_text": query, "cached_results": summary}],
                ids=[hashlib.md5(query.encode()).hexdigest()],
            )
        except Exception:
            pass

    def invalidate(self) -> None:
        """Drop and recreate the in-memory collection."""
        self._init_collection()
        self.hits = 0
        self.misses = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        try:
            return self._collection.count() if self._collection else 0
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# 4. VersionedCache
# ---------------------------------------------------------------------------

class VersionedCache:
    """Corpus-versioned cache keys.

    Bump the version number after every re-index so that all downstream
    caches which prepend the version automatically invalidate.
    """

    _corpus_version: int = 1

    @classmethod
    def bump_version(cls) -> None:
        cls._corpus_version += 1

    @classmethod
    def get_version(cls) -> int:
        return cls._corpus_version

    @staticmethod
    def make_versioned_key(base_key: str) -> str:
        return hashlib.md5(
            f"{base_key}|v{VersionedCache._corpus_version}".encode()
        ).hexdigest()


# ---------------------------------------------------------------------------
# 5. CacheMonitor
# ---------------------------------------------------------------------------

class CacheMonitor:
    """Central registry for all cache layers with aggregate stats."""

    def __init__(self) -> None:
        self._caches: dict[str, Any] = {}

    def register(self, name: str, cache: Any) -> None:
        """Register a named cache instance for monitoring."""
        self._caches[name] = cache

    def report(self) -> dict[str, Any]:
        """Return per-cache statistics."""
        report: dict[str, Any] = {}
        for name, cache in self._caches.items():
            entry: dict[str, Any] = {
                "hit_rate": cache.hit_rate,
                "hits": cache.hits,
                "misses": cache.misses,
            }
            if hasattr(cache, "size"):
                entry["size"] = cache.size
            if hasattr(cache, "maxsize"):
                entry["maxsize"] = cache.maxsize
            if hasattr(cache, "ttl"):
                entry["ttl"] = cache.ttl
            report[name] = entry
        return report

    def invalidate_all(self) -> None:
        """Invalidate every registered cache."""
        for cache in self._caches.values():
            cache.invalidate()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_cache_monitor = CacheMonitor()


def get_cache_monitor() -> CacheMonitor:
    """Return the global :class:`CacheMonitor` singleton."""
    return _cache_monitor
