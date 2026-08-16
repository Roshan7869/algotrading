# Flowsurface-Algotrading Integration — Graphify Typed DAG Plan

```yaml
goal: "Extend flowsurface Rust charting app with orderflow/volume-profile charts +
       local data source + Python bridge, integrated into Algotrading pipeline"
created: "2026-05-21T19:40:00Z"
status: "pending_approval"
execution_tracker:
  total_blocks: 18
  completed: 0
  in_progress: null
  failed: []
  verified: 0
resource_discovery:
  cluster: "frontend_ui"
  iso_top_skills: ["freqtrade-plots", "ds-trading-terminal"]
  thompson_routed: ["adaptive-imagining-cat", "frontend-ui-engineering", "autopilot"]
  orchestrator_tools: ["design-html", "hooks_build_agents", "plan-tune"]
  confidence: 0.833
dependency_graph:
  level_0:
    - P0: "Local data connector in flowsurface"
    - P1: "Python data export bridge"
  level_1:
    - P2: "Add OrderflowChart to content enum + pane system"
    - P3: "Add VolumeProfileChart to content enum + pane system"
  level_2:
    - P4: "Implement OrderflowChart struct + rendering"
    - P5: "Implement VolumeProfileChart struct + rendering"
  level_3:
    - P6: "Implement CVD indicator"
    - P7: "Implement Delta indicator"
    - P8: "Implement Absorption indicator"
  level_4:
    - P9: "Wire local data source to all chart types"
    - P10: "Orderflow/VP settings panels"
  level_5:
    - P11: "Build flowsurface and verify compile"
    - P12: "Streamlit launch page"
  level_6:
    - P13: "Integration test: backtest data → flowsurface"
    - P14: "Integration test: live OHLCV → flowsurface"
```

---

## Phase 0: First Principles Deconstruction

### Root question
Algotrading has 338 OHLCV files, 1735 backtest ZIPs, SQLite trade DB, real-time shared_config state — but **zero graphical charts**. Flowsurface has excellent Rust charts but only connects to live exchanges. The irreducible gap: no offline data source + no orderflow/VP chart types + no Python→Rust bridge.

### Component atomization
| Component | What | Why | Inputs | Outputs | Failure mode |
|-----------|------|-----|--------|---------|--------------|
| LocalConnector | File-based data source replacing WS | Flowsurface only has WS exchange adapters | JSON/Feather files of OHLCV, trades, depth | `StreamKind` events (same as exchange) | Corrupt JSON, missing fields |
| OrderflowChart | Bid/ask delta + CVD footprint chart | No orderflow viz exists in flowsurface | Trades, Klines, Depth | Canvas render of delta bars + CVD line | Performance with 1M+ trades |
| VolumeProfileChart | Volume profile with VAH/VAL/POC | None exists | Trades/Klines | Profile histogram render | Wrong aggregation windows |
| Custom Indicators | CVD divergence, delta squeeze, absorption | Trading needs these signals | KlineDataPoints | Overlay lines/labels on chart | False signals from bad data |
| PythonBridge | Exports Algotrading data to JSON | Rust can't read Python DBs | feather files, SQLite, JSON state | NDJSON files in Flowsurface data dir | Schema mismatch |
| StreamlitLaunch | Config + launch page in UI | User needs to control flowsurface from Streamlit | flowsurface binary path, data dir selection | subprocess.Popen, page UI | Display server (X11/Wayland) issues |

---

## Phase 1: State Analysis (verified)

**Flowsurface source (cloned at flowsurface_src/):**
- 5-layer chart registration: data enums → content kind → pane content → chart struct → dashboard dispatch
- Generic `Chart` trait with `PlotConstants`, `canvas::Program<Message>`, `view<T>()`, `update<T>()`
- Exchange adapters: Binance, Bybit, Hyperliquid, OKX, MEXC — all WS-based
- Data ingestion: `update_latest_klines()`, `ingest_depth()`, `ingest_trades()`, `distribute_fetched_data()`
- 6 current chart types: Starter, Heatmap, ShaderHeatmap, Kline/Footprint, Candlestick, Time&Sales, Ladder, Comparison

**Algotrading data (verified):**
- 338 feather OHLCV files in `user_data/data/`
- 1735 backtest ZIPs in `user_data/backtest_results/`
- `tradesv3.sqlite` (8 live trades, rich schema)
- `shared_config/` (circuit_breaker, market_regime, signal_bus, orchestrator_result — JSON)
- `outcome_history.json` (140 trades)
- `strategy_performance_db.json` (25 strategies)
- ChromaDB (592 strategy vectors + 6 user knowledge)
- **Zero charting exists in Streamlit UI** — pure text/dataframes

---

## Phase 2: Typed DAG — Execution Blocks

### Level 0 (Independent — parallel)

#### BLOCK P0: Local data connector in flowsurface
```yaml
id: "P0"
type: implement
level: 0
files:
  - flowsurface_src/src/connector/local.rs (NEW)
  - flowsurface_src/src/connector.rs (modify)
  - flowsurface_src/Cargo.toml (modify)
description: |
  Create a LocalConnector that reads JSON/NDJSON files from FLOWSURFACE_DATA_PATH
  instead of WebSocket streams. Emulates exchange::Event types so existing dispatch
  code works unchanged. Supports OHLCV (KlineReceived), trades (TradesReceived),
  and depth (DepthReceived) events read from files on a polling interval.
inputs: []
outputs:
  - "local.rs with LocalConnector struct"
  - "Cargo.toml updated with serde_json (if not present)"
guardrails:
  - "Must emit same Event types as exchange adapters (KlineReceived, TradesReceived, DepthReceived)"
  - "Must support polling interval (default 250ms) with file watching (inotify)"
  - "Must not modify any existing exchange adapter code"
  - "Data format: NDJSON lines, one Event per line"
  - "File naming: {ticker}_{stream_type}.jsonl"
resources:
  cluster: "frontend_ui"
  skills: ["frontend-ui-engineering", "autopilot"]
  agents: ["architect"]
estimated_tokens: 4000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

#### BLOCK P1: Python data export bridge
```yaml
id: "P1"
type: implement
level: 0
files:
  - engine/flowsurface_bridge.py (NEW)
description: |
  Python module that reads Algotrading data sources and writes NDJSON files
  compatible with the LocalConnector. Supports:
  - OHLCV from feather files → KlineReceived events
  - Backtest trades from ZIPs → TradesReceived events
  - Live state from shared_config/ → metadata sidecar
  - SQLite trade history → enriched trade events
inputs: []
outputs:
  - "engine/flowsurface_bridge.py with export functions"
guardrails:
  - "All exports go to $FLOWSURFACE_DATA_PATH/algotrading/"
  - "NDJSON format: one JSON object per line"
  - "Kline format: {ticker, timeframe, timestamp_ms, open, high, low, close, volume}"
  - "Trade format: {ticker, timestamp_ms, price, qty, is_buyer_maker}"
  - "Must handle missing data gracefully (empty files = no event, not crash)"
resources:
  cluster: "knowledge_wiki"
  skills: ["adaptive-imagining-cat", "freqtrade-plots"]
  agents: ["researcher"]
estimated_tokens: 3000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

### Level 1 (after P0, P1)

#### BLOCK P2: Add OrderflowChart to content enum + pane system
```yaml
id: "P2"
type: implement
level: 1
depends_on: []
files:
  - flowsurface_src/data/src/layout/pane.rs (modify)
  - flowsurface_src/data/src/chart.rs (modify)
  - flowsurface_src/src/screen/dashboard/pane.rs (modify)
  - flowsurface_src/src/screen/dashboard.rs (modify)
description: |
  Register OrderflowChart in every enum/trait system:
  - ContentKind::OrderflowChart variant + ALL array + fmt
  - Pane::OrderflowChart serialization variant
  - VisualConfig::Orderflow variant
  - Content::Orderflow { chart, indicators, layout } variant
  - Dashboard dispatch arms: update_latest_klines, ingest_depth, ingest_trades
inputs: []
outputs:
  - "Compilable enum registration (chart not yet implemented, uses placeholder/todo)"
guardrails:
  - "Follows exact same pattern as HeatmapChart registration"
  - "Must compile with `cargo check` (even if chart impl is stub)"
  - "Content::Orderflow must implement all required match arms: placeholder(), initialized(), kind(), last_tick(), studies(), toggle_indicator(), etc."
resources:
  cluster: "architect"
  skills: ["frontend-ui-engineering", "autopilot"]
  agents: ["architect"]
estimated_tokens: 5000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

#### BLOCK P3: Add VolumeProfileChart to content enum + pane system
```yaml
id: "P3"
type: implement
level: 1
depends_on: []
files:
  - flowsurface_src/data/src/layout/pane.rs (modify — same file as P2)
  - flowsurface_src/data/src/chart.rs (modify)
  - flowsurface_src/src/screen/dashboard/pane.rs (modify)
  - flowsurface_src/src/screen/dashboard.rs (modify)
description: |
  Register VolumeProfileChart (same pattern as P2). This block is independent
  of P2 but shares files — merge carefully.
inputs: []
outputs:
  - "Compilable enum registration for VolumeProfileChart"
guardrails:
  - "Same pattern as HeatmapChart"
  - "Content::VolumeProfile variant in pane Content enum"
  - "Dashboard dispatch: uses trades for VP calculation"
resources:
  cluster: "architect"
  skills: ["frontend-ui-engineering", "autopilot"]
  agents: ["architect"]
estimated_tokens: 4000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

### Level 2 (after P2, P3)

#### BLOCK P4: Implement OrderflowChart struct + iced canvas rendering
```yaml
id: "P4"
type: implement
level: 2
depends_on: ["P2"]
files:
  - flowsurface_src/src/chart/orderflow.rs (NEW)
  - flowsurface_src/src/chart.rs (modify — add pub mod orderflow)
description: |
  Full OrderflowChart implementation:
  - Stores trades grouped by price level per time bucket
  - Renders bid/ask delta bars (blue=bid dominance, red=ask dominance)
  - CVD (Cumulative Volume Delta) line overlay
  - Footprint numbers on each price cell (total vol, delta, %)
  - Implements Chart trait, PlotConstants, canvas::Program<Message>
inputs: ["P2 — enum registration must exist"]
outputs:
  - "src/chart/orderflow.rs with OrderflowChart struct + all trait impls"
guardrails:
  - "Uses existing ViewState, canvas::Geometry, frame::Frame"
  - "Delta = asks_volume - bids_volume for each price level"
  - "CVD = running cumulative sum of delta across time"
  - "Max 500 price levels visible at once (auto-grouping)"
  - "Color: blue for bid dominance (#2196F3), red for ask (#F44336)"
resources:
  cluster: "frontend_ui"
  skills: ["frontend-ui-engineering", "design-html"]
  agents: ["designer", "architect"]
estimated_tokens: 8000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

#### BLOCK P5: Implement VolumeProfileChart struct + iced canvas rendering
```yaml
id: "P5"
type: implement
level: 2
depends_on: ["P3"]
files:
  - flowsurface_src/src/chart/volumeprofile.rs (NEW)
  - flowsurface_src/src/chart.rs (modify)
description: |
  Volume Profile chart:
  - Horizontal histogram of volume at each price level
  - VAH (Value Area High), VAL (Value Area Low), POC (Point of Control)
  - Value Area = 70% of total volume
  - Distribution curve (gaussian-like fit) overlay
  - Naked POC markers (levels where price hasn't revisited POC)
  - Implements Chart trait, PlotConstants, canvas::Program
inputs: ["P3 — enum registration must exist"]
outputs:
  - "src/chart/volumeprofile.rs with full impl"
guardrails:
  - "VAH/VAL computed as 70% value area"
  - "POC = price level with highest volume"
  - "Uses Frame::fill_rectangle for volume bars"
  - "Distribution curve uses Frame::fill_text for histogram bins"
resources:
  cluster: "frontend_ui"
  skills: ["frontend-ui-engineering", "design-html"]
  agents: ["designer"]
estimated_tokens: 6000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

### Level 3 (after P4, P5)

#### BLOCK P6: Implement CVD indicator
```yaml
id: "P6"
type: implement
level: 3
depends_on: ["P4"]
files:
  - flowsurface_src/src/chart/indicator.rs (modify)
  - flowsurface_src/data/src/chart/indicator.rs (modify — Add OrderFlowIndicator enum)
description: |
  CVD (Cumulative Volume Delta) as a sub-panel indicator below any chart.
  Shows running cumulative delta line with zero-line reference.
  Highlights divergence zones (price up + CVD down = bearish divergence).
inputs: ["P4 — OrderflowChart must exist to host indicator"]
outputs:
  - "OrderFlowIndicator::Cvd variant"
  - "CvdIndicator struct implementing indicator computation + rendering"
guardrails:
  - "CVD = cumulative(asks_vol - bids_vol) per bar"
  - "Divergence detection: 20-bar lookback, price HH + CVD LH = bearish"
  - "Rendered as line chart below main chart (via MultiSplit)"
resources:
  cluster: "frontend_ui"
  skills: ["frontend-ui-engineering", "freqtrade-plots"]
  agents: ["architect"]
estimated_tokens: 4000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

#### BLOCK P7: Implement Delta indicator
```yaml
id: "P7"
type: implement
level: 3
depends_on: ["P4"]
files:
  - flowsurface_src/src/chart/indicator.rs (modify)
description: |
  Per-bar delta indicator showing net volume direction.
  Green bars = positive delta (buying), Red = negative (selling).
  Normalized to percentage of total volume.
inputs: ["P4 — OrderflowChart"]
outputs:
  - "OrderFlowIndicator::Delta variant"
  - "DeltaIndicator struct"
guardrails:
  - "Delta = (ask_vol - bid_vol) / (ask_vol + bid_vol) * 100"
  - "Color gradient: stronger green/red for larger deltas"
  - "Threshold markers at +/-25%, +/-50%"
resources:
  cluster: "frontend_ui"
  skills: ["frontend-ui-engineering"]
  agents: ["architect"]
estimated_tokens: 3000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

#### BLOCK P8: Implement Absorption indicator
```yaml
id: "P8"
type: implement
level: 3
depends_on: ["P4"]
files:
  - flowsurface_src/src/chart/indicator.rs (modify)
description: |
  Absorption squeeze indicator: detects when large volume occurs
  but price barely moves — sign of accumulation/distribution.
  Shows as dots/signals on the chart.
inputs: ["P4 — OrderflowChart"]
outputs:
  - "OrderFlowIndicator::Absorption variant"
  - "AbsorptionIndicator struct"
guardrails:
  - "Absorption = high_volume AND small_range (compared to 20-bar avg)"
  - "Volume > 1.5x average AND range < 0.5x average = signal"
  - "Up absorption (green dot at high) vs down absorption (red dot at low)"
resources:
  cluster: "frontend_ui"
  skills: ["frontend-ui-engineering", "freqtrade-plots"]
  agents: ["architect"]
estimated_tokens: 3000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

### Level 4 (after P6, P7, P8)

#### BLOCK P9: Wire local data source to all chart types
```yaml
id: "P9"
type: implement
level: 4
depends_on: ["P0", "P1", "P4", "P5"]
files:
  - flowsurface_src/src/connector.rs (modify)
  - flowsurface_src/src/screen/dashboard.rs (modify)
description: |
  Wire LocalConnector events into the dashboard dispatch:
  KlineReceived → OrderflowChart.update_latest_kline + VolumeProfile.insert_hist_klines
  TradesReceived → OrderflowChart.insert_trades + VolumeProfile.insert_trades
  DepthReceived (from local file) → OrderflowChart.insert_depth
inputs: ["P0 — LocalConnector", "P4 — OrderflowChart", "P5 — VolumeProfileChart"]
outputs:
  - "Data flows from local files → chart rendering"
guardrails:
  - "Local data reads happen in a background tokio task"
  - "No blocking the UI thread during file reads"
  - "Live exchange WS continues working alongside local mode"
resources:
  cluster: "architect"
  skills: ["autopilot", "frontend-ui-engineering"]
  agents: ["architect"]
estimated_tokens: 4000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

#### BLOCK P10: Orderflow/VP settings panels
```yaml
id: "P10"
type: implement
level: 4
depends_on: ["P4", "P5"]
files:
  - flowsurface_src/src/modal/pane/settings/orderflow.rs (NEW)
  - flowsurface_src/src/modal/pane/settings/volumeprofile.rs (NEW)
  - flowsurface_src/src/modal/pane/settings.rs (modify)
description: |
  Settings modal tabs for custom chart types:
  - Orderflow: delta aggregation period, CVD smoothing, footprint cell sizing
  - VolumeProfile: time range, value area %, POC style, composite mode
inputs: ["P4 — OrderflowChart config struct", "P5 — VolumeProfile config struct"]
outputs:
  - "Settings UI for new chart types"
guardrails:
  - "Follows existing settings pattern (heatmap::Config editor)"
  - "All settings serializable to/from JSON for layout persistence"
resources:
  cluster: "frontend_ui"
  skills: ["frontend-ui-engineering", "design-html"]
  agents: ["designer"]
estimated_tokens: 4000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

### Level 5 (after P9, P10)

#### BLOCK P11: Build flowsurface and verify compile
```yaml
id: "P11"
type: verify
level: 5
depends_on: ["P9", "P10"]
description: |
  Full cargo build --release, fix any compilation errors, verify
  binary produced. Run clippy and rustfmt.
command: "cd flowsurface_src && cargo build --release 2>&1"
guardrails:
  - "Must compile with no errors"
  - "Must pass `cargo clippy --all-targets`"
  - "Must pass `cargo fmt --check`"
  - "Binary output: target/release/flowsurface"
resources:
  cluster: "quality_security"
  skills: ["qa"]
  agents: ["qa-engineer"]
estimated_tokens: 2000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

#### BLOCK P12: Streamlit launch page
```yaml
id: "P12"
type: implement
level: 5
depends_on: ["P1"]
files:
  - ui/pages/11_flowsurface.py (NEW)
  - ui/app.py (modify — add nav link)
description: |
  Streamlit page to:
  - Select data scope (pair, date range, timeframe)
  - Pick chart types (orderflow, volume profile)
  - Configure flowsurface data path
  - Export data via Python bridge
  - Launch flowsurface binary as subprocess
inputs: ["P1 — Python bridge works"]
outputs:
  - "Functional Streamlit launch page"
guardrails:
  - "Must handle DISPLAY env for WSL/X11"
  - "Must validate binary exists before launch"
  - "Export progress shown via st.progress()"
resources:
  cluster: "frontend_ui"
  skills: ["design-html", "frontend-ui-engineering", "freqtrade-plots"]
  agents: ["designer"]
estimated_tokens: 3000
checkpoint: true
checkpoint_file: "plans/flowsurface_graphify_state.json"
status: "pending"
```

### Level 6 (after P11, P12)

#### BLOCK P13: Integration test — backtest data
```yaml
id: "P13"
type: test
level: 6
depends_on: ["P11", "P12"]
description: |
  Export a backtest ZIP's trades to NDJSON, launch flowsurface,
  verify OrderflowChart loads data correctly. Check for:
  - OHLCV bars rendered
  - CVD line visible
  - Delta bars correct
  - No panic/crash on empty data
inputs: ["P11 — binary works", "P12 — export bridge works"]
outputs:
  - "Test results: pass/fail with screenshots (if display available)"
guardrails:
  - "Must not crash with empty data"
  - "Must handle out-of-order timestamps"
  - "Must handle extreme values (0 volume, NaN prices)"
resources:
  cluster: "quality_security"
  skills: ["qa", "browse"]
  agents: ["qa-engineer"]
estimated_tokens: 2000
checkpoint: false
status: "pending"
```

#### BLOCK P14: Integration test — live OHLCV
```yaml
id: "P14"
type: test
level: 6
depends_on: ["P11", "P12"]
description: |
  Export BTC/USDT 1h feather data (2018-2026, 73k rows),
  launch flowsurface, verify VolumeProfile and OrderflowChart
  render correctly with full historical data.
inputs: ["P11 — binary works", "P12 — export bridge works"]
outputs:
  - "Test results for large dataset"
guardrails:
  - "Must handle 73k rows without OOM"
  - "Rendering must stay responsive (no freeze)"
  - "Zoom/pan must work across full range"
resources:
  cluster: "quality_security"
  skills: ["qa", "benchmark"]
  agents: ["qa-engineer"]
estimated_tokens: 2000
checkpoint: false
status: "pending"
```

---

## DAG Visualization

```
Level 0:    [P0: LocalConnector]        [P1: PythonBridge]
                   |                            |
Level 1:    [P2: OrderflowEnum]          [P3: VolumeProfileEnum]
                   |                            |
Level 2:    [P4: OrderflowChart]         [P5: VolumeProfileChart]
              /    |    \                       |
Level 3:  [P6:CVD] [P7:Delta] [P8:Absorption]  |
              \    |    /                      /
Level 4:    [P9: WireLocalData]   [P10: SettingsPanels]
                   |
Level 5:    [P11: BuildVerify]     [P12: StreamlitLaunch]
                   |
Level 6:    [P13: BacktestTest]    [P14: LiveOHLCVTest]
```

---

## Graphify Live Tracking Protocol

### State file: `plans/flowsurface_graphify_state.json`
```json
{
  "plan_id": "flowsurface_integration_v1",
  "created": "2026-05-21T19:40:00Z",
  "last_updated": "2026-05-21T19:40:00Z",
  "total_blocks": 18,
  "blocks": {
    "P0": {"status": "pending", "started": null, "completed": null, "files_changed": [], "output_sha": null},
    "P1": {"status": "pending", "started": null, "completed": null, "files_changed": [], "output_sha": null},
    "...": "..."
  },
  "context_snapshots": [],
  "checkpoint_history": []
}
```

### Recovery protocol
If context compression occurs:
1. Read `plans/flowsurface_graphify_state.json`
2. Find all blocks with `status: "pending"` whose dependencies are all `completed`
3. Resume from the highest numbered completed Level
4. Re-read plan.md for guardrails
5. Continue execution

### Checkpoint triggers
- After every block completion → write state JSON
- Before any block → verify dependencies are complete
- Every 5 minutes → snapshot context + current block

---
