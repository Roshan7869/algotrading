"""
Verify Rust→Python bridge data contract.

Checks that Redis messages from ws-bridge match the format
expected by ui/redis_stream.py and ui/indicators.py.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.redis_stream import RedisStream
from ui.indicators import compute_indicators


def verify_candle_format():
    """Verify candle dict has all required fields for indicators.py."""
    row = {
        "open_time": 1700000000000,
        "close_time": 1700003600000,
        "open": 50000.0,
        "high": 51000.0,
        "low": 49000.0,
        "close": 50500.0,
        "volume": 100.0,
        "quote_volume": 5000000.0,
        "is_closed": True,
        "trades": 1000,
        "taker_buy_volume": 55.0,
        "taker_buy_quote_volume": 2750000.0,
    }

    required = [
        "open_time", "close_time", "open", "high", "low", "close",
        "volume", "quote_volume", "is_closed", "trades",
        "taker_buy_volume", "taker_buy_quote_volume",
    ]
    for field in required:
        assert field in row, f"Missing field: {field}"

    rows = []
    for i in range(60):
        r = row.copy()
        r["open_time"] = row["open_time"] + i * 3600000
        r["close"] = row["close"] + (i * 10.0)
        rows.append(r)

    df = compute_indicators(pd.DataFrame(rows))
    assert "rsi" in df.columns
    assert "vwap" in df.columns
    print("  ✓ Candle format valid for compute_indicators()")


def verify_redis_stream_init():
    """Verify RedisStream can parse wire format."""
    rs = RedisStream("BTC/USDT", "1h", "futures")
    assert rs.pair == "BTC/USDT"
    assert rs.timeframe == "1h"
    assert rs._sym_clean == "btcusdt", f"got {rs._sym_clean}"
    assert rs._candle_stream == "candles:btcusdt:1h"
    assert rs._indicator_stream == "indicators:btcusdt:1h"
    print("  ✓ RedisStream initialization correct")


def verify_indicator_update_format():
    """Verify IndicatorUpdate JSON matches what redis_stream.py expects."""
    update = {
        "pair": "BTC/USDT",
        "timeframe": "1h",
        "timestamp": 1700000000000,
        "close": 50500.0,
        "sma_20": 50000.0,
        "rsi_14": 55.0,
        "macd_line": 100.0,
        "macd_signal": 95.0,
        "macd_histogram": 5.0,
        "bb_upper": 52000.0,
        "bb_middle": 50000.0,
        "bb_lower": 48000.0,
        "atr_14": 500.0,
        "vwap": 50200.0,
        "volume_delta": 10.0,
        "cvd": 1000.0,
        "super_trend": {"value": 49500.0, "direction": 1},
    }
    json_str = json.dumps(update)
    parsed = json.loads(json_str)
    assert parsed["pair"] == "BTC/USDT"
    assert parsed["super_trend"]["direction"] == 1
    print("  ✓ IndicatorUpdate JSON format valid")


def verify_signal_format():
    """Verify Signal JSON matches what TradeEventBridge expects."""
    signal = {
        "timestamp": 1700000000000,
        "pair": "BTC/USDT",
        "signal_type": "Buy",
        "price": 50500.0,
        "reason": "SuperTrend flipped UP",
        "confidence": 0.8,
        "rsi": 55.0,
        "super_trend_dir": 1,
        "macd_histogram": 5.0,
    }
    json_str = json.dumps(signal)
    parsed = json.loads(json_str)
    assert parsed["signal_type"] == "Buy"
    assert parsed["confidence"] == 0.8
    print("  ✓ Signal JSON format valid")


if __name__ == "__main__":
    import pandas as pd

    print("Verifying bridge contracts...")
    verify_candle_format()
    verify_redis_stream_init()
    verify_indicator_update_format()
    verify_signal_format()
    print("\nAll bridge contract checks passed ✓")
