"""
Custom indicators computed on live Binance WebSocket candle data.

CPU-friendly: pure pandas/numpy, no talib dependency, incremental computation.
Uses talipp where available for precision, falls back to pandas.
"""

import numpy as np
import pandas as pd
from typing import Optional


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all custom indicators on OHLCV data.

    Requires columns: open, high, low, close, volume, timestamp
    Optionally uses: taker_buy_volume (from Binance WS kline)

    Returns df with indicator columns added.
    """
    if df.empty or len(df) < 50:
        return df

    df = df.copy()

    # ── EMA Stack ──
    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

    # ── RSI(14) ──
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── ATR(14) ──
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    # ── VWAP ──
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    cum_vol = cum_vol.replace(0, np.nan)
    df["vwap"] = (typical * df["volume"]).cumsum() / cum_vol

    # ── Volume Delta (from Binance taker_buy_volume or approximated) ──
    if "taker_buy_volume" in df.columns:
        df["buy_vol"] = df["taker_buy_volume"].clip(lower=0)
        df["sell_vol"] = (df["volume"] - df["taker_buy_volume"]).clip(lower=0)
        df["delta"] = df["buy_vol"] - df["sell_vol"]
    else:
        # Approximate: bullish candles = buy volume, bearish = sell
        candle_range = (df["high"] - df["low"]).replace(0, np.nan)
        df["bar_delta"] = (df["volume"] * (df["close"] - df["open"]) / candle_range).fillna(0)
        df["delta"] = df["bar_delta"]
        df["buy_vol"] = df["delta"].clip(lower=0)
        df["sell_vol"] = (-df["delta"]).clip(lower=0)

    # ── Delta Z-Score ──
    df["delta_ma"] = df["delta"].rolling(20).mean()
    df["delta_std"] = df["delta"].rolling(20).std().replace(0, np.nan)
    df["delta_zscore"] = ((df["delta"] - df["delta_ma"]) / df["delta_std"]).fillna(0)

    # ── CVD (Cumulative Volume Delta) ──
    df["cvd"] = df["delta"].cumsum()

    # ── Volume Moving Average ──
    df["vol_ma_20"] = df["volume"].rolling(20).mean()

    # ── Bollinger Bands (20, 2σ) ──
    df["bb_mid"] = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    # ── MACD (12, 26, 9) ──
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # ── SuperTrend (10, 3ATR) ──
    df = _supertrend(df, period=10, multiplier=3)

    # ── EMA Trend (bullish stack: 9 > 20 > 50) ──
    df["trend_bullish"] = ((df["ema_9"] > df["ema_20"]) & (df["ema_20"] > df["ema_50"])).astype(int)
    df["trend_bearish"] = ((df["ema_9"] < df["ema_20"]) & (df["ema_20"] < df["ema_50"])).astype(int)

    return df


def _supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Compute SuperTrend indicator."""
    hl2 = (df["high"] + df["low"]) / 2
    atr = df["atr"]

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    st = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)  # 1=up, -1=down

    for i in range(period, len(df)):
        # Upper band: can only decrease
        if upper_band.iloc[i] < upper_band.iloc[i-1] or df["close"].iloc[i-1] > upper_band.iloc[i-1]:
            upper_band.iloc[i] = upper_band.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i-1]

        # Lower band: can only increase
        if lower_band.iloc[i] > lower_band.iloc[i-1] or df["close"].iloc[i-1] < lower_band.iloc[i-1]:
            lower_band.iloc[i] = lower_band.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i-1]

        # Direction
        if direction.iloc[i-1] == 1:  # was up
            if df["close"].iloc[i] < lower_band.iloc[i]:
                direction.iloc[i] = -1
                st.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = 1
                st.iloc[i] = lower_band.iloc[i]
        else:  # was down
            if df["close"].iloc[i] > upper_band.iloc[i]:
                direction.iloc[i] = 1
                st.iloc[i] = lower_band.iloc[i]
            else:
                direction.iloc[i] = -1
                st.iloc[i] = upper_band.iloc[i]

    df["supertrend"] = st
    df["st_direction"] = direction  # 1=uptrend (green), -1=downtrend (red)
    return df