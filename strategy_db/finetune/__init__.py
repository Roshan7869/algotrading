"""Embedding fine-tuning module — linear adapter for domain adaptation."""
from strategy_db.finetune.adapter_embedder import FinetunedEmbedder, get_finetuned_embedder

__all__ = ["FinetunedEmbedder", "get_finetuned_embedder"]
