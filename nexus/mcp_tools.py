"""
NEXUS MCP Tool Definitions — exposes bridge functions as callable MCP tools.

Register these tools with NEXUS MCP tool registry for use by agents
and the adaptive-imagining-cat broker.
"""

from typing import Any

# ── Tool Definitions (JSON Schema for MCP registry) ──────────────

TOOL_DEFINITIONS = [
    {
        "name": "trade_status",
        "description": "Get current trading status: positions, PnL, circuit breaker tier, risk score, agent health",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "execute_backtest",
        "description": "Run a walkforward backtest for a strategy on a pair over a date range",
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": "Strategy name (e.g. 'ensemble_strat_v1')"},
                "pair": {"type": "string", "description": "Trading pair (e.g. 'BTC/USDT')"},
                "timerange": {"type": "string", "description": "Date range (e.g. '20240101-20240601')"},
            },
            "required": ["strategy"],
        },
    },
    {
        "name": "adjust_config",
        "description": "Adjust a runtime configuration parameter (max_drawdown_pct, max_trades_per_day, max_leverage, risk_tier)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Config key: max_drawdown_pct, max_trades_per_day, max_leverage, or risk_tier",
                },
                "value": {"type": "string", "description": "New value for the config key"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "feed_trade_outcome",
        "description": "Feed a completed trade outcome to NEXUS Thompson Sampling learning loop",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pair": {"type": "string", "description": "Trading pair"},
                "side": {"type": "string", "description": "Buy or sell"},
                "pnl_pct": {"type": "number", "description": "P&L percentage"},
                "win": {"type": "boolean", "description": "Whether the trade was profitable"},
                "strategy": {"type": "string", "description": "Strategy name used"},
                "trade_id": {"type": "string", "description": "Optional trade identifier"},
            },
            "required": ["pair", "pnl_pct"],
        },
    },
    {
        "name": "query_strategies",
        "description": "Search the ChromaDB trading strategy knowledge base (592 YouTube strategy chunks) semantically",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Semantic search query (e.g. 'liquidity trap with 1:3 R:R')"},
                "top_k": {"type": "integer", "description": "Number of results (default 5)"},
                "setup_type": {"type": "string", "description": "Filter by setup type (entry, exit, risk_management, psychology, etc.)"},
                "market_condition": {"type": "string", "description": "Filter by market condition (trending, ranging, volatile, reversal)"},
                "keyword": {"type": "string", "description": "Filter by keyword (breakout, momentum, reversal, etc.)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_learning_status",
        "description": "Check ChromaDB learning loop status: collection size, outcome history, win rates",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "record_learning_outcome",
        "description": "Record a trade outcome into the ChromaDB learning loop outcome history",
        "inputSchema": {
            "type": "object",
            "properties": {
                "setup_name": {"type": "string", "description": "Setup/strategy name"},
                "pair": {"type": "string", "description": "Trading pair"},
                "side": {"type": "string", "description": "Buy or sell"},
                "pnl_pct": {"type": "number", "description": "P&L percentage"},
                "exit_reason": {"type": "string", "description": "Exit reason (stop_loss, take_profit, etc.)"},
            },
            "required": ["setup_name", "pair", "pnl_pct"],
        },
    },
    {
        "name": "skill_manage",
        "description": "Manage registered skills: list, get, add, remove, update",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "add", "remove", "update"],
                    "description": "Action to perform",
                },
                "name": {"type": "string", "description": "Skill name"},
                "description": {"type": "string", "description": "Skill description"},
                "category": {"type": "string", "description": "Skill category"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "session_search",
        "description": "Search session memory for previous context by keyword",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "user_preferences",
        "description": "Get, set, delete user preferences",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "set", "delete", "list"],
                    "description": "Action to perform",
                },
                "key": {"type": "string", "description": "Preference key"},
                "value": {"type": "string", "description": "Preference value (for set action)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "cluster_affinities",
        "description": "Get learned cluster affinity scores based on outcome history",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "thompson_stats",
        "description": "Get Thompson sampling statistics: tracked skills, win rates, scores",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "reflection_stats",
        "description": "Get self-reflection statistics: failures, fixes, alternatives",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "regime_aware_search",
        "description": "Search strategies with HMM-detected current market regime + outcome-weighted ranking",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Strategy search query"},
                "pair": {"type": "string", "description": "Trading pair (default: BTC/USDT)"},
                "timeframe": {"type": "string", "description": "Candle timeframe (default: 1h)"},
                "top_k": {"type": "integer", "description": "Number of results (default: 8)"},
                "outcome_weight": {"type": "number", "description": "Outcome vs cosine weight (0.0-1.0, default: 0.3)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "regime_detect",
        "description": "Detect current market regime for a trading pair using HMM",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pair": {"type": "string", "description": "Trading pair (default: BTC/USDT)"},
                "timeframe": {"type": "string", "description": "Candle timeframe (default: 1h)"},
            },
        },
    },
]


def get_tool_definitions() -> list[dict]:
    return TOOL_DEFINITIONS


# ── Tool Handlers ─────────────────────────────────────────────────

def handle_tool_call(name: str, arguments: dict) -> dict:
    from nexus.bridge import get_bridge

    bridge = get_bridge()

    if name == "trade_status":
        return bridge.trade_status()

    if name == "execute_backtest":
        return bridge.execute_backtest(
            strategy=arguments["strategy"],
            pair=arguments.get("pair", "BTC/USDT"),
            timerange=arguments.get("timerange", "20240101-20240601"),
        )

    if name == "adjust_config":
        return bridge.adjust_config(
            key=arguments["key"],
            value=arguments["value"],
        )

    if name == "query_strategies":
        return bridge.query_strategies(
            query=arguments["query"],
            top_k=arguments.get("top_k", 5),
            setup_type=arguments.get("setup_type"),
            market_condition=arguments.get("market_condition"),
            keyword=arguments.get("keyword"),
        )

    if name == "feed_trade_outcome":
        pnl = arguments.get("pnl_pct", 0)
        trade = {
            "pair": arguments.get("pair", "unknown"),
            "side": arguments.get("side", "buy"),
            "pnl_pct": pnl,
            "win": arguments.get("win", pnl > 0),
            "strategy": arguments.get("strategy", "unknown"),
            "trade_id": arguments.get("trade_id", ""),
        }
        bridge.feed_outcome_to_nexus(trade)
        bridge.record_coach_outcome(trade)
        return {"success": True, "fed_to": ["nexus_thompson", "coach"]}

    if name == "check_learning_status":
        return _check_learning_status()

    if name == "record_learning_outcome":
        return _record_learning_outcome(arguments)

    if name == "skill_manage":
        return _handle_skill_manage(arguments)

    if name == "session_search":
        from nexus.session_memory import search_sessions
        return {"results": search_sessions(arguments.get("query", ""), arguments.get("limit", 10))}

    if name == "user_preferences":
        return _handle_user_preferences(arguments)

    if name == "cluster_affinities":
        from nexus.cluster_affinity import get_cluster_affinities
        return {"affinities": get_cluster_affinities()}

    if name == "thompson_stats":
        from nexus.thompson_local import get_thompson_stats
        return get_thompson_stats()

    if name == "reflection_stats":
        from nexus.self_reflection import get_failure_stats
        return get_failure_stats()

    if name == "regime_aware_search":
        from strategy_db.search import regime_aware_search as _ras
        return _ras(
            query=arguments["query"],
            pair=arguments.get("pair", "BTC/USDT"),
            timeframe=arguments.get("timeframe", "1h"),
            top_k=arguments.get("top_k", 8),
            outcome_weight=arguments.get("outcome_weight", 0.3),
        )

    if name == "regime_detect":
        from strategy_db.regime_detector_hmm import HMMRegimeDetector, DATA_PATH
        import pandas as pd
        detector = HMMRegimeDetector()
        pair = arguments.get("pair", "BTC/USDT")
        timeframe = arguments.get("timeframe", "1h")
        safe_pair = pair.replace("/", "_")
        fname = DATA_PATH / safe_pair / f"{timeframe}.feather"
        if not fname.exists():
            return {"error": f"No OHLCV data for {pair} {timeframe} at {fname}"}
        df = pd.read_feather(fname)
        if len(df) < 50:
            return {"error": f"Insufficient data: {len(df)} candles"}
        regime, metrics = detector.predict(df, lookback=len(df))
        return {"regime": regime, "metrics": metrics}

    return {"error": f"Unknown tool: {name}"}


def _check_learning_status() -> dict:
    from knowledge.learning_loop import LearningLoop
    loop = LearningLoop()
    try:
        loop._lazy_init()
    except Exception as e:
        return {"error": f"Learning loop init failed: {e}", "chroma_available": False}
    return {
        "collection": loop._collection_name if hasattr(loop, "_collection_name") else "trading_strategies",
        "count": loop._collection.count() if hasattr(loop, "_collection") and loop._collection else 0,
    }


def _handle_skill_manage(args: dict) -> dict:
    from nexus.skill_manager import list_skills, get_skill, add_skill, remove_skill, update_skill
    action = args.get("action", "list")
    if action == "list":
        return {"skills": list_skills()}
    if action == "get":
        skill = get_skill(args.get("name", ""))
        if skill:
            return {"skill": skill}
        return {"error": f"Skill '{args.get('name')}' not found"}
    if action == "add":
        return add_skill(
            name=args.get("name", ""),
            description=args.get("description", ""),
            category=args.get("category", "general"),
        )
    if action == "remove":
        return remove_skill(args.get("name", ""))
    if action == "update":
        return update_skill(args.get("name", ""), description=args.get("description"))
    return {"error": f"Unknown action: {action}"}


def _handle_user_preferences(args: dict) -> dict:
    from nexus.user_preferences import get, set, delete, list_keys, get_all
    action = args.get("action", "list")
    if action == "list":
        return {"keys": list_keys()}
    if action == "get":
        return {"value": get(args.get("key"))}
    if action == "set":
        return set(args.get("key", ""), args.get("value", ""))
    if action == "delete":
        return delete(args.get("key", ""))
    return {"error": f"Unknown action: {action}"}


def _record_learning_outcome(args: dict) -> dict:
    from knowledge.learning_loop import LearningLoop
    from knowledge.trade_encoder import encode_trade_outcome
    loop = LearningLoop()
    record = encode_trade_outcome(
        setup_name=args["setup_name"],
        pair=args["pair"],
        side=args.get("side", "buy"),
        pnl_pct=args["pnl_pct"],
        exit_reason=args.get("exit_reason", ""),
    )
    try:
        loop._record_outcome(record)
        return {"success": True, "recorded": record}
    except Exception as e:
        return {"success": False, "error": str(e)}
