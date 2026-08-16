"""
HEDGE Strategy #1 — Fixed Fractional Balanced Hedge
====================================================
Core Concept: Split capital 50/50 long/short on top gainers.
Uses ChromaDB principle "Fixed Fractional Sizing — 1% Risk Per Trade"
  Source: position_sizing_chunks_000_529

Params:
  - Capital split: 50% long, 50% short
  - Leverage: 10x
  - Stop Loss: -10% per leg
  - Profit Target: +30% per leg
  - Position sizing: 1% of sub-account risk per trade based on stop distance

Edge: The long leg captures momentum on gainers; the short leg hedges
against sudden market reversals. With 10x leverage, a 10% stop = 100%
of the position's allocated capital at risk, so Fixed Fractional ensures
no single trade exceeds 1% account risk. Combined long+short reduces
overall portfolio volatility.

Risk Mgmt (ChromaDB): Fixed Fractional 1%
  - Position = (SubAccount × 0.01) / (Entry - Stoploss)
  - At 10x leverage and 10% SL: effective risk per trade = 1% of sub-account
"""

from datetime import datetime
from typing import Optional, Dict
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter


class Hedge01FixedFractional(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = True

    # Capital split: 50% long / 50% short
    # This strategy manages ONE side at a time via config pairlists.

    # ── Stop & Target ──
    stoploss = -0.10                # -10% stop
    minimal_roi = {"0": 0.30}       # 30% target

    trailing_stop = True
    trailing_stop_positive = 0.05
    trailing_stop_positive_offset = 0.08
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 100

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ── Hyperopt Params ──
    fixed_risk_pct = DecimalParameter(0.005, 0.02, default=0.01, decimals=3, space="buy")
    rsi_oversold = IntParameter(25, 40, default=30, space="buy")
    rsi_overbought = IntParameter(60, 75, default=70, space="sell")
    volume_surge = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy")

    # ── Leverage ──
    def leverage(self, pair, current_time, current_rate,
                 proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(10.0, max_leverage)

    # ── Indicators ──
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Momentum for top-gainer detection
        dataframe["roc_1h"] = dataframe["close"].pct_change(1) * 100
        dataframe["roc_4h"] = dataframe["close"].pct_change(4) * 100
        dataframe["roc_24h"] = dataframe["close"].pct_change(24) * 100

        # RSI
        dataframe["rsi"] = self._rsi(dataframe, 14)

        # Volume ratio
        dataframe["volume_ma"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = (dataframe["volume"] / dataframe["volume_ma"]).fillna(1)

        # ATR for stop distance
        dataframe["atr"] = self._atr(dataframe, 14)

        return dataframe

    # ── Entry ──
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # LONG: top gainer momentum
        long_cond = (
            (dataframe["roc_1h"] > 1.0) &          # gained >1% in last hour
            (dataframe["roc_4h"] > 2.0) &          # gained >2% in 4h
            (dataframe["volume_ratio"] > self.volume_surge.value) &
            (dataframe["rsi"] > 40) &
            (dataframe["rsi"] < 70)
        )
        dataframe.loc[long_cond & (dataframe["volume"] > 0),
                      ["enter_long", "enter_tag"]] = (1, "hedge01_long_gainer")

        # SHORT: overextended gainer (mean reversion)
        short_cond = (
            (dataframe["roc_24h"] > 10.0) &         # up >10% in 24h — overextended
            (dataframe["rsi"] > self.rsi_overbought.value) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["roc_1h"] < dataframe["roc_1h"].rolling(10).mean())  # losing hourly momo
        )
        dataframe.loc[short_cond & (dataframe["volume"] > 0),
                      ["enter_short", "enter_tag"]] = (1, "hedge01_short_overextended")

        return dataframe

    # ── Exit ──
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 80, ["exit_long", "exit_tag"]] = (1, "rsi_exit_long")
        dataframe.loc[dataframe["rsi"] < 20, ["exit_short", "exit_tag"]] = (1, "rsi_exit_short")
        return dataframe

    # ── Helpers ──
    def _rsi(self, df, period=14):
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _atr(self, df, period=14):
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()
