#!/usr/bin/env python3
"""
Strategy Knowledge Base — Semantic Query Tool

Usage:
  python strategy_db/query.py "find mean reversion setups with 2:1 R:R"
  python strategy_db/query.py "liquidity trap" --setup-type market_structure
  python strategy_db/query.py "breakout" --keyword momentum --top-k 10
  python strategy_db/query.py --list-types
  python strategy_db/query.py --list-conditions
"""

import argparse
import json

from search import search, list_setup_types, list_market_conditions


def format_result(r: dict, i: int) -> str:
    return (
        f"\n{'─' * 60}"
        f"\n[{i}] {r['setup_name']}  (score: {r['score']})"
        f"\n    Type: {r['setup_type']}  |  Timeframe: {r['timeframe']}"
        f"\n    Condition: {r['market_condition']}  |  Style: {r['strategy_style']}"
        f"\n    Risk/Reward: {r['risk_reward']}"
        f"\n    Keywords: {r['keywords']}"
        f"\n    Channel: {r['channel_name']}"
        f"\n    Video: {r['video_title']}"
        f"\n    {r['chunk_text'][:300]}..."
    )


def main():
    parser = argparse.ArgumentParser(description="Semantic search over trading strategy knowledge base")
    parser.add_argument("query", nargs="?", help="Natural language search query")
    parser.add_argument("--setup-type", help="Filter by setup type")
    parser.add_argument("--market-condition", help="Filter by market condition")
    parser.add_argument("--keyword", help="Filter by keyword")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--list-types", action="store_true", help="List available setup types")
    parser.add_argument("--list-conditions", action="store_true", help="List available market conditions")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.list_types:
        types = list_setup_types()
        print("Available setup types:")
        for t in types:
            print(f"  • {t}")
        return

    if args.list_conditions:
        conds = list_market_conditions()
        print("Available market conditions:")
        for c in conds:
            print(f"  • {c}")
        return

    if not args.query:
        parser.print_help()
        return

    results = search(
        query=args.query,
        top_k=args.top_k,
        setup_type=args.setup_type,
        market_condition=args.market_condition,
        keyword=args.keyword,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    elif results:
        print(f"\nFound {len(results)} matching strategies:")
        for i, r in enumerate(results, 1):
            print(format_result(r, i))
    else:
        print("No matching strategies found.")


if __name__ == "__main__":
    main()
