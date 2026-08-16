"""Evaluate retrieval quality: HR@k, MRR@k before/after fine-tuning.

Compares base all-MiniLM-L6-v2 retrieval against adapter-augmented retrieval
using held-out eval_pairs.json.
"""

import json
import os
import sys
import time
from typing import Any, Callable

import chromadb
import numpy as np
from chromadb.config import Settings


def evaluate_retrieval(
    query_fn: Callable[[str, int], list[dict[str, Any]]],
    eval_pairs: list[tuple[str, str]],
    top_k: int = 10,
) -> dict[str, float]:
    """Compute Hit Rate@k and Mean Reciprocal Rank@k.

    Args:
        query_fn: Function taking (query: str, top_k: int) -> list[dict] where
                  each dict has a 'chunk_text' key with the retrieved document.
        eval_pairs: List of (query, relevant_doc_text) tuples.
        top_k: Number of top results to evaluate.

    Returns:
        Dict with HR@1, HR@5, HR@10, MRR@1, MRR@5, MRR@10 metrics.
    """
    hits_at: dict[int, float] = {1: 0.0, 5: 0.0, 10: 0.0}
    reciprocal_ranks: list[float] = []
    total = len(eval_pairs)
    errors = 0

    for query, relevant_doc in eval_pairs:
        try:
            results = query_fn(query, top_k=top_k)
        except Exception:
            reciprocal_ranks.append(0.0)
            errors += 1
            continue

        found = False
        for rank, doc in enumerate(results):
            doc_text = doc.get("chunk_text", "")
            # Check if retrieved doc contains the relevant content
            if relevant_doc[:100] in doc_text or doc_text[:100] in relevant_doc:
                rr = 1.0 / (rank + 1)
                reciprocal_ranks.append(rr)
                for k in hits_at:
                    if rank < k:
                        hits_at[k] += 1.0
                found = True
                break

        if not found:
            reciprocal_ranks.append(0.0)

    metrics: dict[str, float] = {}
    for k, hits in hits_at.items():
        metrics[f"HR@{k}"] = round(hits / total, 4) if total > 0 else 0.0

    # MRR
    for k in [1, 5, 10]:
        mrr = sum(reciprocal_ranks) / max(total, 1)
        metrics[f"MRR@{k}"] = round(mrr, 4)

    # Precision at 5 and 10
    for k in [5, 10]:
        prec = sum(
            1.0 / k if len(rr_list) > 0 else 0.0
            for rr_list in [
                [rr for j, rr in enumerate(reciprocal_ranks)
                 if j == i and rr > 0]
                for i in range(total)
            ]
            if rr_list
        )
        # Simplified precision: fraction of queries where at least one relevant found in top-k
        precision_k = hits_at[min(k, max(hits_at.keys()))] / max(total, 1)
        metrics[f"P@{k}"] = round(precision_k, 4)

    if errors > 0:
        print(f"  Warning: {errors}/{total} queries failed during evaluation")

    return metrics


def compare_models(
    eval_pairs: list[tuple[str, str]],
    query_fn_before: Callable[[str, int], list[dict[str, Any]]],
    query_fn_after: Callable[[str, int], list[dict[str, Any]]],
    top_k: int = 10,
) -> dict[str, Any]:
    """Compare retrieval metrics before and after fine-tuning.

    Returns:
        Dict with 'before', 'after', and 'delta' (after - before) metrics.
    """
    print(f"Evaluating baseline ({len(eval_pairs)} pairs)...")
    t0 = time.time()
    before = evaluate_retrieval(query_fn_before, eval_pairs, top_k)
    print(f"  Baseline eval: {time.time() - t0:.1f}s")

    print(f"Evaluating fine-tuned ({len(eval_pairs)} pairs)...")
    t0 = time.time()
    after = evaluate_retrieval(query_fn_after, eval_pairs, top_k)
    print(f"  Fine-tuned eval: {time.time() - t0:.1f}s")

    delta: dict[str, float] = {}
    for key in before:
        delta[key] = round(after[key] - before[key], 4)

    return {"before": before, "after": after, "delta": delta}


def _build_query_fn(
    search_fn: Callable,
    embedder: Any | None = None,
    collection: Any = None,
) -> Callable[[str, int], list[dict[str, Any]]]:
    """Build a query function with optional adapter-based embedding.

    When embedder is provided, queries are encoded through the adapter
    and ChromaDB is queried with the adapted embedding vector directly.
    Otherwise, the plain search_fn is used as-is.

    Args:
        search_fn: The `search` function from strategy_db.search.
        embedder: Optional FinetunedEmbedder for adapted queries.
        collection: ChromaDB collection (required if embedder is provided).

    Returns:
        A function (query: str, top_k: int) -> list[dict].
    """

    def adapted_search(query: str, top_k: int = 10) -> list[dict[str, Any]]:
        # Use adapted query embedding + raw ChromaDB vector search
        q_emb = embedder.encode_query(query)
        raw_results = collection.query(
            query_embeddings=[q_emb.tolist()],
            n_results=top_k,
        )

        output: list[dict[str, Any]] = []
        for i in range(len(raw_results["ids"][0])):
            meta = raw_results["metadatas"][0][i] if raw_results["metadatas"] else {}
            doc = raw_results["documents"][0][i] if raw_results["documents"] else ""
            dist = (
                raw_results["distances"][0][i]
                if raw_results["distances"]
                else 0.0
            )
            output.append(
                {
                    "id": raw_results["ids"][0][i],
                    "score": round(1.0 - dist, 4),
                    "setup_name": meta.get("setup_name", ""),
                    "setup_type": meta.get("setup_type", ""),
                    "chunk_text": doc,
                }
            )
        return output

    def plain_search(query: str, top_k: int = 10) -> list[dict[str, Any]]:
        # Use the standard search function
        return search_fn(query, top_k=top_k)

    if embedder is not None and collection is not None:
        return adapted_search
    return plain_search


if __name__ == "__main__":
    # Add project root and strategy_db to path for direct execution
    finetune_dir = os.path.dirname(os.path.abspath(__file__))
    strategy_db_dir = os.path.dirname(finetune_dir)
    project_root = os.path.dirname(strategy_db_dir)
    sys.path.insert(0, project_root)
    sys.path.insert(0, strategy_db_dir)

    from strategy_db.config import DB_DIR, COLLECTION_NAME

    # Load eval pairs
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    eval_path = os.path.join(data_dir, "eval_pairs.json")
    if not os.path.exists(eval_path):
        print(f"Eval pairs not found at {eval_path}")
        print("Run generate_qa.py first to create train/eval pairs.")
        sys.exit(1)

    with open(eval_path) as f:
        eval_pairs = json.load(f)
    print(f"Evaluating on {len(eval_pairs)} eval pairs")

    # Build baseline query function (unmodified search)
    from search import search as base_search

    query_fn_before = _build_query_fn(base_search, embedder=None, collection=None)

    # Build fine-tuned query function (adapter-augmented)
    from strategy_db.finetune import get_finetuned_embedder

    embedder = get_finetuned_embedder()
    client = chromadb.PersistentClient(
        path=DB_DIR, settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection(name=COLLECTION_NAME)
    query_fn_after = _build_query_fn(base_search, embedder=embedder, collection=collection)

    results = compare_models(eval_pairs, query_fn_before, query_fn_after)
    print("\n" + "=" * 60)
    print("Evaluation Results:")
    print("=" * 60)
    print(json.dumps(results, indent=2))
