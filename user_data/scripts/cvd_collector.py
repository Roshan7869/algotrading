"""
Binance CVD (Cumulative Volume Delta) Collector
================================================
Connects to Binance WebSocket for real-time trade data,
computes CVD per candle (taker buy - taker sell volume),
and saves as feather files compatible with backtesting.

Usage:
  python3 user_data/scripts/cvd_collector.py backfill BTC/USDT:USDT --days 3
  python3 user_data/scripts/cvd_collector.py stream BTC/USDT:USDT --duration 60
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

BINANCE_FUTURES_WS = "wss://fstream.binance.com/ws"
BINANCE_FUTURES_REST = "https://fapi.binance.com"
DATA_DIR = Path(os.environ.get("DATA_DIR", "user_data/data/binance/cvd"))


def symbol_to_binance(pair: str) -> str:
    """Convert 'BTC/USDT:USDT' -> 'BTCUSDT' for Binance futures"""
    base = pair.split("/")[0]
    return base.upper() + "USDT"


def binance_to_pair(symbol: str) -> str:
    base = symbol.replace("USDT", "")
    return f"{base}/USDT:USDT"


async def stream_trades(pair: str, duration_secs: int = 60):
    """Subscribe to aggTrade stream and print CVD incrementally"""
    import websockets

    symbol = symbol_to_binance(pair).lower()
    url = f"{BINANCE_FUTURES_WS}/{symbol}@aggTrade"
    print(f"Connecting to {url} ...")

    trades = []
    start = time.time()

    async with websockets.connect(url) as ws:
        print(f"Streaming {pair} for {duration_secs}s ...")
        while time.time() - start < duration_secs:
            msg = json.loads(await ws.recv())
            if "e" in msg and msg["e"] == "aggTrade":
                price = float(msg["p"])
                qty = float(msg["q"])
                is_sell = msg["m"]  # True = seller aggressively sold (taker sell)
                trades.append({
                    "timestamp": datetime.fromtimestamp(msg["T"] / 1000, tz=timezone.utc),
                    "price": price,
                    "volume": qty,
                    "is_taker_sell": is_sell,
                    "value": price * qty,
                })

    df = pd.DataFrame(trades)
    if len(df) == 0:
        print("No trades received")
        return

    df["is_taker_buy"] = ~df["is_taker_sell"]
    df["taker_buy_vol"] = df["volume"] * df["is_taker_buy"]
    df["taker_sell_vol"] = df["volume"] * df["is_taker_sell"]
    df["taker_buy_value"] = df["value"] * df["is_taker_buy"]
    df["taker_sell_value"] = df["value"] * df["is_taker_sell"]

    total_buy_vol = df["taker_buy_vol"].sum()
    total_sell_vol = df["taker_sell_vol"].sum()
    cvd = total_buy_vol - total_sell_vol
    buy_pct = total_buy_vol / (total_buy_vol + total_sell_vol) * 100

    print(f"\n{pair} — {duration_secs}s stream")
    print(f"  Trades: {len(df)}")
    print(f"  Taker Buy Vol:  {total_buy_vol:.4f}")
    print(f"  Taker Sell Vol: {total_sell_vol:.4f}")
    print(f"  CVD: {cvd:+.4f}")
    print(f"  Buy Volume %: {buy_pct:.1f}%")

    out = DATA_DIR / f"{symbol_to_binance(pair)}_cvd_stream.feather"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_feather(out)
    print(f"  Saved: {out}")


def backfill_agg_trades(pair: str, days: int = 3):
    """Backfill historical aggTrades via Binance REST API and compute hourly CVD"""
    symbol = symbol_to_binance(pair)
    url = f"{BINANCE_FUTURES_REST}/fapi/v1/aggTrades"
    end_time = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_time = end_time - days * 24 * 3600 * 1000

    print(f"Backfilling {pair} ({symbol}) for {days} days ...")
    all_trades = []
    limit = 1000
    current_end = end_time

    while current_end > start_time:
        params = {
            "symbol": symbol,
            "endTime": current_end,
            "limit": limit,
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"  API error {resp.status_code}: {resp.text[:200]}")
            break
        trades = resp.json()
        if not trades:
            break
        all_trades.extend(trades)
        current_end = trades[0]["T"] - 1
        pct = (1 - (current_end - start_time) / (end_time - start_time)) * 100
        print(f"  Fetched {len(trades)} trades ({pct:.0f}% complete, {len(all_trades)} total)", end="\r")
        time.sleep(0.3)

    print(f"\n  Total trades: {len(all_trades)}")

    records = []
    for t in all_trades:
        records.append({
            "timestamp": datetime.fromtimestamp(t["T"] / 1000, tz=timezone.utc),
            "price": float(t["p"]),
            "volume": float(t["q"]),
            "is_taker_sell": t["m"],
        })

    df = pd.DataFrame(records)
    if len(df) == 0:
        print("No trades")
        return

    df = df.sort_values("timestamp").reset_index(drop=True)
    df["is_taker_buy"] = ~df["is_taker_sell"]
    df["taker_buy_vol"] = df["volume"] * df["is_taker_buy"]
    df["taker_sell_vol"] = df["volume"] * df["is_taker_sell"]
    df["taker_buy_value"] = df["price"] * df["volume"] * df["is_taker_buy"]
    df["taker_sell_value"] = df["price"] * df["volume"] * df["is_taker_sell"]

    # Resample to 1h candles
    df.set_index("timestamp", inplace=True)
    hourly = pd.DataFrame()
    hourly["volume"] = df["volume"].resample("1h").sum()
    hourly["taker_buy_vol"] = df["taker_buy_vol"].resample("1h").sum()
    hourly["taker_sell_vol"] = df["taker_sell_vol"].resample("1h").sum()
    hourly["trades"] = df["volume"].resample("1h").count()
    hourly["cvd"] = hourly["taker_buy_vol"] - hourly["taker_sell_vol"]
    hourly["cvd_cumulative"] = hourly["cvd"].cumsum()
    hourly["buy_ratio"] = hourly["taker_buy_vol"] / hourly["volume"].replace(0, float("nan"))
    hourly["cvd_divergence"] = hourly["cvd"].rolling(24).sum()
    hourly = hourly.reset_index()
    hourly["date"] = hourly["timestamp"]

    # Merge OHLCV data if available
    ohlcv_path = Path(f"user_data/data/binance/futures/{symbol}_USDT-1h-futures.feather")
    if ohlcv_path.exists():
        ohlcv = pd.read_feather(ohlcv_path)
        ohlcv["date"] = pd.to_datetime(ohlcv["date"])
        hourly = hourly.merge(ohlcv[["date", "open", "high", "low", "close"]], on="date", how="left")

    out = DATA_DIR / f"{symbol}_cvd_1h.feather"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hourly.to_feather(out)
    print(f"  Saved: {out} ({len(hourly)} hourly candles)")
    print(f"  Total CVD (cumulative): {hourly['cvd_cumulative'].iloc[-1]:+.2f}")
    print(f"  Avg Buy Ratio: {hourly['buy_ratio'].mean():.1%}")
    return hourly


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Binance CVD Collector")
    sub = parser.add_subparsers(dest="mode", required=True)

    stream_p = sub.add_parser("stream", help="Stream live trades")
    stream_p.add_argument("pair", help="e.g. BTC/USDT:USDT")
    stream_p.add_argument("--duration", type=int, default=60, help="Duration in seconds")

    backfill_p = sub.add_parser("backfill", help="Backfill historical aggTrades")
    backfill_p.add_argument("pair", help="e.g. DOGE/USDT:USDT")
    backfill_p.add_argument("--days", type=int, default=3, help="Days to backfill")

    args = parser.parse_args()

    if args.mode == "stream":
        asyncio.run(stream_trades(args.pair, args.duration))
    elif args.mode == "backfill":
        backfill_agg_trades(args.pair, args.days)
