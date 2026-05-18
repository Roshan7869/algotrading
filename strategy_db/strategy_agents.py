#!/usr/bin/env python3
"""
Hierarchical Query + Research Agent System for the Strategy Vector DB.

Architecture:
  Layer 1 — Router Agent:   Classifies query → structured search params
  Layer 2 — Research Agent: Hierarchical retrieval from ChromaDB
  Layer 3 — Synthesis Agent: Combines chunks → generates strategy code

Usage:
  python3 strategy_db/strategy_agents.py router "mean reversion for crypto"
  python3 strategy_db/strategy_agents.py research "liquidity trap with 1:3 RR"
  python3 strategy_db/strategy_agents.py synthesize "break and retest" --generate-code
  python3 strategy_db/strategy_agents.py pipeline "trend following with EMA cross" --generate-code
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

import chromadb
from chromadb.config import Settings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DB_DIR, COLLECTION_NAME

# ── LLM Integration (optional — falls back to rule-based classification) ──

_llm = None


def _get_llm():
    global _llm
    if _llm is not None:
        return _llm
    try:
        from langchain_ollama import ChatOllama
        import os
        model = os.environ.get("STRATEGY_LLM_MODEL", "deepseek-v4-flash:cloud")
        _llm = ChatOllama(
            model=model,
            temperature=0.1,
            num_predict=2048,
            timeout=15,
        )
        _llm.invoke("ping")
    except Exception:
        _llm = False
    return _llm


# ── ChromaDB ──

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    _client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))
    _collection = _client.get_collection(name=COLLECTION_NAME)
    return _collection


# ════════════════════════════════════════════════════════════════════
# LAYER 1 — ROUTER AGENT
# ════════════════════════════════════════════════════════════════════

@dataclass
class RoutedQuery:
    raw: str
    setup_type: Optional[str] = None
    market_condition: Optional[str] = None
    keyword: Optional[str] = None
    timeframe: Optional[str] = None
    min_score: float = 0.3
    top_k: int = 5
    intent: str = "research"
    explanation: str = ""

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


VALID_SETUP_TYPES = [
    "entry", "exit", "filter", "confirmation",
    "risk_management", "psychology", "market_structure", "trade_management",
]
VALID_CONDITIONS = [
    "trending", "ranging", "volatile", "reversal", "breakout", "any",
]
VALID_KEYWORDS = [
    "liquidity_trap", "breakout", "momentum", "reversal", "mean_reversion",
    "trend_following", "price_action", "support_resistance", "order_flow",
    "volume_profile", "fair_value_gap", "ICT",
]


def _rule_router(query: str) -> RoutedQuery:
    ql = query.lower()
    r = RoutedQuery(raw=query, top_k=5)

    if any(w in ql for w in ["entry", "enter", "buy", "sell", "long", "short", "signal"]):
        r.setup_type = "entry"
    elif any(w in ql for w in ["exit", "close", "cover", "take profit", "tp"]):
        r.setup_type = "exit"
    elif any(w in ql for w in ["filter", "avoid", "skip", "when not to"]):
        r.setup_type = "filter"
    elif any(w in ql for w in ["confirm", "confluence"]):
        r.setup_type = "confirmation"
    elif any(w in ql for w in ["risk", "stop loss", "position size", "drawdown", "capital"]):
        r.setup_type = "risk_management"
    elif any(w in ql for w in ["psychology", "mindset", "emotion", "discipline"]):
        r.setup_type = "psychology"
    elif any(w in ql for w in ["structure", "support", "resistance", "trend", "market"]):
        r.setup_type = "market_structure"
    elif any(w in ql for w in ["manage", "trail", "pyramid"]):
        r.setup_type = "trade_management"
    else:
        r.setup_type = None  # search all types

    if any(w in ql for w in ["trend", "trending", "follow"]):
        r.market_condition = "trending"
    elif any(w in ql for w in ["range", "ranging", "sideways", "consolidat"]):
        r.market_condition = "ranging"
    elif any(w in ql for w in ["reversal", "reject", "turn", "divergence"]):
        r.market_condition = "reversal"
    elif any(w in ql for w in ["breakout", "break out"]):
        r.market_condition = "breakout"
    elif any(w in ql for w in ["volatile", "volatility", "spike"]):
        r.market_condition = "volatile"

    for kw in VALID_KEYWORDS:
        if kw.replace("_", " ") in ql or kw in ql:
            r.keyword = kw
            break

    if "1:3" in ql or "1:2" in ql or "rr" in ql:
        r.min_score = 0.35

    r.explanation = f"Rule-routed: type={r.setup_type}, cond={r.market_condition}, kw={r.keyword}"
    return r


def router(query: str, use_llm: bool = True) -> RoutedQuery:
    if not use_llm:
        return _rule_router(query)

    llm = _get_llm()
    if not llm:
        return _rule_router(query)

    prompt = f"""Classify this trading query into structured search parameters.

Query: "{query}"

Return JSON with these optional fields:
  - setup_type: {" | ".join(VALID_SETUP_TYPES)} or null
  - market_condition: {" | ".join(VALID_CONDITIONS)} or null
  - keyword: one from {VALID_KEYWORDS[:10]} or null
  - timeframe: e.g. "1h", "daily", "intraday", or null
  - top_k: int 3-10 (default 5)
  - intent: "research" | "generate_strategy" | "risk_analysis"
  - explanation: brief reasoning

Return ONLY valid JSON, no other text."""

    try:
        resp = llm.invoke(prompt)
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
        r = RoutedQuery(raw=query)
        r.setup_type = data.get("setup_type") or None
        r.market_condition = data.get("market_condition") or None
        r.keyword = data.get("keyword") or None
        r.timeframe = data.get("timeframe") or None
        r.top_k = min(data.get("top_k", 5), 10)
        r.intent = data.get("intent", "research")
        r.explanation = data.get("explanation", "LLM-routed")
        return r
    except Exception:
        return _rule_router(query)


# ════════════════════════════════════════════════════════════════════
# LAYER 2 — RESEARCH AGENT (hierarchical retrieval)
# ════════════════════════════════════════════════════════════════════

def _build_where(rq: RoutedQuery) -> Optional[dict]:
    filters = []
    if rq.setup_type and rq.setup_type not in ("market_structure",):
        filters.append({"setup_type": {"$eq": rq.setup_type}})
    if not filters:
        return None
    return filters[0]


def _matches_keywords(keywords_str: str, keyword: str) -> bool:
    if not keyword:
        return True
    kw_str_lower = keywords_str.lower().replace("_", " ")
    search_terms = keyword.lower().replace("_", " ").split()
    if not search_terms:
        return True
    return any(term in kw_str_lower for term in search_terms)


def _matches_condition(cond_str: str, target: str) -> bool:
    if not target:
        return True
    search = target.lower().replace("_", " ").replace("-", " ")
    cond = cond_str.lower().replace("_", " ").replace("-", " ").replace("|", " ")
    search_terms = search.split()
    return any(term in cond for term in search_terms)


def _hierarchical_search(rq: RoutedQuery, collection) -> list[dict]:
    """
    Multi-stage retrieval:
      Stage 1: Broad semantic search (top_k * 4) with metadata filters
      Stage 2: Post-filter by keyword (ChromaDB $contains unreliable)
      Stage 3: Re-rank by score and truncate
    """
    broad_k = rq.top_k * 4
    results = collection.query(
        query_texts=[rq.raw],
        n_results=broad_k,
        where=_build_where(rq),
    )

    entries = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]
        dist = results["distances"][0][i]
        score = round(1.0 - dist, 4)

        kw_str = meta.get("keywords", "")
        cond_str = meta.get("market_condition", "")

        # Post-filter by keyword and condition
        if not _matches_keywords(kw_str, rq.keyword or ""):
            continue
        if not _matches_condition(cond_str, rq.market_condition or ""):
            continue

        entries.append({
            "id": results["ids"][0][i],
            "score": score,
            "setup_name": meta.get("setup_name", ""),
            "setup_type": meta.get("setup_type", ""),
            "market_condition": cond_str,
            "timeframe": meta.get("timeframe", ""),
            "strategy_style": meta.get("strategy_style", ""),
            "risk_reward": meta.get("risk_reward", ""),
            "keywords": kw_str,
            "channel_name": meta.get("channel_name", ""),
            "video_title": meta.get("video_title", ""),
            "chunk_text": doc,
        })

    entries.sort(key=lambda x: x["score"], reverse=True)
    entries = [e for e in entries if e["score"] >= rq.min_score]
    return entries[:rq.top_k]


def _stage2_deepen(rq: RoutedQuery, entries: list[dict], collection) -> list[dict]:
    """Stage 2: For top result, do a follow-up search with discovered keywords."""
    if not entries:
        return entries

    top = entries[0]
    discovered_kw = top.get("keywords", "")
    discovered_type = top.get("setup_type", "")

    additional_filters = {}
    if discovered_kw and not rq.keyword:
        additional_filters["keyword"] = discovered_kw.split(",")[0].strip()
    if discovered_type and not rq.setup_type:
        additional_filters["setup_type"] = discovered_type

    if additional_filters:
        deep_rq = RoutedQuery(
            raw=rq.raw,
            **additional_filters,
            top_k=rq.top_k,
            min_score=rq.min_score * 0.85,
        )
        deeper = _hierarchical_search(deep_rq, collection)
        existing_ids = {e["id"] for e in entries}
        for d in deeper:
            if d["id"] not in existing_ids:
                entries.append(d)
                existing_ids.add(d["id"])

    return entries[:rq.top_k + 3]


def research(query: str, use_llm: bool = True, top_k: int = 5) -> dict:
    rq = router(query, use_llm=use_llm)
    rq.top_k = top_k
    collection = _get_collection()

    stage1 = _hierarchical_search(rq, collection)
    stage2 = _stage2_deepen(rq, stage1, collection)

    return {
        "query": query,
        "routed": rq.to_dict(),
        "primary_results": stage1,
        "deepened_results": stage2,
        "total_candidates": len(stage1),
        "total_deepened": len(stage2),
    }


# ════════════════════════════════════════════════════════════════════
# LAYER 3 — SYNTHESIS AGENT
# ════════════════════════════════════════════════════════════════════

STRATEGY_TEMPLATE = '''from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
import pandas as pd
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class {class_name}(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "{timeframe}"
    can_short = {can_short}
    minimal_roi = {roi}
    stoploss = {stoploss}
    trailing_stop = {trailing_stop}
    startup_candle_count = {startup_candles}

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
{indicators}

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
{entry_logic}

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
{exit_logic}
'''


def synthesize(query: str, generate_code: bool = False, use_llm: bool = True) -> dict:
    res = research(query, use_llm=use_llm, top_k=8)
    entries = res["deepened_results"]

    summary = {
        "query": query,
        "sources_found": len(entries),
        "sources": [
            {"name": e["setup_name"], "type": e["setup_type"],
             "condition": e["market_condition"], "score": e["score"]}
            for e in entries
        ],
        "strategy_code": None,
    }

    if entries:
        top = entries[0]
        summary["primary_setup"] = top["setup_name"]
        summary["primary_type"] = top["setup_type"]
        summary["market_condition"] = top["market_condition"]
        summary["timeframe"] = top.get("timeframe", "1h")
        summary["risk_reward"] = top.get("risk_reward", "not specified")
        summary["chunk_text"] = top["chunk_text"][:500]

        combined_kw = set()
        for e in entries:
            for kw in e.get("keywords", "").split(","):
                combined_kw.add(kw.strip())
        summary["combined_keywords"] = sorted(kw for kw in combined_kw if kw)

    if generate_code:
        summary["strategy_code"] = _generate_code(query, entries, use_llm)

    return summary


def _generate_code(query: str, entries: list[dict], use_llm: bool) -> Optional[str]:
    if not entries:
        return None

    llm = _get_llm()
    if not llm or not use_llm:
        return _rule_codegen(query, entries)

    context = json.dumps([
        {"name": e["setup_name"], "type": e["setup_type"],
         "text": e["chunk_text"][:400], "keywords": e.get("keywords", "")}
        for e in entries[:5]
    ], indent=2)

    prompt = f"""You are a Freqtrade strategy expert. Generate a complete Python strategy class from these strategy chunks.

User query: "{query}"

Relevant knowledge base chunks:
{context}

Generate a production-quality Freqtrade strategy with:
- INTERFACE_VERSION = 3, can_short = True
- populate_indicators() with all needed TA indicators
- populate_entry_trend() with entry logic derived from the chunks
- populate_exit_trend() or custom_exit() with exit logic
- ATR-based dynamic stoploss via custom_stoploss()
- 3-8 hyperoptable IntParameter/DecimalParameter
- BTC regime filter, volume confirmation
- startup_candle_count appropriate for indicators used
- trailing_stop support

Return ONLY valid Python code, no markdown, no explanation."""

    try:
        resp = llm.invoke(prompt)
        code = resp.content.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[1]
            if "```" in code:
                code = code.rsplit("```", 1)[0]
        if "class " in code:
            return code
        return None
    except Exception:
        return _rule_codegen(query, entries)


def _rule_codegen(query: str, entries: list[dict]) -> str:
    top = entries[0] if entries else {}
    name = top.get("setup_name", query).replace(" ", "").replace("-", "_")[:30]
    tf = "1h"
    for e in entries:
        et = e.get("timeframe", "")
        if et and et != "universal" and "not specified" not in et:
            tf = et.split("|")[0].split(",")[0].strip().split(" ")[0]
            break

    indicators = []
    if any("rsi" in (e.get("keywords", "") + e.get("setup_name", "")).lower() for e in entries):
        indicators.append("        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)")
    if any("atr" in (e.get("keywords", "") + "atr") for e in entries):
        indicators.append("        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)")
    if any("ema" in (e.get("keywords", "") + e.get("setup_name", "")).lower() for e in entries):
        indicators.append("        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)")
        indicators.append("        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)")
    if any("macd" in kw for e in entries for kw in e.get("keywords", "").split(",")):
        indicators.append("        macd = ta.MACD(dataframe)")
        indicators.append("        dataframe['macd'] = macd['macd']")
        indicators.append("        dataframe['macdsignal'] = macd['macdsignal']")
    if any("adx" in kw for e in entries for kw in e.get("keywords", "").split(",")):
        indicators.append("        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)")
    if any("volume" in kw for e in entries for kw in e.get("keywords", "").split(",")):
        indicators.append("        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()")
    if not indicators:
        indicators.append("        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)")

    can_short = str("short" in query.lower() or any(
        "short" in e.get("keywords", "") for e in entries)).lower()

    return STRATEGY_TEMPLATE.format(
        class_name=f"AutoGen_{name}",
        timeframe=tf,
        can_short=can_short,
        roi='{"0": 0.15, "120": 0.08, "360": 0.04, "720": 0.02}',
        stoploss="-0.05",
        trailing_stop="True",
        startup_candles="100",
        indicators="\n".join(indicators),
        entry_logic="        dataframe['enter_long'] = 0\n        dataframe['enter_short'] = 0",
        exit_logic="        dataframe['exit_long'] = 0\n        dataframe['exit_short'] = 0",
    )


# ════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Strategy Research Agent System")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("router", help="Classify/route a query")
    r.add_argument("query", help="Natural language query")
    r.add_argument("--no-llm", action="store_true", help="Skip LLM, use rule-based only")

    rs = sub.add_parser("research", help="Hierarchical research from vector DB")
    rs.add_argument("query", help="Natural language query")
    rs.add_argument("--top-k", type=int, default=5)
    rs.add_argument("--no-llm", action="store_true", help="Skip LLM, use rule-based only")

    s = sub.add_parser("synthesize", help="Synthesize strategy from research results")
    s.add_argument("query", help="Natural language query")
    s.add_argument("--generate-code", action="store_true", help="Generate strategy Python code")
    s.add_argument("--no-llm", action="store_true")

    p = sub.add_parser("pipeline", help="Full pipeline: route → research → synthesize")
    p.add_argument("query", help="Natural language query")
    p.add_argument("--generate-code", action="store_true")
    p.add_argument("--no-llm", action="store_true")

    args = parser.parse_args()

    if args.command == "router":
        rq = router(args.query, use_llm=not args.no_llm)
        print(json.dumps(rq.to_dict(), indent=2))

    elif args.command == "research":
        result = research(args.query, use_llm=not args.no_llm, top_k=args.top_k)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "synthesize":
        result = synthesize(args.query, generate_code=args.generate_code,
                           use_llm=not args.no_llm)
        print(json.dumps({k: v for k, v in result.items() if k != "strategy_code"},
                         indent=2, default=str))
        if result["strategy_code"]:
            print("\n" + "=" * 60)
            print("GENERATED STRATEGY CODE")
            print("=" * 60)
            print(result["strategy_code"])

    elif args.command == "pipeline":
        rq = router(args.query, use_llm=not args.no_llm)
        print("── ROUTER ──")
        print(json.dumps(rq.to_dict(), indent=2))

        res = research(args.query, use_llm=not args.no_llm, top_k=5)
        print("\n── RESEARCH ──")
        print(f"Primary: {res['primary_results'][0]['setup_name'] if res['primary_results'] else 'none'}")
        print(f"Results: {len(res['deepened_results'])}")
        for e in res['deepened_results'][:5]:
            print(f"  [{e['score']}] {e['setup_name']:45s} | {e['setup_type']:20s} | {e['market_condition']}")

        syn = synthesize(args.query, generate_code=args.generate_code,
                        use_llm=not args.no_llm)
        print("\n── SYNTHESIS ──")
        print(f"Primary Setup: {syn.get('primary_setup', 'N/A')}")
        print(f"Market Condition: {syn.get('market_condition', 'N/A')}")
        print(f"Timeframe: {syn.get('timeframe', 'N/A')}")
        print(f"Keywords: {', '.join(syn.get('combined_keywords', [])[:10])}")

        if syn["strategy_code"]:
            print("\n" + "=" * 60)
            print("GENERATED STRATEGY CODE")
            print("=" * 60)
            print(syn["strategy_code"])


if __name__ == "__main__":
    main()
