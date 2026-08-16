"""
Binance WebSocket client for real-time candlestick & trade data.

Provides a threaded WebSocket connection that accumulates:
  - kline (candlestick) updates with partial-bar updates
  - aggrTrade (trade) updates for volume delta / CVD

Usage:
    from ui.binance_ws import BinanceStream
    stream = BinanceStream(pair="BTC/USDT", timeframe="1h")
    stream.start()
    df = stream.get_candles()  # pandas DataFrame with OHLCV + volume_delta
    stream.stop()
"""

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import websocket

log = logging.getLogger(__name__)

# Binance futures & spot WS endpoints
FUTURES_WS = "wss://fstream.binance.com/ws"
SPOT_WS = "wss://stream.binance.com:9443/ws"

INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h",
    "12h": "12h", "1d": "1d", "3d": "3d", "1w": "1w", "1M": "1M",
}


def _pair_to_stream(pair: str, market: str = "futures") -> str:
    """Convert 'BTC/USDT' → 'btcusdt' for stream names."""
    symbol = pair.replace("/", "").replace(":USDT", "").lower()
    return symbol


class BinanceStream:
    """Threaded Binance WebSocket for live candle + trade data."""

    def __init__(
        self,
        pair: str = "BTC/USDT",
        timeframe: str = "1h",
        market: str = "futures",
        max_candles: int = 500,
        max_trades: int = 1000,
    ):
        self.pair = pair
        self.timeframe = timeframe
        self.market = market
        self.max_candles = max_candles
        self.max_trades = max_trades

        self.stream_symbol = _pair_to_stream(pair, market)
        self.interval = INTERVAL_MAP.get(timeframe, "1h")

        # Data stores
        self._candles: dict[int, dict] = {}  # open_time → candle dict
        self._trades: deque = deque(maxlen=max_trades)
        self._sorted_candles: list[dict] = []
        self._last_sort_time: float = 0

        # State
        self._running = False
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = threading.Event()
        self._error: Optional[str] = None
        self._candle_count = 0
        self._trade_count = 0

    # --- Connection ---

    def start(self):
        """Start the WebSocket connection in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_ws, daemon=True)
        self._thread.start()
        connected = self._connected.wait(timeout=10)
        if not connected:
            self._error = "Connection timeout"
        return connected

    def stop(self):
        """Stop the WebSocket connection."""
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected.clear()

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def status(self) -> dict:
        return {
            "pair": self.pair,
            "timeframe": self.timeframe,
            "market": self.market,
            "connected": self.is_connected(),
            "candles": len(self._candles),
            "trades": self._trade_count,
            "error": self._error,
        }

    # --- Data access ---

    def get_candles(self) -> pd.DataFrame:
        """Return accumulated candles as a DataFrame."""
        self._sort_candles()
        if not self._sorted_candles:
            return pd.DataFrame()
        df = pd.DataFrame(self._sorted_candles)
        df = df.sort_values("open_time").reset_index(drop=True)
        return df

    def get_trades(self) -> pd.DataFrame:
        """Return accumulated trades as a DataFrame."""
        if not self._trades:
            return pd.DataFrame()
        df = pd.DataFrame(list(self._trades))
        return df

    # --- Internal ---

    def _sort_candles(self):
        """Re-sort candles dict → list (called periodically, not every tick)."""
        now = time.time()
        if now - self._last_sort_time < 0.5:
            return  # Throttle: 2x/sec max
        self._sorted_candles = list(self._candles.values())
        self._last_sort_time = now

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Kline stream
        if "k" in data:
            self._process_kline(data["k"])
        # AggTrade stream
        elif "e" in data and data["e"] == "aggTrade":
            self._process_trade(data)

    def _process_kline(self, k: dict):
        open_time = k["t"]
        candle = {
            "open_time": open_time,
            "close_time": k["T"],
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "quote_volume": float(k["q"]),
            "is_closed": k["x"],
            "trades": int(k.get("n", 0)),
            "taker_buy_volume": float(k.get("V", 0)),
            "taker_buy_quote_volume": float(k.get("Q", 0)),
            "timestamp": pd.Timestamp(open_time, unit="ms", tz="UTC"),
        }
        self._candles[open_time] = candle
        self._candle_count = len(self._candles)

        # Trim old candles beyond max
        if self._candle_count > self.max_candles + 100:
            sorted_times = sorted(self._candles.keys())
            for t in sorted_times[: self._candle_count - self.max_candles]:
                del self._candles[t]

    def _process_trade(self, t: dict):
        trade = {
            "timestamp": pd.Timestamp(t["T"], unit="ms", tz="UTC"),
            "price": float(t["p"]),
            "qty": float(t["q"]),
            "is_sell": not t["m"],  # m=True → buyer is maker → market sell
            "trade_id": t["a"],
        }
        self._trades.append(trade)
        self._trade_count += 1

    def _on_error(self, ws, error):
        self._error = str(error)
        log.warning("Binance WS error: %s", error)

    def _on_close(self, ws, close_status, close_msg):
        self._connected.clear()
        log.info("Binance WS closed: %s %s", close_status, close_msg)

    def _on_open(self, ws):
        self._connected.set()
        self._error = None
        log.info("Binance WS connected: %s %s", self.pair, self.timeframe)

    def _run_ws(self):
        sym = self.stream_symbol
        tf = self.interval
        base = FUTURES_WS if self.market == "futures" else SPOT_WS
        # Combined stream: klines + aggTrades
        stream_url = f"{base}/{sym}@kline_{tf}/{sym}@aggTrade"

        ws = websocket.WebSocketApp(
            stream_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )
        self._ws = ws
        ws.run_forever(ping_interval=30, ping_timeout=10)

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass