---
name: freqtrade-strategy
description: Strategy system for signal generation, entry/exit logic
version: 1.0.0
category: trading
tags: [freqtrade, strategy, signals, entry, exit, indicators]
---

# Freqtrade Strategy

The strategy system defines trading logic: indicator computation, signal generation, entry/exit conditions, and position management.

## Key Components
- `IStrategy` base class with `populate_indicators()`, `populate_entry_trend()`, `populate_exit_trend()`
- 27+ IStrategy implementations discovered dynamically by StrategyRegistry
- Regime-based strategy selection (trending/ranging/volatile/reversal)
- Custom indicators via pandas/ta-lib

## Trigger Phrases
- "write a new strategy", "modify strategy parameters"
- "list available strategies", "show strategy performance"
