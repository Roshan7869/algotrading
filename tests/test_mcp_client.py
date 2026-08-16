"""
Tests for MCP Client
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from mcp_layer.mcp_client import McpClient
from mcp_layer.finance_mcp_server import FinanceMcpServer


def test_mcp_server_tools_list():
    server = FinanceMcpServer()
    tools = server.list_tools()
    names = [t["name"] for t in tools]
    assert "get_quote" in names
    assert "get_ohlcv" in names
    assert "get_ta" in names
    assert "get_news" in names
    assert "get_company_info" in names
    assert "get_market_status" in names
    assert "screen_stocks" in names


def test_mcp_server_get_quote():
    server = FinanceMcpServer()
    result = server.get_quote("AAPL")
    assert "symbol" in result
    assert result["symbol"] == "AAPL"
    assert "price" in result
    assert "change" in result


def test_mcp_server_get_ohlcv():
    server = FinanceMcpServer()
    result = server.get_ohlcv("AAPL", "1d", "1mo")
    assert result["symbol"] == "AAPL"
    assert "data" in result


def test_mcp_server_get_ta():
    server = FinanceMcpServer()
    result = server.get_ta("AAPL", ["RSI", "MACD"])
    assert result["symbol"] == "AAPL"
    assert "RSI" in result["indicators"]
    assert "MACD" in result["indicators"]


def test_mcp_server_get_news():
    server = FinanceMcpServer()
    result = server.get_news("AAPL", 3)
    assert result["symbol"] == "AAPL"
    assert len(result["news"]) <= 3


def test_mcp_server_get_company_info():
    server = FinanceMcpServer()
    result = server.get_company_info("AAPL")
    assert result["symbol"] == "AAPL"
    assert "name" in result
    assert "sector" in result


def test_mcp_server_market_status():
    server = FinanceMcpServer()
    result = server.get_market_status()
    assert "market_open" in result
    assert "is_weekend" in result


def test_mcp_server_handle_initialize():
    server = FinanceMcpServer()
    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert "result" in response
    assert response["result"]["protocolVersion"] == "2024-11-05"


def test_mcp_server_handle_tools_list():
    server = FinanceMcpServer()
    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert "result" in response
    assert "tools" in response["result"]


def test_mcp_server_handle_tools_call():
    server = FinanceMcpServer()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_market_status", "arguments": {}}
    })
    assert "result" in response


def test_mcp_server_handle_unknown_method():
    server = FinanceMcpServer()
    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "unknown", "params": {}})
    assert "error" in response
    assert "Method not found" in response["error"]["message"]


def test_mcp_server_get_top_gainers():
    server = FinanceMcpServer()
    result = server.get_top_gainers(3)
    assert "count" in result or "error" in result


@pytest.mark.skipif(not os.environ.get("MCP_LIVE_TEST"), reason="Set MCP_LIVE_TEST=1 to run live subprocess test")
def test_mcp_client_live_connect():
    with McpClient() as client:
        tools = client.list_tools()
        assert len(tools) > 0
        quote = client.get_quote("AAPL")
        assert quote["symbol"] == "AAPL"
        status = client.get_market_status()
        assert "market_open" in status
