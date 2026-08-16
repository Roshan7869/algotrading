"""
NEXUS — Algotrading Bridge
===========================
Bidirectional bridge connecting NEXUS v4 orchestration to the Algotrading engine.

Exports:
    NexusBridge         — singleton (trade_status, execute_backtest, adjust_config)
    get_bridge          — thread-safe singleton accessor
    record_outcome      — feed trade outcomes to NEXUS Thompson Sampling
    get_tool_definitions — MCP tool JSON Schemas
    handle_tool_call     — MCP tool dispatch
"""

from nexus.bridge import NexusBridge, get_bridge
from nexus.event_bridge import record_outcome
from nexus.mcp_tools import get_tool_definitions, handle_tool_call

__all__ = [
    "NexusBridge",
    "get_bridge",
    "record_outcome",
    "get_tool_definitions",
    "handle_tool_call",
]
