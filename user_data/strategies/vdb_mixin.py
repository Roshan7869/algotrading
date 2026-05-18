"""Stub: VDBMixin — placeholder for vector database integration.
Strategies inherit this but currently use no methods.
Expand with actual ChromaDB/VDB query implementation as needed."""
from typing import Any, Optional


class VDBMixin:
    """Placeholder mixin for vector database strategy queries."""

    def query_vdb(self, query: str, top_k: int = 5) -> list:
        """Query the vector database for similar strategies (no-op stub)."""
        return []

    def record_outcome(self, trade_result: dict) -> None:
        """Record a trade outcome to VDB for feedback (no-op stub)."""
        pass

    def get_strategy_context(self, pair: str, regime: str = "any") -> dict:
        """Get regime-adapted strategy context from VDB (no-op stub)."""
        return {}

    def _vdb_is_available(self) -> bool:
        """Check if VDB is available (always False in backtest)."""
        return False

    def _vdb_entry_setups(self, pair: str, top_k: int = 3) -> list:
        """Get entry setups from VDB (no-op stub for backtesting)."""
        return []
