"""
Parallel CVD download for all 40 pairs from Binance spot aggTrades archive.
Uses ThreadPoolExecutor to download multiple pairs concurrently.
"""
import concurrent.futures
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

BINANCE_ARCHIVE = "https://data.binance.vision/data/spot/daily/aggTrades"
CVD_DIR = Path("user_data/data/binance/cvd")
CVD_DIR.mkdir(parents=True, exist_ok=True)

# All base symbols from config_all_40.json
ALL_SYMBOLS = [
    "1000PEPE", "1000SHIB", "AAVE", "ADA", "ALGO", "APT", "ARB", "ATOM",
    "AVAX", "BCH", "BIO", "BTC", "DOGE", "DOT", "EDEN", "ENA", "ETH",
    "FARTCOIN", "FIL", "HBAR", "HYPE", "KAS", "LINK", "LTC", "NEAR",
    "ONDO", "OP", "RENDER", "SOL", "STORJ", "SUI", "TON", "TRX", "VET",
    "WLD", "XLM", "XMR", "XRP", "XTZ", "ZEC"
]


def download_agg_trades(symbol: str, date: str) -> pd.DataFrame | None:
    url = f"{BINANCE_ARCHIVE}/{symbol}USDT/{symbol}USDT-aggTrades-{date}.zip"
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        csv_file = [f for f in z.namelist() if f.endswith(".csv")][0]
        df = pd.read_csv(
            z.open(csv_file), header=None,
            names=["agg_id", "price", "qty", "first_id", "last_id", "timestamp", "is_buyer_maker", "best_match"]
        )
        return df
    except Exception:
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


def process_pair(symbol: str) -> tuple[str, int, str, str]:
    out = CVD_DIR / f"{symbol}USDT_cvd_1h.feather"
    if out.exists():
        existing = pd.read_feather(out)
        return (symbol, len(existing), "skipped (exists)", "already_downloaded")

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)

    all_hourly = []
    current = start_date
    downloaded_days = 0

    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        trades = download_agg_trades(symbol, date_str)
        if trades is not None:
            hourly = compute_hourly_cvd(trades)
            if len(hourly) > 0:
                all_hourly.append(hourly)
                downloaded_days += 1
        current += timedelta(days=1)

    if not all_hourly:
        return (symbol, 0, "no data", "no_archive_data")

    result = pd.concat(all_hourly, ignore_index=True)
    result = result.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    result["timestamp"] = result["date"].astype("int64") // 10 ** 6
    result.to_feather(out)
    return (symbol, len(result), f"{downloaded_days}d -> {len(result)} candles", "downloaded")


if __name__ == "__main__":
    import sys

    symbols = [s.upper() for s in sys.argv[1:]] if len(sys.argv) > 1 else ALL_SYMBOLS

    print(f"Starting CVD download for {len(symbols)} symbols (15 workers)...")
    print(f"{'Symbol':<12} {'Candles':<8} Status")
    print("-" * 50)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_map = {executor.submit(process_pair, s): s for s in symbols}
        for future in concurrent.futures.as_completed(future_map):
            sym, count, status, _ = future.result()
            results.append((sym, count, status))
            avg_ratio = 0.0
            out_path = CVD_DIR / f"{sym}USDT_cvd_1h.feather"
            if out_path.exists():
                df = pd.read_feather(out_path)
                avg_ratio = df["buy_ratio"].mean() if "buy_ratio" in df.columns else 0
            status_indicator = f"{status}, avg_buy_ratio={avg_ratio:.3f}" if "downloaded" in status else status
            print(f"{sym:<12} {count:<8} {status_indicator}")

    total_pairs = len([r for r in results if r[1] > 0])
    print(f"\nDone. {total_pairs}/{len(symbols)} pairs have CVD data.")
