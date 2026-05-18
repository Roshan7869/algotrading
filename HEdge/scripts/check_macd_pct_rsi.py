import pandas as pd
import numpy as np
from pathlib import Path

data_dir = Path("user_data/data/binance/futures")
pairs = ["XRP", "NEAR", "LINK", "DOT", "DOGE", "1000SHIB", "KAS", "TRX", "AVAX", "SUI", "ENA", "OP", "ARB", "ALGO"]

print("=== MACD% (normalized) analysis for each pair ===\n")
print(f"{'Pair':>8} | {'Candles':>7} | {'MaxRSI':>6} | {'MaxMACD%':>8} | {'MACD%>1.3+RSI>70':>17} | {'MACD%>1.0+RSI>65':>16} | {'MACD%>0.5+RSI>60':>16}")
print("-" * 95)

for pair in pairs:
    fname = data_dir / f"{pair}_USDT_USDT-1h-futures.feather"
    if not fname.exists():
        continue
    df = pd.read_feather(fname)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= "2026-05-11"]
    df = df[df["date"] < "2026-05-18"]
    if len(df) < 30:
        continue
    
    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss_ = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, min_periods=14).mean()
    al = loss_.ewm(alpha=1/14, min_periods=14).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    # MACD% = MACD / close * 100
    ef = df["close"].ewm(span=12, adjust=False).mean()
    es = df["close"].ewm(span=26, adjust=False).mean()
    macd_line = ef - es
    macd_pct = (macd_line / df["close"]) * 100
    
    mr = rsi.max()
    mm = macd_pct.max()
    b1 = ((macd_pct > 1.3) & (rsi > 70)).sum()
    b2 = ((macd_pct > 1.0) & (rsi > 65)).sum()
    b3 = ((macd_pct > 0.5) & (rsi > 60)).sum()
    
    print(f"{pair:>8} | {len(df):>7} | {mr:>6.1f} | {mm:>8.2f}% | {b1:>17} | {b2:>16} | {b3:>16}")

# XRP detail on May 14-15
print("\n=== XRP May 14-15 DETAIL (MACD% and RSI) ===")
fname = data_dir / "XRP_USDT_USDT-1h-futures.feather"
df = pd.read_feather(fname)
df["date"] = pd.to_datetime(df["date"])
df = df[df["date"] >= "2026-05-14"]
df = df[df["date"] < "2026-05-16"]
delta = df["close"].diff()
gain = delta.clip(lower=0)
loss_ = -delta.clip(upper=0)
ag = gain.ewm(alpha=1/14, min_periods=14).mean()
al = loss_.ewm(alpha=1/14, min_periods=14).mean()
rs = ag / al.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))
ef = df["close"].ewm(span=12, adjust=False).mean()
es = df["close"].ewm(span=26, adjust=False).mean()
macd_line = ef - es
macd_pct = (macd_line / df["close"]) * 100
df["rsi"] = rsi
df["macd_pct"] = macd_pct

for _, row in df.iterrows():
    trigger = " <<<" if row["macd_pct"] > 1.0 and row["rsi"] > 65 else ""
    print(f"  {row['date']}  close={row['close']:.4f}  rsi={row['rsi']:.1f}  macd%={row['macd_pct']:.2f}%{trigger}")