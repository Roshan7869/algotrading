"""Domain-adapted embedder with linear adapter for query transformations.

Singleton wrapper around all-MiniLM-L6-v2 that optionally applies a trained
linear adapter to query embeddings. Document embeddings remain frozen so
no re-indexing of ChromaDB is required.
"""

import os

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


class FinetunedEmbedder:
    """Wraps base embedder with optional linear adapter for domain-adapted queries.

    Only transforms QUERY embeddings. Document embeddings stay frozen.
    Uses singleton pattern to avoid reloading the base model.

    Usage:
        fe = get_finetuned_embedder()
        q_emb = fe.encode_query("How to trade FVG entry?")
        doc_emb = fe.encode_document("FVG is a fair value gap...")
    """

    _instance: "FinetunedEmbedder | None" = None

    def __new__(cls, adapter_dir: str | None = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, adapter_dir: str | None = None):
        if self._initialized:
            return

        self.base_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        self.adapter: torch.nn.Module | None = None
        self.adapter_loaded: bool = False

        if adapter_dir is None:
            adapter_dir = os.path.join(os.path.dirname(__file__), "adapter_v1")

        self._try_load_adapter(adapter_dir)
        self._initialized = True

    def _try_load_adapter(self, adapter_dir: str) -> None:
        """Attempt to load adapter weights from disk.

        Fails gracefully if adapter.pt does not exist or cannot be loaded.
        """
        adapter_path = os.path.join(adapter_dir, "adapter.pt")
        if not os.path.exists(adapter_path):
            print(
                f"[finetuned] No adapter found at {adapter_path}, "
                f"using base model only"
            )
            return

        try:
            from strategy_db.finetune.train_adapter import LinearAdapter

            checkpoint = torch.load(
                adapter_path, map_location="cpu", weights_only=True
            )
            self.adapter = LinearAdapter(dim=checkpoint["dim"])
            self.adapter.load_state_dict(checkpoint["adapter_state_dict"])
            self.adapter.eval()
            self.adapter_loaded = True
            print(
                f"[finetuned] Adapter loaded "
                f"(trained on {checkpoint['train_pairs']} pairs)"
            )
        except Exception as e:
            print(f"[finetuned] Failed to load adapter: {e}")
            self.adapter = None

    def encode(
        self, texts: list[str], is_query: bool = True
    ) -> np.ndarray:
        """Encode texts. Only applies adapter for queries.

        Args:
            texts: List of text strings to encode.
            is_query: If True, apply the linear adapter to the embedding.

        Returns:
            numpy array of shape (len(texts), 384) with normalized embeddings.
        """
        embeddings = self.base_model.encode(texts, normalize_embeddings=True)

        if is_query and self.adapter is not None:
            with torch.no_grad():
                t = torch.tensor(embeddings)
                adapted = self.adapter(t)
                return adapted.numpy()

        return embeddings

    def encode_query(self, text: str) -> np.ndarray:
        """Encode a single query text with adapter applied (if loaded)."""
        return self.encode([text], is_query=True)[0]

    def encode_document(self, text: str) -> np.ndarray:
        """Encode a single document text without adapter."""
        return self.encode([text], is_query=False)[0]

    def is_adapted(self) -> bool:
        """Return True if a fine-tuned adapter is loaded and active."""
        return self.adapter_loaded

    @classmethod
    def clear(cls) -> None:
        """Reset singleton (useful for testing)."""
        cls._instance = None


def get_finetuned_embedder(
    adapter_dir: str | None = None,
) -> FinetunedEmbedder:
    """Factory function returning the singleton FinetunedEmbedder instance."""
    return FinetunedEmbedder(adapter_dir)
