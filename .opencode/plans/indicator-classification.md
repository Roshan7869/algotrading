# Indicator Classification — On-Chart vs Sub-Chart

## Category A: Price-Scale Overlays (share candle Y-axis)
These indicators output values in **price space** — they should render directly on the candle chart.

| # | Indicator | Current render | Overlay target | Reasoning |
|---|-----------|---------------|----------------|-----------|
| 1 | BollingerBands | Sub-chart (%b, 0-1) | **On-chart** (upper/mid/lower in price) | Band prices are in price space. Current sub-chart shows %b (normalized). Overlay shows actual bands. |
| 2 | VWAP | Sub-chart | **On-chart** (line) | VWAP is a price-level line. Should be golden dashed line on candles like TradingView. |
| 3 | ALMA | Sub-chart | **On-chart** (line) | Moving average in price space. |
| 4 | PivotPoints | Sub-chart | **On-chart** (horizontal lines) | R1/R2/R3/PP/S1/S2/S3 are all price levels. |
| 5 | ATR | Sub-chart | **Sub-chart** (stays) | Value is in price units but as a magnitude measure, not a level. Keep as sub-chart. |

**Note**: SMA/EMA don't exist as separate KlineIndicators. SMA is part of BollingerBands (mid line). The `ta.rs` has `sma_series()`/`ema_series()` but they're not exposed as standalone indicators in the UI. The user computes them via the bridge. We may need to add standalone SMA/EMA indicators to Flowsurface.

Actually, re-checking: SMA/EMA aren't in the 23 KlineIndicators. ALMA is the only MA-type indicator. SMA is embedded in Bollinger's middle band. So "MA on chart" means exposing Bollinger's middle band as a standalone overlay, and potentially adding new SMA/EMA indicators.

## Category B: Structural Overlays (zones/markers at price levels)
These indicate **specific price levels or regions** — they benefit from being on the candle chart.

| # | Indicator | Current render | Overlay target | Reasoning |
|---|-----------|---------------|----------------|-----------|
| 6 | FVG | Sub-chart | **On-chart** (zones) | Price gap zones between wicks. Most useful when seen on candles. |
| 7 | OrderBlock | Sub-chart | **On-chart** (zones) | Price ranges at swing bases. Essential on candles. |
| 8 | MSS | Sub-chart | **On-chart** (markers) | Structure break markers at swing points. |
| 9 | CVD Divergence | Sub-chart | **On-chart** (markers) | Divergence signals overlaid at price. |
| 10 | LVN/HVN | Sub-chart | **On-chart** (horizontal bars) | Volume nodes at price levels. Should render as horizontal bars/circles on candles. |
| 11 | CandlestickPattern | Sub-chart | **On-chart** (markers) | Pattern labels at candle locations. | 

## Category C: Sub-Chart Only (different Y-scale)
These indicators measure **different units** than price — they must remain in separate panels.

| # | Indicator | Y-axis scale | Reasoning |
|---|-----------|-------------|-----------|
| 12 | RSI | 0-100 | Oscillator range, unrelated to price |
| 13 | MACD | Oscillates around 0 | Difference of EMAs, not price |
| 14 | Volume | Share/contract count | Volume units |
| 15 | CumulativeDelta (CVD) | Accumulated volume units | Not price-scaled |
| 16 | OpenInterest | Contract count | Not price-scaled |
| 17 | Aroon | 0-100 | Time-based oscillator |
| 18 | ADX | 0-100 | Trend strength oscillator |
| 19 | PerCandleDelta | Volume units per bar | Not price-scaled |
| 20 | PerCandleAbsorption | Volume metrics | Not price-scaled |
| 21 | PerCandleZScore | Standard deviations | Statistical measure |
| 22 | PerCandleImbalance | Ratio (0-inf) | Not price-scaled |
| 23 | RVOL | Ratio | Current vs average volume |

## Summary

| Layer | Count | Indicators |
|-------|-------|------------|
| **On-chart overlays (need draw_overlay)** | **11** | Bollinger, VWAP, ALMA, PivotPoints, FVG, OrderBlock, MSS, CVD Divergence, LVN, CandlestickPattern, ATR (optional) |
| **Sub-charts (keep as-is)** | **12** | RSI, MACD, Volume, CumulativeDelta, OpenInterest, Aroon, ADX, PerCandleDelta, Absorption, ZScore, Imbalance, RVOL |

## Implementation Priority

**Phase 3 (highest value first)**: VWAP → Bollinger → ALMA → PivotPoints
**Phase 4 (structural)**: FVG → OrderBlock → MSS → CVD Divergence → LVN → CandlestickPattern
