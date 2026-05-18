from __future__ import annotations

from pathlib import Path
from typing import Any

from .schemas import TradeDecision


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RiskGate:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def evaluate(self, decision: TradeDecision, context: dict[str, Any]) -> tuple[bool, list[str]]:
        failures: list[str] = []
        if decision.decision != "approve":
            failures.append(f"decision_not_approve:{decision.decision}")
        if decision.side not in {"long", "short"}:
            failures.append("missing_trade_side")
        if decision.confidence < float(context.get("min_confidence", 0.7)):
            failures.append("confidence_below_threshold")
        if decision.max_leverage > self._configured_leverage_limit():
            failures.append("model_leverage_above_config_limit")
        if decision.stake_pct > float(context.get("max_stake_pct", 0.10)):
            failures.append("stake_pct_above_limit")
        if int(context.get("open_trades", 0)) >= int(self.config.get("max_open_trades", 3)):
            failures.append("max_open_trades_reached")
        if float(context.get("daily_drawdown_pct", 0.0)) > float(context.get("max_daily_drawdown_pct", 5.0)):
            failures.append("daily_drawdown_limit")
        if float(context.get("total_drawdown_pct", 0.0)) > float(context.get("max_total_drawdown_pct", 15.0)):
            failures.append("total_drawdown_limit")
        if float(context.get("spread_bps", 0.0)) > float(context.get("max_spread_bps", 15.0)):
            failures.append("spread_too_wide")
        if not self.config.get("dry_run", True) and not context.get("live_approved", False):
            failures.append("live_mode_requires_explicit_approval")
        return (len(failures) == 0, failures)

    def _configured_leverage_limit(self) -> float:
        strategy_dir = PROJECT_ROOT / "user_data" / "strategies"
        try:
            import sys

            sys.path.insert(0, str(strategy_dir))
            from leverage_config import DEFAULT_LEVERAGE

            return float(DEFAULT_LEVERAGE)
        except Exception:
            return float(self.config.get("leverage", 1))

