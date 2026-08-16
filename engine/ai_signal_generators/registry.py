"""Registry of all AI signal generators."""

from typing import Optional

from core import Signal
from engine.ai_signal_generators.base import SignalGenerator


class GeneratorRegistry:
    def __init__(self):
        self._generators: dict[str, SignalGenerator] = {}

    def register(self, generator: SignalGenerator):
        self._generators[generator.name] = generator

    def unregister(self, name: str):
        self._generators.pop(name, None)

    def get(self, name: str) -> Optional[SignalGenerator]:
        return self._generators.get(name)

    def list_names(self) -> list:
        return list(self._generators.keys())

    def list_enabled(self) -> list:
        return [n for n, g in self._generators.items() if g.enabled]

    def generate_all(self, pair: str) -> list:
        signals = []
        for name, gen in self._generators.items():
            if gen.enabled:
                try:
                    signal = gen.generate(pair)
                    signals.append(signal)
                except Exception as e:
                    signals.append(Signal(
                        pair=pair,
                        action="NEUTRAL",
                        confidence=0.0,
                        direction="neutral",
                        source=name,
                        reason=f"Error: {e}",
                    ))
        return signals

    def generate_all_multi(self, pairs: list) -> dict:
        return {p: self.generate_all(p) for p in pairs}

    def consensus(self, pair: str) -> Signal:
        signals = self.generate_all(pair)
        if not signals:
            return Signal(pair=pair, action="NEUTRAL", confidence=0.0, direction="neutral", source="consensus")

        avg_conf = sum(s.confidence for s in signals) / len(signals)
        numeric_scores = [s.numeric_action * s.confidence for s in signals]
        avg_score = sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0

        directions = [s.direction for s in signals if s.direction != "neutral"]
        direction = max(set(directions), key=directions.count) if directions else "neutral"

        if avg_score >= 1.0:
            action = "STRONG_BUY"
        elif avg_score >= 0.3:
            action = "BUY"
        elif avg_score <= -1.0:
            action = "STRONG_SELL"
        elif avg_score <= -0.3:
            action = "SELL"
        else:
            action = "NEUTRAL"

        return Signal(
            pair=pair,
            action=action,
            confidence=round(avg_conf, 4),
            direction=direction,
            source="consensus",
            reason=f"Consensus of {len(signals)} generators: {', '.join(s.source for s in signals)}",
        )


_registry: Optional[GeneratorRegistry] = None


def get_registry() -> GeneratorRegistry:
    global _registry
    if _registry is None:
        _registry = GeneratorRegistry()
    return _registry
