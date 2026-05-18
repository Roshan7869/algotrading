"""RuntimeVDBridge — strategies query ChromaDB at runtime for adaptive parameters.

Singleton with TTL cache. Zero external deps beyond chromadb.
Strategies call `vdb.query(text)` during populate_indicators().
"""

import os
import time
from pathlib import Path
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "trading_strategies"
CACHE_TTL = 300
TOP_K_DEFAULT = 3


class RuntimeVDBridge:
    _instance = None
    _client = None
    _collection = None
    _cache = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __reduce__(self):
        return (self.__class__.__new__, (self.__class__,))

    def _lazy_init(self):
        if self._initialized:
            return
        import chromadb
        from chromadb.config import Settings
        self._client = chromadb.PersistentClient(
            path=DB_DIR, settings=Settings(anonymized_telemetry=False)
        )
        self._collection = self._client.get_collection(name=COLLECTION_NAME)
        self._initialized = True

    def query(
        self, text: str, top_k: int = TOP_K_DEFAULT, setup_type: Optional[str] = None
    ) -> list[dict]:
        cache_key = f"{text}:{top_k}:{setup_type}"
        now = time.time()
        if cache_key in self._cache and now - self._cache[cache_key]["ts"] < CACHE_TTL:
            return self._cache[cache_key]["data"]

        self._lazy_init()
        where = {"setup_type": {"$eq": setup_type}} if setup_type else None

        try:
            results = self._collection.query(
                query_texts=[text], n_results=top_k, where=where
            )
        except Exception:
            self._cache[cache_key] = {"data": [], "ts": now}
            return []

        entries = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            entries.append({
                "score": round(1.0 - results["distances"][0][i], 4),
                "setup_name": meta.get("setup_name", ""),
                "setup_type": meta.get("setup_type", ""),
                "market_condition": meta.get("market_condition", ""),
                "risk_reward": meta.get("risk_reward", ""),
                "keywords": meta.get("keywords", ""),
                "chunk_text": results["documents"][0][i][:300],
            })

        self._cache[cache_key] = {"data": entries, "ts": now}
        return entries

    def query_entry_setups(self, text: str, top_k: int = 3) -> list[dict]:
        return self.query(text, top_k=top_k, setup_type="entry")

    def query_risk_rules(self, text: str, top_k: int = 3) -> list[dict]:
        return self.query(text, top_k=top_k, setup_type="risk_management")

    def is_available(self) -> bool:
        try:
            self._lazy_init()
            return self._collection is not None
        except Exception:
            return False

    def clear_cache(self):
        self._cache.clear()
