---
name: freqtrade-exchange
description: Exchange adapters for Binance, Kraken, and others
version: 1.0.0
category: trading
tags: [freqtrade, exchange, binance, kraken, ccxt]
---

# Freqtrade Exchange

Exchange adapter layer built on CCXT, providing unified interface to multiple cryptocurrency exchanges.

## Supported Exchanges
- Binance (spot + futures)
- Kraken
- Coinbase
- Bybit
- OKX
- KuCoin
- Custom exchange configs via CCXT

## Capabilities
- Market data (OHLCV, orderbook, ticker)
- Order management (market, limit, stop-loss)
- Balance and position queries
- Rate limit handling and retry logic

## Trigger Phrases
- "add new exchange", "check exchange balance"
- "verify exchange connection", "test API keys"
