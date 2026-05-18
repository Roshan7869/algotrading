#!/usr/bin/env python3
"""
Gcode Harness Bridge — Strategy Knowledge Base

Call this from Gcode during a session to query the trading strategy vector DB.
Gcode invokes via bash tool: python3 strategy_db/gcode_bridge.py <args>

Usage within Gcode:
  python3 strategy_db/gcode_bridge.py query "mean reversion setups"
  python3 strategy_db/gcode_bridge.py query --setup-type entry --keyword breakout
  python3 strategy_db/gcode_bridge.py list-types
  python3 strategy_db/gcode_bridge.py list-conditions
  python3 strategy_db/gcode_bridge.py get "Liquidity Trap"

Output is JSON for easy parsing by the agent.
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from search import search, list_setup_types, list_market_conditions
from outcome_sync import sync_to_chromadb, compute_setup_win_rates, load_chunk_stats


def cmd_query(args):
    results = search(
        query=args.query,
        top_k=args.top_k,
        setup_type=args.setup_type,
        market_condition=args.market_condition,
        keyword=args.keyword,
    )
    print(json.dumps({"status": "ok", "count": len(results), "results": results}, indent=2))


def cmd_list_types(_args):
    types = list_setup_types()
    print(json.dumps({"status": "ok", "types": types}, indent=2))


def cmd_list_conditions(_args):
    conds = list_market_conditions()
    print(json.dumps({"status": "ok", "conditions": conds}, indent=2))


def cmd_get(args):
    results = search(query=args.setup_name, top_k=5)
    exact = [r for r in results if args.setup_name.lower() in r["setup_name"].lower()]
    if exact:
        print(json.dumps({"status": "ok", "count": len(exact), "results": exact}, indent=2))
    elif results:
        print(json.dumps({"status": "ok", "count": len(results), "results": results, "note": "Exact match not found; showing closest"}, indent=2))
    else:
        print(json.dumps({"status": "not_found", "message": f"No strategy found matching '{args.setup_name}'"}, indent=2))


def cmd_outcome_sync(_args):
    result = sync_to_chromadb(verbose=False)
    print(json.dumps({"status": "ok", "synced": result["synced"], "skipped": result["skipped"], "errors": result["errors"], "win_rates": result["win_rates"]}, indent=2))


def cmd_setup_performance(_args):
    win_rates = compute_setup_win_rates()
    print(json.dumps({"status": "ok", "setups": win_rates}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Gcode strategy knowledge bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", help="Semantic search strategies")
    q.add_argument("query", help="Natural language query")
    q.add_argument("--setup-type", help="Filter by setup type")
    q.add_argument("--market-condition", help="Filter by market condition")
    q.add_argument("--keyword", help="Filter by keyword")
    q.add_argument("--top-k", type=int, default=5)

    g = sub.add_parser("get", help="Find a specific strategy by name")
    g.add_argument("setup_name", help="Strategy name to find")

    sub.add_parser("list-types", help="List all setup types")
    sub.add_parser("list-conditions", help="List all market conditions")

    sub.add_parser("outcome-sync", help="Sync trade outcomes to ChromaDB metadata")
    sub.add_parser("setup-performance", help="Show setup win rates from outcome history")

    parsed = parser.parse_args()
    cmds = {
        "query": cmd_query,
        "get": cmd_get,
        "list-types": cmd_list_types,
        "list-conditions": cmd_list_conditions,
        "outcome-sync": cmd_outcome_sync,
        "setup-performance": cmd_setup_performance,
    }
    cmds[parsed.command](parsed)


if __name__ == "__main__":
    main()
