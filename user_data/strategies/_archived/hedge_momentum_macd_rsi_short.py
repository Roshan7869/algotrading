"""
HEDGE MOMENTUM — MACD% + RSI Confluence — SHORT VARIANT
=======================================================
Entry: MACD/Close > 0.8% AND RSI > 70 → SHORT ONLY
Stop Loss: -10%
Take Profit: +30%
Trailing: Breakeven after +3%

This is the SHORT half of the hedge pair.
Run alongside hedge_momentum_macd_rsi_long for full hedge.
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, Trade


class HedgeMomentumMacdRsiShort(IStrategy):
    """MACD% + RSI momentum — SHORT ONLY"""

    can_short: bool = True  # Short only
    timeframe = "1h"
    startup_candle_count: int = 100

    stoploss = -0.10
    minimal_roi = {"0": 0.30}

    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    stake_amount = "unlimited"
    tradable_balance_ratio = 0.5
    max_open_trades = 18

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)
    rsi_period = IntParameter(7, 21, default=14, space="buy", optimize=False)
    macd_fast = IntParameter(8, 21, default=12, space="buy", optimize=False)
    macd_slow = IntParameter(21, 52, default=26, space="buy", optimize=False)
    macd_signal_period = IntParameter(5, 13, default=9, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    @staticmethod
    def _calc_rsi(series, period=14):
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calc_macd(df, fast=12, slow=26, signal=9):
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return pd.DataFrame({"macd": macd_line, "macdsignal": signal_line, "macdhist": histogram})

    def populate_indicators(self, dataframe, metadata):
        period = int(self.rsi_period.value)
        dataframe["rsi"] = self._calc_rsi(dataframe["close"], period)
        fast, slow, sig = int(self.macd_fast.value), int(self.macd_slow.value), int(self.macd_signal_period.value)
        macd_df = self._calc_macd(dataframe, fast, slow, sig)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        dataframe["ema_50"] = dataframe["close"].ewm(span=50, adjust=False).mean()
        dataframe["ema_200"] = dataframe["close"].ewm(span=200, adjust=False).mean()
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        macd_pct_above = dataframe["macd_pct"] > float(self.macd_pct_threshold.value)
        rsi_above = dataframe["rsi"] > int(self.rsi_threshold.value)
        dataframe.loc[
            (macd_pct_above) & (rsi_above) & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        # Exit short: RSI drops below 50 (momentum fading)
        dataframe.loc[
            (dataframe["rsi"] < 50),
            ["exit_short", "exit_tag"]
        ] = (1, "macd_pct_rsi_exit_short")
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        if current_profit > 0.03:
            return -0.005
        return None