"""Kronos strategy runner — batch runs Kronos strategies and aggregates signals."""

from core import Signal
from engine.ai_signal_generators.base import SignalGenerator


class KronosGenerator(SignalGenerator):
    name = "kronos"
    description = "Kronos — multi-strategy signal aggregation"

    def __init__(self):
        super().__init__()
        self._strategies = []

    def generate(self, pair: str) -> Signal:
        from engine.strategy_registry import StrategyRegistry

        registry = StrategyRegistry()
        registry.scan()

        all_strats = registry.list_strategies(active_only=True)
        kronos_strats = [s.name for s in all_strats if "kronos" in s.name.lower()]
        if not kronos_strats:
            return Signal(
                pair=pair,
                action="NEUTRAL",
                confidence=0.0,
                direction="neutral",
                source=self.name,
                reason="No Kronos strategies found in registry",
            )

        buys = 0
        sells = 0
        total_conf = 0.0
        results = []

        for name in kronos_strats:
            info = registry.get(name)
            if info is None:
                continue
            win_rate = info.win_rate if info.win_rate > 0 else 0.5
            total_pnl = info.total_pnl
            results.append(f"{name}: WR={win_rate:.0%}, PnL={total_pnl:.1%}")

            if total_pnl > 5:
                buys += 1
                total_conf += win_rate
            elif total_pnl < -3:
                sells += 1
                total_conf += (1 - win_rate)

        num = buys + sells
        if num == 0:
            return Signal(
                pair=pair,
                action="NEUTRAL",
                confidence=0.0,
                direction="neutral",
                source=self.name,
                reason="; ".join(results),
            )

        avg_conf = total_conf / num
        if buys > sells:
            action = "BUY"
            direction = "long"
        elif sells > buys:
            action = "SELL"
            direction = "short"
        else:
            action = "NEUTRAL"
            direction = "neutral"

        return Signal(
            pair=pair,
            action=action,
            confidence=round(min(avg_conf, 0.95), 4),
            direction=direction,
            source=self.name,
            reason="; ".join(results),
        )
