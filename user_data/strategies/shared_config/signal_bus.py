"""Stub: shared_config.signal_bus — placeholder for signal bus singleton."""

class _SignalBus:
    """No-op signal bus stub."""
    def publish(self, pair, signal_type, value=None):
        pass
    def subscribe(self, pair, signal_type):
        return None
    def get_latest(self, pair, signal_type):
        return None

_BUS = None

def get_bus():
    global _BUS
    if _BUS is None:
        _BUS = _SignalBus()
    return _BUS
