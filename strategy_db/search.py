import chromadb
from chromadb.config import Settings

from config import DB_DIR, COLLECTION_NAME, TOP_K_DEFAULT


_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    _client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))
    _collection = _client.get_collection(name=COLLECTION_NAME)
    return _collection


def search(
    query: str,
    top_k: int = TOP_K_DEFAULT,
    setup_type: str | None = None,
    market_condition: str | None = None,
    keyword: str | None = None,
    min_confidence: float | None = None,
) -> list[dict]:
    collection = _get_collection()

    where_filters = []
    if setup_type:
        where_filters.append({"setup_type": {"$eq": setup_type}})
    if market_condition:
        where_filters.append({"market_condition": {"$eq": market_condition}})
    if keyword:
        where_filters.append({"keywords": {"$contains": keyword}})

    where = None
    if len(where_filters) == 1:
        where = where_filters[0]
    elif len(where_filters) > 1:
        where = {"$and": where_filters}

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where,
    )

    output = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]
        dist = results["distances"][0][i]
        output.append({
            "id": results["ids"][0][i],
            "score": round(1.0 - dist, 4),
            "setup_name": meta.get("setup_name", ""),
            "setup_type": meta.get("setup_type", ""),
            "timeframe": meta.get("timeframe", ""),
            "market_condition": meta.get("market_condition", ""),
            "strategy_style": meta.get("strategy_style", ""),
            "channel_name": meta.get("channel_name", ""),
            "video_title": meta.get("video_title", ""),
            "risk_reward": meta.get("risk_reward", ""),
            "keywords": meta.get("keywords", ""),
            "assets": meta.get("assets", ""),
            "author_concept": meta.get("author_concept", ""),
            "chunk_text": doc,
        })
    return output


def list_setup_types() -> list[str]:
    collection = _get_collection()
    all_meta = collection.get(include=["metadatas"])
    types = set()
    for m in all_meta["metadatas"]:
        if m.get("setup_type"):
            types.add(m["setup_type"])
    return sorted(types)


def list_market_conditions() -> list[str]:
    collection = _get_collection()
    all_meta = collection.get(include=["metadatas"])
    conds = set()
    for m in all_meta["metadatas"]:
        if m.get("market_condition"):
            conds.add(m["market_condition"])
    return sorted(conds)
