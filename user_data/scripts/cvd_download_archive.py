"""
Download Binance spot daily aggTrades archive and compute hourly CVD.
Uses data.binance.vision public archive for 30-day historical coverage.
"""

import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

BINANCE_ARCHIVE = "https://data.binance.vision/data/spot/daily/aggTrades"
CVD_DIR = Path("user_data/data/binance/cvd")
CVD_DIR.mkdir(parents=True, exist_ok=True)

PAIRS = ["1000PEPE", "BIO", "DOGE", "FIL", "OP", "RENDER", "SUI"]


def download_agg_trades(symbol: str, date: str) -> pd.DataFrame | None:
    url = f"{BINANCE_ARCHIVE}/{symbol}USDT/{symbol}USDT-aggTrades-{date}.zip"
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        csv_file = [f for f in z.namelist() if f.endswith(".csv")][0]
        df = pd.read_csv(z.open(csv_file), header=None,
                         names=["agg_id", "price", "qty", "first_id", "last_id", "timestamp", "is_buyer_maker", "best_match"])
        return df
    except Exception as e:
        print(f"  Error downloading {symbol} {date}: {e}")
        return None


def compute_hourly_cvd(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="us")
    df = df.sort_values("datetime")
    df["is_taker_buy"] = ~df["is_buyer_maker"]
    df["taker_buy_vol"] = df["qty"] * df["is_taker_buy"]
    df["taker_sell_vol"] = df["qty"] * (~df["is_taker_buy"])
    df = df.set_index("datetime")

    hourly = pd.DataFrame()
    hourly["volume"] = df["qty"].resample("1h").sum()
    hourly["taker_buy_vol"] = df["taker_buy_vol"].resample("1h").sum()
    hourly["taker_sell_vol"] = df["taker_sell_vol"].resample("1h").sum()
    hourly["trades"] = df["qty"].resample("1h").count()
    hourly["cvd"] = hourly["taker_buy_vol"] - hourly["taker_sell_vol"]
    hourly["cvd_cumulative"] = hourly["cvd"].cumsum()
    hourly["buy_ratio"] = hourly["taker_buy_vol"] / hourly["volume"].replace(0, float("nan"))
    hourly["cvd_divergence"] = hourly["cvd"].rolling(24).sum()
    hourly = hourly.reset_index()
    hourly.rename(columns={"datetime": "date"}, inplace=True)
    return hourly


def process_pair(symbol: str):
    print(f"\n=== {symbol} ===")
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)

    all_hourly = []
    current = start_date

    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        print(f"  {date_str}...", end=" ", flush=True)
        trades = download_agg_trades(symbol, date_str)
        if trades is not None:
            hourly = compute_hourly_cvd(trades)
            if len(hourly) > 0:
                all_hourly.append(hourly)
                print(f"{len(trades):,} trades -> {len(hourly)} hourly candles")
            else:
                print("no candles")
        else:
            print("no data")
        current += timedelta(days=1)

    if not all_hourly:
        print(f"  No data for {symbol}")
        return

    result = pd.concat(all_hourly, ignore_index=True)
    if "date" not in result.columns:
        print(f"  No date column for {symbol}")
        return
    result = result.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    result["timestamp"] = result["date"].astype("int64") // 10**6

    out = CVD_DIR / f"{symbol}USDT_cvd_1h.feather"
    result.to_feather(out)
    print(f"  Saved: {out} ({len(result)} candles, {result.date.min()} to {result.date.max()})")
    print(f"  Avg buy_ratio: {result.buy_ratio.mean():.3f}")


if __name__ == "__main__":
    import sys
    symbols = sys.argv[1:] if len(sys.argv) > 1 else PAIRS
    for s in symbols:
        process_pair(s.upper())
