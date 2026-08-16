#!/usr/bin/env python3
"""
Register ChromaDB strategy vectors as NEXUS routable resources.

Extracts all 592 ChromaDB vectors (embeddings, documents, metadata) and
registers each as a "skill"-type resource in the NEXUS SQLite+FAISS index.

Usage:
    python3 nexus/server/register_chromadb.py

After running, rebuild the FAISS index:
    cd /home/roshan/nexus && python3 server/scripts/phase4_build_faiss.py
"""

import sqlite3
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import chromadb
from chromadb.config import Settings
import numpy as np

NEXUS_DB = Path.home() / "nexus" / "db" / "nexus.db"
CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "strategy_db" / "chroma_db"
COLLECTION_NAME = "trading_strategies"

CLUSTER = "knowledge_wiki"
REPO_NAME = "algotrading"
FILE_PATH = "strategy_db/chroma_db"
RESOURCE_TYPE = "skill"
TIER = 2


def main():
    nexus_db = str(NEXUS_DB)
    if not os.path.exists(nexus_db):
        print(f"ERROR: NEXUS DB not found at {nexus_db}")
        sys.exit(1)

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection(name=COLLECTION_NAME)

    print("Fetching all ChromaDB vectors with embeddings...")
    data = collection.get(include=["embeddings", "documents", "metadatas"])
    total = len(data["ids"])
    print(f"Found {total} vectors in ChromaDB '{COLLECTION_NAME}'")

    conn = sqlite3.connect(nexus_db)
    cur = conn.cursor()

    registered = 0
    skipped_exists = 0
    skipped_no_embedding = 0

    for idx in range(total):
        cid = data["ids"][idx]
        meta = data["metadatas"][idx] or {}
        doc_text = (data["documents"][idx] or "") if data["documents"] else ""
        embedding = data["embeddings"][idx] if isinstance(data.get("embeddings"), (list, np.ndarray)) and len(data["embeddings"]) > idx else None

        setup_name = meta.get("setup_name", "").strip()
        setup_type = meta.get("setup_type", "")
        channel = meta.get("channel_name", "")

        resource_name = f"chromadb-{cid}"[:255]
        description = (
            f"{setup_name} — {setup_type} setup from {channel}"
            if channel
            else f"{setup_name} — {setup_type} setup"
        )
        body_text = f"{setup_name}\n\n{meta.get('video_title', '')}\n\n{meta.get('keywords', '')}\n\n{meta.get('assets', '')}\n\n{doc_text}"

        existing = cur.execute(
            "SELECT id FROM resources WHERE name=? AND repo_name=?",
            (resource_name, REPO_NAME),
        ).fetchone()
        if existing:
            skipped_exists += 1
            continue

        if embedding is None:
            skipped_no_embedding += 1
            continue

        emb_array = np.array(embedding, dtype=np.float32)
        emb_bytes = emb_array.tobytes()
        token_count = len(body_text) // 3

        try:
            cur.execute(
                """
                INSERT INTO resources
                (name, resource_type, repo_name, file_path, description, body_text,
                 embedding, token_count, status, tier, times_triggered,
                 times_correct, times_wrong)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, 0, 0, 0)
                """,
                (
                    resource_name,
                    RESOURCE_TYPE,
                    REPO_NAME,
                    FILE_PATH,
                    description[:500],
                    body_text[:15000],
                    emb_bytes,
                    token_count,
                    TIER,
                ),
            )
            resource_id = cur.lastrowid

            cur.execute(
                """
                INSERT INTO resource_embeddings
                (resource_id, model_name, embedding, created_at)
                VALUES (?, 'sentence-transformers/all-MiniLM-L6-v2', ?, datetime('now'))
                """,
                (resource_id, emb_bytes),
            )

            cur.execute(
                """
                INSERT INTO cluster_membership (cluster_name, resource_id, affinity)
                VALUES (?, ?, 0.7)
                ON CONFLICT(cluster_name, resource_id) DO UPDATE SET affinity=excluded.affinity
                """,
                (CLUSTER, resource_id),
            )

            registered += 1
        except sqlite3.IntegrityError:
            skipped_exists += 1
            continue

        if registered % 100 == 0:
            conn.commit()
            print(f"  ... {registered} registered")

    conn.commit()
    conn.close()

    print()
    print("=" * 60)
    print("REGISTRATION SUMMARY")
    print("=" * 60)
    print(f"  Total ChromaDB vectors:  {total}")
    print(f"  Registered in NEXUS:     {registered}")
    print(f"  Skipped (already exist): {skipped_exists}")
    print(f"  Skipped (no embedding):  {skipped_no_embedding}")
    print(f"  Target cluster:          {CLUSTER}")
    print()
    print("Next step — rebuild FAISS index:")
    print("  cd /home/roshan/nexus && python3 server/scripts/phase4_build_faiss.py")
    print()

    return registered > 0


if __name__ == "__main__":
    main()
