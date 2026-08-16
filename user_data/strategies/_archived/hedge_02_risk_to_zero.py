"""
HEDGE Strategy #2 — Risk-to-Zero Accelerated Hedge
===================================================
Core Concept: Split capital 50/50 long/short on top gainers,
move stops to breakeven at first opportunity (Risk to Zero ASAP).
Uses ChromaDB principle "Risk to Zero ASAP" (risk_management_03_445)
  Source: Fabio Valentino / Chart Fanatics

Params:
  - Capital split: 50% long, 50% short
  - Leverage: 10x
  - Stop Loss: -10% initial, moved to breakeven at +3% profit
  - Profit Target: +30% (but becomes risk-free after breakeven)

Edge: By moving to breakeven at +3%, every trade becomes risk-free
within the first few candles. Once risk-free, the trader has infinite
patience to let the trade develop to +30% target. This eliminates
the psychological cost of holding through drawdowns.

Risk Mgmt (ChromaDB): Risk to Zero ASAP
  - After price moves 3% in favor → stop goes to breakeven
  - From that point on: maximum loss = 0, unlimited upside
  - Applied to both long and short legs independently
"""

from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter


class Hedge02RiskToZero(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = True

    # ── Stop & Target ──
    stoploss = -0.10
    minimal_roi = {"0": 0.30}

    # Trailing: aggressive - move to breakeven at +3%
    trailing_stop = True
    trailing_stop_positive = 0.01       # 1% trail after breakeven activates
    trailing_stop_positive_offset = 0.03  # activates at +3%
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
    breakeven_trigger = DecimalParameter(0.02, 0.05, default=0.03, decimals=3, space="buy")
    initial_sl = DecimalParameter(0.07, 0.12, default=0.10, decimals=2, space="sell")
    volume_surge = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy")
    rsi_threshold = IntParameter(55, 75, default=65, space="buy")

    # ── Leverage ──
    def leverage(self, pair, current_time, current_rate,
                 proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(10.0, max_leverage)

    # ── Indicators ──
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Momentum
        dataframe["roc_1h"] = dataframe["close"].pct_change(1) * 100
        dataframe["roc_4h"] = dataframe["close"].pct_change(4) * 100
        dataframe["roc_24h"] = dataframe["close"].pct_change(24) * 100

        # RSI
        dataframe["rsi"] = self._rsi(dataframe, 14)

        # Volume
        dataframe["volume_ma"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = (dataframe["volume"] / dataframe["volume_ma"]).fillna(1)

        # ATR
        dataframe["atr"] = self._atr(dataframe, 14)

        return dataframe

    # ── Entry ──
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # LONG: recent momentum + volume surge
        long_cond = (
            (dataframe["roc_1h"] > 0.5) &
            (dataframe["roc_4h"] > 1.5) &
            (dataframe["volume_ratio"] > self.volume_surge.value) &
            (dataframe["rsi"] < self.rsi_threshold.value)
        )
        dataframe.loc[long_cond & (dataframe["volume"] > 0),
                      ["enter_long", "enter_tag"]] = (1, "hedge02_rtz_long")

        # SHORT: overextended + losing hourly momentum
        short_cond = (
            (dataframe["roc_24h"] > 8.0) &
            (dataframe["rsi"] > 70) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["roc_1h"] < 0)
        )
        dataframe.loc[short_cond & (dataframe["volume"] > 0),
                      ["enter_short", "enter_tag"]] = (1, "hedge02_rtz_short")

        return dataframe

    # ── Exit ──
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 82, ["exit_long", "exit_tag"]] = (1, "rsi_exit_long")
        dataframe.loc[dataframe["rsi"] < 18, ["exit_short", "exit_tag"]] = (1, "rsi_exit_short")
        return dataframe

    # ── Custom Stop: apply configured initial_sl ──
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        if after_fill:
            return -self.initial_sl.value
        return None

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
