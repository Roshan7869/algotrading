"""Stub: SignalBusMixin — placeholder for inter-strategy signal bus.
Strategies inherit this but currently use no methods.
Expand with actual signal bus implementation as needed."""
from typing import Any


class SignalBusMixin:
    """Placeholder mixin for inter-strategy signal communication."""

    def publish_signal(self, pair: str, signal_type: str, value: Any = None) -> None:
        """Publish a signal to the bus (no-op stub)."""
        pass

    def get_signal(self, pair: str, signal_type: str) -> Any:
        """Read a signal from the bus (no-op stub)."""
        return None

    def has_signal(self, pair: str, signal_type: str) -> bool:
        """Check if a signal exists on the bus (no-op stub)."""
        return False

    def _load_signals(self) -> dict:
        """Return default signal values for backtesting (no external bus available)."""
        return {
            "ta_rating": "Hold",
            "sentiment_score": 0.0,
            "breaker_state": "HEALTHY",
        }
