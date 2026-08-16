---
name: freqtrade-data
description: Data management for OHLCV candles and market data
version: 1.0.0
category: trading
tags: [freqtrade, data, ohlcv, candles, market-data]
---

# Freqtrade Data

Data management subsystem: market data download, storage, and preprocessing.

## Capabilities
- OHLCV candle download (configurable timeframes: 1m, 5m, 15m, 1h, 4h, 1d, etc.)
- Pair list management and filtering
- Data format conversion (JSON, SQLite, Parquet)
- Data gap filling and cleaning
- Incremental data updates

## Trigger Phrases
- "download new data", "update market data"
- "check data freshness", "list available pairs"
