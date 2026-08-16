# Phase 6: Production Serving & TUI Integration

## First Principles Root Cause Analysis

### Core Question
*Why do well-built RAG systems fail when served to real users and tools?*

### Decomposition to First Principles

**Principle 1: Serving latency is a UX constraint, not an infrastructure detail**
- A TUI tool (OpenCode, Claude Code, Hermes) has an attention budget of ~2-3 seconds per tool call
- If a RAG query takes >2s, the TUI tool will time out, the user sees an error, and trust is lost
- Current architecture: MCP server `mcp_server.py` handles one query at a time synchronously
- A single expensive query blocks ALL subsequent queries (head-of-line blocking)
- **Root cause**: Synchronous single-threaded serving cannot meet TUI latency requirements under concurrent load

**Principle 2: Two separate MCP servers means two separate failure modes**
- Strategy DB MCP (port auto-assigned, 9 tools) and NEXUS MCP (port auto-assigned, 15+ tools)
- TUI tools must be configured with two MCP endpoints
- If either server fails, its tools are unavailable — but the TUI has no way to know which tools are down
- If both servers are up but on swapped ports, the TUI calls the wrong tool
- **Root cause**: Multiple MCP servers create coordination overhead, configuration fragility, and unclear failure domains — violating the principle that a system should present a single coherent interface

**Principle 3: A query pipeline is only as strong as its weakest link**
- The complete pipeline is: query → cache check → embed → hybrid search → rerank → log → return
- If any stage throws an unhandled exception, the user gets a 500 error with zero results
- If the cross-encoder model fails to load, the ENTIRE query pipeline fails
- If ChromaDB is corrupted (disk full during persistence), the ENTIRE system is down
- **Root cause**: Tight coupling of stages means a failure in ANY stage takes down the ENTIRE system. There is no graceful degradation path.

### Root Cause Statement

> **The RAG system has no serving layer — it's a collection of Python scripts and MCP handlers with no unified gateway, no timeout management, no graceful degradation, and no monitoring. Every component failure is a system failure. Every slow query blocks all subsequent queries. Every new tool requires manual MCP configuration. This architecture cannot serve production TUI workloads because it has no isolation between components, no fallback paths, and no coherent interface.**

### Measured Evidence
- Two separate MCP servers (Strategy DB + NEXUS) with no gateway
- No timeout handling — a single 3s query blocks the server
- No graceful degradation — cross-encoder failure = full pipeline failure
- No health endpoint for the query pipeline
- No concurrent request handling
- No configuration for TUI tools — users must manually configure MCP endpoints
- No automatic tool discovery

---

## Current State Analysis

| Component | Status | Limitation |
|-----------|--------|------------|
| Strategy DB MCP server | ✅ Working | Single-threaded, no timeout, no health |
| NEXUS MCP server | ✅ Working | Separate endpoint, no cross-discovery |
| OpenCode connector | ⚠️ Partial | Only connects to NEXUS |
| Unified gateway | ❌ Missing | No router/dispatcher |
| Health endpoint | ❌ Missing | No /health for RAG pipeline |
| Timeout management | ❌ Missing | No timeout on long queries |
| Concurrent request handling | ❌ Missing | Synchronous, one-at-a-time |
| Graceful degradation | ❌ Missing | Any failure = 500 error |
| TUI tool configuration | ❌ Missing | Manual MCP config needed |
| Auto-discovery | ❌ Missing | Tools not advertised |

---

## Typed Execution Plan

### DAG

```
Phase 6.1 ──[Unified FastAPI gateway (port 8200)]───────────────► Checkpoint 6.1
    │                                                              │ Router: /api/trading/*
    ▼                                                              │ Router: /api/nexus/*
Phase 6.2 ──[Health endpoint + readiness probe]──────────────────► Checkpoint 6.2
    │                                                              │ /health returns: all component statuses
    ▼                                                              │ readiness_gate for load balancers
Phase 6.3 ──[Timeout + concurrent request handling]──────────────► Checkpoint 6.3
    │                                                              │ asyncio timeout per request
    ▼                                                              │ ThreadPoolExecutor for model inference
Phase 6.4 ──[Graceful degradation cascade]───────────────────────► Checkpoint 6.4
    │                                                              │ fallback chain: full → rerank → hybrid → dense
    ▼                                                              │ each fallback logged
Phase 6.5 ──[TUI tool config generation + auto-discovery]────────► Checkpoint 6.5
    │                                                              │ generates opencode.json snippet
    ▼                                                              │ /api/tools returns all available tools
Phase 6.6 ──[Benchmark: latency, throughput, degradation paths]──► Done
                                                                   │ p95 < 500ms, 10 qps, all fallbacks tested
```

### Phase 6.1 — Unified FastAPI Gateway

```python
# strategy_db/gateway.py
from fastapi import FastAPI, HTTPException, Request
from contextlib import asynccontextmanager
from pydantic import BaseModel
import asyncio
import time

app = FastAPI(title="Algotrading RAG Gateway", version="1.0.0")

# Shared state
class AppState:
    def __init__(self):
        self.strategy_db = None
        self.reranker = None
        self.query_logger = None
        self.config = {}

state = AppState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: lazy-init all components
    from strategy_db.query import StrategyDB
    state.strategy_db = StrategyDB()
    from strategy_db.reranker import Reranker
    try:
        state.reranker = Reranker()
    except Exception as e:
        state.reranker = None  # Graceful degradation
        print(f"[gateway] Reranker unavailable: {e}")
    from strategy_db.monitoring import QueryLogger
    state.query_logger = QueryLogger()
    yield
    # Shutdown: cleanup
    state.strategy_db = None
    state.reranker = None

app.router.lifespan_context = lifespan

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    setup_type: str | None = None
    market_condition: str | None = None
    use_cache: bool = True
    timeout_ms: int = 1500

class QueryResponse(BaseModel):
    results: list[dict]
    latency_ms: float
    cache_hit: bool
    degradation_level: str  # "full" | "no_rerank" | "no_hybrid" | "fallback"
    total_results: int

@app.post("/api/trading/query", response_model=QueryResponse)
async def query_trading(request: QueryRequest):
    t0 = time.time()
    try:
        results = await asyncio.wait_for(
            _execute_query(request),
            timeout=request.timeout_ms / 1000,
        )
    except asyncio.TimeoutError:
        raise HTTPException(503, "Query timed out")
    latency = (time.time() - t0) * 1000
    return QueryResponse(
        results=results,
        latency_ms=latency,
        cache_hit=state._last_cache_hit,
        degradation_level=state._last_degradation,
        total_results=len(results),
    )

async def _execute_query(request: QueryRequest) -> list[dict]:
    """Execute with degradation cascade."""
    level = "full"
    # Level 1: Full pipeline (hybrid + rerank + cache)
    try:
        if state.reranker and state.strategy_db:
            return await state.strategy_db.search_with_rerank_async(
                request.query, top_k=request.top_k
            )
    except Exception as e:
        print(f"[gateway] Full pipeline failed: {e}")
        level = "no_rerank"
    # Level 2: Hybrid only (no rerank)
    try:
        if state.strategy_db:
            return state.strategy_db.hybrid_search(request.query, top_k=request.top_k)
    except Exception as e:
        print(f"[gateway] Hybrid failed: {e}")
        level = "fallback"
    # Level 3: Pure dense (always works)
    state._last_degradation = level
    return state.strategy_db.pure_dense_search(request.query, top_k=request.top_k)
```

### Phase 6.2 — Health Endpoint

```python
@app.get("/health")
async def health():
    statuses = {}
    # Check ChromaDB
    try:
        state.strategy_db.client.heartbeat()
        statuses["chromadb"] = "ok"
    except Exception:
        statuses["chromadb"] = "down"
    # Check reranker
    statuses["reranker"] = "ok" if state.reranker else "unavailable"
    # Check cache
    statuses["cache"] = "ok" if state.strategy_db.embedding_cache else "disabled"
    # Check total indexed docs
    statuses["total_docs"] = len(state.strategy_db.all_chunks) if state.strategy_db else 0
    # Overall
    all_ok = all(v == "ok" or v == "disabled" or isinstance(v, int) for v in statuses.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "components": statuses,
        "version": "1.0.0",
        "uptime_seconds": time.time() - state._start_time,
    }
```

### Phase 6.3 — Timeout + Concurrency

```python
# In gateway.py startup
import asyncio
from concurrent.futures import ThreadPoolExecutor

MODEL_EXECUTOR = ThreadPoolExecutor(max_workers=2)

@app.post("/api/trading/query")
async def query_trading(request: QueryRequest):
    # Run model inference (blocking) in thread pool
    loop = asyncio.get_event_loop()
    results = await asyncio.wait_for(
        loop.run_in_executor(MODEL_EXECUTOR, _execute_query_sync, request),
        timeout=request.timeout_ms / 1000,
    )
```

### Phase 6.4 — Graceful Degradation Cascade

```
Pipeline Level 0 (full): cache → embed → BM25 → ChromaDB → RRF → rerank → log
    ↓ any failure
Pipeline Level 1: cache → embed → BM25 → ChromaDB → RRF → log  (skip reranker)
    ↓ any failure
Pipeline Level 2: cache → embed → ChromaDB → log  (skip BM25 + reranker)
    ↓ any failure
Pipeline Level 3: pure ChromaDB query_texts → log  (no caches, no extras)
    ↓ any failure
Response: {"error": "all pipelines failed", "results": []}
```

```python
PIPELINE_CASCADE = [
    ("full", lambda: _pipeline_full(request)),
    ("no_rerank", lambda: _pipeline_no_rerank(request)),
    ("no_hybrid", lambda: _pipeline_no_hybrid(request)),
    ("fallback", lambda: _pipeline_fallback(request)),
]

for level_name, pipeline_fn in PIPELINE_CASCADE:
    try:
        results = await pipeline_fn()
        state._last_degradation = level_name
        return results
    except Exception as e:
        print(f"[gateway] {level_name} failed: {e}")
        continue

# All pipelines failed
state._last_degradation = "all_failed"
return []
```

### Phase 6.5 — TUI Tool Config Generation

```python
@app.get("/api/tools")
async def list_tools():
    """Return tools compatible with OpenCode/Claude Code MCP format."""
    return {
        "servers": [
            {
                "name": "algotrading-rag",
                "url": "http://localhost:8200",
                "tools": [
                    {
                        "name": "query_strategies",
                        "description": "Query trading strategy database",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "top_k": {"type": "integer", "default": 5},
                                "setup_type": {"type": "string", "nullable": True},
                            }
                        }
                    },
                    {
                        "name": "health",
                        "description": "Check RAG system health",
                        "input_schema": {"type": "object", "properties": {}}
                    }
                ]
            }
        ]
    }

@app.get("/api/opencode-config")
async def opencode_config():
    """Generate OpenCode MCP config snippet."""
    return {
        "mcpServers": {
            "algotrading-rag": {
                "url": "http://localhost:8200",
                "description": "Algotrading strategy RAG database with hybrid search + reranking"
            }
        }
    }
```

---

## Audit Benchmarks

### Pre-Phase Baseline

| Metric | Current Value | Target |
|--------|---------------|--------|
| MCP servers | 2 separate | 1 unified gateway |
| Max concurrent requests | 1 | 10+ |
| Request timeout handling | None | Configurable per-request |
| Graceful degradation | None | 4-level cascade |
| /health endpoint | None | Returns all component status |
| TUI config generation | Manual | Auto-generated |
| P95 latency | ~280ms (uncached) | <500ms (degraded) |
| Throughput | ~3.5 qps | >10 qps |

### Post-Phase Verification Matrix

| Check | Tool | Pass Criteria |
|-------|------|---------------|
| Gateway serves on :8200 | `curl localhost:8200/health` | Returns 200 |
| Health endpoint works | `curl /health` | All components reported |
| Query returns results | `curl -X POST /api/trading/query -d '{"query":"FVG"}'` | Returns JSON with results |
| Timeout works | Query with 1ms timeout → 503 | HTTP 503 returned |
| Concurrent requests work | 10 simultaneous curl requests | All return, no connection refused |
| Degradation works | Kill reranker → query still works | Returns results, degradation_level = "no_rerank" |
| Full degradation works | Kill everything → query returns empty | Empty results, no exception |
| Tools list generated | `curl /api/tools` | Returns tool schema |
| OpenCode config snippet | `curl /api/opencode-config` | Valid JSON for MCP servers |

---

## Verification Protocol (Block-Level)

### Block 1: Gateway Startup

```bash
# Start gateway in background
python3 strategy_db/gateway.py &
GATEWAY_PID=$!
sleep 3

# Health check
curl -s http://localhost:8200/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status'] == 'ok'"
echo "Health OK"

kill $GATEWAY_PID
```

### Block 2: Query Endpoint

```bash
python3 strategy_db/gateway.py &
sleep 3

curl -s -X POST http://localhost:8200/api/trading/query \
  -H "Content-Type: application/json" \
  -d '{"query":"FVG liquidity grab entry","top_k":5}' | python3 -c "
import sys, json
resp = json.load(sys.stdin)
assert len(resp['results']) == 5
assert resp['latency_ms'] > 0
assert resp['degradation_level'] in ('full', 'no_rerank', 'no_hybrid', 'fallback')
print(f'Query OK: {len(resp[\"results\"])} results, {resp[\"latency_ms\"]:.0f}ms, level={resp[\"degradation_level\"]}')
"

kill %1
```

### Block 3: Timeout

```bash
# Query with 1ms timeout (should timeout immediately)
curl -s -X POST http://localhost:8200/api/trading/query \
  -H "Content-Type: application/json" \
  -d '{"query":"FVG","timeout_ms":1}'
# Should return 503
assert http_code == 503
```

### Block 4: Concurrent Requests

```bash
# Launch 10 concurrent requests
for i in $(seq 1 10); do
    curl -s -X POST http://localhost:8200/api/trading/query \
      -H "Content-Type: application/json" \
      -d '{"query":"FVG entry","timeout_ms":2000}' &
done
wait
# All 10 should succeed — count responses
```

### Block 5: Tools Discovery

```bash
curl -s http://localhost:8200/api/tools | python3 -c "
import sys, json
tools = json.load(sys.stdin)
assert 'servers' in tools
assert len(tools['servers']) >= 1
assert 'tools' in tools['servers'][0]
print(f'Tools OK: {len(tools[\"servers\"][0][\"tools\"])} tools')
"
```

### Block 6: OpenCode Config

```bash
curl -s http://localhost:8200/api/opencode-config | python3 -c "
import sys, json
config = json.load(sys.stdin)
assert 'mcpServers' in config
assert 'algotrading-rag' in config['mcpServers']
print('OpenCode config valid')
"
```

---

## Deployment Architecture

```
┌──────────────────────────────────────────────────────┐
│                    TUI Tools                         │
│  (OpenCode / Claude Code / Hermes)                   │
└────────────────────────┬─────────────────────────────┘
                         │ MCP protocol
                         ▼
┌──────────────────────────────────────────────────────┐
│            Unified Gateway (:8200)                    │
│  FastAPI + asyncio + ThreadPoolExecutor               │
│                                                      │
│  /api/trading/query    → Strategy DB pipeline        │
│  /api/nexus/*          → NEXUS routing               │
│  /health               → Component status            │
│  /api/tools            → Tool discovery              │
│  /api/opencode-config  → MCP config snippet          │
└────────┬────────────────────────┬────────────────────┘
         │                        │
         ▼                        ▼
┌──────────────────┐   ┌──────────────────┐
│ Strategy DB RAG  │   │  NEXUS Router    │
│ ChromaDB         │   │  FAISS + SQLite  │
│ MiniLM + BM25    │   │  Tool Attention  │
│ Cross-encoder    │   │  v4 pipeline     │
│ Caches           │   │                  │
└──────────────────┘   └──────────────────┘
```

---

## Rollback Plan

| Failure | Action |
|---------|--------|
| Gateway port conflict | Change port to 8201 or auto-detect free port |
| FastAPI dependency missing | pip install fastapi uvicorn; if unavailable, use existing MCP server |
| ThreadPoolExecutor OOM | Reduce max_workers to 1 |
| Async timeout fails | Use sync handler with signal.alarm fallback |
| /api/tools returns 404 | Route is optional; TUI can still use direct MCP server |

## Estimated Effort

| Task | Time | Dependencies |
|------|------|-------------|
| Phase 6.1 — FastAPI gateway | 1h | fastapi, uvicorn |
| Phase 6.2 — Health endpoint | 15 min | Phase 6.1 |
| Phase 6.3 — Timeout + concurrency | 30 min | Phase 6.1 |
| Phase 6.4 — Degradation cascade | 30 min | Phase 6.1 |
| Phase 6.5 — TUI config generation | 20 min | Phase 6.1 |
| Phase 6.6 — Benchmark | 30 min | All above |
| **Total** | **~3h 5min** | |

---

## Success Criteria

- [ ] Unified FastAPI gateway running on port 8200
- [ ] `/health` returns component-level status (chromadb, reranker, cache, total_docs)
- [ ] Query endpoint (`/api/trading/query`) returns results with latency, cache_hit, degradation_level
- [ ] Timeout handling: requests exceeding `timeout_ms` return 503
- [ ] Concurrent request handling: 10 simultaneous queries all complete
- [ ] Graceful degradation cascade: 4 levels (full → no_rerank → no_hybrid → fallback)
- [ ] Tool discovery endpoint (`/api/tools`) returns MCP-compatible schema
- [ ] OpenCode config snippet (`/api/opencode-config`) is valid JSON
- [ ] P95 latency < 500ms (full pipeline), < 200ms (degraded)
- [ ] Throughput > 10 queries/second
- [ ] No single component failure takes down the entire system
