---
name: trading-agents-autopilot
description: Autopilot system for automated trading workflow
version: 1.0.0
category: ai
tags: [autopilot, automated, trading, workflow, agents]
---

# Trading Agents Autopilot

Fully automated trading workflow: market analysis → signal generation → risk check → execution → feedback loop.

## Pipeline
1. Market data ingestion (MCP finance tools)
2. Multi-agent analysis (regime, sentiment, technicals)
3. Signal generation with confidence scoring
4. Risk gate check (circuit breaker + learning loop)
5. Execution via Freqtrade bridge
6. Outcome recording → ChromaDB update → NEXUS feedback

## Trigger Phrases
- "start autopilot", "enable automated trading"
- "check autopilot status", "pause autopilot"
