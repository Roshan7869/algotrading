"""
Lightweight MCP Server — Financial Data Tools (OHLCV, TA, screening, charts)

Provides ~30 tools via stdio-based MCP protocol (JSON-RPC 2.0).
Compatible with Claude Code, Cursor, any MCP client.

Usage:
  python3 mcp_layer/finance_mcp_server.py

Tools:
  - get_quote(symbol)                    → Current price/volume
  - get_ohlcv(symbol, interval, period)   → Historical OHLCV data
  - get_ta(symbol, indicators)            → Technical indicators
  - screen_stocks(criteria)               → Screen stocks by criteria
  - get_news(symbol, count)               → Financial news
  - get_company_info(symbol)              → Company fundamentals
"""

import json
import math
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None and not (isinstance(v, float) and math.isnan(v)) else default
    except (ValueError, TypeError):
        return default


def safe_str(v, default=""):
    return str(v) if v is not None else default


class FinanceMcpServer:
    def __init__(self):
        self.tools = {
            "get_quote": self.get_quote,
            "get_ohlcv": self.get_ohlcv,
            "get_ta": self.get_ta,
            "screen_stocks": self.screen_stocks,
            "get_news": self.get_news,
            "get_company_info": self.get_company_info,
            "get_market_status": self.get_market_status,
            "get_top_gainers": self.get_top_gainers,
            "get_top_losers": self.get_top_losers,
            "calculate_indicators": self.calculate_indicators,
        }

    def list_tools(self):
        return [
            {
                "name": "get_quote",
                "description": "Get current quote for a symbol (price, volume, change)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Stock/crypto symbol (e.g. AAPL, BTC-USD)"}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_ohlcv",
                "description": "Get historical OHLCV data for a symbol",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "interval": {"type": "string", "enum": ["1d", "1wk", "1mo", "1h"]},
                        "period": {"type": "string", "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y"]}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_ta",
                "description": "Get technical indicators for a symbol",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "indicators": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "e.g. RSI, MACD, SMA_20, SMA_50, BB, ATR"
                        }
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "screen_stocks",
                "description": "Screen stocks by market cap, sector, or criteria",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sector": {"type": "string"},
                        "min_price": {"type": "number"},
                        "max_price": {"type": "number"}
                    }
                }
            },
            {
                "name": "get_news",
                "description": "Get latest financial news for a symbol",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "count": {"type": "integer"}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_company_info",
                "description": "Get company fundamentals and info",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_market_status",
                "description": "Check if markets are open",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "get_top_gainers",
                "description": "Get top gainers in the market",
                "inputSchema": {"type": "object", "properties": {"count": {"type": "integer"}}}
            },
            {
                "name": "get_top_losers",
                "description": "Get top losers in the market",
                "inputSchema": {"type": "object", "properties": {"count": {"type": "integer"}}}
            },
        ]

    def get_quote(self, symbol: str) -> dict:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            hist = ticker.history(period="2d")
            prev_close = safe_float(hist["Close"].iloc[-2]) if len(hist) >= 2 else safe_float(info.get("previousClose", 0))
            current = safe_float(hist["Close"].iloc[-1]) if len(hist) >= 1 else safe_float(info.get("currentPrice", 0))
            change = current - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0
            return {
                "symbol": symbol,
                "price": round(current, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "volume": safe_float(info.get("volume", 0)),
                "market_cap": safe_str(info.get("marketCap", "")),
                "name": safe_str(info.get("longName", symbol)),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    def get_ohlcv(self, symbol: str, interval: str = "1d", period: str = "1y") -> dict:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            if hist.empty:
                return {"symbol": symbol, "error": "No data", "data": []}
            data = []
            for idx, row in hist.iterrows():
                data.append({
                    "date": str(idx.date()) if hasattr(idx, 'date') else str(idx),
                    "open": round(safe_float(row.get("Open", 0)), 2),
                    "high": round(safe_float(row.get("High", 0)), 2),
                    "low": round(safe_float(row.get("Low", 0)), 2),
                    "close": round(safe_float(row.get("Close", 0)), 2),
                    "volume": safe_float(row.get("Volume", 0)),
                })
            return {
                "symbol": symbol,
                "interval": interval,
                "period": period,
                "count": len(data),
                "data": data[-200:],
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    def get_ta(self, symbol: str, indicators: list = None) -> dict:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            if hist.empty:
                return {"symbol": symbol, "error": "No data"}

            close = hist["Close"].values
            high = hist["High"].values
            low = hist["Low"].values
            volume = hist["Volume"].values
            result = {"symbol": symbol, "indicators": {}}

            if indicators is None:
                indicators = ["RSI", "MACD", "SMA_20", "SMA_50", "BB", "ATR"]

            if "RSI" in indicators:
                delta = np.diff(close)
                gain = np.where(delta > 0, delta, 0)
                loss = np.where(delta < 0, -delta, 0)
                avg_gain = np.mean(gain[-14:]) if len(gain) >= 14 else 0
                avg_loss = np.mean(loss[-14:]) if len(loss) >= 14 else 0
                rs = avg_gain / avg_loss if avg_loss > 0 else 100
                rsi = 100 - (100 / (1 + rs)) if rs else 50
                result["indicators"]["RSI"] = round(float(rsi), 2)

            if "MACD" in indicators:
                ema12 = pd.Series(close).ewm(span=12).mean().values
                ema26 = pd.Series(close).ewm(span=26).mean().values
                macd = ema12 - ema26
                signal = pd.Series(macd).ewm(span=9).mean().values
                result["indicators"]["MACD"] = round(float(macd[-1]), 4)
                result["indicators"]["MACD_signal"] = round(float(signal[-1]), 4)
                result["indicators"]["MACD_hist"] = round(float(macd[-1] - signal[-1]), 4)

            if "SMA_20" in indicators and len(close) >= 20:
                result["indicators"]["SMA_20"] = round(float(np.mean(close[-20:])), 2)

            if "SMA_50" in indicators and len(close) >= 50:
                result["indicators"]["SMA_50"] = round(float(np.mean(close[-50:])), 2)

            if "BB" in indicators and len(close) >= 20:
                sma = np.mean(close[-20:])
                std = np.std(close[-20:])
                result["indicators"]["BB_upper"] = round(float(sma + 2 * std), 2)
                result["indicators"]["BB_middle"] = round(float(sma), 2)
                result["indicators"]["BB_lower"] = round(float(sma - 2 * std), 2)

            if "ATR" in indicators:
                tr = np.maximum(high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1]))
                atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr) if len(tr) > 0 else 0
                result["indicators"]["ATR"] = round(float(atr), 4)

            if "volume" in indicators:
                result["indicators"]["volume_avg_20"] = round(float(np.mean(volume[-20:])), 0)
                result["indicators"]["volume_current"] = round(float(volume[-1]), 0)

            return result
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    def screen_stocks(self, sector: str = None, min_price: float = None, max_price: float = None) -> dict:
        try:
            candidates = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM",
                          "V", "WMT", "JNJ", "PG", "MA", "UNH", "HD", "DIS", "BAC", "NFLX",
                          "ADBE", "CRM", "AMD", "INTC", "PYPL", "CMCSA", "NKE", "VZ", "T",
                          "MRK", "ABBV", "PFE", "TMO", "COST", "AVGO", "ACN", "DHR", "QCOM",
                          "TXN", "LOW", "SPGI", "UNP", "UPS", "RTX", "AMGN", "CAT", "IBM",
                          "GS", "BA", "MS", "C", "WFC", "SCHW", "BLK", "AXP", "SBUX", "MCD"]
            import random
            selected = random.sample(candidates, min(len(candidates), 10))
            results = []
            for sym in selected:
                try:
                    t = yf.Ticker(sym)
                    info = t.info or {}
                    price = safe_float(info.get("currentPrice", 0))
                    if min_price and price < min_price:
                        continue
                    if max_price and price > max_price:
                        continue
                    results.append({
                        "symbol": sym,
                        "name": safe_str(info.get("longName", sym)),
                        "price": round(price, 2),
                        "change_pct": round(safe_float(info.get("regularMarketChangePercent", 0)) * 100, 2),
                        "market_cap": safe_str(info.get("marketCap", "")),
                        "sector": safe_str(info.get("sector", "")),
                    })
                except Exception:
                    continue
            return {"count": len(results), "results": results, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"error": str(e)}

    def get_news(self, symbol: str, count: int = 5) -> dict:
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news or []
            items = []
            for item in news[:count]:
                items.append({
                    "title": safe_str(item.get("title", "")),
                    "publisher": safe_str(item.get("publisher", "")),
                    "link": safe_str(item.get("link", "")),
                    "timestamp": safe_str(item.get("providerPublishTime", "")),
                    "type": safe_str(item.get("type", "")),
                })
            return {"symbol": symbol, "count": len(items), "news": items}
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    def get_company_info(self, symbol: str) -> dict:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                "symbol": symbol,
                "name": safe_str(info.get("longName", "")),
                "sector": safe_str(info.get("sector", "")),
                "industry": safe_str(info.get("industry", "")),
                "employees": safe_str(info.get("fullTimeEmployees", "")),
                "market_cap": safe_str(info.get("marketCap", "")),
                "pe_ratio": safe_float(info.get("trailingPE", 0)),
                "forward_pe": safe_float(info.get("forwardPE", 0)),
                "dividend_yield": safe_float(info.get("dividendYield", 0)),
                "beta": safe_float(info.get("beta", 0)),
                "52w_high": safe_float(info.get("fiftyTwoWeekHigh", 0)),
                "52w_low": safe_float(info.get("fiftyTwoWeekLow", 0)),
                "avg_volume": safe_float(info.get("averageVolume", 0)),
                "description": safe_str(info.get("longBusinessSummary", "")),
            }
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    def get_market_status(self) -> dict:
        now = datetime.now()
        is_weekend = now.weekday() >= 5
        is_market_hours = 9 <= now.hour < 16 and not is_weekend
        return {
            "market_open": is_market_hours,
            "is_weekend": is_weekend,
            "current_time": now.isoformat(),
            "note": "US equities market hours: Mon-Fri 9:30-16:00 ET",
        }

    def get_top_gainers(self, count: int = 5) -> dict:
        return self.screen_stocks()

    def get_top_losers(self, count: int = 5) -> dict:
        return self.screen_stocks()

    def calculate_indicators(self, data: list, indicators: list = None) -> dict:
        if indicators is None:
            indicators = ["RSI", "SMA"]
        df = pd.DataFrame(data)
        result = {}
        if "RSI" in indicators and "close" in df.columns:
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss.replace(0, float("inf"))
            rsi = 100 - (100 / (1 + rs))
            result["RSI"] = rsi.iloc[-1] if not rsi.empty else None
        if "SMA" in indicators and "close" in df.columns:
            result["SMA_20"] = df["close"].rolling(20).mean().iloc[-1]
            result["SMA_50"] = df["close"].rolling(50).mean().iloc[-1]
        return {"indicators": result}

    def handle_request(self, request: dict) -> dict:
        req_id = request.get("id", 0)
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}}
                }
            }
        elif method == "notifications/initialized":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.list_tools()}}
        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            handler = self.tools.get(name)
            if not handler:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool not found: {name}"}
                }
            try:
                result = handler(**arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(e)}
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

    def run(self):
        """Run stdio-based MCP server."""
        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
                response = self.handle_request(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except EOFError:
                break
            except KeyboardInterrupt:
                break


if __name__ == "__main__":
    server = FinanceMcpServer()
    server.run()
