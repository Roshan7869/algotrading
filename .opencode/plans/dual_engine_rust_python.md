# Dual-Engine Rust + Python — Graphify Typed DAG Plan

```yaml
goal: "Build Rust WS+indicator+execution engine with Python Streamlit+NEXUS integration via Redis IPC"
created: "2026-05-23T13:30:00Z"
execution_tracker:
  total_blocks: 7
  completed: 0
  in_progress: null
dependency_graph:
  level_0:
    - R0: "Rust project scaffold (bridge crate)"
    - R1: "Rust WS engine (fastwebsockets connector)"
  level_1:
    - R2: "Rust indicator engine (ta.rs-based)"
  level_2:
    - R3: "Redis IPC publisher (Rust→Redis)"
    - R4: "Python Redis subscriber (Streamlit)"
  level_3:
    - R5: "NEXUS learning loop integration"
  level_4:
    - R6: "Verification & latency benchmark"
```

---

## Phase 0: First Principles Deconstruction

### Root question
Streamlit/Plotly renders charts via SVGs — the bottleneck is CPU-bound Python: WS ingestion (`websocket-client`, GIL-threaded), indicator math (pandas/numpy per-tick), and Plotly figure construction (Python→JSON). The existing `flowsurface-src/` has Rust `ta.rs` (zero-alloc f32 math) and GPU-accelerated iced/wgpu rendering — but zero integration with the Python stack.

### Component atomization
| Component | What | Why | Inputs | Outputs | Failure mode |
|-----------|------|-----|--------|---------|--------------|
| Rust WS Engine | Replace Python BinanceStream with fastwebsockets | Sub-5ms frame ingestion vs 50-200ms Python | Binance WebSocket | Normalized candles + trades | WS disconnect |
| Rust TA Engine | Replace pandas indicators with ta.rs | 0.3ms/1000 bars vs 15ms pandas | OHLCV array | 20+ indicator values | Divergence from Python math |
| Redis IPC | Rust publishes JSON, Python subscribes | Eliminate Python from data path | Rust-computed data | JSON on Redis channel | Redis down |
| Redis Subscriber | Streamlit reads from Redis instead of Python WS | Zero Python latency for live data | Redis channel | pandas DataFrame | Schema mismatch |
| NEXUS Bridge | Trade outcomes → Thompson → ChromaDB | Close the learning loop | Trade PnL | Weighted strategy search | Outcome mismatch |

---

## Phase 1: State Analysis (verified)

**Python WS (current):**
- `ui/binance_ws.py:230` — threaded Python `websocket-client` daemon
- WS URL: `wss://fstream.binance.com/ws/{symbol}@kline_{tf}/{symbol}@aggTrade`
- Candle dict in `_candles[open_time]`, trades in `_trades` deque
- `get_candles()` → pandas DataFrame via `_sort_candles()`

**Python indicators (current):**
- `ui/indicators.py:142` — pure pandas: EMA, RSI, ATR, VWAP, BB, MACD, SuperTrend, Delta, CVD, Z-Score
- `compute_indicators(df)` → df with 20+ indicator columns

**Rust `flowsurface_src` (existing):**
- `flowsurface_src/data/src/chart/ta.rs` — 1384 lines of zero-allocation f32 math
- 20+ indicators: SMA, EMA, ALMA, RSI, MACD, BB, ADX, Aroon, VWAP, ATR, Delta Z-Score, FVG, Order Blocks, Swing Points, Candle Patterns
- GPU charting via iced + wgpu (native desktop only, no WASM)

**Redis (infrastructure):**
- Docker container `quantdinger-redis` on `127.0.0.1:6379`
- Already used for signal bus in `shared_config/signals/`

---

## Phase 2: Typed DAG — Execution Blocks

### Level 0 (Independent — parallel)

#### BLOCK R0: Rust project scaffold
```yaml
id: "R0"
type: implement
level: 0
files:
  - flowsurface_src/bridge/Cargo.toml (NEW)
  - flowsurface_src/bridge/src/main.rs (NEW)
  - flowsurface_src/bridge/src/config.rs (NEW)
  - flowsurface_src/Cargo.toml (modify L30-35)
description: |
  Create a new Rust workspace member `bridge/` with dependencies:
  fastwebsockets, tokio, redis, serde_json, chrono.
  Entry binary reads args (pair, tf, market) and initializes tokio runtime.
guardrails:
  - "Must compile with `cargo build -p ws-bridge`"
  - "Must not modify any existing flowsurface code"
estimated_tokens: 2000
checkpoint: true
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| R0-T1 | `flowsurface_src/bridge/Cargo.toml` | NEW | new | Create with deps: fastwebsockets, tokio, redis, serde_json, chrono | file exists |
| R0-T2 | `flowsurface_src/bridge/src/main.rs` | NEW | new | Binary entry: tokio::main, arg parsing, signal handler | `cargo check` |
| R0-T3 | `flowsurface_src/bridge/src/config.rs` | NEW | new | Config struct: WS_URL, REDIS_URL, pair/tf/market, max_candles | file exists |
| R0-T4 | `flowsurface_src/Cargo.toml` | L30-35 | modify | Add `bridge` member to workspace | `cargo build` |

#### BLOCK R1: Rust WS Engine
```yaml
id: "R1"
type: implement
level: 0
files:
  - flowsurface_src/bridge/src/ws.rs (NEW)
  - flowsurface_src/bridge/src/candles.rs (NEW)
description: |
  fastwebsockets connector to Binance combined stream.
  CandleStore manages BTreeMap<u64, Candle> with trim-to-limit.
  Reconnect with exponential backoff (max 5 retries).
guardrails:
  - "Same WS protocol as binance_ws.py: wss://fstream.binance.com/ws/{sym}@kline_{tf}/{sym}@aggTrade"
  - "Must emit same candle field names"
estimated_tokens: 4000
checkpoint: true
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| R1-T1 | `flowsurface_src/bridge/src/ws.rs` | L1-30 | new | Imports + BinanceWS struct with connect() method | compile |
| R1-T2 | `flowsurface_src/bridge/src/ws.rs` | L31-70 | new | `_process_kline()` — parse `k` field to Candle | unit test |
| R1-T3 | `flowsurface_src/bridge/src/ws.rs` | L71-100 | new | `_process_trade()` — parse aggTrade | unit test |
| R1-T4 | `flowsurface_src/bridge/src/ws.rs` | L101-140 | new | Reconnect loop — exponential backoff 1s/2s/4s/8s/16s, max 5 | compile |
| R1-T5 | `flowsurface_src/bridge/src/candles.rs` | L1-40 | new | CandleStore struct: BTreeMap<u64, Candle>, insert, get_all, trim | unit test |
| R1-T6 | `flowsurface_src/bridge/src/candles.rs` | L41-60 | new | `from_kline_stream()` — parser mirroring binance_ws.py:159-183 | compile |

### Level 1 (after R0, R1)

#### BLOCK R2: Rust indicator engine
```yaml
id: "R2"
type: implement
level: 1
deps: ["R0", "R1"]
files:
  - flowsurface_src/bridge/src/indicators.rs (NEW)
description: |
  Reuse flowsurface_src/data/src/chart/ta.rs functions for all 20+ indicators.
  Port missing deltas: Volume Delta, CVD, Delta Z-Score, SuperTrend, EMA trend.
guardrails:
  - "Must match Python indicator values within 0.01% tolerance"
  - "Read-only reference to ta.rs — no modifications needed there"
estimated_tokens: 5000
checkpoint: true
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| R2-T1 | `flowsurface_src/bridge/src/indicators.rs` | L1-40 | new | Imports + `compute_indicators()` entry point taking &[Candle] → IndicatorOutput | compile |
| R2-T2 | `flowsurface_src/bridge/src/indicators.rs` | L41-80 | new | EMA (9/20/50) using ta.rs `ema_series()`, RSI using `rsi_last()` | verify values |
| R2-T3 | `flowsurface_src/bridge/src/indicators.rs` | L81-120 | new | MACD (12/26/9), Bollinger Bands (20, 2σ) using `macd()`, `bollinger_bands()` | verify values |
| R2-T4 | `flowsurface_src/bridge/src/indicators.rs` | L121-160 | new | VWAP, ATR using `vwap_series()`, `atr_series()` | verify values |
| R2-T5 | `flowsurface_src/bridge/src/indicators.rs` | L161-220 | new | Volume Delta: buy_vol/sell_vol/delta; CVD: cumsum; Delta Z-Score: (delta - ma_20)/std_20 | verify values |
| R2-T6 | `flowsurface_src/bridge/src/indicators.rs` | L221-280 | new | SuperTrend: HL2 ± 3*ATR with band persistence logic (port indicators.py:100-141) | verify values |
| R2-T7 | `flowsurface_src/bridge/src/indicators.rs` | L281-310 | new | EMA trend: trend_bullish = ema_9 > ema_20 > ema_50 | compile |
| R2-T8 | `flowsurface_src/bridge/src/indicators.rs` | L311-340 | new | IndicatorOutput struct: all 25+ fields serializable to JSON | compile |

### Level 2 (after R2)

#### BLOCK R3: Redis IPC Publisher
```yaml
id: "R3"
type: implement
level: 2
deps: ["R2"]
files:
  - flowsurface_src/bridge/src/redis_pub.rs (NEW)
  - flowsurface_src/bridge/src/main.rs (modify L50-95)
description: |
  Redis pub/sub bridge. WS→indicators→Redis pipeline in tokio main loop.
  Channel: algotrading:{pair}:{tf}:candles
  Publish on every completed kline, heartbeat every 5s.
guardrails:
  - "Redis host: 127.0.0.1:6379 (no auth by default)"
  - "JSON format must match schema expected by Python subscriber"
estimated_tokens: 3000
checkpoint: true
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| R3-T1 | `flowsurface_src/bridge/src/redis_pub.rs` | L1-30 | new | `RedisPublisher` struct: connect to `redis://127.0.0.1:6379` | compile |
| R3-T2 | `flowsurface_src/bridge/src/redis_pub.rs` | L31-70 | new | `publish_candles()` — serialize IndicatorOutput → JSON, publish to channel | compile |
| R3-T3 | `flowsurface_src/bridge/src/redis_pub.rs` | L71-90 | new | Heartbeat publish every 5 seconds if no completed kline | compile |
| R3-T4 | `flowsurface_src/bridge/src/main.rs` | L50-95 | modify | Wire WS → indicators → Redis in tokio::select! main loop | `cargo build` |
| R3-T5 | - | terminal | execute | Start bridge, verify `redis-cli SUBSCRIBE` shows data | redis-cli |

#### BLOCK R4: Python Redis Subscriber
```yaml
id: "R4"
type: implement
level: 2
deps: ["R2"]
files:
  - ui/redis_stream.py (NEW)
  - ui/pages/11_flowsurface.py (modify L34-54, L178-210, L200)
  - requirements.txt (modify append)
description: |
  Replace Python BinanceStream + compute_indicators with Redis subscriber.
  RedisStream class subscribes to algotrading:{pair}:{tf}:candles,
  parses JSON → pandas DataFrame. Indicators already computed in Rust.
guardrails:
  - "Must be drop-in compatible with existing flowsurface page"
  - "Indicators column names must match what render_flowsurface_chart() expects"
estimated_tokens: 3000
checkpoint: true
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| R4-T1 | `ui/redis_stream.py` | L1-30 | new | `RedisStream` class: init with pair/tf/market, redis client, channel name | file exists |
| R4-T2 | `ui/redis_stream.py` | L31-60 | new | `get_candles()` — parse latest JSON from Redis → pandas DataFrame | unit test |
| R4-T3 | `ui/redis_stream.py` | L61-80 | new | `status()` — connected state, last_update, candle_count | compile |
| R4-T4 | `ui/redis_stream.py` | L81-100 | new | `stop()` — close Redis connection | compile |
| R4-T5 | `ui/pages/11_flowsurface.py` | L34-54 | modify | `_get_stream()` → return RedisStream instead of BinanceStream | page loads |
| R4-T6 | `ui/pages/11_flowsurface.py` | L200 | modify | Remove `df = compute_indicators(df)` — done in Rust | no crash |
| R4-T7 | `requirements.txt` | append | modify | Add `redis>=5.0.0` | pip install |

### Level 3 (after R3, R4)

#### BLOCK R5: NEXUS Learning Loop
```yaml
id: "R5"
type: implement
level: 3
deps: ["R3", "R4"]
files:
  - nexus/event_bridge.py (modify L10-45)
  - flowsurface_src/bridge/src/execution.rs (NEW)
  - flowsurface_src/bridge/src/main.rs (modify L95-120)
  - .env (modify append)
description: |
  Connect trade outcomes back through NEXUS:
  - Rust execution stub reads signals from Redis, publishes outcomes
  - NEXUS event_bridge receives outcomes → Thompson update → ChromaDB
  - Full OODA loop: execute → outcome → learn → better strategy
guardrails:
  - "Outcome format must match existing event_bridge.py schema"
  - "Rust execution is stub-only — dry-run mode by default"
estimated_tokens: 4000
checkpoint: true
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| R5-T1 | `flowsurface_src/bridge/src/execution.rs` | L1-40 | new | Trade struct + ExecutionEngine stub: `execute_signal(Signal)` | compile |
| R5-T2 | `flowsurface_src/bridge/src/execution.rs` | L41-80 | new | OutcomePublisher: after exit, serialize trade outcome → Redis `algotrading:outcomes` | compile |
| R5-T3 | `flowsurface_src/bridge/src/main.rs` | L95-120 | modify | Add signal subscriber loop: listen `algotrading:signals`, call execution | compile |
| R5-T4 | `nexus/event_bridge.py` | L10-45 | modify | `record_trade(trade_dict)` — takes outcome from Redis, calls record_outcome() | test |
| R5-T5 | `nexus/event_bridge.py` | L46-55 | modify | Subscribe to `algotrading:outcomes` Redis channel | test |
| R5-T6 | `.env` | append | modify | Add REDIS_URL, RUST_WS_BRIDGE_ENABLED | file exists |

### Level 4 (after R5)

#### BLOCK R6: Verification & Benchmark
```yaml
id: "R6"
type: verify
level: 4
deps: ["R5"]
files:
  - scripts/test_rust_bridge.py (NEW)
  - scripts/benchmark_latency.py (NEW)
  - graphify-out/live_tracker.py (modify L28-88)
  - graphify-out/phase_tracker.json (modify — seed R0-R6)
description: |
  Full E2E verification: Rust bridge → Redis → Streamlit.
  Latency benchmark comparing Python vs Rust pipeline.
  Update live_tracker PHASE_IDS/DEPS/FILES with R0-R6.
guardrails:
  - "All 10 NEXUS features must still pass (113/113)"
  - "Rust pipeline must be >= 5x faster than Python for 1000-candle indicator batch"
estimated_tokens: 3000
checkpoint: true
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| R6-T1 | `scripts/test_rust_bridge.py` | NEW | new | E2E test: start Rust bridge → verify Redis data → verify Streamlit renders → stop | pytest |
| R6-T2 | `scripts/benchmark_latency.py` | NEW | new | Compare Python WS→pandas vs Rust WS→ta.rs→Redis for 100 candles | report output |
| R6-T3 | `graphify-out/live_tracker.py` | L28-88 | modify | Add R0-R6 to PHASE_IDS, PHASE_DEPS, PHASE_FILES | track.py live works |
| R6-T4 | `graphify-out/phase_tracker.json` | modify | modify | Seed R0-R6 phase structures with all tasks | track.py status shows phases |
| R6-T5 | terminal | execute | execute | Full verification suite: 113/113 NEXUS + Rust E2E + latency report | all pass |

---

## File Summary

| File | Action | Phase |
|------|--------|-------|
| `flowsurface_src/bridge/Cargo.toml` | NEW | R0 |
| `flowsurface_src/bridge/src/main.rs` | NEW | R0, R3, R5 |
| `flowsurface_src/bridge/src/config.rs` | NEW | R0 |
| `flowsurface_src/bridge/src/ws.rs` | NEW | R1 |
| `flowsurface_src/bridge/src/candles.rs` | NEW | R1 |
| `flowsurface_src/bridge/src/indicators.rs` | NEW | R2 |
| `flowsurface_src/bridge/src/redis_pub.rs` | NEW | R3 |
| `flowsurface_src/bridge/src/execution.rs` | NEW | R5 |
| `flowsurface_src/Cargo.toml` | MODIFY L30-35 | R0 |
| `ui/redis_stream.py` | NEW | R4 |
| `ui/pages/11_flowsurface.py` | MODIFY L34-54, L178-210, L200 | R4 |
| `nexus/event_bridge.py` | MODIFY L10-45 | R5 |
| `requirements.txt` | MODIFY append | R4 |
| `.env` | MODIFY append | R5 |
| `scripts/test_rust_bridge.py` | NEW | R6 |
| `scripts/benchmark_latency.py` | NEW | R6 |
| `graphify-out/live_tracker.py` | MODIFY L28-88 | R6 |
| `graphify-out/phase_tracker.json` | MODIFY seed | R6 |

---

## Live Tracking Protocol

```bash
# Start tracking
python3 graphify-out/track.py init-plan "Dual Engine Rust Python" "Build Rust WS+indicator+execution engine"
python3 graphify-out/track.py start R0

# Per-phase: begin, edit, mark, complete
python3 graphify-out/track.py start  R0
python3 graphify-out/track.py mark   R0 R0-T1 verified
python3 graphify-out/track.py mark   R0 R0-T2 verified
python3 graphify-out/track.py mark   R0 R0-T3 verified
python3 graphify-out/track.py mark   R0 R0-T4 verified
python3 graphify-out/track.py complete R0

# Monitor progress
python3 graphify-out/track.py live     # DAG overview
python3 graphify-out/track.py status   # Task-level detail
python3 graphify-out/track.py checkpoint R2  # Save state
```
