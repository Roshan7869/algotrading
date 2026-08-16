---
name: test-strategies
description: Single strategy backtest validation
version: 1.0.0
category: testing
tags: [testing, strategy, backtest, validation]
---

# Strategy Testing

Individual strategy backtest validation with standardized metrics and pass/fail criteria.

## Validation Process
1. Run backtest with 6-month minimum history
2. Check minimum trade count (>= 20)
3. Verify Sharpe ratio >= 0.5
4. Confirm max drawdown <= 30%
5. Validate profit factor >= 1.2
6. Compare against baseline strategy

## Trigger Phrases
- "test single strategy", "validate strategy"
- "check strategy meets criteria"
