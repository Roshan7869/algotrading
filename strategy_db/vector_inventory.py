"""
Phase 1.1: Vector Inventory — Extract & index all ChromaDB vectors.

Outputs strategy_db/vector_inventory.json with full metadata index.
"""

import json
import os
from collections import Counter, defaultdict

import chromadb
from chromadb.config import Settings

DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "trading_strategies"


def load_inventory() -> dict:
    """Fetch all vectors from ChromaDB and build a structured index."""
    client = chromadb.PersistentClient(
        path=DB_DIR, settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection(name=COLLECTION_NAME)

    results = collection.get(include=["metadatas", "documents", "embeddings"])
    metadatas = results["metadatas"]
    documents = results["documents"]
    ids = results["ids"]
    embeddings = results.get("embeddings", [])

    # Build records with full metadata
    records = []
    for i, (vid, meta, doc) in enumerate(zip(ids, metadatas, documents)):
        records.append(
            {
                "id": vid,
                "setup_name": meta.get("setup_name", ""),
                "setup_type": meta.get("setup_type", ""),
                "channel_name": meta.get("channel_name", ""),
                "video_title": meta.get("video_title", ""),
                "author_concept": meta.get("author_concept", ""),
                "keywords": meta.get("keywords", ""),
                "market_condition": meta.get("market_condition", ""),
                "strategy_style": meta.get("strategy_style", ""),
                "timeframe": meta.get("timeframe", ""),
                "assets": meta.get("assets", ""),
                "risk_reward": meta.get("risk_reward", ""),
                "chunk_id": meta.get("chunk_id", ""),
                "outcome_total_trades": meta.get("outcome_total_trades"),
                "outcome_win_rate": meta.get("outcome_win_rate"),
                "outcome_avg_pnl_pct": meta.get("outcome_avg_pnl_pct"),
                "outcome_avg_r_multiple": meta.get("outcome_avg_r_multiple"),
                "chunk_text_preview": doc[:300] if doc else "",
                "chunk_text_length": len(doc) if doc else 0,
            }
        )

    # Build indexes
    by_setup_type = defaultdict(list)
    by_channel = defaultdict(list)
    by_keyword = defaultdict(list)
    by_market_condition = defaultdict(list)
    by_style = defaultdict(list)
    by_timeframe = defaultdict(list)
    by_video = defaultdict(list)

    has_outcome = 0

    for r in records:
        by_setup_type[r["setup_type"] or "uncategorized"].append(r["id"])
        by_channel[r["channel_name"] or "not_specified"].append(r["id"])

        for kw in (r["keywords"] or "").split(","):
            kw = kw.strip()
            if kw:
                by_keyword[kw].append(r["id"])

        by_market_condition[r["market_condition"] or "any"].append(r["id"])
        by_style[r["strategy_style"] or "not_specified"].append(r["id"])
        by_timeframe[r["timeframe"] or "not_specified"].append(r["id"])
        by_video[r["video_title"] or "no_video"].append(r["id"])

        if r["outcome_total_trades"] is not None:
            has_outcome += 1

    inventory = {
        "total_vectors": len(records),
        "explored": has_outcome,
        "unexplored": len(records) - has_outcome,
        "indexes": {
            "by_setup_type": {k: len(v) for k, v in sorted(by_setup_type.items())},
            "by_channel": {k: len(v) for k, v in sorted(by_channel.items())},
            "by_keyword": {k: len(v) for k, v in sorted(by_keyword.items(), key=lambda x: -len(x[1]))},
            "by_market_condition": {k: len(v) for k, v in sorted(by_market_condition.items())},
            "by_strategy_style": {k: len(v) for k, v in sorted(by_style.items())},
            "by_timeframe": {k: len(v) for k, v in sorted(by_timeframe.items())},
            "by_video": {k: len(v) for k, v in sorted(by_video.items(), key=lambda x: -len(x[1]))},
        },
        "records": records,
    }

    return inventory


def print_summary(inv: dict):
    """Print a human-readable summary to stdout."""
    print(f"Total vectors: {inv['total_vectors']}")
    print(f"Explored (has outcome): {inv['explored']}")
    print(f"Unexplored: {inv['unexplored']}")
    print()

    for idx_name, idx_data in inv["indexes"].items():
        print(f"--- {idx_name} ---")
        for k, v in list(idx_data.items())[:15]:
            print(f"  {v:4d}  {k}")
        if len(idx_data) > 15:
            print(f"  ... and {len(idx_data) - 15} more")
        print()


if __name__ == "__main__":
    inventory = load_inventory()

    out_path = os.path.join(os.path.dirname(__file__), "vector_inventory.json")
    with open(out_path, "w") as f:
        json.dump(inventory, f, indent=2)

    print(f"\nInventory saved to {out_path}")
    print_summary(inventory)
