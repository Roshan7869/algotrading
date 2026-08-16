# Pro-Level Indicators — Execution Plan

**Goal:** Build all pro-level configurable indicators with per-candle orderflow, LVN, MSS, CVD divergence, and parameter customization system in flowsurface Rust engine

**Created:** 2026-05-23
**NEXUS Clusters:** architect (0.45), frontend_ui (0.39)
**Resources:** autopilot, frontend-ui-engineering, adaptive-imagining-cat

---

## Dependency Graph

```
Level 0: P0 (Research) → P1 (Architecture)
Level 1: P1 → P2 (Param System)
Level 2: P2 → P3 (Per-candle OF) + P4 (ATR + Pivots) + P5 (LVN/HVN)
Level 3: P3+P4+P5 → P6 (MSS + CVD Divergence + RVOL)
Level 4: P6 → P7 (Param UI Widgets)
Level 5: P7 → P8 (Strategy KB Integration)
Level 6: P8 → P9 (Testing + Verify)
```

---

## Phase 0: Foundation & Research

**Type:** research  
**Status:** complete  
**Guardrails:** All claims verifiable from codebase audit, ChromaDB queries, and published research

### Tasks

| ID | File | Lines | Action | Change | Status |
|----|------|-------|--------|--------|--------|
| P0-T1 | `flowsurface_src/data/src/chart/ta.rs` | full | verify | Audit all 2051 lines of math engine | ✅ verified |
| P0-T2 | `flowsurface_src/src/chart/indicator/kline/` | full | verify | Audit all 13 indicator panel implementations | ✅ verified |
| P0-T3 | `flowsurface_src/data/src/chart/indicator.rs` | full | verify | Audit Indicator trait + enum definitions | ✅ verified |
| P0-T4 | `flowsurface_src/src/chart/indicator/kline.rs` | full | verify | Audit KlineIndicatorImpl trait + factory | ✅ verified |
| P0-T5 | `flowsurface_src/src/chart/orderflow.rs` | full | verify | Audit orderflow chart metrics (CVD, Delta, Absorption, ZScore, Imbalance) | ✅ verified |
| P0-T6 | `flowsurface_src/src/chart/volumeprofile.rs` | full | verify | Audit volume profile (POC, VAH, VAL — no LVN) | ✅ verified |
| P0-T7 | `flowsurface_src/src/modal/pane/settings.rs` | full | verify | Audit study::Configurator pattern for UI reuse | ✅ verified |
| P0-T8 | `strategy_db/gcode_bridge.py` | — | query | Query ChromaDB for indicator usage across 592 strategy chunks | ✅ verified |
| P0-T9 | Research synthesis | — | verify | Research papers + TradingView/NinjaTrader/LuxAlgo/GoCharting professional patterns | ✅ verified |

### Key Findings
- **13 kline indicator panels** exist but ALL have **hardcoded parameters** (RSI=14, MACD=12/26/9, BB=20/2, etc.)
- **Orderflow metrics** (CVD, Delta, Absorption, ZScore, Imbalance) only exist on **separate orderflow chart page** — not as kline indicator panels
- **LVN (Low Volume Node)**: ❌ Not implemented anywhere
- **MSS (Market Structure Shift)**: ❌ Not implemented anywhere
- **CVD Divergence**: ❌ Not implemented anywhere
- **RVOL (Relative Volume)**: ❌ Not implemented anywhere
- **Study::Configurator** pattern exists for Footprint/Heatmap — perfect template for param UI
- **VisualConfig** already serde-serialized — extends naturally for indicator params

---

## Phase 1: Architecture Design

**Type:** plan  
**Status:** in_progress  
**Guardrails:** Must NOT break existing 13 indicator panels. Must be backward-compatible. Must follow existing `VisualConfig` + `study::Configurator` patterns.

### Architecture Decision: Indicator Param System

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INDICATOR CONFIG SYSTEM                       │
│                                                                      │
│  IndicatorConfig enum (new)                                          │
│  ├── Rsi(RsiConfig { period: usize, ob: f32, os: f32 })            │
│  ├── Macd(MacdConfig { fast: usize, slow: usize, signal: usize })  │
│  ├── Bollinger(BbConfig { period: usize, stddev: f32 })            │
│  ├── Adx(AdxConfig { period: usize, di_threshold: f32 })           │
│  ├── Aroon(AroonConfig { period: usize })                           │
│  ├── Alma(AlmaConfig { period: usize, offset: f32, sigma: f32 })   │
│  ├── Lvn(LvnConfig { threshold: f32, min_bins: usize })            │
│  ├── Mss(MssConfig { swing_lookback: usize, confirm: usize })      │
│  ├── CvdDivergence(CvdDivConfig { lookback: usize, type: enum })   │
│  └── Rvol(RvolConfig { lookback: usize })                           │
│                                                                      │
│  Stored in: Settings → VisualConfig → Kline(KlineConfig)            │
│  Extended to: KlineConfig { ..., indicator_params: IndicatorConfigs }│
│                                                                      │
│  Applied via: KlineIndicatorImpl::apply_config(&mut self, config)   │
└─────────────────────────────────────────────────────────────────────┘
```

### Files to Modify

| File | Change |
|------|--------|
| `data/src/layout/pane.rs` | Extend `Kline(kline::Config)` with `indicator_params: HashMap<KlineIndicator, IndicatorConfig>` |
| `data/src/chart/indicator.rs` | Add `IndicatorConfig` enum with all variant configs |
| `data/src/chart/kline.rs` | Extend `Config` struct with `indicator_params` |
| `src/chart/indicator/kline.rs` | Add `apply_config()` to `KlineIndicatorImpl` trait |
| `src/chart/kline.rs` | Pass params from Settings to `make_empty()` / `rebuild_from_source()` |
| `src/modal/pane/settings.rs` | Add param editor UI per indicator using study::Configurator pattern |

### New Indicator Panels to Build

| Indicator | Location | Depends On |
|-----------|----------|------------|
| ATR panel | `src/chart/indicator/kline/atr.rs` | P2 (param system) — uses period config |
| Pivot Points | `src/chart/indicator/kline/pivot.rs` | P2 — uses type/config |
| Per-candle Delta | `src/chart/indicator/kline/per_candle_delta.rs` | P2 |
| Per-candle Absorption | `src/chart/indicator/kline/per_candle_absorption.rs` | P2 |
| Per-candle ZScore | `src/chart/indicator/kline/per_candle_zscore.rs` | P2 |
| Per-candle Imbalance | `src/chart/indicator/kline/per_candle_imbalance.rs` | P2 |
| LVN panel | `src/chart/indicator/kline/lvn.rs` | P2 |
| MSS panel | `src/chart/indicator/kline/mss.rs` | P2 |
| CVD Divergence | `src/chart/indicator/kline/cvd_divergence.rs` | P2 |
| RVOL panel | `src/chart/indicator/kline/rvol.rs` | P2 |

---

## Phase 2: Indicator Config System

**Type:** implement  
**Status:** pending  
**Dependencies:** P1  
**Estimated tokens:** 8000  
**Checkpoint:** true  

### Level 0 Batch (parallel, no dependencies)

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P2-T1 | `data/src/chart/indicator.rs` | NEW | new | Add `IndicatorConfig` enum with variant per indicator and all numerical fields |
| P2-T2 | `data/src/chart/kline.rs` | L337-345 | modify | Extend `Config` struct: add `indicator_params: HashMap<KlineIndicator, IndicatorConfig>` |
| P2-T3 | `data/src/layout/pane.rs` | L174-185 | modify | Update `VisualConfig::Kline` serde to include new config |

### Level 1 Batch (depends on enum definition)

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P2-T4 | `src/chart/indicator/kline.rs` | L30-80 | modify | Add `apply_config(&mut self, config: &IndicatorConfig)` to `KlineIndicatorImpl` trait |
| P2-T5 | `src/chart/kline.rs` | L249-253 | modify | Update `make_empty()` → `make_with_config()` to accept `&IndicatorConfig` |
| P2-T6 | `src/chart/kline.rs` | L160-200 | modify | Store `indicator_params: HashMap<KlineIndicator, IndicatorConfig>` in `KlineChart` |
| P2-T7 | `src/chart/kline.rs` | L500-550 | modify | Add `fn apply_indicator_config(&mut self, which: KlineIndicator, config: IndicatorConfig)` |

### Level 2 Batch (update each indicator panel)

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P2-T8 | `src/chart/indicator/kline/rsi.rs` | L60-80 | modify | Read `period`, `ob_level`, `os_level` from config instead of hardcoded 14 |
| P2-T9 | `src/chart/indicator/kline/macd.rs` | L65-80 | modify | Read `fast`, `slow`, `signal` from config instead of hardcoded 12/26/9 |
| P2-T10 | `src/chart/indicator/kline/bollinger.rs` | L70-85 | modify | Read `period`, `stddev` from config instead of hardcoded 20/2.0 |
| P2-T11 | `src/chart/indicator/kline/adx.rs` | L65-80 | modify | Read `period`, `di_threshold` from config |
| P2-T12 | `src/chart/indicator/kline/aroon.rs` | L65-80 | modify | Read `period` from config instead of hardcoded 25 |
| P2-T13 | `src/chart/indicator/kline/alma.rs` | L60-75 | modify | Read `period`, `offset`, `sigma` from config |
| P2-T14 | `src/chart/indicator/kline/order_block.rs` | L34-50 | modify | Read `body_threshold`, `impulse_count`, `lookback` from config |
| P2-T15 | `src/chart/indicator/kline/candlestick_pattern.rs` | L50-65 | modify | Read thresholds from config |

---

## Phase 3: New Indicator — ATR + Pivot Points Overlay

**Type:** implement  
**Status:** pending  
**Dependencies:** P2  
**Estimated tokens:** 4000  
**Checkpoint:** true  

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P3-T1 | `src/chart/indicator/kline/atr.rs` | NEW | new | ATR indicator panel: `AtrPoint { atr }`, period from config, `ta::atr_series()` |
| P3-T2 | `src/chart/indicator/kline.rs` | L144-170 | modify | Register ATR in `make_with_config()` |
| P3-T3 | `data/src/chart/indicator.rs` | L30-45 | modify | Add `Atr` variant to `KlineIndicator` enum |
| P3-T4 | `flowsurface_src/src/chart/indicator/kline/pivot.rs` | NEW | new | Pivot Points overlay: classic/fib/camarilla, `ta::PivotPoints` |
| P3-T5 | `data/src/chart/indicator.rs` | L30-45 | modify | Add `PivotPoints` variant to `KlineIndicator` |

---

## Phase 4: New Indicators — Per-Candle Orderflow Panels

**Type:** implement  
**Status:** pending  
**Dependencies:** P2  
**Estimated tokens:** 6000  
**Checkpoint:** true  

These wire **existing orderflow data** from `OrderflowChart` (CVD/delta/absorption/zscore/imbalance) into **toggleable kline indicator panels**.

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P4-T1 | `src/chart/indicator/kline/per_candle_delta.rs` | NEW | new | Per-candle delta bars panel. Data source: `CandleStore` trades → per-candle delta |
| P4-T2 | `src/chart/indicator/kline/per_candle_absorption.rs` | NEW | new | Absorption markers on kline. Uses `ta::detect_absorption()` |
| P4-T3 | `src/chart/indicator/kline/per_candle_zscore.rs` | NEW | new | Delta Z-Score line panel. Uses `ta::delta_zscore_series()` |
| P4-T4 | `src/chart/indicator/kline/per_candle_imbalance.rs` | NEW | new | Imbalance Ratio line panel. Uses `ta::imbalance_ratio_series()` |
| P4-T5 | `data/src/chart/indicator.rs` | L30-55 | modify | Add `PerCandleDelta`, `PerCandleAbsorption`, `PerCandleZScore`, `PerCandleImbalance` variants |
| P4-T6 | `src/chart/indicator/kline.rs` | L144-180 | modify | Register all 4 new panels in factory |
| P4-T7 | `src/chart/kline.rs` | L200-250 | modify | Forward trade data to per-candle indicators via `on_insert_trades()` |

**Key design decision:** Per-candle orderflow indicators need access to raw trades. The `KlineIndicatorImpl` trait already has `on_insert_trades()`. Each new panel will accumulate trade-by-trade delta per candle, then emit the aggregate value.

---

## Phase 5: New Indicators — LVN + HVN Detection

**Type:** implement  
**Status:** pending  
**Dependencies:** P2  
**Estimated tokens:** 5000  
**Checkpoint:** true  

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P5-T1 | `data/src/chart/ta.rs` | L1790-1850 | new | Add `lvn_detection()` function: takes volume bins, threshold factor, min_bins. Returns `Vec<LvnZone>`. Algorithm from research (LuxAlgo + MQL5 AVPT): flag bins where volume < threshold × rolling_mean(volume), cluster contiguous flagged bins |
| P5-T2 | `data/src/chart/ta.rs` | L1850-1890 | new | Add `hvn_detection()` function: similar but bin volume > threshold × mean. Cluster into HVN zones |
| P5-T3 | `src/chart/indicator/kline/lvn.rs` | NEW | new | LVN/HVN overlay panel: renders colored zones on price chart. Config: `lvn_threshold`, `hvn_threshold`, `min_bins`, `value_area_pct` |
| P5-T4 | `data/src/chart/indicator.rs` | L30-55 | modify | Add `Lvn` variant |
| P5-T5 | `src/chart/indicator/kline.rs` | L144-180 | modify | Register LVN panel in factory |
| P5-T6 | `src/chart/volumeprofile.rs` | L180-220 | modify | Upgrade `recalculate_levels()` to also compute LVN/HVN zones using new ta.rs functions, emit them via the volume profile data stream |

**LVN Algorithm (from LuxAlgo + MQL5 research):**
1. Build volume bins per price level (same as existing volume profile)
2. Compute rolling mean ± stddev over N surrounding bins
3. Flag bin as LVN if volume < mean × `lvn_threshold` (default 0.5)
4. Flag bin as HVN if volume > mean × `hvn_threshold` (default 1.5) OR volume > top 20% percentile
5. Cluster contiguous flagged bins into zones
6. Filter: discard zones with width < `min_bins` (default 3)
7. Return `Vec<LvnZone { top, bottom, is_lvn, strength }>`

---

## Phase 6: New Indicators — MSS + CVD Divergence + RVOL

**Type:** implement  
**Status:** pending  
**Dependencies:** P3+P4+P5  
**Estimated tokens:** 6000  
**Checkpoint:** true  

### MSS (Market Structure Shift)

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P6-T1 | `data/src/chart/ta.rs` | L1890-1960 | new | Add `detect_market_structure_shift()`: uses `swing_points()` to find fractals, detects when price breaks structure high/low and retests. Returns `Vec<MssSignal { index, direction, broken_level }>` |
| P6-T2 | `src/chart/indicator/kline/mss.rs` | NEW | new | MSS indicator panel: arrows/colored bars for MSS signals. Config: swing_lookback, confirm_bars |
| P6-T3 | `data/src/chart/indicator.rs` | L30-55 | modify | Add `Mss` variant |

### CVD Divergence

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P6-T4 | `src/chart/indicator/kline/cvd_divergence.rs` | NEW | new | CVD Divergence detector: compares CVD trend direction vs price direction. Regular divergence (price higher high, CVD lower high) + Hidden divergence. Uses configurable lookback |
| P6-T5 | `data/src/chart/indicator.rs` | L30-55 | modify | Add `CvdDivergence` variant |

### RVOL (Relative Volume)

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P6-T6 | `data/src/chart/ta.rs` | L1960-1990 | new | Add `relative_volume_series()`: `volume / sma(volume, period)`. Returns ratio, >1 = above avg, <1 = below avg |
| P6-T7 | `src/chart/indicator/kline/rvol.rs` | NEW | new | RVOL panel: line + colored zones (high > threshold, low < threshold). Config: lookback, high_threshold, low_threshold |
| P6-T8 | `data/src/chart/indicator.rs` | L30-55 | modify | Add `Rvol` variant |

---

## Phase 7: Parameter Edit UI

**Type:** implement  
**Status:** pending  
**Dependencies:** P2+P3+P4+P5+P6  
**Estimated tokens:** 5000  
**Checkpoint:** true  

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P7-T1 | `src/modal/pane/settings.rs` | L600-700 | new | Add `fn kline_indicator_param_view(indicator: KlineIndicator, config: &IndicatorConfig, on_change) → Element`. Renders sliders/inputs per param using study::Configurator expandable card pattern |
| P7-T2 | `src/modal/pane/settings.rs` | L700-750 | new | Add config widgets for each variant: RSI (period slider), MACD (3 sliders), BB (period+stddev), ADX (period+threshold), Aroon (period), ALMA (period+offset+sigma), LVN/HVN (threshold sliders), MSS (lookback slider), etc. |
| P7-T3 | `src/modal/pane/indicators.rs` | L80-120 | modify | Add gear icon ⚙ next to each enabled indicator that opens the config panel |
| P7-T4 | `src/modal/pane/indicators.rs` | L120-150 | modify | Wire config change events → `Message::IndicatorConfigChanged(KlineIndicator, IndicatorConfig)` |
| P7-T5 | `src/chart/kline.rs` | L480-510 | modify | Handle `Message::IndicatorConfigChanged`: update stored config, call `indicator.apply_config()`, `rebuild_from_source()` |
| P7-T6 | `src/chart.rs` | L60-65 | modify | Add `IndicatorConfigChanged` variant to chart `Message` enum |

---

## Phase 8: Strategy KB Integration

**Type:** implement  
**Status:** pending  
**Dependencies:** P7  
**Estimated tokens:** 3000  
**Checkpoint:** false  

| ID | File | Lines | Action | Change |
|----|------|-------|--------|--------|
| P8-T1 | `nexus/bridge.py` | L100-130 | modify | Add `get_indicator_config(strategy_name) → IndicatorConfig`: queries ChromaDB for strategy, returns recommended indicator parameters |
| P8-T2 | `strategy_db/runtime_bridge.py` | L50-80 | modify | Add endpoint: `smart_params(setup_type, market_condition) → Dict[KlineIndicator, IndicatorConfig]`: returns optimal params based on strategy KB + outcome history |
| P8-T3 | `ui/pages/11_flowsurface.py` | L200-250 | modify | Add "Smart Config" button that calls `runtime_bridge.smart_params()` and applies recommended params to all indicators |
| P8-T4 | `src/chart/kline.rs` | L550-580 | modify | Add `apply_smart_config(&mut self, configs: HashMap<KlineIndicator, IndicatorConfig>)` batch method |

---

## Phase 9: Testing + Verification

**Type:** test + verify  
**Status:** pending  
**Dependencies:** P8  
**Estimated tokens:** 5000  
**Checkpoint:** true  

| ID | Action | Verification |
|----|--------|-------------|
| P9-T1 | Build: `cargo build --bin flowsurface` | Zero errors, zero new warnings |
| P9-T2 | Rust unit tests: `cargo test --lib` | All indicator math tests pass (including new LVN, MSS, RVOL tests) |
| P9-T3 | Verify RSI config: set period=7 → chart recomputes | `cargo test --lib rsi` |
| P9-T4 | Verify MACD config: set fast=5, slow=13, signal=5 | `cargo test --lib macd` |
| P9-T5 | Verify LVN detection logic | `cargo test --lib lvn` |
| P9-T6 | Verify MSS detection logic | `cargo test --lib mss` |
| P9-T7 | Verify RVOL computation | `cargo test --lib rvol` |
| P9-T8 | E2E: launch app, toggle all 5 new indicator panels | Manual: no crash, data renders |
| P9-T9 | E2E: change param in UI → panel recomputes | Manual: verify visual update |
| P9-T10 | Regression: all existing 13 indicator panels still work | Manual: no crash, same output |
| P9-T11 | `cargo clippy` | Zero new warnings |
| P9-T12 | Python bridge scripts: `scripts/verify_bridge.py` | All 4 contract checks pass |

---

## Progress Tracking

| Phase | Status | Tasks | Done |
|-------|--------|-------|------|
| P0: Research | ✅ complete | 9 | 9 |
| P1: Architecture | 🔄 in_progress | 1 | 0 |
| P2: Config System | ⏳ pending | 15 | 0 |
| P3: ATR + Pivots | ⏳ pending | 5 | 0 |
| P4: Per-candle OF | ⏳ pending | 7 | 0 |
| P5: LVN/HVN | ⏳ pending | 6 | 0 |
| P6: MSS + CVD Div + RVOL | ⏳ pending | 8 | 0 |
| P7: Param UI | ⏳ pending | 6 | 0 |
| P8: KB Integration | ⏳ pending | 4 | 0 |
| P9: Testing | ⏳ pending | 12 | 0 |
| **Total** | | **73** | **9** |
