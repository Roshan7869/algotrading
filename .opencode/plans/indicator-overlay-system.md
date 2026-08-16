# Plan: Flowsurface On-Chart Indicator Overlay System

## Goal
Design and implement on-chart indicator overlay system for Flowsurface desktop with strategy-aware layouts and professional trading workstation features.

## Created
2026-05-24

---

## Resource Discovery (Phase 0.7)

| Resource | Type | Confidence | Rationale |
|----------|------|------------|-----------|
| `frontend_ui` | cluster | 0.38 | GUI indicator rendering |
| `plan-design-review` | skill | 0.99 | Design review for indicator layout |
| `design-consultation` | skill | 0.85 | Visual design system |
| `plan-eng-review` | skill | 0.85 | Architecture review |
| `qa` | skill | — | Testing overlays |
| `architect` | agent | — | System design |
| `researcher` | agent | — | Study professional setups |
| `strategy-kb` | MCP | — | Query strategy database |

---

## Dependency Graph

```
level_0: [P1, P2]           # Research + Trait design (parallel)
level_1: [P3]               # Price-scale overlays (needs P1+P2)
level_2: [P4]               # Structural overlays (needs P3)
level_3: [P5, P6]           # Preset layouts + Config CRUD (parallel, needs P4)
level_4: [P7]               # Volume Profile (needs P4)
level_5: [P8]               # Verification (needs P5+P6+P7)
```

---

## Phases

### P1: Research & Indicator Classification
**Type**: research
**Status**: not_started
**Deps**: none
**Guardrails**: Every classification must cite evidence from code or strategy DB
**Estimated tokens**: 4000
**Checkpoint**: true

#### Tasks

**P1-T1 — Classify all 23 KlineIndicators by rendering type**
- **File**: `flowsurface_src/data/src/chart/indicator.rs`
- **Lines**: KlineIndicator enum
- **Action**: research
- **Change**: For each of the 23 KlineIndicator variants, determine: (a) is it price-scale based? (b) does it share the candle chart's Y-axis? (c) can it be overlaid on candles?
- **Output**: classification table → on-chart vs sub-chart
- **Subtasks**:
  - P1-T1.1: Identify price-scale indicators (SMA, EMA, ALMA, VWAP, Bollinger, PivotPoints)
  - P1-T1.2: Identify structural overlay indicators (FVG, OrderBlock, MSS, CvdDivergence)
  - P1-T1.3: Identify sub-chart-only indicators (RSI, MACD, Volume, ATR, Aroon, ADX, CVD, Delta, Absorption, ZScore, Imbalance, LVN, OpenInterest, Candlestick, RVOL)
- **Verification**: All 23 classified, rationale documented

**P1-T2 — Study professional trading workstation layouts**
- **File**: strategy-kb / research
- **Lines**: N/A
- **Action**: research
- **Change**: Query ChromaDB strategy knowledge base for professional indicator setups. Study TradingView, Sierra Chart, ATAS, Jigsaw patterns.
- **Output**: Layout pattern catalog
- **Subtasks**:
  - P1-T2.1: Query ChromaDB for strategy setups that reference specific indicator combinations
  - P1-T2.2: Research TradingView-style overlay vs sub-chart patterns
  - P1-T2.3: Study orderflow workstation layouts (CVD+Delta+DOM+Footprint)
- **Verification**: Layout patterns documented

**P1-T3 — Identify data pipeline requirements for overlays**
- **File**: `flowsurface_src/src/chart/kline.rs`
- **Lines**: L940-L1119
- **Action**: research
- **Change**: Trace how `KlineChart::draw()` accesses candle data. Understand `ViewState.price_to_y()` coordinate mapping. Identify what data overlay indicators need access to.
- **Output**: Data flow diagram for overlays
- **Verification**: Data dependencies documented

---

### P2: On-Chart Overlay Trait Design
**Type**: implement
**Status**: not_started
**Deps**: P1
**Guardrails**: Must not break existing indicator rendering
**Estimated tokens**: 6000
**Checkpoint**: true

#### Tasks

**P2-T1 — Add `draw_overlay()` and `is_overlay()` to `KlineIndicatorImpl` trait**
- **File**: `flowsurface_src/src/chart/indicator/kline.rs`
- **Lines**: L98-L143
- **Action**: modify
- **Change**: Add two trait methods with default no-op implementations:
  ```rust
  fn is_overlay(&self) -> bool { false }
  fn draw_overlay(&self, frame: &mut Frame, ctx: &ViewState,
      theme: &Theme, range: RangeInclusive<u64>) {}
  ```
- **Subtasks**:
  - P2-T1.1: Modify trait definition at L98-L143
  - P2-T1.2: Verify no existing indicators break (default impl = no-op)
- **Verification**: `cargo build -p flowsurface` passes

**P2-T2 — Modify `KlineChart::view_indicators()` to separate overlays from sub-charts**
- **File**: `flowsurface_src/src/chart/kline.rs`
- **Lines**: L52-L78
- **Action**: modify
- **Change**: Split `view_indicators()` into:
  - `view_overlay_indicators() -> Vec<&dyn KlineIndicatorImpl>` — indicators where `is_overlay() == true`
  - `view_subchart_indicators() -> Vec<Element>` — indicators where `is_overlay() == false`
- **Subtasks**:
  - P2-T2.1: Add overlay filtering method
  - P2-T2.2: Keep sub-chart rendering unchanged
- **Verification**: `cargo build` passes, sub-chart indicators still render

**P2-T3 — Modify `KlineChart::draw()` to call overlay renders**
- **File**: `flowsurface_src/src/chart/kline.rs`
- **Lines**: L1084-L1087 (after candle drawing, before last price line)
- **Action**: modify
- **Change**: After candle bodies/wicks are drawn, iterate overlay-capable indicators and call `draw_overlay()` on the same canvas frame
- **Subtasks**:
  - P2-T3.1: Identify insertion point in draw() method
  - P2-T3.2: Add overlay iteration loop
  - P2-T3.3: Verify no interference with existing candle rendering
- **Verification**: `cargo build` passes

**P2-T4 — Modify `chart.rs view()` to exclude overlays from sub-chart panel**
- **File**: `flowsurface_src/src/chart.rs`
- **Lines**: L575-L608
- **Action**: modify
- **Change**: When building the MultiSplit panel stack, exclude overlay indicators (they're now drawn on main chart). Only pass sub-chart indicators to `view_indicators()`.
- **Subtasks**:
  - P2-T4.1: Filter indicators passed to MultiSplit
  - P2-T4.2: Ensure data_labels_always_visible and other settings still apply
- **Verification**: `cargo build` passes, non-overlay indicators still render correctly

---

### P3: Price-Scale On-Chart Overlays
**Type**: implement
**Status**: not_started
**Deps**: P2
**Guardrails**: Must use candle chart's `price_to_y()` not separate YScale
**Estimated tokens**: 8000
**Checkpoint**: true

#### Tasks

**P3-T1 — Implement `draw_overlay()` for SMA indicators**
- **File**: `flowsurface_src/src/chart/indicator/kline/`
- **Lines**: NEW
- **Action**: modify
- **Change**: Add `is_overlay() -> true` and `draw_overlay()` to existing SMA indicator modules. Render SMA lines directly on candle chart canvas using `ctx.price_to_y()`.
- **Subtasks**:
  - P3-T1.1: Modify SMA indicator to implement draw_overlay
  - P3-T1.2: Draw line series using candle chart coordinate system
  - P3-T1.3: Verify lines align perfectly with candle prices
- **Verification**: Overlay SMA lines visible on candle chart, aligned with price

**P3-T2 — Implement `draw_overlay()` for EMA indicators**
- **File**: `flowsurface_src/src/chart/indicator/kline/`
- **Lines**: NEW
- **Action**: modify
- **Change**: Same as P3-T1 but for EMA. Add overlay rendering to existing EMA indicator module.
- **Verification**: Overlay EMA lines visible and aligned

**P3-T3 — Implement `draw_overlay()` for Bollinger Bands**
- **File**: `flowsurface_src/src/chart/indicator/kline/bollinger.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: Bollinger Bands (upper/middle/lower) rendered as overlay on candle chart. Middle line as solid, bands as semi-transparent fill.
- **Subtasks**:
  - P3-T3.1: Draw middle SMA line
  - P3-T3.2: Draw upper/lower band lines with dash style
  - P3-T3.3: Optional semi-transparent fill between bands
- **Verification**: Bollinger bands overlay on candles, correct price alignment

**P3-T4 — Implement `draw_overlay()` for VWAP**
- **File**: `flowsurface_src/src/chart/indicator/kline/vwap.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: VWAP line drawn as overlay. Golden line with dot/dash style.
- **Verification**: VWAP overlay visible on candle chart

**P3-T5 — Implement `draw_overlay()` for ALMA**
- **File**: `flowsurface_src/src/chart/indicator/kline/alma.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: ALMA line drawn as overlay on candle chart.
- **Verification**: ALMA overlay visible and aligned

---

### P4: Structural On-Chart Overlays
**Type**: implement
**Status**: not_started
**Deps**: P3
**Guardrails**: Structural overlays must render at correct price levels, not as continuous lines
**Estimated tokens**: 8000
**Checkpoint**: true

#### Tasks

**P4-T1 — Implement `draw_overlay()` for Pivot Points**
- **File**: `flowsurface_src/src/chart/indicator/kline/pivot_points.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: Draw horizontal lines at R1/R2/R3/PP/S1/S2/S3 levels on candle chart.
- **Verification**: Pivot levels visible as horizontal lines on candle chart

**P4-T2 — Implement `draw_overlay()` for FVG (Fair Value Gaps)**
- **File**: `flowsurface_src/src/chart/indicator/kline/fvg.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: Render FVG zones as semi-transparent rectangular regions on candle chart between imbalance extremes.
- **Verification**: FVG rectangles visible between correct candle wicks

**P4-T3 — Implement `draw_overlay()` for Order Blocks**
- **File**: `flowsurface_src/src/chart/indicator/kline/order_block.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: Render OB zones as semi-transparent rectangular regions on candle chart.
- **Verification**: OB rectangles visible at correct swing base candle ranges

**P4-T4 — Implement `draw_overlay()` for MSS (Market Structure Shift)**
- **File**: `flowsurface_src/src/chart/indicator/kline/mss.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: Draw MSS markers (arrows/lines) at structure break points on candle chart.
- **Verification**: MSS markers visible at correct swing break points

**P4-T5 — Implement `draw_overlay()` for CVD Divergence**
- **File**: `flowsurface_src/src/chart/indicator/kline/cvd_divergence.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: Draw divergence markers on candle chart where CVD and price diverge.
- **Verification**: Divergence markers visible at correct price-CVD divergence points

---

### P5: Strategy-Aware Preset Layouts
**Type**: implement
**Status**: not_started
**Deps**: P4
**Guardrails**: Presets must map to real ChromaDB strategy categories
**Estimated tokens**: 5000
**Checkpoint**: true

#### Tasks

**P5-T1 — Define strategy layout presets from ChromaDB categories**
- **File**: `flowsurface_src/data/src/chart/indicator.rs` (new config)
- **Lines**: NEW
- **Action**: new
- **Change**: Create preset layout definitions based on ChromaDB strategy categories:
  - `scalping` → Volume, CVD, Delta, Absorption, Imbalance, DOM
  - `swing` → EMA, VWAP, Bollinger, RSI, MACD, LVN
  - `orderflow` → CVD, Delta, Absorption, ZScore, Imbalance, Footprint
  - `ict_mss` → FVG, OrderBlock, MSS, CVD Divergence, PivotPoints
  - `trend` → SMA, EMA, Bollinger, ATR, ADX, RVOL
- **Subtasks**:
  - P5-T1.1: Query ChromaDB for strategy categories and indicator combinations
  - P5-T1.2: Define LayoutPreset enum with indicator+config combinations
  - P5-T1.3: Create default configs for each preset
- **Verification**: Presets compile and load

**P5-T2 — Add layout preset selector UI**
- **File**: `flowsurface_src/src/modal/pane/indicators.rs`
- **Lines**: NEW
- **Action**: modify
- **Change**: Add dropdown/selector in indicator modal for "Layout Preset". Selecting a preset replaces current indicator list with preset config.
- **Subtasks**:
  - P5-T2.1: Add preset selector widget
  - P5-T2.2: Wire preset selection to indicator replacement
  - P5-T2.3: Add "Reset to Preset" button
- **Verification**: Preset selector appears and changes indicator set

**P5-T3 — Wire presets to indicator config (periods, thresholds)**
- **File**: `flowsurface_src/src/modal/pane/settings.rs`
- **Lines**: L629-L1103
- **Action**: modify
- **Change**: When a preset is loaded, apply its custom IndicatorConfig values (not just which indicators but their parameters)
- **Verification**: Preset applies parameter values

---

### P6: Indicator Config CRUD
**Type**: implement
**Status**: not_started
**Deps**: P4
**Guardrails**: Must not break existing parameter editing
**Estimated tokens**: 6000
**Checkpoint**: true

#### Tasks

**P6-T1 — Add indicator parameter editor modal**
- **File**: `flowsurface_src/src/modal/pane/settings.rs`
- **Lines**: L629-L1103
- **Action**: modify
- **Change**: Enhance existing parameter sliders to support:
  - All numerical parameters (period, threshold, multiplier, etc.)
  - Color picker per indicator line
  - Toggle visibility per indicator component (e.g., show upper BB only)
- **Subtasks**:
  - P6-T1.1: Audit existing IndicatorConfig for all parameter types
  - P6-T1.2: Add color config field per indicator
  - P6-T1.3: Add component visibility toggles
- **Verification**: All parameters editable via UI

**P6-T2 — Add/remove indicator instances dynamically**
- **File**: `flowsurface_src/src/modal/pane/indicators.rs`
- **Lines**: L1-L162
- **Action**: modify
- **Change**: Support multiple instances of same indicator type (e.g., SMA(20) + SMA(50) + SMA(200)). Currently the `Vec<KlineIndicator>` is a set — change to allow duplicates with different configs.
- **Subtasks**:
  - P6-T2.1: Change data model to allow duplicate indicator types
  - P6-T2.2: Update UI to distinguish instances by config
  - P6-T2.3: Add instance naming/labeling
- **Verification**: Multiple SMA instances with different periods possible

**P6-T3 — Serialize/deserialize custom indicator configs**
- **File**: `flowsurface_src/data/src/layout/` or `data/src/config/`
- **Lines**: NEW
- **Action**: new
- **Change**: Save/load user's custom indicator configurations as part of layout persistence
- **Verification**: Config persists across app restart

---

### P7: Volume Profile Enhancement
**Type**: implement
**Status**: not_started
**Deps**: P4
**Guardrails**: Must not break existing LVN/HVN implementation
**Estimated tokens**: 6000
**Checkpoint**: true

#### Tasks

**P7-T1 — Research full session volume profile implementation**
- **File**: `flowsurface_src/data/src/chart/ta.rs`
- **Lines**: L508-L596 (existing LVN/HVN)
- **Action**: research
- **Change**: Compare current LVN/HVN implementation with TradingView-style volume profile (session-based, value area, VAH/VAL, POC). Identify gaps.
- **Output**: Gap analysis document
- **Verification**: Gaps documented

**P7-T2 — Implement session-based volume profile**
- **File**: `flowsurface_src/data/src/chart/ta.rs` or new module
- **Lines**: NEW
- **Action**: new
- **Change**: Add volume profile computation: price binning, volume aggregation, value area calculation (70%), POC identification, VAH/VAL calculation.
- **Verification**: VP matches expected values from test data

**P7-T3 — Add volume profile indicator render**
- **File**: `flowsurface_src/src/chart/indicator/kline/` (new `volume_profile.rs`)
- **Lines**: NEW
- **Action**: new
- **Change**: New indicator module rendering horizontal volume histogram on the right side of the candle chart (overlay or sub-panel). Shows POC line, value area, high-volume nodes.
- **Verification**: Volume profile renders with correct data

---

### P8: Verification & Benchmark
**Type**: verify
**Status**: not_started
**Deps**: P5, P6, P7
**Guardrails**: All 23 indicators still functional, no regressions
**Estimated tokens**: 4000
**Checkpoint**: true

#### Tasks

**P8-T1 — Verify all 23 indicators still render correctly**
- **File**: terminal
- **Lines**: -
- **Action**: execute
- **Change**: Run Flowsurface desktop. Toggle each of the 23 indicators. Verify:
  - Overlay indicators appear on candle chart
  - Sub-chart indicators appear in panels below
  - No crashes, no missing data
- **Verification**: All 23 verified

**P8-T2 — Verify overlay alignment with candle prices**
- **File**: terminal
- **Lines**: -
- **Action**: execute
- **Change**: Cross-check SMA/EMA/Bollinger overlay values against known data points. Ensure price_to_y() mapping produces correct alignment.
- **Verification**: All overlays within 1px of expected position

**P8-T3 — Verify layout presets work**
- **File**: terminal
- **Lines**: -
- **Action**: execute
- **Change**: Test each layout preset (scalping, swing, orderflow, ict_mss, trend). Verify correct indicators load with correct parameters.
- **Verification**: All 5 presets functional

**P8-T4 — Verify indicator config CRUD persistence**
- **File**: terminal
- **Lines**: -
- **Action**: execute
- **Change**: Add custom indicator instance, configure parameters, close and reopen app. Verify config persists.
- **Verification**: Config persists across restart

**P8-T5 — Performance benchmark**
- **File**: terminal (manual)
- **Lines**: -
- **Action**: execute
- **Change**: Measure frame rate with 0, 5, 10, 15, 20 overlay indicators. Ensure no frame drops.
- **Verification**: No significant performance regression

---

## Guardrails (Global)

1. `cargo build -p flowsurface` must pass after every phase
2. No existing 23 indicators may break (all must still render)
3. Overlay indicators must use candle chart's price_to_y() coordinate system
4. Sub-chart indicators must remain unchanged
5. All config parameters must be persisted across sessions
6. Layout presets must have traceable mapping to ChromaDB strategy data

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Overlay indicators misaligned with candles | High | Test with known data points, visual verification |
| Performance regression with many overlays | Medium | Benchmark in P8-T5, cap overlays if needed |
| Multiple indicator instances breaks existing layout loading | Medium | Backward-compatible serialization format |
| Volume profile computation too slow | Low | Offload to background computation or cache |

---

## Resources

| Phase | Cluster | Skills | Agents |
|-------|---------|--------|--------|
| P1 | knowledge_wiki | researcher, strategy-kb | researcher |
| P2 | frontend_ui | plan-eng-review | architect, code-reviewer |
| P3 | frontend_ui | plan-design-review | architect, designer |
| P4 | frontend_ui | plan-design-review | architect, designer |
| P5 | knowledge_wiki | adaptive-imagining-cat | specification |
| P6 | frontend_ui | design-consultation | designer |
| P7 | backend_api | adaptive-imagining-cat | researcher |
| P8 | quality_security | qa, review | qa-engineer, code-reviewer |

---

## Approval

Present this plan to the user. Type "go" or "approve" to start autopilot execution.
