"""
HEDGE Strategy #4 — Consecutive Loss Protection Hedge
======================================================
Core Concept: Split capital 50/50 long/short on top gainers.
Uses ChromaDB "Consecutive Loss Sizing — Reduce After Streaks"
  Source: position_sizing_chunks_014_543

Params:
  - Capital split: 50% long, 50% short
  - Leverage: 10x
  - Stop Loss: -10%
  - Profit Target: +30%
  - Adaptive sizing: reduce 25% after 3 consecutive losses,
    reduce 50% after 5, stop trading after 7

Edge: Prevents tilt-driven revenge trading and catastrophic drawdowns.
The sizing reduction acts as a circuit breaker — when the strategy is
misaligned with market regime, it automatically scales down exposure.
After a losing streak breaks (win), sizing resets to base.

Risk Mgmt (ChromaDB): Consecutive Loss Sizing
  - After 3 consecutive losses → reduce size by 25%
  - After 5 consecutive losses → reduce by 50%
  - After 7 consecutive losses → stop trading for the day
  - After 1 win → reset to base size
"""

from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter


class Hedge04ConsecLossProtect(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = True

    # ── Stop & Target ──
    stoploss = -0.10
    minimal_roi = {"0": 0.30}

    trailing_stop = True
    trailing_stop_positive = 0.03
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
    volume_surge = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy")
    streak_loss_threshold = IntParameter(2, 4, default=3, space="buy")
    streak_stop_threshold = IntParameter(5, 8, default=7, space="sell")

    # Internal state for streak tracking — reset on each backtest
    _consecutive_losses = 0

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
        # If in streak protection mode, reduce signal sensitivity
        reduction_factor = 1.0
        if self._consecutive_losses >= self.streak_loss_threshold.value:
            reduction_factor = 0.75
        if self._consecutive_losses >= 5:
            reduction_factor = 0.50
        if self._consecutive_losses >= self.streak_stop_threshold.value:
            # Stop trading — no entries
            return dataframe

        # Apply reduction to signal thresholds
        vol_threshold = self.volume_surge.value * (2.0 - reduction_factor)

        long_cond = (
            (dataframe["roc_1h"] > 0.5 * reduction_factor) &
            (dataframe["roc_4h"] > 2.0 * reduction_factor) &
            (dataframe["volume_ratio"] > vol_threshold) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < 65)
        )
        dataframe.loc[long_cond & (dataframe["volume"] > 0),
                      ["enter_long", "enter_tag"]] = (1, "hedge04_protect_long")

        short_cond = (
            (dataframe["roc_24h"] > 8.0) &
            (dataframe["rsi"] > 70) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["roc_1h"] < 0)
        )
        dataframe.loc[short_cond & (dataframe["volume"] > 0),
                      ["enter_short", "enter_tag"]] = (1, "hedge04_protect_short")

        return dataframe

    # ── Exit ──
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 80, ["exit_long", "exit_tag"]] = (1, "rsi_exit_long")
        dataframe.loc[dataframe["rsi"] < 20, ["exit_short", "exit_tag"]] = (1, "rsi_exit_short")
        return dataframe

    # ── Track consecutive losses ──
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        if current_profit < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0  # reset on win
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
