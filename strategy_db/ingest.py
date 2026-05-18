import json
import os
import glob

import chromadb
from chromadb.config import Settings

from schema import StrategyChunk, text_for_embedding
from config import STRATEGY_DIR, DB_DIR, COLLECTION_NAME


def load_all_chunks() -> list[StrategyChunk]:
    txt_files = sorted(glob.glob(os.path.join(STRATEGY_DIR, "*.txt")))
    chunks: list[StrategyChunk] = []
    for path in txt_files:
        with open(path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"  Skipping {os.path.basename(path)}: invalid JSON")
                continue
            for item in data:
                chunks.append(StrategyChunk.from_dict(item))
    return chunks


def load_simple_chunks() -> list[StrategyChunk]:
    """Load simplified chunk format from strategy_db/source_data/*.json.

    These files use a simpler schema with only: setup_name, setup_type,
    market_condition, strategy_style, keywords, description. We expand
    them into full StrategyChunk objects.
    """
    source_dir = os.path.join(os.path.dirname(__file__), "source_data")
    if not os.path.exists(source_dir):
        print(f"  Source data directory not found: {source_dir}")
        return []

    json_files = sorted(glob.glob(os.path.join(source_dir, "*.json")))
    chunks: list[StrategyChunk] = []

    for path in json_files:
        with open(path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"  Skipping {os.path.basename(path)}: invalid JSON")
                continue

            source_name = os.path.splitext(os.path.basename(path))[0]
            for i, item in enumerate(data):
                # Convert keywords from comma-separated string to list
                keywords = item.get("keywords", "")
                if isinstance(keywords, str):
                    keywords = [k.strip() for k in keywords.split(",")]
                elif isinstance(keywords, list):
                    keywords = keywords

                description = item.get("description", item.get("chunk_text", ""))
                setup_type = item.get("setup_type", "unknown")

                chunk = StrategyChunk(
                    chunk_id=f"{source_name}_{i:03d}",
                    source_type="synthetic",
                    youtube_url="",
                    video_title="",
                    channel_name="ChromaDB Knowledge Expansion",
                    setup_name=item.get("setup_name", f"Unknown {source_name}"),
                    setup_type=setup_type,
                    timeframe=item.get("timeframe", "1h"),
                    market_condition=item.get("market_condition", "any"),
                    strategy_style=item.get("strategy_style", "multi-style"),
                    assets_applicable=item.get("assets_applicable", ["BTC", "ETH", "SOL"]),
                    chunk_text=description,
                    entry_condition=item.get("entry_condition", ""),
                    confirmation_signal=item.get("confirmation_signal", ""),
                    stop_loss_rule=item.get("stop_loss_rule", ""),
                    target_exit_rule=item.get("target_exit_rule", ""),
                    invalidation_condition=item.get("invalidation_condition", ""),
                    risk_reward=item.get("risk_reward", ""),
                    position_sizing=item.get("position_sizing", ""),
                    psychology_note=item.get("psychology_note", ""),
                    edge_description=item.get("edge_description", description[:200] if description else ""),
                    confluence_factors=item.get("confluence_factors", keywords[:5] if isinstance(keywords, list) else []),
                    keywords=keywords if isinstance(keywords, list) else [],
                    transcript_evidence=item.get("transcript_evidence", ""),
                    start_timestamp="",
                    end_timestamp="",
                    source_section=source_name,
                    author_concept=False,
                    confidence=float(item.get("confidence", 0.7)),
                )
                chunks.append(chunk)

        print(f"  Loaded {len(data)} chunks from {os.path.basename(path)}")

    return chunks


def build_metadata(chunk: StrategyChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "setup_name": chunk.setup_name,
        "setup_type": chunk.setup_type,
        "timeframe": chunk.timeframe,
        "market_condition": chunk.market_condition,
        "strategy_style": chunk.strategy_style,
        "channel_name": chunk.channel_name,
        "video_title": chunk.video_title,
        "risk_reward": chunk.risk_reward,
        "keywords": ",".join(chunk.keywords),
        "assets": ",".join(chunk.assets_applicable),
        "author_concept": str(chunk.author_concept),
    }


def main():
    chunks = load_all_chunks()
    print(f"Loaded {len(chunks)} chunks from strategy/")

    simple_chunks = load_simple_chunks()
    print(f"Loaded {len(simple_chunks)} chunks from source_data/")
    chunks.extend(simple_chunks)
    print(f"Total chunks to ingest: {len(chunks)}")

    client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))

    existing_collections = client.list_collections()
    existing_names = [c.name for c in existing_collections]
    if COLLECTION_NAME in existing_names:
        print(f"Removing existing collection '{COLLECTION_NAME}'")
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    texts = [text_for_embedding(c) for c in chunks]
    metadatas = [build_metadata(c) for c in chunks]
    ids = [f"{c.source_section}_{c.chunk_id}_{i}" for i, c in enumerate(chunks)]

    batch_size = 32
    for i in range(0, len(chunks), batch_size):
        batch_end = min(i + batch_size, len(chunks))
        collection.add(
            documents=texts[i:batch_end],
            metadatas=metadatas[i:batch_end],
            ids=ids[i:batch_end],
        )
        print(f"  Ingested {batch_end}/{len(chunks)} chunks")

    print(f"\nDone. {collection.count()} vectors in ChromaDB at {DB_DIR}")


if __name__ == "__main__":
    main()
