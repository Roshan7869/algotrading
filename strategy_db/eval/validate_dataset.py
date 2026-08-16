#!/usr/bin/env python3
"""Validate ChromaDB eval dataset self-consistency.

Checks:
1. All gold_chunk_ids exist in ChromaDB collection
2. No duplicate query_ids
3. Stratification coverage
4. All setup_types are valid
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / 'Downloads/Algotrading'))
from strategy_db.search import _get_collection

VALID_SETUP_TYPES = {
    "entry", "exit", "confirmation", "risk_management", "market_structure",
    "psychology", "position_sizing", "trade_management", "philosophy",
    "filter", "session_filter",
}

def validate(dataset_path: str) -> dict:
    with open(dataset_path) as f:
        data = json.load(f)

    errors = []
    warnings = []

    # Check 1: No duplicate query_ids
    qids = [d["query_id"] for d in data]
    if len(qids) != len(set(qids)):
        dupes = [q for q in qids if qids.count(q) > 1]
        errors.append(f"Duplicate query_ids: {set(dupes)}")

    # Check 2: All gold_chunk_ids exist in ChromaDB
    collection = _get_collection()
    all_meta = collection.get(include=["metadatas", "documents"])
    existing_names = set()
    for m, doc in zip(all_meta["metadatas"], all_meta["documents"]):
        if m and m.get("setup_name"):
            existing_names.add(m["setup_name"])
        if doc:
            existing_names.add(doc)

    missing = set()
    for d in data:
        for chunk_id in d.get("gold_chunk_ids", d.get("relevant_chunk_ids", [])):
            if chunk_id not in existing_names:
                missing.add(chunk_id)

    if missing:
        errors.append(f"{len(missing)} gold_chunk_ids not found in ChromaDB: {list(missing)[:10]}...")

    # Check 3: Valid setup_types
    invalid_types = set()
    for d in data:
        if d.get("setup_type") not in VALID_SETUP_TYPES:
            invalid_types.add(d.get("setup_type"))
    if invalid_types:
        errors.append(f"Invalid setup_types: {invalid_types}")

    # Check 4: Stratification
    from collections import Counter
    st = Counter(d["setup_type"] for d in data)
    mc = Counter(d.get("market_condition", "any") for d in data)

    if min(st.values()) < 5:
        under = {k: v for k, v in st.items() if v < 5}
        warnings.append(f"Under-represented setup_types (< 5): {under}")

    # Check 5: All required fields present
    required = {"query_id", "query", "relevant_chunk_ids", "setup_type", "difficulty"}
    for d in data:
        for field in required:
            if field not in d:
                errors.append(f"Missing field '{field}' in {d.get('query_id', 'unknown')}")
                break

    return {
        "total_queries": len(data),
        "errors": errors,
        "warnings": warnings,
        "setup_type_distribution": dict(st),
        "market_condition_distribution": dict(mc),
        "missing_chunk_ids": len(missing),
        "valid": len(errors) == 0,
    }


if __name__ == "__main__":
    dataset = str(Path.home() / 'Downloads/Algotrading/strategy_db/eval/eval_dataset.json')
    result = validate(dataset)

    print(f"Validation Results:")
    print(f"  Total queries: {result['total_queries']}")
    print(f"  Valid: {result['valid']}")

    if result['errors']:
        print(f"\n  ERRORS ({len(result['errors'])}):")
        for e in result['errors']:
            print(f"    ❌ {e}")

    if result['warnings']:
        print(f"\n  WARNINGS ({len(result['warnings'])}):")
        for w in result['warnings']:
            print(f"    ⚠️  {w}")

    print(f"\n  Setup types: {result['setup_type_distribution']}")
    print(f"  Market conditions: {result['market_condition_distribution']}")

    if result['valid']:
        print("\n✅ Dataset is self-consistent")
    else:
        print(f"\n❌ {len(result['errors'])} errors found")
        sys.exit(1)
