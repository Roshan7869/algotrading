#!/usr/bin/env python3
"""
preview.py — Live signal preview for any Freqtrade strategy.

Loads strategy dynamically, fetches last 200 candles via CCXT,
calls populate_indicators() + populate_entry_trend(), and prints
BUY/SELL signals without executing any trades.

Usage:
  python3 scripts/analytics/preview.py --strategy AroonMomentumEngine_Hybrid
  python3 scripts/analytics/preview.py --strategy AroonMomentumEngine_Hybrid --pair SOL/USDT:USDT
"""

import argparse
import importlib
import sys
from pathlib import Path

STRATEGIES_DIR = Path(__file__).resolve().parent.parent.parent / "user_data" / "strategies"


def load_strategy_class(strategy_name: str):
    """Dynamically load a strategy class by name."""
    sys.path.insert(0, str(STRATEGIES_DIR))
    module = importlib.import_module(strategy_name)
    for attr in dir(module):
        cls = getattr(module, attr)
        if isinstance(cls, type) and "IStrategy" in [b.__name__ for b in cls.__mro__]:
            return cls
    raise ValueError(f"No IStrategy subclass found in {strategy_name}")


def fetch_recent_candles(pair: str, timeframe: str = "1h", limit: int = 200) -> list:
    """Fetch recent candles via CCXT/Binance (read-only, no trade)."""
    import ccxt
    exchange = ccxt.binance({"options": {"defaultType": "future"}})
    ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
    return ohlcv


def main():
    parser = argparse.ArgumentParser(description="Preview strategy signals without trading")
    parser.add_argument("--strategy", required=True, help="Strategy class name (e.g., AroonMomentumEngine_Hybrid)")
    parser.add_argument("--pair", default="BTC/USDT:USDT", help="Trading pair to preview")
    parser.add_argument("--timeframe", default="1h", help="Timeframe (default: 1h)")
    parser.add_argument("--candles", type=int, default=200, help="Number of candles (default: 200)")
    args = parser.parse_args()

    print(f"\n  Preview: {args.strategy} on {args.pair} ({args.timeframe}, {args.candles}c)\n")

    StrategyClass = load_strategy_class(args.strategy)
    strategy = StrategyClass(config={"runmode": "dry_run"})

    ohlcv = fetch_recent_candles(args.pair, args.timeframe, args.candles)
    print(f"  Fetched {len(ohlcv)} candles from Binance\n")

    import pandas as pd
    df = pd.DataFrame(ohlcv, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"], unit="ms")

    metadata = {"pair": args.pair}
    df = strategy.populate_indicators(df, metadata)
    df = strategy.populate_entry_trend(df, metadata)

    signals = df[["date", "close", "enter_long", "enter_short", "enter_tag"]].tail(20)
    print("  Last 20 candles:\n")
    print(signals.to_string(index=False))

    last = df.iloc[-1]
    if last.get("enter_long", 0) == 1:
        print(f"\n  >>> BUY signal: {last.get('enter_tag', 'N/A')}")
    elif last.get("enter_short", 0) == 1:
        print(f"\n  >>> SELL signal: {last.get('enter_tag', 'N/A')}")
    else:
        print(f"\n  >>> NO SIGNAL (last candle)")

    print(f"\n  Close: ${last['close']:.4f}")


if __name__ == "__main__":
    main()
