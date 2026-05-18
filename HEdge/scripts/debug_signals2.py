"""Debug: verify signal generation for XRP"""
import pandas as pd
import numpy as np
from pathlib import Path

data_dir = Path("user_data/data/binance/futures")
fname = data_dir / "XRP_USDT_USDT-1h-futures.feather"
df = pd.read_feather(fname)
df["date"] = pd.to_datetime(df["date"])

# Get last 200 candles
df = df.tail(200).reset_index(drop=True)

# RSI 14
delta = df["close"].diff()
gain = delta.clip(lower=0)
loss_ = -delta.clip(upper=0)
ag = gain.ewm(alpha=1/14, min_periods=14).mean()
al = loss_.ewm(alpha=1/14, min_periods=14).mean()
rs = ag / al.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))

# MACD%
ema_fast = df["close"].ewm(span=12, adjust=False).mean()
ema_slow = df["close"].ewm(span=26, adjust=False).mean()
macd_line = ema_fast - ema_slow
macd_pct = (macd_line / df["close"]) * 100

df["rsi"] = rsi
df["macd_pct"] = macd_pct

# Entry: macd_pct > 0.8 AND rsi > 70 AND volume > 0
mask = (df["macd_pct"] > 0.8) & (df["rsi"] > 70) & (df["volume"] > 0)
df["enter_long"] = 0
df["enter_short"] = 0
df.loc[mask, "enter_long"] = 1
df.loc[mask, "enter_short"] = 1

# May range
may_df = df[df["date"] >= "2026-05-11"]
may_df = may_df[may_df["date"] < "2026-05-18"]

print(f"XRP May 11-18: {len(may_df)} candles")
print(f"enter_long signals: {may_df['enter_long'].sum()}")
print(f"enter_short signals: {may_df['enter_short'].sum()}")

signals = may_df[may_df["enter_long"] == 1]
for _, row in signals.iterrows():
    print(f"  SIGNAL: {row['date']}  close={row['close']:.4f}  rsi={row['rsi']:.1f}  macd_pct={row['macd_pct']:.2f}%")

# Check volume
print(f"\nVolume: min={may_df['volume'].min()}, max={may_df['volume'].max()}, all>0: {(may_df['volume'] > 0).all()}")

# Check 1st 5 rows for NaN indicators  
print(f"\nFirst 5 rows of indicators:")
for _, row in may_df.head(5).iterrows():
    rsi_str = "NaN" if pd.isna(row["rsi"]) else f"{row['rsi']:.1f}"
    macd_str = "NaN" if pd.isna(row["macd_pct"]) else f"{row['macd_pct']:.2f}%"
    print(f"  {row['date']}  rsi={rsi_str}  macd_pct={macd_str}")