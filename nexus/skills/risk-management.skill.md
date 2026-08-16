---
name: risk-management
description: Risk management (stoploss, leverage, position sizing)
version: 1.0.0
category: risk
tags: [risk, management, stoploss, leverage, position-sizing]
---

# Risk Management

Comprehensive risk management system: circuit breaker, position sizing, stoploss management, and drawdown enforcement.

## Components
- **Circuit Breaker** (EnforcedRiskGate): 5 RiskTiers (NORMAL, CAUTION, ELEVATED, HIGH, KILL), physically blocks trades at PAUSE
- **HEdge Coordinator**: Composite risk score (circuit breaker 40%, learn win rate 25%, drawdown 20%, agent health 15%)
- **SubAgentOverseer**: Agent heartbeat monitoring with TTLs, daily trade limits
- **System Drawdown Enforcer**: Max 20% drawdown limit

## Risk Tiers
| Tier | Max Trades | Max Leverage | Description |
|------|-----------|-------------|-------------|
| NORMAL | 10 | 3.0 | Full operation |
| CAUTION | 6 | 2.0 | Reduce exposure |
| ELEVATED | 3 | 1.0 | Minimal trading |
| HIGH | 1 | 1.0 | Exit only |
| KILL | 0 | 0 | Emergency halt |

## Trigger Phrases
- "check risk status", "what is the current risk tier"
- "show circuit breaker state", "adjust risk limits"
- "run risk check", "check system drawdown"
