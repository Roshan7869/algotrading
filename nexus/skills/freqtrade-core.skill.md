---
name: freqtrade-core
description: Freqtrade main engine
version: 1.0.0
category: trading
tags: [freqtrade, engine, trading, bot]
---

# Freqtrade Core

The Freqtrade main engine manages the trading loop: data ingestion → strategy evaluation → trade execution → position management.

## Capabilities
- Configurable trading loop with configurable intervals
- Multi-exchange support via CCXT
- Dry-run and live trading modes
- Position management (entry, exit, stoploss, trailing)
- Periodic market data refresh and indicator recalculation

## Trigger Phrases
- "start the bot", "stop trading", "restart freqtrade"
- "check if freqtrade is running"
