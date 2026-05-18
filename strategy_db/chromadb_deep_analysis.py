#!/usr/bin/env python3
"""Deep analysis of ChromaDB contents - setup types, keywords, conditions, styles."""
import sys
sys.path.insert(0, "strategy_db")
from search import _get_collection
from collections import Counter, defaultdict

col = _get_collection()
results = col.get(include=["metadatas", "documents"])

type_keywords = defaultdict(Counter)
type_conditions = defaultdict(Counter)
type_styles = defaultdict(Counter)

for i in range(len(results["ids"])):
    meta = results["metadatas"][i]
    st = meta.get("setup_type", "?")
    mc = meta.get("market_condition", "?")
    ss = meta.get("strategy_style", "?")
    kw = meta.get("keywords", "")
    
    type_conditions[st][mc] += 1
    type_styles[st][ss] += 1
    if kw:
        for k in kw.split(","):
            k = k.strip()
            if k:
                type_keywords[st][k] += 1

for st in sorted(type_keywords.keys()):
    print("")
    print(f"=== {st.upper()} — Top 25 Keywords ===")
    for kw, cnt in type_keywords[st].most_common(25):
        print(f"  {kw:40s} {cnt:3d}x")
    print(f"  --- Market Conditions ---")
    for mc, cnt in type_conditions[st].most_common(5):
        print(f"  {mc:25s} {cnt:3d}x")
    print(f"  --- Strategy Styles ---")
    for ss, cnt in type_styles[st].most_common(5):
        print(f"  {ss:25s} {cnt:3d}x")

# Cross-reference: which setup_types have the most unique concepts?
print("")
print("=" * 80)
print("CONCEPT UNIQUENESS PER SETUP TYPE")
print("=" * 80)
for st in sorted(type_keywords.keys()):
    unique_kw = len(type_keywords[st])
    total_kw = sum(type_keywords[st].values())
    print(f"  {st:20s} — {unique_kw:4d} unique keywords, {total_kw:4d} total keyword refs, {type_conditions[st].total():4d} conditions span")