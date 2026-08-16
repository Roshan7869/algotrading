import json
import threading
import time
from typing import Optional
import pandas as pd

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None


class RedisStream:
    def __init__(self, pair: str, timeframe: str, market: str, max_candles: int = 600,
                 redis_host: str = "127.0.0.1", redis_port: int = 6379):
        self.pair = pair
        self.timeframe = timeframe
        self.market = market
        self.max_candles = max_candles
        self.redis_host = redis_host
        self.redis_port = redis_port

        self._candles: dict[int, dict] = {}
        self._connected = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[str] = None
        self._last_candle_id: Optional[str] = None
        self._last_indicator_id: Optional[str] = None
        self._indicator_values: dict = {}

        self._sym_clean = pair.replace("/", "").replace(":USDT", "").lower()
        self._candle_stream = f"candles:{self._sym_clean}:{timeframe}"
        self._indicator_stream = f"indicators:{self._sym_clean}:{timeframe}"

        if redis_lib is None:
            self._error = "redis package not installed. Install with: pip install redis"

    def start(self) -> bool:
        if redis_lib is None:
            self._connected = False
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        for _ in range(20):
            if self._connected:
                return True
            time.sleep(0.1)
        return self._connected

    def stop(self):
        self._running = False
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_candles(self) -> pd.DataFrame:
        if not self._candles:
            return pd.DataFrame()
        sorted_candles = sorted(self._candles.values(), key=lambda x: x["open_time"])
        df = pd.DataFrame(sorted_candles)
        df = df.sort_values("open_time").reset_index(drop=True)
        return df

    def get_indicator_values(self) -> dict:
        return self._indicator_values

    def status(self) -> dict:
        return {
            "pair": self.pair,
            "timeframe": self.timeframe,
            "market": self.market,
            "connected": self._connected,
            "candles": len(self._candles),
            "error": self._error,
        }

    def _run(self):
        try:
            r = redis_lib.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
            r.ping()
            self._connected = True
            self._error = None

            while self._running:
                self._read_candles(r)
                self._read_indicators(r)
                time.sleep(0.1)
        except Exception as e:
            self._error = str(e)
            self._connected = False

    def _read_candles(self, r):
        try:
            kwargs = {"count": 10}
            if self._last_candle_id:
                kwargs["block"] = 500
                result = r.xread({self._candle_stream: self._last_candle_id}, **kwargs)
            else:
                result = r.xread({self._candle_stream: "$"}, block=500, count=10)

            if not result:
                return

            for stream_name, messages in result:
                for msg_id, msg_data in messages:
                    self._last_candle_id = msg_id
                    raw = msg_data.get("data", "{}")
                    candle = json.loads(raw)
                    ot = candle["open_time"]
                    candle["timestamp"] = pd.Timestamp(ot, unit="ms", tz="UTC")
                    self._candles[ot] = candle

            self._trim_candles()
        except Exception as e:
            log_prefix = self._error or ""
            if "READONLY" not in str(e):
                self._error = f"candle read error: {e}"

    def _read_indicators(self, r):
        try:
            kwargs = {"count": 1}
            if self._last_indicator_id:
                kwargs["block"] = 100
                result = r.xread({self._indicator_stream: self._last_indicator_id}, **kwargs)
            else:
                result = r.xread({self._indicator_stream: "$"}, block=100, count=1)

            if not result:
                return

            for stream_name, messages in result:
                for msg_id, msg_data in messages:
                    self._last_indicator_id = msg_id
                    raw = msg_data.get("data", "{}")
                    self._indicator_values = json.loads(raw)
        except Exception:
            pass

    def _trim_candles(self):
        if len(self._candles) > self.max_candles + 100:
            sorted_keys = sorted(self._candles.keys())
            remove_count = len(sorted_keys) - self.max_candles
            for k in sorted_keys[:remove_count]:
                del self._candles[k]
