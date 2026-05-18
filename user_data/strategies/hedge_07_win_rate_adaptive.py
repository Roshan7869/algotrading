"""
HEDGE Strategy #7 — Win Rate Adaptive Dynamic Hedge
====================================================
Core Concept: Split capital 50/50 long/short on top gainers.
Uses ChromaDB "Win Rate Adaptive Sizing — Size With Streak"
  Source: position_sizing_chunks_024_553

Params:
  - Capital split: 50% long, 50% short
  - Leverage: 10x
  - Stop Loss: -10%
  - Profit Target: +30%
  - Adaptive sizing:
    After 3 wins → +25%, After 5 wins → +50%
    After 1 loss → base, After 2 losses → -25%, After 3 losses → -50%

Edge: Combines anti-martingale (increase on wins) with protective
reduction on losses. Wins cluster when strategy is aligned with regime;
scaling up during alignment maximizes returns. Losses signal misalignment;
scaling down protects capital. This dual-direction adaptation is more
sophisticated than pure anti-martingale.

Risk Mgmt (ChromaDB): Win Rate Adaptive
  - 3 wins → +25% size
  - 5 wins → +50% size
  - 1 loss → base size
  - 2 losses → -25% size
  - 3 losses → -50% size
  - Never increase after loss
"""

from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter


class Hedge07WinRateAdaptive(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = True

    # ── Stop & Target ──
    stoploss = -0.10
    minimal_roi = {"0": 0.30}

    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
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
    rsi_ob = IntParameter(68, 80, default=74, space="sell")

    # Streak tracking
    _streak_consecutive_wins = 0
    _streak_consecutive_losses = 0

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

    # ── Entry — signal strength adapts to streak ──
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Adjust threshold based on streak
        win_boost = 1.0
        if self._streak_consecutive_wins >= 5:
            win_boost = 1.5
        elif self._streak_consecutive_wins >= 3:
            win_boost = 1.25

        loss_penalty = 1.0
        if self._streak_consecutive_losses >= 3:
            loss_penalty = 0.5
        elif self._streak_consecutive_losses >= 2:
            loss_penalty = 0.75

        signal_factor = win_boost * loss_penalty

        long_cond = (
            (dataframe["roc_1h"] > 0.5 * (2.0 - signal_factor)) &
            (dataframe["roc_4h"] > 2.0 * (2.0 - signal_factor)) &
            (dataframe["volume_ratio"] > self.vol_surge.value / signal_factor) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < 65)
        )
        dataframe.loc[long_cond & (dataframe["volume"] > 0),
                      ["enter_long", "enter_tag"]] = (1, "hedge07_adaptive_long")

        short_cond = (
            (dataframe["roc_24h"] > 8.0) &
            (dataframe["rsi"] > self.rsi_ob.value) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["roc_1h"] < 0)
        )
        dataframe.loc[short_cond & (dataframe["volume"] > 0),
                      ["enter_short", "enter_tag"]] = (1, "hedge07_adaptive_short")

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
            self._streak_consecutive_wins += 1
            self._streak_consecutive_losses = 0
        else:
            self._streak_consecutive_losses += 1
            self._streak_consecutive_wins = 0
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
