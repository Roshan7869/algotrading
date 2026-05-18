from datetime import datetime, timezone
from typing import Optional, Union
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    DecimalParameter,
    IntParameter,
    BooleanParameter,
    informative,
)

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import merge_informative_pair
from signal_bus_mixin import SignalBusMixin


class RsiDivergenceStrategy(IStrategy, SignalBusMixin):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    minimal_roi = {
        "0": 0.30,
        "120": 0.15,
        "360": 0.08,
        "720": 0.04,
    }

    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.05
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count: int = 150

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    rsi_period = IntParameter(10, 20, default=14, space="buy", optimize=True, load=True)

    lookback_left = IntParameter(5, 15, default=10, space="buy", optimize=True, load=True)
    lookback_right = IntParameter(3, 8, default=5, space="buy", optimize=True, load=True)

    rsi_oversold = IntParameter(20, 40, default=30, space="buy", optimize=True, load=True)
    rsi_overbought = IntParameter(60, 80, default=70, space="sell", optimize=True, load=True)

    divergence_strength = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy", optimize=True, load=True)
    adx_filter = BooleanParameter(default=True, space="buy", optimize=True, load=True)

    atr_multiplier = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(2.0, 4.0, default=3.0, decimals=1, space="sell", optimize=True, load=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "1h"))
        return informative_pairs

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def _find_swing_points(self, series: pd.Series, left: int, right: int) -> tuple:
        high_idx = (
            series.rolling(window=left + right + 1, center=True)
            .apply(lambda x: x.argmax() == left, raw=True)
            .astype(bool)
        )
        low_idx = (
            series.rolling(window=left + right + 1, center=True)
            .apply(lambda x: x.argmin() == left, raw=True)
            .astype(bool)
        )
        return high_idx, low_idx

    def _detect_bullish_divergence(self, close: pd.Series, rsi: pd.Series, left: int, right: int) -> pd.Series:
        _, low_idx = self._find_swing_points(close, left, right)
        _, rsi_low_idx = self._find_swing_points(rsi, left, right)

        close_lows = close[low_idx]
        rsi_lows = rsi[rsi_low_idx]

        divergence = pd.Series(False, index=close.index)

        if len(close_lows) < 2:
            return divergence

        for i in range(1, len(close_lows)):
            prev_close_low = close_lows.iloc[i - 1]
            curr_close_low = close_lows.iloc[i]
            prev_rsi_low = rsi_lows.iloc[i - 1]
            curr_rsi_low = rsi_lows.iloc[i]

            if curr_close_low < prev_close_low and curr_rsi_low > prev_rsi_low:
                divergence.iloc[close_lows.index[i]] = True

        return divergence

    def _detect_bearish_divergence(self, close: pd.Series, rsi: pd.Series, left: int, right: int) -> pd.Series:
        high_idx, _ = self._find_swing_points(close, left, right)
        rsi_high_idx, _ = self._find_swing_points(rsi, left, right)

        close_highs = close[high_idx]
        rsi_highs = rsi[rsi_high_idx]

        divergence = pd.Series(False, index=close.index)

        if len(close_highs) < 2:
            return divergence

        for i in range(1, len(close_highs)):
            prev_close_high = close_highs.iloc[i - 1]
            curr_close_high = close_highs.iloc[i]
            prev_rsi_high = rsi_highs.iloc[i - 1]
            curr_rsi_high = rsi_highs.iloc[i]

            if curr_close_high > prev_close_high and curr_rsi_high < prev_rsi_high:
                divergence.iloc[close_highs.index[i]] = True

        return divergence

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        dataframe["bullish_div"] = self._detect_bullish_divergence(
            dataframe["close"], dataframe["rsi"],
            self.lookback_left.value, self.lookback_right.value,
        )
        dataframe["bearish_div"] = self._detect_bearish_divergence(
            dataframe["close"], dataframe["rsi"],
            self.lookback_left.value, self.lookback_right.value,
        )

        rsi_diff = (dataframe["rsi"].diff(self.lookback_left.value)).abs()
        close_diff = (dataframe["close"].diff(self.lookback_left.value)).abs() / dataframe["close"]
        dataframe["div_strength"] = rsi_diff * close_diff * 100

        if self.dp:
            inf_tf = "4h"
            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=inf_tf)
            if len(informative) > 0:
                informative["rsi"] = ta.RSI(informative, timeperiod=self.rsi_period.value)
                informative["ema_200"] = ta.EMA(informative, timeperiod=200)
                informative = informative[["date", "rsi", "ema_200"]].copy()
                informative.columns = ["date", "rsi_4h", "ema_200_4h"]
                dataframe = pd.merge(dataframe, informative, on="date", how="left")
                dataframe["rsi_4h"] = dataframe["rsi_4h"].ffill()
                dataframe["ema_200_4h"] = dataframe["ema_200_4h"].ffill()
            else:
                dataframe["rsi_4h"] = dataframe["rsi"]
                dataframe["ema_200_4h"] = dataframe["ema_200"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        signals = self._load_signals()
        dataframe["signal_ta"] = 1 if signals["ta_rating"] in ("Buy", "Overweight") else (-1 if signals["ta_rating"] in ("Sell", "Underweight") else 0)
        dataframe["signal_sentiment"] = signals["sentiment_score"]
        dataframe["signal_healthy"] = 1 if signals["breaker_state"] == "HEALTHY" else 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        volume_ok = dataframe["volume"] > dataframe["volume_ma"]
        div_strong = dataframe["div_strength"] > self.divergence_strength.value

        ema_slope_ok = dataframe["ema_50"] > dataframe["ema_200"]
        rsi_4h_oversold = dataframe["rsi_4h"] < 50

        long_conditions = (
            dataframe["bullish_div"]
            & (dataframe["rsi"] < self.rsi_oversold.value)
            & volume_ok
            & div_strong
            & ema_slope_ok
            & rsi_4h_oversold
        )

        if self.adx_filter.value:
            long_conditions = long_conditions & (dataframe["adx"] > 15)

        rsi_4h_overbought = dataframe["rsi_4h"] > 50
        ema_slope_bad = dataframe["ema_50"] < dataframe["ema_200"]

        short_conditions = (
            dataframe["bearish_div"]
            & (dataframe["rsi"] > self.rsi_overbought.value)
            & volume_ok
            & div_strong
            & ema_slope_bad
            & rsi_4h_overbought
        )

        if self.adx_filter.value:
            short_conditions = short_conditions & (dataframe["adx"] > 15)

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "rsi_div_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "rsi_div_short"]

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = dataframe["bearish_div"] & (dataframe["rsi"] > 50)
        exit_short = dataframe["bullish_div"] & (dataframe["rsi"] < 50)

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "rsi_div_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "rsi_div_exit_short"]

        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.stoploss

        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)
        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle["atr"]
        except (IndexError, KeyError):
            return self.stoploss

        if pd.isna(atr_value) or atr_value <= 0:
            return self.stoploss

        stop_distance = atr_value * self.atr_multiplier.value
        if trade.is_short:
            stop_price = trade.open_rate + stop_distance
            stop_loss_pct = -((stop_price - current_rate) / current_rate)
        else:
            stop_price = trade.open_rate - stop_distance
            stop_loss_pct = -((current_rate - stop_price) / current_rate)

        return max(stop_loss_pct, self.stoploss)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs) -> Optional[Union[str, bool]]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]
        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)
        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle["atr"]
        except (IndexError, KeyError):
            return None

        if pd.isna(atr_value) or atr_value <= 0:
            return None

        if trade.is_short:
            if last_candle.get("bullish_div", False):
                return "div_reversal_short"
        else:
            if last_candle.get("bearish_div", False):
                return "div_reversal_long"

        atr_move = atr_value * self.atr_multiplier.value
        if trade.is_short:
            target_profit_pct = (atr_move * self.risk_reward.value) / current_rate
            if current_profit >= target_profit_pct:
                return f"short_tp_{self.risk_reward.value}r"
        else:
            tp_distance = atr_move * self.risk_reward.value
            tp_price = trade.open_rate + tp_distance
            if current_rate >= tp_price:
                return f"long_tp_{self.risk_reward.value}r"

        return None
