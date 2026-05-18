"""
HEDGE Strategy #6 — Anti-Martingale Streak Exploitation Hedge
==============================================================
Core Concept: Split capital 50/50 long/short on top gainers.
Uses ChromaDB "Anti-Martingale — Double Down After Wins"
  Source: position_sizing_chunks_026_555

Params:
  - Capital split: 50% long, 50% short
  - Leverage: 10x base
  - Stop Loss: -10%
  - Profit Target: +30%
  - Sizing: base 2% risk → increase 50% after each win (cap 4%)
    → reset on loss

Edge: Wins cluster when the strategy is aligned with the market regime.
Anti-martingale exploits this by increasing sizing after wins (when
strategy is in sync with the market). Losses cause immediate reset to
base size, preventing large drawdowns during misaligned periods.

Risk Mgmt (ChromaDB): Anti-Martingale
  - Base: 2% risk per trade
  - After 1 win: 3%
  - After 2 wins: 4% (cap)
  - After loss: reset to 2%
  - NEVER increase after a loss
"""

from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter


class Hedge06AntiMartingale(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = True

    # ── Stop & Target ──
    stoploss = -0.10
    minimal_roi = {"0": 0.30}

    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.05
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
    vol_surge = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy")
    base_size_pct = DecimalParameter(0.01, 0.03, default=0.02, decimals=3, space="buy")
    max_size_pct = DecimalParameter(0.03, 0.06, default=0.04, decimals=3, space="buy")
    win_streak = 0  # internal state

    # ── Leverage ──
    def leverage(self, pair, current_time, current_rate,
                 proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(10.0, max_leverage)

    # ── Indicators ──
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["roc_1h"] = dataframe["close"].pct_change(1) * 100
        dataframe["roc_4h"] = dataframe["close"].pct_change(4) * 100
        dataframe["roc_24h"] = dataframe["close"].pct_change(24) * 100
        dataframe["rsi"] = self._rsi(dataframe, 14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = (dataframe["volume"] / dataframe["volume_ma"]).fillna(1)
        dataframe["atr"] = self._atr(dataframe, 14)
        return dataframe

    # ── Entry ──
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_cond = (
            (dataframe["roc_1h"] > 0.5) &
            (dataframe["roc_4h"] > 2.0) &
            (dataframe["volume_ratio"] > self.vol_surge.value) &
            (dataframe["rsi"] > 40) &
            (dataframe["rsi"] < 68)
        )
        dataframe.loc[long_cond & (dataframe["volume"] > 0),
                      ["enter_long", "enter_tag"]] = (1, "hedge06_anti_long")

        short_cond = (
            (dataframe["roc_24h"] > 10.0) &
            (dataframe["rsi"] > 72) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["roc_1h"] < 0)
        )
        dataframe.loc[short_cond & (dataframe["volume"] > 0),
                      ["enter_short", "enter_tag"]] = (1, "hedge06_anti_short")

        return dataframe

    # ── Exit ──
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 82, ["exit_long", "exit_tag"]] = (1, "rsi_exit_long")
        dataframe.loc[dataframe["rsi"] < 18, ["exit_short", "exit_tag"]] = (1, "rsi_exit_short")
        return dataframe

    # ── Streak tracking ──
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        if current_profit > 0:
            self.win_streak = min(self.win_streak + 1, 10)
        else:
            self.win_streak = 0
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
