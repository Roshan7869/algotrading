#!/usr/bin/env python3
"""Unified RAG Gateway — FastAPI server wrapping Strategy DB + NEXUS routing.

Provides:
  POST /api/trading/query   — Strategy RAG with degradation cascade
  GET  /health              — Component health status
  GET  /api/tools           — MCP-compatible tool discovery
  GET  /api/opencode-config — OpenCode MCP config snippet
  GET  /api/stats           — Query statistics (last N days)

Start:
  python3 strategy_db/gateway.py
  python3 strategy_db/gateway.py --port 8200 --host 0.0.0.0
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# Ensure strategy_db is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Models ──────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language search query")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results")
    setup_type: Optional[str] = Field(default=None, description="Filter by setup type")
    market_condition: Optional[str] = Field(default=None, description="Filter by market condition")
    use_cache: bool = Field(default=True, description="Enable caching")
    timeout_ms: int = Field(default=30000, ge=100, le=120000, description="Query timeout")


class QueryResponse(BaseModel):
    results: list[dict]
    latency_ms: float
    cache_hit: bool = False
    degradation_level: str = "full"
    total_results: int = 0


class HealthResponse(BaseModel):
    status: str
    components: dict
    version: str
    uptime_seconds: float


# ── Internal Adapter: wraps existing search.py module ──────────────────────

class _StrategyDBAdapter:
    """Adapts the real StrategyDB class into a stable interface for the gateway.

    This wrapper exists so the gateway works even if the StrategyDB class
    is unavailable — it falls back to module-level helpers.
    """

    def __init__(self):
        self._db = None
        self._search_fn = None
        self._collection = None

        try:
            from strategy_db.search import StrategyDB, _get_collection
            self._db = StrategyDB()
            self._collection = _get_collection()
        except Exception:
            try:
                from strategy_db.search import _get_collection, search as search_fn
                self._collection = _get_collection()
                self._search_fn = search_fn
            except Exception:
                pass

    @property
    def available(self) -> bool:
        return self._db is not None or self._search_fn is not None

    def query_with_cache(self, query: str, top_k: int = 5, **kwargs) -> tuple[list[dict], dict]:
        if self._db is not None:
            return self._db.query_with_cache(query, top_k=top_k, **kwargs)
        results = self.hybrid_search(query, top_k=top_k, **kwargs)
        return results, {"cache_hit": False, "degradation_level": "fallback"}

    def hybrid_search(self, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        if self._db is not None:
            return self._db.hybrid_search(query, top_k=top_k, **kwargs)
        if not self._search_fn:
            return []
        return self._search_fn(
            query, top_k=top_k,
            setup_type=kwargs.get("setup_type"),
            market_condition=kwargs.get("market_condition"),
        )

    def search_with_rerank(self, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        if self._db is not None:
            return self._db.search_with_rerank(query, final_top_k=top_k, **kwargs)
        return self.hybrid_search(query, top_k=top_k, **kwargs)

    def pure_dense_search(self, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        if self._db is not None:
            return self._db.pure_dense_search(query, top_k=top_k, **kwargs)
        if not self._search_fn:
            return []
        return self._search_fn(query, top_k=top_k,
                               setup_type=kwargs.get("setup_type"),
                               market_condition=kwargs.get("market_condition"))

    def list_setup_types(self) -> list[str]:
        if self._db is not None:
            return self._db._list_setup_types() if hasattr(self._db, '_list_setup_types') else []
        return []

    def list_market_conditions(self) -> list[str]:
        if self._db is not None:
            return self._db._list_market_conditions() if hasattr(self._db, '_list_market_conditions') else []
        return []


# ── Simple inline query logger (until monitoring.py exists) ────────────────

class _QueryLogger:
    """In-memory query logger. Replaced by strategy_db.monitoring.QueryLogger
    when available."""

    def __init__(self, log_path: Path | None = None):
        self._log_path = log_path or Path(
            os.path.join(os.path.dirname(__file__), "query_log.json")
        )
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        if self._log_path.exists():
            try:
                with open(self._log_path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._entries = data
            except Exception:
                pass

    def _save(self):
        try:
            with open(self._log_path, "w") as f:
                json.dump(self._entries[-10_000:], f, default=str)
        except Exception:
            pass

    def log(
        self,
        query: str = "",
        top_k: int = 5,
        results: list | None = None,
        latency_ms: float = 0,
        cache_layer: str = "",
        reranker_used: bool = False,
        hybrid_used: bool = True,
    ) -> None:
        self._entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "top_k": top_k,
            "result_count": len(results) if results else 0,
            "latency_ms": round(latency_ms, 2),
            "cache_layer": cache_layer,
            "reranker_used": reranker_used,
            "hybrid_used": hybrid_used,
        })
        if len(self._entries) % 50 == 0:
            self._save()

    def get_recent_stats(self, days: int = 7) -> dict:
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        recent = [
            e for e in self._entries
            if datetime.fromisoformat(e["timestamp"]).timestamp() > cutoff
        ]
        latencies = [e["latency_ms"] for e in recent if e.get("latency_ms")]
        return {
            "total_queries": len(recent),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "min_latency_ms": round(min(latencies), 2) if latencies else 0,
            "max_latency_ms": round(max(latencies), 2) if latencies else 0,
            "degradation_distribution": {
                level: sum(1 for e in recent if e.get("cache_layer") == level)
                for level in {"full", "no_rerank", "no_hybrid", "fallback", "timeout_fallback"}
            },
        }

    def daily_rollup(self) -> dict:
        """Return rollup grouped by day."""
        days: dict[str, list] = {}
        for e in self._entries:
            day = e["timestamp"][:10]
            days.setdefault(day, []).append(e)
        return {
            day: {
                "total": len(entries),
                "avg_latency_ms": round(
                    sum(e["latency_ms"] for e in entries) / len(entries), 2
                ) if entries else 0,
            }
            for day, entries in sorted(days.items())
        }


# ── Application State ───────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self.strategy_db: _StrategyDBAdapter | None = None
        self.reranker = None
        self.query_logger: _QueryLogger | None = None
        self._start_time = time.time()
        self._last_cache_hit = False
        self._last_degradation = "full"
        self._ready = False

    async def initialize(self):
        """Lazy-init all components. Failures are non-fatal."""

        # Strategy DB — use adapter wrapper for stable interface
        self.strategy_db = _StrategyDBAdapter()
        if self.strategy_db.available:
            print("[gateway] StrategyDB adapter loaded")
        else:
            print("[gateway] StrategyDB FAILED: no search module")

        # Reranker (optional)
        try:
            from strategy_db.reranker import get_reranker
            self.reranker = get_reranker()
            if self.reranker.is_available():
                print(f"[gateway] Reranker loaded: {self.reranker.model_name}")
            else:
                print("[gateway] Reranker not available (model not loaded)")
                self.reranker = None
        except ImportError:
            print("[gateway] Reranker module not found (skipping)")
            self.reranker = None
        except Exception as e:
            print(f"[gateway] Reranker FAILED: {e}")
            self.reranker = None

        # Query Logger (required) — try import, fall back to inline
        try:
            from strategy_db.monitoring import QueryLogger  # type: ignore[attr-defined]
            self.query_logger = QueryLogger()
            print("[gateway] QueryLogger loaded (monitoring module)")
        except ImportError:
            self.query_logger = _QueryLogger()
            print("[gateway] QueryLogger inline (monitoring module not found)")
        except Exception as e:
            print(f"[gateway] QueryLogger FAILED: {e}")
            self.query_logger = _QueryLogger()

        self._ready = True

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time


# ── FastAPI App ─────────────────────────────────────────────────────────────

MODEL_EXECUTOR = ThreadPoolExecutor(max_workers=2)

state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await state.initialize()
    yield
    MODEL_EXECUTOR.shutdown(wait=True)


app = FastAPI(
    title="Algotrading RAG Gateway",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Degradation Cascade ────────────────────────────────────────────────────

def _execute_query_sync(request: QueryRequest) -> tuple[list[dict], str, bool]:
    """Execute query with 4-level degradation cascade. Runs in thread pool."""
    query = request.query
    top_k = request.top_k
    db = state.strategy_db

    if db is None or not db.available:
        return [], "fallback", False

    # Level 0: Cache + hybrid (BM25 fusion + ChromaDB)
    degradation = "no_rerank"
    try:
        results, meta = db.query_with_cache(
            query,
            top_k=top_k,
            use_hybrid=True,
            use_cache=request.use_cache,
            use_rerank=False,
            setup_type=request.setup_type,
            market_condition=request.market_condition,
        )
        return results, degradation, meta.get("cache_hit", False)
    except Exception as e:
        print(f"[gateway] Level 0 (hybrid+cache) failed: {e}")

    # Level 1: Pure dense search (ChromaDB only)
    degradation = "no_hybrid"
    try:
        results = db.pure_dense_search(
            query, top_k=top_k,
            setup_type=request.setup_type,
            market_condition=request.market_condition,
        )
        return results, degradation, False
    except Exception as e:
        print(f"[gateway] Level 1 (dense) failed: {e}")

    # Level 2: Complete failure
    degradation = "fallback"
    print(f"[gateway] All pipelines failed for query: {query}")
    return [], degradation, False


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/api/trading/query", response_model=QueryResponse)
async def query_trading(request: QueryRequest):
    """Query the trading strategy knowledge base with automatic degradation."""
    t0 = time.time()

    if state.strategy_db is None or not state.strategy_db.available:
        raise HTTPException(
            status_code=503,
            detail="Strategy DB not available",
        )

    try:
        loop = asyncio.get_event_loop()
        results, degradation, cache_hit = await asyncio.wait_for(
            loop.run_in_executor(MODEL_EXECUTOR, _execute_query_sync, request),
            timeout=request.timeout_ms / 1000.0,
        )
    except asyncio.TimeoutError:
        # Emergency fallback: try pure_dense with short timeout
        try:
            results = state.strategy_db.pure_dense_search(
                request.query,
                top_k=request.top_k,
                setup_type=request.setup_type,
                market_condition=request.market_condition,
            )
            degradation = "timeout_fallback"
            cache_hit = False
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Query timed out and fallback failed",
            )

    latency = (time.time() - t0) * 1000

    # Log
    if state.query_logger:
        try:
            state.query_logger.log(
                query=request.query,
                top_k=request.top_k,
                results=results,
                latency_ms=latency,
                cache_layer=degradation,
                reranker_used=(degradation == "full"),
                hybrid_used=(degradation in ("full", "no_rerank")),
            )
        except Exception:
            pass

    state._last_cache_hit = cache_hit
    state._last_degradation = degradation

    return QueryResponse(
        results=results,
        latency_ms=round(latency, 2),
        cache_hit=cache_hit,
        degradation_level=degradation,
        total_results=len(results),
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Component-level health check."""
    statuses: dict[str, str | int] = {}

    # ChromaDB
    try:
        if state.strategy_db is None:
            statuses["chromadb"] = "not_initialized"
            statuses["total_docs"] = 0
        elif hasattr(state.strategy_db, '_ensure_init'):
            state.strategy_db._ensure_init()
            count = state.strategy_db._collection.count() if hasattr(state.strategy_db, '_collection') and state.strategy_db._collection else 0
            statuses["chromadb"] = "ok"
            statuses["total_docs"] = count
        elif state.strategy_db._collection:
            count = state.strategy_db._collection.count()
            statuses["chromadb"] = "ok"
            statuses["total_docs"] = count
        else:
            statuses["chromadb"] = "not_initialized"
            statuses["total_docs"] = 0
    except Exception as e:
        statuses["chromadb"] = f"error: {e}"
        statuses["total_docs"] = 0

    # Reranker
    statuses["reranker"] = (
        "ok" if (state.reranker and state.reranker.is_available()) else "unavailable"
    )

    # Logging
    statuses["query_logger"] = "ok" if state.query_logger else "unavailable"

    # Overall
    core_ok = statuses.get("chromadb") == "ok"
    all_ok = core_ok

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        components=statuses,
        version="1.0.0",
        uptime_seconds=round(state.uptime, 2),
    )


@app.get("/api/tools")
async def list_tools():
    """Return MCP-compatible tool schema for auto-discovery."""
    return {
        "servers": [
            {
                "name": "algotrading-rag",
                "url": "http://localhost:8200",
                "tools": [
                    {
                        "name": "query_strategies",
                        "description": (
                            "Query the trading strategy knowledge base using hybrid search "
                            "(BM25 + vector) with cross-encoder reranking. Returns top-k "
                            "matching strategies with scores, setup types, market conditions, "
                            "and risk/reward ratios."
                        ),
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Natural language query about trading strategies, setups, or concepts",
                                },
                                "top_k": {
                                    "type": "integer",
                                    "default": 5,
                                    "description": "Number of results to return (1-50)",
                                },
                                "setup_type": {
                                    "type": "string",
                                    "description": "Optional filter: entry, exit, risk_management, market_structure, psychology",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "list_strategy_types",
                        "description": "List all available trading strategy setup types in the knowledge base",
                        "input_schema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "name": "rag_health",
                        "description": "Check the health and status of the RAG pipeline components",
                        "input_schema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                ],
            }
        ]
    }


@app.get("/api/opencode-config")
async def opencode_config():
    """Generate MCP server configuration snippet for OpenCode/Claude Code."""
    return {
        "mcpServers": {
            "algotrading-rag": {
                "url": "http://localhost:8200",
                "transport": "http",
                "description": (
                    "Algotrading strategy RAG — hybrid search (BM25 + vector) "
                    "with cross-encoder reranking over trading strategy chunks"
                ),
            }
        }
    }


@app.get("/api/stats")
async def query_stats(days: int = Query(default=7, ge=1, le=90)):
    """Get query statistics for the last N days."""
    if state.query_logger:
        try:
            stats = state.query_logger.get_recent_stats(days)
            return {"status": "ok", "days": days, "stats": stats}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "unavailable", "message": "Query logger not initialized"}


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Algotrading RAG Gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print(f"Starting Algotrading RAG Gateway on {args.host}:{args.port}")
    uvicorn.run(
        "strategy_db.gateway:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
