import pandas as pd
import numpy as np
from pathlib import Path

data_dir = Path("user_data/data/binance/futures")
pairs = ["XRP", "NEAR", "ENA", "1000SHIB", "DOGE", "SUI", "LINK", "AVAX", "OP", "ARB", "DOT", "KAS", "TRX", "ALGO", "VET", "ONDO", "WLD", "XLM"]

for pair in pairs:
    fname = data_dir / f"{pair}_USDT_USDT-1h-futures.feather"
    if not fname.exists():
        print(f"{pair:5s}: NO DATA FILE")
        continue
    df = pd.read_feather(fname)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= "2026-05-11"]
    df = df[df["date"] < "2026-05-18"]
    if len(df) < 20:
        print(f"{pair:5s}: Only {len(df)} candles in 7d range")
        continue
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss_ = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, min_periods=14).mean()
    al = loss_.ewm(alpha=1/14, min_periods=14).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    ef = df["close"].ewm(span=12, adjust=False).mean()
    es = df["close"].ewm(span=26, adjust=False).mean()
    mc = ef - es
    mr = rsi.max()
    mm = mc.max()
    b1 = ((mc > 0.02) & (rsi > 75)).sum()
    b2 = ((mc > 0.01) & (rsi > 70)).sum()
    b3 = ((mc > 0.005) & (rsi > 65)).sum()
    # Also show recent XRP values
    if pair == "XRP":
        print(f"\n=== XRP DETAIL (last 7 days) ===")
        xrp = df.copy()
        xrp["rsi"] = rsi
        xrp["macd"] = mc
        triggers = xrp[(mc > 0.01) | (rsi > 65)]
        for _, row in triggers.iterrows():
            print(f"  {row['date']}  close={row['close']:.4f}  rsi={row['rsi']:.1f}  macd={row['macd']:.4f}")
        print()
    print(f"{pair:5s}: candles={len(df):3d} maxRSI={mr:.1f} maxMACD={mm:.4f} strict02_75={b1} med01_70={b2} loose005_65={b3}")