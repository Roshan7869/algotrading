---
name: aroon-momentum-engine
description: AroonMomentumEngine_Hybrid using Aroon + ATR + RSI indicators
version: 1.0.0
category: trading
tags: [strategy, aroon, momentum, atr, rsi, hybrid]
---

# Aroon Momentum Engine

Hybrid strategy combining Aroon Up/Down, ATR (volatility), and RSI (momentum) for entry/exit signals.

## Strategy Logic
- **Entry**: Aroon Up crosses above Aroon Down + RSI > 50 + volume confirmation
- **Exit**: Aroon Down crosses above Aroon Up or RSI < 30
- **Filters**: ATR-based volatility filter, trend strength confirmation

## Parameters
- `aroon_period`: 25 (default)
- `atr_multiplier`: 2.0
- `rsi_upper`: 70
- `rsi_lower`: 30

## Trigger Phrases
- "check aroon signals", "run aroon strategy test"
- "adjust aroon parameters"
