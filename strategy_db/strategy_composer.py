"""
Phase 1.2: Strategy Composer — Group ChromaDB chunks into complete strategy blueprints.

Groups chunks by:
1. Natural groups (same video_title → coherent system)
2. Orphan matching (keyword overlap + complementary setup_types)

Outputs strategy_db/strategy_blueprints.json
"""

import json
import os
import re
from collections import defaultdict, Counter

INVENTORY_PATH = os.path.join(os.path.dirname(__file__), "vector_inventory.json")
BLUEPRINTS_PATH = os.path.join(os.path.dirname(__file__), "strategy_blueprints.json")


def load_inventory() -> dict:
    with open(INVENTORY_PATH) as f:
        return json.load(f)


def tokenize_keywords(kw_str: str) -> set:
    """Split and normalize keywords into a set."""
    if not kw_str:
        return set()
    tokens = set()
    for part in kw_str.split(","):
        part = part.strip().lower().replace(" ", "_")
        if part and len(part) > 1:
            tokens.add(part)
    return tokens


def jaccard_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def keyword_overlap_score(a_keywords: str, b_keywords: str) -> float:
    """Score how related two chunks are by keyword similarity."""
    return jaccard_similarity(tokenize_keywords(a_keywords), tokenize_keywords(b_keywords))


COMPLEMENTARY_PAIRS = {
    "entry": {"exit", "filter", "confirmation", "risk_management"},
    "exit": {"entry", "filter", "risk_management"},
    "filter": {"entry", "exit", "confirmation"},
    "confirmation": {"entry", "filter"},
    "risk_management": {"entry", "exit", "position_sizing"},
    "position_sizing": {"risk_management", "entry"},
}

SETUP_TYPE_WEIGHTS = {
    "entry": 4,
    "exit": 3,
    "risk_management": 2,
    "filter": 2,
    "confirmation": 2,
    "position_sizing": 2,
    "session_filter": 2,
    "market_structure": 1,
    "psychology": 1,
    "trade_management": 1,
    "philosophy": 0,
}


def extract_strategy_name(video_title: str, chunks: list) -> str:
    """Derive a short strategy name from video title or chunk content."""
    if video_title and video_title not in ("not specified", "no_video"):
        name = video_title
        name = re.sub(r"\s*—.*$", "", name)
        name = re.sub(r"\s*\|.*$", "", name)
        name = re.sub(r"\s*\(.*?\)\s*$", "", name)
        name = name.strip()
        if len(name) > 60:
            name = name[:57] + "..."
        return name

    # Fallback: combine entry names
    entry_names = [
        c["setup_name"] for c in chunks if c["setup_type"] == "entry"
    ]
    if entry_names:
        combined = " + ".join(entry_names[:3])
        if len(combined) > 70:
            combined = combined[:67] + "..."
        return combined

    return "ComposedStrategy"


def score_blueprint(chunks: list) -> dict:
    """Score a group of chunks as a complete strategy blueprint."""
    types_present = Counter(c["setup_type"] for c in chunks)
    total_weight = sum(SETUP_TYPE_WEIGHTS.get(t, 0) for t in types_present)

    completeness = 0
    if types_present.get("entry", 0) > 0:
        completeness += 4
    if types_present.get("exit", 0) > 0:
        completeness += 3
    if types_present.get("filter", 0) > 0:
        completeness += 2
    if types_present.get("risk_management", 0) > 0:
        completeness += 2
    if completeness >= 9:
        tier_label = "full"
    elif completeness >= 6:
        tier_label = "partial"
    else:
        tier_label = "fragment"

    # Keyword cohesion among non-psychology chunks
    keyword_sets = [
        tokenize_keywords(c["keywords"])
        for c in chunks
        if c["setup_type"] not in ("psychology", "philosophy")
    ]
    cohesion = 0.0
    if len(keyword_sets) > 1:
        scores = []
        for i in range(len(keyword_sets)):
            for j in range(i + 1, len(keyword_sets)):
                scores.append(jaccard_similarity(keyword_sets[i], keyword_sets[j]))
        cohesion = sum(scores) / len(scores) if scores else 0.0

    # Market condition alignment
    conditions = set(
        c["market_condition"] for c in chunks if c["market_condition"] and c["market_condition"] != "any"
    )
    alignment = 1.0 if len(conditions) <= 1 else 1.0 / len(conditions)

    return {
        "completeness_score": completeness,
        "tier": tier_label,
        "keyword_cohesion": round(cohesion, 3),
        "condition_alignment": round(alignment, 2),
        "total_weight": total_weight,
        "types_present": dict(types_present),
    }


def determine_tier(score: dict, chunks: list) -> str:
    """Determine implementation tier based on content."""
    keywords = set()
    for c in chunks:
        keywords.update(tokenize_keywords(c["keywords"]))

    chunk_text = " ".join(c.get("chunk_text_preview", "") for c in chunks).lower()

    # Tier 1: Rules-based TA indicators
    ta_indicators = {
        "rsi", "ema", "macd", "adx", "atr", "bollinger_bands", "sma", "ma",
        "stoch", "vwap", "squeeze", "breakout", "divergence", "crossover",
        "moving_average", "volume", "smoothed_ma",
    }
    has_ta = bool(keywords & ta_indicators) or any(
        ind in chunk_text for ind in ["rsi", "ema ", "macd", "adx", "atr", "bollinger"]
    )

    # Tier 2: Price action / structured patterns
    pa_patterns = {
        "engulfing", "fvg", "fair_value_gap", "order_block", "breaker_block",
        "liquidity", "sweep", "double_top", "double_bottom", "flag", "pennant",
        "support", "resistance", "trendline", "fibonacci", "candlestick",
        "pin_bar", "doji", "inside_bar",
    }
    has_pa = bool(keywords & pa_patterns) or any(
        p in chunk_text for p in ["engulf", "fvg", "order block", "liquidity sweep", "support", "resistance"]
    )

    # Tier 3: Subjective
    subjective = {"psychology", "discipline", "mindset", "philosophy"}
    has_subjective = bool(keywords & subjective)

    if has_ta and score["completeness_score"] >= 6:
        return "tier1"
    elif has_pa and score["completeness_score"] >= 4:
        return "tier2"
    elif has_subjective:
        return "tier3"
    elif score["completeness_score"] >= 4:
        return "tier2"
    else:
        return "tier3"


def build_natural_groups(records: list) -> list:
    """Group chunks by video_title — these are natural coherent strategies."""
    by_video = defaultdict(list)
    for r in records:
        video = r["video_title"] or "no_video"
        by_video[video].append(r)

    blueprints = []
    for video, chunks in by_video.items():
        if video in ("not specified", "no_video"):
            continue

        score = score_blueprint(chunks)
        tier = determine_tier(score, chunks)

        bp = {
            "strategy_id": f"N{len(blueprints) + 1:03d}",
            "name": extract_strategy_name(video, chunks),
            "source": "natural_group",
            "video_title": video,
            "channel": chunks[0].get("channel_name", ""),
            "components": {
                "entry": [c for c in chunks if c["setup_type"] == "entry"],
                "exit": [c for c in chunks if c["setup_type"] == "exit"],
                "filter": [c for c in chunks if c["setup_type"] in ("filter", "confirmation", "session_filter")],
                "risk_management": [c for c in chunks if c["setup_type"] in ("risk_management", "position_sizing")],
                "psychology": [c for c in chunks if c["setup_type"] in ("psychology", "philosophy")],
                "market_structure": [c for c in chunks if c["setup_type"] == "market_structure"],
                "trade_management": [c for c in chunks if c["setup_type"] == "trade_management"],
            },
            "score": score,
            "tier": tier,
            "total_chunks": len(chunks),
            "chunk_ids": [c["id"] for c in chunks],
        }
        blueprints.append(bp)

    return blueprints


def build_composed_groups(records: list, natural_ids: set) -> list:
    """
    Match orphaned chunks (not in natural groups) into composed strategies.

    Algorithm:
    1. Separate orphans by setup_type
    2. For each entry orphan, find best exit + filter + risk matches by keyword overlap
    3. Score each candidate group
    """
    orphans = [r for r in records if r["id"] not in natural_ids]

    by_type = defaultdict(list)
    for r in orphans:
        by_type[r["setup_type"] or "other"].append(r)

    entries = by_type.get("entry", [])
    exits = by_type.get("exit", [])
    filters = by_type.get("filter", []) + by_type.get("confirmation", [])
    risk = by_type.get("risk_management", []) + by_type.get("position_sizing", [])
    market_struct = by_type.get("market_structure", [])
    psych = by_type.get("psychology", [])

    used_ids = set()
    blueprints = []

    # For each entry, find best complementary matches
    for entry in entries:
        if entry["id"] in used_ids:
            continue

        components = {"entry": [entry]}
        used_ids.add(entry["id"])

        # Find best exit match
        best_exit = _best_match(entry, exits, used_ids)
        if best_exit:
            components["exit"] = [best_exit]
            used_ids.add(best_exit["id"])

        # Find best filter match
        best_filter = _best_match(entry, filters, used_ids)
        if best_filter:
            components["filter"] = [best_filter]
            used_ids.add(best_filter["id"])

        # Find best risk match
        best_risk = _best_match(entry, risk, used_ids)
        if best_risk:
            components["risk_management"] = [best_risk]
            used_ids.add(best_risk["id"])

        # Add any matching market_structure or psychology (lower priority)
        for pool, key in [(market_struct, "market_structure"), (psych, "psychology")]:
            match = _best_match(entry, pool, used_ids, min_score=0.05)
            if match:
                components.setdefault(key, []).append(match)
                used_ids.add(match["id"])

        all_chunks = []
        for v in components.values():
            all_chunks.extend(v)

        score = score_blueprint(all_chunks)
        tier = determine_tier(score, all_chunks)

        bp = {
            "strategy_id": f"C{len(blueprints) + 1:03d}",
            "name": extract_strategy_name("", all_chunks),
            "source": "composed",
            "video_title": "",
            "channel": "composed",
            "components": components,
            "score": score,
            "tier": tier,
            "total_chunks": len(all_chunks),
            "chunk_ids": [c["id"] for c in all_chunks],
        }
        blueprints.append(bp)

    # Remaining unmatched orphans → individual-concept blueprints (tier3)
    remaining = [r for r in orphans if r["id"] not in used_ids]
    for r in remaining:
        used_ids.add(r["id"])
        bp = {
            "strategy_id": f"S{len(blueprints) + 1:03d}",
            "name": r["setup_name"][:60] or r["id"],
            "source": "single",
            "video_title": "",
            "channel": r.get("channel_name", ""),
            "components": {r["setup_type"]: [r]},
            "score": {"completeness_score": 1, "tier": "fragment", "keyword_cohesion": 0, "condition_alignment": 0, "total_weight": 0, "types_present": {r["setup_type"]: 1}},
            "tier": "tier3",
            "total_chunks": 1,
            "chunk_ids": [r["id"]],
        }
        blueprints.append(bp)

    return blueprints


def _best_match(source, pool, used_ids, min_score=0.05):
    """Find best matching chunk from pool by keyword similarity."""
    source_kw = source.get("keywords", "") or ""
    best = None
    best_score = min_score

    for candidate in pool:
        if candidate["id"] in used_ids:
            continue
        score = keyword_overlap_score(source_kw, candidate.get("keywords", "") or "")
        # Bonus for same market condition
        if (source.get("market_condition") and candidate.get("market_condition") and
                source["market_condition"] == candidate["market_condition"] and
                source["market_condition"] not in ("any", "")):
            score += 0.15
        # Bonus for same strategy style
        if (source.get("strategy_style") and candidate.get("strategy_style") and
                source["strategy_style"] == candidate["strategy_style"] and
                source["strategy_style"] not in ("any", "not specified", "")):
            score += 0.1
        # Bonus for same channel
        if (source.get("channel_name") and candidate.get("channel_name") and
                source["channel_name"] == candidate["channel_name"] and
                source["channel_name"] not in ("not specified", "")):
            score += 0.1

        if score > best_score:
            best_score = score
            best = candidate

    return best


def main():
    inventory = load_inventory()
    records = inventory["records"]

    print(f"Building blueprints from {len(records)} vectors...")

    # Phase 1: Natural groups from video titles
    natural = build_natural_groups(records)
    natural_ids = set()
    for bp in natural:
        natural_ids.update(bp["chunk_ids"])

    print(f"  Natural groups (by video): {len(natural)}")
    print(f"  Chunks in natural groups: {len(natural_ids)}")

    # Phase 2: Composed groups from orphans
    composed = build_composed_groups(records, natural_ids)
    print(f"  Composed groups: {len(composed)}")

    # Combine
    all_blueprints = natural + composed

    # Summary stats
    tier_counts = Counter(bp["tier"] for bp in all_blueprints)
    source_counts = Counter(bp["source"] for bp in all_blueprints)
    completeness_counts = Counter(bp["score"]["tier"] for bp in all_blueprints)

    output = {
        "total_blueprints": len(all_blueprints),
        "total_chunks_used": sum(bp["total_chunks"] for bp in all_blueprints),
        "total_chunks_available": len(records),
        "summary": {
            "by_tier": dict(tier_counts),
            "by_source": dict(source_counts),
            "by_completeness": dict(completeness_counts),
        },
        "blueprints": all_blueprints,
    }

    with open(BLUEPRINTS_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved to {BLUEPRINTS_PATH}")
    print(f"\n=== Summary ===")
    print(f"Total blueprints: {len(all_blueprints)}")
    print(f"By tier: {dict(tier_counts)}")
    print(f"By source: {dict(source_counts)}")
    print(f"By completeness: {dict(completeness_counts)}")

    # Show first few blueprints
    print(f"\n=== Sample Blueprints ===")
    for bp in all_blueprints[:5]:
        comp = bp["components"]
        has = {k: len(v) for k, v in comp.items() if v}
        print(f"  {bp['strategy_id']}: {bp['name'][:50]:50s} [{bp['tier']:5s}] {has}")
    print(f"  ... and {len(all_blueprints) - 5} more")


if __name__ == "__main__":
    main()
