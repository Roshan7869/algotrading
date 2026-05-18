#!/usr/bin/env python3
"""
Strategy Knowledge Base — MCP Server

Exposes the ChromaDB trading strategy vector database as MCP tools
for AI agents (Gcode, Hermes, Claude Code, etc.).

Tools:
  query_strategies       - Semantic search across strategy chunks
  get_strategy           - Find a specific strategy by name
  list_setup_types       - List all available setup types
  list_market_conditions - List all market condition categories
  strategy_stats         - DB statistics (chunk count, types, sources)
  regime_detect          - Detect market regime for a pair using HMM
  strategy_context       - Get regime-adapted strategy context (adaptive scoring)
  outcome_sync           - Sync trade outcomes to ChromaDB chunk metadata
  sentiment_query        - Query news sentiment from FinBERT pipeline

Usage:
  python3 strategy_db/mcp_server.py

Registered in Hermes config.yaml as:
  mcp_servers:
    strategy-kb:
      command: /usr/bin/python3
      args: [strategy_db/mcp_server.py]
      enabled: true
"""

import json
import sys
import os

# Ensure strategy_db is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from search import search, list_setup_types, list_market_conditions, _get_collection
from config import DB_DIR, COLLECTION_NAME

# Create MCP server
app = Server("strategy-kb")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_strategies",
            description=(
                "Semantic search across trading strategy chunks in the vector database. "
                "Returns matching strategies with setup details, entry/exit rules, "
                "risk management, and psychology notes. Supports filtering by setup type, "
                "market condition, and keyword."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query describing the trading concept or setup you're looking for. "
                                        "Examples: 'absorption squeeze setup', 'risk management for scalping', "
                                        "'how to enter on break of compression', 'CVD divergence for exit'",
                    },
                    "setup_type": {
                        "type": "string",
                        "description": "Filter by strategy category. One of: entry, exit, confirmation, risk_management, "
                                        "market_structure, psychology, position_sizing, trade_management, philosophy",
                    },
                    "market_condition": {
                        "type": "string",
                        "description": "Filter by market condition. One of: trending, ranging, ranging_to_trending, any",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Filter by keyword tag (e.g., 'CVD', 'absorption', 'breakout', 'LVN', 'scalping')",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5, max: 20)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_strategy",
            description=(
                "Find a specific trading strategy by exact or fuzzy name match. "
                "Returns the full strategy chunk with all fields: entry condition, "
                "stop loss, target, psychology note, edge description, and transcript evidence."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Strategy name to search for. Supports partial/fuzzy matching. "
                                        "Examples: 'Risk to Zero', 'LVN Rebalance', 'compression squeeze'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of candidates to consider for fuzzy matching (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_setup_types",
            description=(
                "List all available strategy setup type categories in the database. "
                "Returns category names like: entry, exit, confirmation, risk_management, etc. "
                "Use these values for the setup_type filter in query_strategies."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_market_conditions",
            description=(
                "List all available market condition categories in the database. "
                "Returns condition names like: trending, ranging, ranging_to_trending, any. "
                "Use these values for the market_condition filter in query_strategies."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="strategy_stats",
            description=(
                "Get statistics about the strategy knowledge base: total chunk count, "
                "distribution by setup type, market condition, strategy style, channel/source, "
                "and unique keywords. Useful for understanding coverage and gaps."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="regime_detect",
            description=(
                "Detect the current market regime for a trading pair using the HMM regime detector. "
                "Loads the last 100 candles from local feather data, runs HMMRegimeDetector.predict(), "
                "and returns the regime label (trending_up, trending_down, ranging, volatile) with "
                "confidence metrics including regime probabilities, stability score, and volatility measures."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pair": {
                        "type": "string",
                        "description": "Trading pair in format like 'BTC/USDT' or 'BTC_USDT_USDT'. "
                                        "Examples: 'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT'",
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Candle timeframe. Supported: '1h', '4h'. Default: '1h'",
                        "default": "1h",
                    },
                },
                "required": ["pair"],
            },
        ),
        Tool(
            name="strategy_context",
            description=(
                "Get regime-adapted strategy context from ChromaDB, combining cosine similarity "
                "with outcome-weighted scores. Uses RegimeAwareQueryEngine.get_adaptive_strategy_context() "
                "to retrieve strategies tailored to the current market regime, ranked by an adaptive "
                "score that blends semantic relevance with historical win-rate performance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "regime": {
                        "type": "string",
                        "description": "Market regime label. One of: trending_up, trending_down, ranging, volatile",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of top strategy chunks to return (default: 8)",
                        "default": 8,
                    },
                    "outcome_weight": {
                        "type": "number",
                        "description": "Weight for outcome history vs cosine similarity (0.0-1.0). "
                                        "0.0 = pure cosine similarity, 1.0 = pure outcome history. Default: 0.3",
                        "default": 0.3,
                    },
                },
                "required": ["regime"],
            },
        ),
        Tool(
            name="outcome_sync",
            description=(
                "Sync trade outcome history from outcome_history.json into ChromaDB chunk metadata. "
                "Reads all recorded trade outcomes, computes per-chunk win rates and regime-specific "
                "performance, then updates ChromaDB chunk metadata with outcome_win_rate, "
                "outcome_avg_pnl_pct, outcome_avg_r_multiple, and outcome_regime_win_rates. "
                "Essential for closing the feedback loop between live trading and strategy retrieval."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="sentiment_query",
            description=(
                "Query the news sentiment pipeline for relevant news and sentiment analysis. "
                "Searches the FinBERT-powered news_sentiment ChromaDB collection for articles "
                "matching the query. Returns sentiment scores, headlines, sources, and relevance. "
                "Useful for gauging market sentiment before trade decisions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for news sentiment. "
                                        "Examples: 'BTC bullish rally', 'ETH regulation ban', "
                                        "'inflation macro impact crypto', 'SEC ETF approval'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of news results to return (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "query_strategies":
            results = search(
                query=arguments["query"],
                top_k=arguments.get("top_k", 5),
                setup_type=arguments.get("setup_type"),
                market_condition=arguments.get("market_condition"),
                keyword=arguments.get("keyword"),
            )
            # Truncate chunk_text for readability
            for r in results:
                if len(r.get("chunk_text", "")) > 500:
                    r["chunk_text_preview"] = r["chunk_text"][:500] + "..."
                    r["chunk_text_full"] = r["chunk_text"]
                    r["chunk_text"] = r["chunk_text_preview"]
                    del r["chunk_text_preview"]

            output = {
                "status": "ok",
                "count": len(results),
                "query": arguments["query"],
                "results": results,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "get_strategy":
            results = search(query=arguments["name"], top_k=arguments.get("top_k", 5))
            # Try exact match first
            name_lower = arguments["name"].lower()
            exact = [r for r in results if name_lower in r.get("setup_name", "").lower()]
            matched = exact if exact else results

            output = {
                "status": "ok" if matched else "not_found",
                "count": len(matched),
                "search_term": arguments["name"],
                "results": matched,
                "match_type": "exact" if exact else "semantic_fallback" if results else "none",
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "list_setup_types":
            types = list_setup_types()
            output = {"status": "ok", "setup_types": types, "count": len(types)}
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "list_market_conditions":
            conds = list_market_conditions()
            output = {"status": "ok", "market_conditions": conds, "count": len(conds)}
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "strategy_stats":
            collection = _get_collection()
            all_data = collection.get(include=["metadatas"])
            total = len(all_data["ids"])

            # Compute distributions
            type_dist = {}
            cond_dist = {}
            style_dist = {}
            channel_dist = {}
            kw_set = set()

            for m in all_data["metadatas"]:
                t = m.get("setup_type", "unknown")
                type_dist[t] = type_dist.get(t, 0) + 1
                c = m.get("market_condition", "unknown")
                cond_dist[c] = cond_dist.get(c, 0) + 1
                s = m.get("strategy_style", "unknown")
                style_dist[s] = style_dist.get(s, 0) + 1
                ch = m.get("channel_name", "unknown")
                channel_dist[ch] = channel_dist.get(ch, 0) + 1
                for kw in m.get("keywords", "").split(","):
                    kw = kw.strip()
                    if kw:
                        kw_set.add(kw)

            output = {
                "status": "ok",
                "total_chunks": total,
                "setup_type_distribution": dict(sorted(type_dist.items(), key=lambda x: -x[1])),
                "market_condition_distribution": dict(sorted(cond_dist.items(), key=lambda x: -x[1])),
                "strategy_style_distribution": dict(sorted(style_dist.items(), key=lambda x: -x[1])),
                "channel_distribution": dict(sorted(channel_dist.items(), key=lambda x: -x[1])),
                "unique_keywords_count": len(kw_set),
                "db_path": DB_DIR,
                "collection_name": COLLECTION_NAME,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "regime_detect":
            from regime_detector_hmm import HMMRegimeDetector, DATA_PATH

            pair_raw = arguments.get("pair", "BTC/USDT")
            timeframe = arguments.get("timeframe", "1h")

            # Normalize pair format: BTC/USDT -> BTC_USDT_USDT
            pair_normalized = pair_raw.replace("/", "_")
            if not pair_normalized.endswith("_USDT"):
                pair_normalized = pair_normalized + "_USDT"

            # Build feather file path
            feather_path = DATA_PATH / f"{pair_normalized}-{timeframe}-futures.feather"

            if not feather_path.exists():
                # Try alternative patterns
                alt_paths = [
                    DATA_PATH / f"{pair_normalized}-{timeframe}-futures.feather",
                    DATA_PATH / f"{pair_raw.replace('/', '_')}-{timeframe}-futures.feather",
                ]
                found = False
                for p in alt_paths:
                    if p.exists():
                        feather_path = p
                        found = True
                        break
                if not found:
                    # List available pairs for helpful error message
                    available = sorted(
                        f.stem.replace(f"-{timeframe}-futures", "")
                        for f in DATA_PATH.glob(f"*-{timeframe}-futures.feather")
                    )
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "message": f"No data file found for pair={pair_raw}, timeframe={timeframe}",
                        "searched_path": str(feather_path),
                        "available_pairs": available[:20],
                        "hint": "Use pair format like 'BTC/USDT' or 'BTC_USDT_USDT'",
                    }, indent=2))]

            # Load candles
            import pandas as pd
            df = pd.read_feather(str(feather_path))
            # Standardize column names to lowercase (same as load_btc_data)
            df.columns = [c.lower().replace("_", "").replace("-", "") for c in df.columns]

            # Take last 100 candles
            if len(df) > 100:
                df = df.tail(100).reset_index(drop=True)
            elif len(df) < 50:
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "message": f"Insufficient data: only {len(df)} candles available (need at least 50)",
                    "pair": pair_raw,
                    "timeframe": timeframe,
                }, indent=2))]

            # Run HMM prediction
            detector = HMMRegimeDetector()
            detector.load()
            regime, metrics = detector.predict(df, lookback=len(df))

            output = {
                "status": "ok",
                "pair": pair_raw,
                "timeframe": timeframe,
                "candles_used": len(df),
                "regime": regime,
                "confidence": metrics.get("regime_probs", {}),
                "metrics": metrics,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

        elif name == "strategy_context":
            from regime_query import RegimeAwareQueryEngine

            regime = arguments.get("regime", "ranging")
            top_k = arguments.get("top_k", 8)
            outcome_weight = arguments.get("outcome_weight", 0.3)

            valid_regimes = ["trending_up", "trending_down", "ranging", "volatile"]
            if regime not in valid_regimes:
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "message": f"Invalid regime '{regime}'. Must be one of: {valid_regimes}",
                }, indent=2))]

            engine = RegimeAwareQueryEngine()
            context = engine.get_adaptive_strategy_context(
                regime=regime,
                top_k=top_k,
                outcome_weight=outcome_weight,
            )

            output = {
                "status": "ok",
                "regime": regime,
                "top_k": top_k,
                "outcome_weight": outcome_weight,
                "context": context,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "outcome_sync":
            from regime_query import OutcomeTracker

            tracker = OutcomeTracker()
            result = tracker.update_chunk_scores_from_outcomes()

            output = {
                "status": "ok",
                "updated": result.get("updated", 0),
                "skipped": result.get("skipped", 0),
                "errors": result.get("errors", 0),
                "details_count": len(result.get("details", [])),
                "details": result.get("details", [])[:20],  # truncate for readability
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

        elif name == "sentiment_query":
            from news_pipeline import FinBERTNewsEmbedder

            query = arguments.get("query", "")
            top_k = arguments.get("top_k", 5)

            if not query:
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "message": "Query parameter is required",
                }, indent=2))]

            # Use shared ChromaDB client from search module
            client = _get_collection()._client
            embedder = FinBERTNewsEmbedder(client=client)
            results = embedder.query_relevant_news(query=query, top_k=top_k)

            if not results:
                output = {
                    "status": "ok",
                    "query": query,
                    "count": 0,
                    "results": [],
                    "message": "No news sentiment entries found. Try running the news pipeline first to ingest data.",
                }
            else:
                articles = []
                for r in results:
                    meta = r.get("metadata", {})
                    articles.append({
                        "headline": meta.get("headline", ""),
                        "source": meta.get("source", ""),
                        "sentiment_label": meta.get("sentiment_label", ""),
                        "sentiment_score": meta.get("sentiment_score", 0),
                        "method": meta.get("method", ""),
                        "impact_assets": meta.get("impact_assets", ""),
                        "categories": meta.get("categories", ""),
                        "hours_old": meta.get("hours_old", 0),
                        "relevance_decay": meta.get("relevance_decay", 0),
                        "distance": round(r.get("distance", 1.0), 4),
                    })
                output = {
                    "status": "ok",
                    "query": query,
                    "count": len(articles),
                    "results": articles,
                }

            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}, indent=2))]

    except Exception as e:
        import traceback
        return [TextContent(type="text", text=json.dumps({
            "error": str(e),
            "tool": name,
            "traceback": traceback.format_exc(),
        }, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())