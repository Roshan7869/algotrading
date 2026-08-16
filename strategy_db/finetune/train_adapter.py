"""Train a linear adapter on domain Q/A pairs (CPU, ~2 min).

Uses contrastive loss with in-batch negatives. The adapter is a 384->384 linear
projection applied only to query embeddings. Document embeddings stay frozen
so no re-indexing is required.

Optimization: All embeddings are pre-computed once before the training loop
to avoid redundant encoding on every batch. This keeps total training under
2 minutes on CPU.
"""

import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from sentence_transformers import SentenceTransformer


class LinearAdapter(nn.Module):
    """Linear projection 384->384 applied to query embeddings only.

    Initialized near identity so the adapter starts as a no-op and
    gradually learns domain-specific query transformations.
    """

    def __init__(self, dim: int = 384):
        super().__init__()
        self.linear = nn.Linear(dim, dim, bias=False)
        # Initialize near identity
        nn.init.eye_(self.linear.weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x)


def precompute_embeddings(
    model: SentenceTransformer,
    train_pairs: list[tuple[str, str]],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Pre-compute all query and document embeddings once.

    Deduplicates document texts to avoid redundant encoding when multiple
    queries map to the same document chunk.

    Args:
        model: Frozen SentenceTransformer for encoding.
        train_pairs: List of (query_text, document_text) tuples.

    Returns:
        Tuple of (query_embs, pos_embs, neg_embs) each shape (N, 384).
        neg_embs are shifted by one (in-batch negatives).
    """
    num_pairs = len(train_pairs)
    print(f"Pre-computing embeddings for {num_pairs} pairs...")
    t0 = time.time()

    # Build deduplication map for documents
    doc_to_idx: dict[str, int] = {}
    unique_docs: list[str] = []
    doc_idx_map: list[int] = []  # maps pair index -> unique doc index

    for _, doc_text in train_pairs:
        if doc_text not in doc_to_idx:
            doc_to_idx[doc_text] = len(unique_docs)
            unique_docs.append(doc_text)
        doc_idx_map.append(doc_to_idx[doc_text])

    # Batch-encode all unique documents
    print(f"  Encoding {len(unique_docs)} unique documents...")
    unique_doc_embs = model.encode(
        unique_docs,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=64,
    )

    # Batch-encode all queries
    queries = [q for q, _ in train_pairs]
    print(f"  Encoding {len(queries)} queries...")
    query_embs = model.encode(
        queries,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=64,
    )

    # Build tensors
    q_tensor = torch.tensor(query_embs, dtype=torch.float32)
    p_tensor = torch.zeros(num_pairs, 384, dtype=torch.float32)
    for i, doc_idx in enumerate(doc_idx_map):
        p_tensor[i] = torch.tensor(unique_doc_embs[doc_idx], dtype=torch.float32)

    # In-batch negatives: shift document embeddings by one
    n_tensor = torch.cat([p_tensor[1:], p_tensor[:1]], dim=0)

    elapsed = time.time() - t0
    print(f"  Pre-computation done in {elapsed:.1f}s")
    return q_tensor, p_tensor, n_tensor


def train_adapter(
    train_pairs: list[tuple[str, str]],
    output_dir: str = "strategy_db/finetune/adapter_v1",
    epochs: int = 4,
    batch_size: int = 32,
    lr: float = 0.001,
) -> LinearAdapter:
    """Train linear adapter with contrastive loss on CPU.

    Architecture:
      - Freeze the base `all-MiniLM-L6-v2` SentenceTransformer.
      - Train a 384->384 LinearAdapter applied only to query embeddings.
      - Positive pairs: (query, matching document) from train_pairs.
      - In-batch negatives: shifted documents within each batch.

    Loss = pos_loss + 0.5 * neg_loss where:
      - pos_loss = 1.0 - mean(cosine_similarity(q_adapted, p_emb))
      - neg_loss = max(cosine_similarity(q_adapted, n_emb) - 0.3, 0)

    Args:
        train_pairs: List of (query_text, document_text) tuples.
        output_dir: Directory to save adapter.pt and config.json.
        epochs: Number of training epochs.
        batch_size: Batch size for training.
        lr: Learning rate for Adam optimizer.

    Returns:
        Trained LinearAdapter module.
    """
    device = torch.device("cpu")
    print(f"Loading base model 'all-MiniLM-L6-v2' on {device}...")
    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    model.eval()  # Freeze base model

    # Pre-compute all embeddings once
    q_all, p_all, n_all = precompute_embeddings(model, train_pairs)

    adapter = LinearAdapter(dim=384).to(device)
    optimizer = torch.optim.Adam(adapter.parameters(), lr=lr)

    os.makedirs(output_dir, exist_ok=True)

    num_pairs = len(train_pairs)
    print(
        f"Training on {num_pairs} pairs, "
        f"{epochs} epochs, batch_size={batch_size}, lr={lr}"
    )

    t_train_start = time.time()

    for epoch in range(epochs):
        total_loss = 0.0
        n_batches = 0

        # Shuffle pair indices each epoch
        perm = torch.randperm(num_pairs)

        for i in range(0, num_pairs, batch_size):
            batch_indices = perm[i : i + batch_size]

            # Index into pre-computed tensors
            q_emb = q_all[batch_indices]
            p_emb = p_all[batch_indices]
            n_emb = n_all[batch_indices]

            # Apply adapter to query only
            q_adapted = adapter(q_emb)

            # Positive loss: want q_adapted close to p_emb
            pos_sim = nn.functional.cosine_similarity(q_adapted, p_emb)
            pos_loss = (1.0 - pos_sim).mean()

            # Negative loss: push similarity below 0.3 margin
            neg_sim = nn.functional.cosine_similarity(q_adapted, n_emb)
            neg_loss = torch.clamp(neg_sim - 0.3, min=0).mean()

            loss = pos_loss + 0.5 * neg_loss

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)
        print(f"  Epoch {epoch + 1}/{epochs}: loss={avg_loss:.6f}")

    train_elapsed = time.time() - t_train_start
    print(f"Training loop completed in {train_elapsed:.1f}s")

    # Save adapter weights and training metadata
    torch.save(
        {
            "adapter_state_dict": adapter.state_dict(),
            "dim": 384,
            "epochs": epochs,
            "train_pairs": num_pairs,
        },
        os.path.join(output_dir, "adapter.pt"),
    )

    # Save human-readable config
    with open(os.path.join(output_dir, "config.json"), "w") as f:
        json.dump(
            {
                "base_model": "all-MiniLM-L6-v2",
                "dim": 384,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "train_pairs": num_pairs,
            },
            f,
            indent=2,
        )

    print(f"Adapter saved to {output_dir}")
    return adapter


if __name__ == "__main__":
    strategy_db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, strategy_db_dir)

    data_dir = os.path.join(os.path.dirname(__file__), "data")

    # Generate data if not already present
    if not os.path.exists(os.path.join(data_dir, "train_pairs.json")):
        print("Generating Q/A pairs first...")
        from strategy_db.finetune.generate_qa import (
            generate_dataset,
            save_pairs,
        )
        from ingest import load_all_chunks, load_simple_chunks

        chunks = load_all_chunks()
        chunks.extend(load_simple_chunks())
        train_pairs, eval_pairs = generate_dataset(chunks, queries_per_chunk=4)
        save_pairs(train_pairs, eval_pairs, data_dir)

    with open(os.path.join(data_dir, "train_pairs.json")) as f:
        train_pairs = json.load(f)

    t0 = time.time()
    adapter = train_adapter(
        train_pairs,
        output_dir=os.path.join(os.path.dirname(__file__), "adapter_v1"),
        epochs=8,
        batch_size=64,
        lr=0.002,
    )
    elapsed = time.time() - t0
    print(f"Total wall time: {elapsed:.1f}s")
