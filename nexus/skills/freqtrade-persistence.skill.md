---
name: freqtrade-persistence
description: Trade database with SQLite persistence
version: 1.0.0
category: trading
tags: [freqtrade, persistence, database, sqlite, trades]
---

# Freqtrade Persistence

SQLite-backed trade database storing all trade records, positions, orders, and logs.

## Tables
- `trades` — Open and closed trades with entry/exit details
- `orders` — Exchange order records
- `positions` — Current open positions
- `performance` — Strategy-level performance aggregation
- `pairlock` — Locked pairs (cool-down)

## Trigger Phrases
- "show trade history", "check database size"
- "export trades", "query recent trades"
