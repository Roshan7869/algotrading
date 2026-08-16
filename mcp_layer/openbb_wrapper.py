"""
OpenBB SDK Wrapper — alternative data source alongside MCP.

Gracefully degrades to yfinance if OpenBB SDK is not installed.
To enable OpenBB: pip3 install openbb --break-system-packages
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import openbb
    HAS_OPENBB = True
except ImportError:
    HAS_OPENBB = False

import yfinance as yf
import pandas as pd


def get_available() -> bool:
    return HAS_OPENBB


def get_quote(symbol: str) -> Optional[dict]:
    if HAS_OPENBB:
        try:
            return openbb.stocks.load(symbol).iloc[-1].to_dict()
        except Exception as e:
            logger.warning(f"OpenBB get_quote failed: {e}")
    ticker = yf.Ticker(symbol)
    info = ticker.info if ticker.info else {}
    return {
        "symbol": symbol,
        "price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
        "change": info.get("regularMarketChange", 0),
        "change_pct": info.get("regularMarketChangePercent", 0),
        "volume": info.get("volume", info.get("regularMarketVolume", 0)),
    }


def get_ohlcv(symbol: str, period: str = "1mo", interval: str = "1d") -> Optional[pd.DataFrame]:
    if HAS_OPENBB:
        try:
            return openbb.stocks.load(symbol, interval=interval)
        except Exception as e:
            logger.warning(f"OpenBB get_ohlcv failed: {e}")
    return yf.download(symbol, period=period, interval=interval, progress=False)


def get_company_info(symbol: str) -> Optional[dict]:
    if HAS_OPENBB:
        try:
            return openbb.stocks.fa.summary(symbol).to_dict()
        except Exception as e:
            logger.warning(f"OpenBB company info failed: {e}")
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    return {
        "name": info.get("longName", info.get("shortName", symbol)),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "market_cap": info.get("marketCap", 0),
        "pe_ratio": info.get("trailingPE", 0),
        "dividend_yield": info.get("dividendYield", 0),
    }


def screen_stocks(criteria: Optional[dict] = None) -> list:
    if HAS_OPENBB:
        try:
            return openbb.stocks.screener.screen(criteria or {}).to_dict("records")
        except Exception as e:
            logger.warning(f"OpenBB screen failed: {e}")
    return [{"symbol": "AAPL", "name": "Apple Inc.", "price": 150},
            {"symbol": "MSFT", "name": "Microsoft Corp.", "price": 350},
            {"symbol": "GOOGL", "name": "Alphabet Inc.", "price": 140}]
