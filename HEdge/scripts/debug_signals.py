"""Debug script: save indicator values for XRP to check signal generation"""
import pandas as pd
import numpy as np
from pathlib import Path

data_dir = Path("user_data/data/binance/futures")
fname = data_dir / "XRP_USDT_USDT-1h-futures.feather"
df = pd.read_feather(fname)
df["date"] = pd.to_datetime(df["date"])

# Take last 200 candles
df = df.tail(200).reset_index(drop=True)

# Same indicators as strategy
delta = df["close"].diff()
gain = delta.clip(lower=0)
loss_ = -delta.clip(upper=0)
ag = gain.ewm(alpha=1/14, min_periods=14).mean()
al = loss_.ewm(alpha=1/14, min_periods=14).mean()
rs = ag / al.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))

ema_fast = df["close"].ewm(span=12, adjust=False).mean()
ema_slow = df["close"].ewm(span=26, adjust=False).mean()
macd_line = ema_fast - ema_slow
macd_pct = (macd_line / df["close"]) * 100

# Entry conditions (same as strategy)
macd_pct_above = macd_pct > 0.8
rsi_above = rsi > 70
long_signal = macd_pct_above & rsi_above
short_signal = macd_pct_above & rsi_above

# Filter to May 11-17
df["rsi"] = rsi
df["macd_pct"] = macd_pct
df["macd"] = macd_line
df["long_signal"] = long_signal
df["short_signal"] = short_signal

may_data = df[df["date"] >= "2026-05-11"]
may_data = may_data[may_data["date"] < "2026-05-18"]

print(f"Total candles in range: {len(may_data)}")
print(f"RSI not NaN: {may_data['rsi'].notna().sum()}")
print(f"MACD% not NaN: {may_data['macd_pct'].notna().sum()}")
print(f"Long signals: {may_data['long_signal'].sum()}")
print(f"Short signals: {may_data['short_signal'].sum()}")
print()

# Show all signals
signals = may_data[may_data["long_signal"] | may_data["short_signal"]]
if len(signals) > 0:
    for _, row in signals.iterrows():
        print(f"  {row['date']}  close={row['close']:.4f}  rsi={row['rsi']:.1f}  macd_pct={row['macd_pct']:.2f}%")
else:
    print("NO SIGNALS FOUND")
    print("\nClosest to triggering (MACD_pct > 0.5 or RSI > 65):")
    close = may_data[(may_data["macd_pct"] > 0.5) | (may_data["rsi"] > 65)]
    for _, row in close.iterrows():
        print(f"  {row['date']}  close={row['close']:.4f}  rsi={row['rsi']:.1f} if NaN:  macd_pct={row['macd_pct']:.2f}% if NaN:")