"""Cross-encoder reranker for two-stage retrieval."""

import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional


class Reranker:
    """Second-stage cross-encoder reranker.

    Over-retrieve N candidates from hybrid search, then rescore
    with cross-encoder that processes (query, document) pairs jointly.

    Model: BAAI/bge-reranker-v2-m3 (FP16, ~120MB)
    Fallback: cross-encoder/ms-marco-TinyBERT-L-2 (~60MB)
    """

    _instance = None

    def __new__(cls, model_name: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        if self._initialized:
            return
        self.model_name = model_name
        self._model = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._initialized = True
        self.load_time_ms = 0.0

    def _lazy_load(self):
        """Lazy-load the cross-encoder model."""
        if self._model is not None:
            return
        t0 = time.time()
        from sentence_transformers import CrossEncoder
        try:
            self._model = CrossEncoder(
                self.model_name,
                max_length=512,
                device="cpu",
            )
        except Exception:
            # Fallback to smaller model
            print(f"[reranker] Failed to load {self.model_name}, falling back to TinyBERT-L-2")
            self.model_name = "cross-encoder/ms-marco-TinyBERT-L-2"
            self._model = CrossEncoder(
                self.model_name,
                max_length=512,
                device="cpu",
            )
        self.load_time_ms = (time.time() - t0) * 1000
        print(f"[reranker] Loaded {self.model_name} in {self.load_time_ms:.0f}ms")

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
        batch_size: int = 5,
    ) -> list[dict]:
        """Score (query, doc_text) pairs and return top_k by score.

        Args:
            query: User query string
            candidates: List of dicts, each must have 'chunk_text' key
            top_k: Number of top results to return
            batch_size: Batch size for cross-encoder inference

        Returns:
            Candidates list with 'rerank_score' added, sorted by score DESC, trimmed to top_k
        """
        self._lazy_load()

        if len(candidates) <= top_k:
            for c in candidates:
                c["rerank_score"] = c.get("score", 0.0)
            return candidates

        # Truncate long texts to 2048 chars (cross-encoder limit)
        pairs = [(query, doc.get("chunk_text", "")[:2048]) for doc in candidates]
        scores = self._model.predict(pairs, batch_size=batch_size, show_progress_bar=False)

        for doc, score in zip(candidates, scores):
            doc["rerank_score"] = float(score)

        candidates.sort(key=lambda x: -x.get("rerank_score", 0))
        return candidates[:top_k]

    async def rerank_async(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Async wrapper for rerank (runs blocking inference in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.rerank,
            query,
            candidates,
            top_k,
        )

    def is_available(self) -> bool:
        """Check if reranker can be loaded."""
        try:
            self._lazy_load()
            return self._model is not None
        except Exception:
            return False

    def clear(self):
        """Reset singleton (for testing)."""
        self._model = None
        self._initialized = False


def get_reranker() -> Reranker:
    return Reranker()
