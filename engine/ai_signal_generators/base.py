"""Base class for all AI signal generators."""

from core import Signal


class SignalGenerator:
    name: str = "base"
    description: str = "Base signal generator"

    def __init__(self):
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def generate(self, pair: str) -> Signal:
        raise NotImplementedError

    def generate_multi(self, pairs: list[str]) -> list[Signal]:
        return [self.generate(p) for p in pairs]
