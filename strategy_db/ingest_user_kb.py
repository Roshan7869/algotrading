#!/usr/bin/env python3
"""
Ingest user knowledge base (markdown files from user_kb/) into ChromaDB.

Reads *.md files from the user_kb/ directory, splits each into chunks
by ## headings, and ingests into a dedicated 'user_knowledge' collection
in the same ChromaDB instance (same all-MiniLM-L6-v2 embeddings).

Usage:
    python3 strategy_db/ingest_user_kb.py
"""

import os
import sys
import glob
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.config import Settings

from strategy_db.config import DB_DIR
from strategy_db.ingest import text_for_embedding

USER_KB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_kb")
COLLECTION_NAME = "user_knowledge"


def load_markdown_files() -> list[dict]:
    """Read all *.md files from user_kb/ and split into chunks by ## headings."""
    md_files = sorted(glob.glob(os.path.join(USER_KB_DIR, "*.md")))
    chunks = []

    for path in md_files:
        with open(path) as f:
            content = f.read()

        source_name = os.path.splitext(os.path.basename(path))[0]
        sections = re.split(r"\n(?=##\s)", content)

        for i, section in enumerate(sections):
            lines = section.strip().split("\n")
            heading = ""
            body_lines = []
            for line in lines:
                if line.startswith("## ") or line.startswith("# "):
                    heading = line.lstrip("#").strip()
                else:
                    body_lines.append(line)
            body = "\n".join(body_lines).strip()
            if not body:
                body = heading
                heading = ""

            chunk_id = f"{source_name}_{i:03d}"
            chunks.append({
                "chunk_id": chunk_id,
                "source": source_name,
                "heading": heading,
                "body": body,
                "full_text": f"{heading}\n\n{body}" if heading else body,
            })

    return chunks


def ingest():
    chunks = load_markdown_files()
    print(f"Loaded {len(chunks)} chunks from user_kb/")

    client = chromadb.PersistentClient(
        path=DB_DIR, settings=Settings(anonymized_telemetry=False)
    )

    existing_collections = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing_collections:
        collection = client.get_collection(name=COLLECTION_NAME)
        count = collection.count()
        print(f"Existing collection '{COLLECTION_NAME}' has {count} vectors")
    else:
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"Created new collection '{COLLECTION_NAME}'")

    texts = [c["full_text"] for c in chunks]
    metadatas = [
        {
            "source": c["source"],
            "heading": c["heading"],
            "chunk_id": c["chunk_id"],
        }
        for c in chunks
    ]
    ids = [c["chunk_id"] for c in chunks]

    collection.add(
        documents=texts,
        metadatas=metadatas,
        ids=ids,
    )

    count = collection.count()
    print(f"Ingested {len(chunks)} chunks into '{COLLECTION_NAME}' ({count} total vectors)")


if __name__ == "__main__":
    ingest()
