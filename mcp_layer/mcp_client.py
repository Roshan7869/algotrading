"""
MCP Client — connects to the Finance MCP server via subprocess stdio.

Provides a clean Python API over the JSON-RPC 2.0 MCP protocol.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional


class McpClient:
    def __init__(self, server_script: Optional[str] = None):
        if server_script is None:
            server_script = str(Path(__file__).parent / "finance_mcp_server.py")
        self._server_script = server_script
        self._proc: Optional[subprocess.Popen] = None
        self._req_id = 0

    def connect(self):
        if self._proc is not None:
            return
        self._proc = subprocess.Popen(
            [sys.executable, self._server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        result = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
        })
        return result

    def disconnect(self):
        if self._proc:
            self._proc.terminate()
            self._proc.wait(timeout=5)
            self._proc = None

    def list_tools(self) -> list:
        result = self._send("tools/list", {})
        return (result or {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict = None) -> Any:
        if arguments is None:
            arguments = {}
        result = self._send("tools/call", {"name": name, "arguments": arguments})
        content = (result or {}).get("content", [])
        for item in content:
            if item.get("type") == "text":
                return json.loads(item["text"])
        return result

    def get_quote(self, symbol: str) -> dict:
        return self.call_tool("get_quote", {"symbol": symbol})

    def get_ohlcv(self, symbol: str, interval: str = "1d", period: str = "1y") -> dict:
        return self.call_tool("get_ohlcv", {"symbol": symbol, "interval": interval, "period": period})

    def get_ta(self, symbol: str, indicators: list = None) -> dict:
        return self.call_tool("get_ta", {"symbol": symbol, "indicators": indicators})

    def screen_stocks(self, sector: str = None, min_price: float = None, max_price: float = None) -> dict:
        params = {}
        if sector:
            params["sector"] = sector
        if min_price is not None:
            params["min_price"] = min_price
        if max_price is not None:
            params["max_price"] = max_price
        return self.call_tool("screen_stocks", params)

    def get_news(self, symbol: str, count: int = 5) -> dict:
        return self.call_tool("get_news", {"symbol": symbol, "count": count})

    def get_company_info(self, symbol: str) -> dict:
        return self.call_tool("get_company_info", {"symbol": symbol})

    def get_market_status(self) -> dict:
        return self.call_tool("get_market_status", {})

    def _send(self, method: str, params: dict) -> Optional[dict]:
        if not self._proc:
            raise RuntimeError("Not connected. Call connect() first.")
        self._req_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }
        request_line = json.dumps(request) + "\n"
        self._proc.stdin.write(request_line)
        self._proc.stdin.flush()
        response_line = self._proc.stdout.readline()
        if not response_line:
            return None
        try:
            response = json.loads(response_line.strip())
            if "error" in response:
                raise RuntimeError(f"MCP error: {response['error']}")
            return response.get("result")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid MCP response: {response_line}") from e

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
