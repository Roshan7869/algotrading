#!/usr/bin/env python3
"""Deep dive into ChromaDB contents."""
import sys, json
sys.path.insert(0, "strategy_db")
from search import _get_collection

col = _get_collection()
results = col.get(include=["metadatas", "documents"])

sources = {}
for i in range(len(results["ids"])):
    meta = results["metadatas"][i]
    src = meta.get("source_name", "unknown")
    if src not in sources:
        sources[src] = {
            "count": 0,
            "source_type": meta.get("source_type", "?"),
            "channel": meta.get("channel_name", "?"),
            "setups": []
        }
    sources[src]["count"] += 1
    sources[src]["setups"].append({
        "name": meta.get("setup_name", "?"),
        "type": meta.get("setup_type", "?"),
        "condition": meta.get("market_condition", "?"),
        "kw": meta.get("keywords", "?"),
    })

sep = "=" * 80
for src, info in sorted(sources.items(), key=lambda x: -x[1]["count"]):
    print()
    print(sep)
    print(f"SOURCE: {src} ({info['count']} chunks)")
    print(f"  Type: {info['source_type']} | Channel: {info['channel']}")
    for c in info["setups"]:
        kws = c["kw"][:70] if c["kw"] else ""
        nm = c["name"][:55]
        print(f"  [{c['type']:18s}] {nm:55s} | mkt={c['condition']:20s} | kw={kws}")