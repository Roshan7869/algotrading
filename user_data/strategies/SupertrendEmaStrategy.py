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


class SupertrendEmaStrategy(IStrategy, SignalBusMixin):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    minimal_roi = {
        "0": 0.20,
        "120": 0.10,
        "360": 0.05,
        "720": 0.02,
    }

    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.06
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count: int = 100

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    supertrend_period = IntParameter(7, 14, default=10, space="buy", optimize=True, load=True)
    supertrend_multiplier = DecimalParameter(1.5, 4.0, default=3.0, decimals=1, space="buy", optimize=True, load=True)
    ema_fast_period = IntParameter(10, 30, default=20, space="buy", optimize=True, load=True)
    ema_slow_period = IntParameter(100, 250, default=200, space="buy", optimize=True, load=True)
    adx_threshold = IntParameter(15, 30, default=20, space="buy", optimize=True, load=True)
    atr_multiplier = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "1h"))
        return informative_pairs

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def supertrend(self, dataframe: DataFrame, period: int = 10, multiplier: float = 3.0) -> DataFrame:
        hl2 = (dataframe["high"] + dataframe["low"]) / 2
        atr = ta.ATR(dataframe, timeperiod=period)
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)

        supertrend = np.full(len(dataframe), np.nan)
        direction = np.full(len(dataframe), 1)

        for i in range(period, len(dataframe)):
            prev_upper = upper_band.iloc[i - 1]
            prev_lower = lower_band.iloc[i - 1]

            if pd.isna(supertrend[i - 1]):
                supertrend[i] = upper_band.iloc[i]
                direction[i] = -1
            elif direction[i - 1] == 1:
                if dataframe["close"].iloc[i] < prev_lower:
                    direction[i] = -1
                    supertrend[i] = prev_lower
                else:
                    supertrend[i] = max(upper_band.iloc[i], prev_lower)
                    direction[i] = 1
            else:
                if dataframe["close"].iloc[i] > prev_upper:
                    direction[i] = 1
                    supertrend[i] = prev_upper
                else:
                    supertrend[i] = min(lower_band.iloc[i], prev_upper)
                    direction[i] = -1

        dataframe["supertrend"] = supertrend
        dataframe["supertrend_direction"] = direction
        dataframe["supertrend_up"] = direction == 1
        dataframe["supertrend_down"] = direction == -1
        dataframe["supertrend_turn_up"] = (direction == 1) & (pd.Series(direction).shift(1) == -1)
        dataframe["supertrend_turn_down"] = (direction == -1) & (pd.Series(direction).shift(1) == 1)

        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.supertrend(dataframe, self.supertrend_period.value, self.supertrend_multiplier.value)

        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast_period.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow_period.value)
        dataframe["ema_slope"] = dataframe["ema_fast"] - dataframe["ema_fast"].shift(5)

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()

        if self.dp:
            inf_tf = "4h"
            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=inf_tf)
            if len(informative) > 0:
                informative = self.supertrend(informative, self.supertrend_period.value, self.supertrend_multiplier.value)
                informative["ema_fast_4h"] = ta.EMA(informative, timeperiod=self.ema_fast_period.value)
                informative = informative[["date", "supertrend_direction", "ema_fast_4h"]].copy()
                informative.columns = ["date", "st_direction_4h", "ema_fast_4h"]
                dataframe = pd.merge(dataframe, informative, on="date", how="left")
                dataframe["st_direction_4h"] = dataframe["st_direction_4h"].ffill()
                dataframe["ema_fast_4h"] = dataframe["ema_fast_4h"].ffill()
            else:
                dataframe["st_direction_4h"] = 1
                dataframe["ema_fast_4h"] = dataframe["ema_fast"]

        if self.dp and metadata["pair"] != "BTC/USDT:USDT":
            try:
                btc_data = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1h")
                if len(btc_data) > 0:
                    btc_data = self.supertrend(btc_data, self.supertrend_period.value, self.supertrend_multiplier.value)
                    btc_data["ema_50"] = ta.EMA(btc_data, timeperiod=50)
                    btc_data = btc_data[["date", "supertrend_direction", "ema_50"]].copy()
                    btc_data.columns = ["date", "btc_st_direction", "btc_ema_50"]
                    dataframe = pd.merge(dataframe, btc_data, on="date", how="left")
                    dataframe["btc_st_direction"] = dataframe["btc_st_direction"].ffill().fillna(1)
                    dataframe["btc_ema_50"] = dataframe["btc_ema_50"].ffill()
                    dataframe["btc_bullish"] = dataframe["btc_st_direction"] == 1
                else:
                    dataframe["btc_bullish"] = True
            except Exception:
                dataframe["btc_bullish"] = True
        else:
            dataframe["btc_bullish"] = True

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
        trend_ok = dataframe["adx"] > self.adx_threshold.value
        mtf_ok = dataframe["st_direction_4h"] == 1

        ema_aligned = (dataframe["ema_fast"] > dataframe["ema_slow"]) & (dataframe["ema_slope"] > 0)
        ema_cross_down = (dataframe["ema_fast"] < dataframe["ema_slow"]) & (dataframe["ema_slope"] < 0)

        long_conditions = (
            dataframe["supertrend_turn_up"]
            & volume_ok
            & trend_ok
            & mtf_ok
            & ema_aligned
            & (dataframe["close"] > dataframe["ema_slow"])
            & dataframe["btc_bullish"]
        )

        short_conditions = (
            dataframe["supertrend_turn_down"]
            & volume_ok
            & trend_ok
            & (dataframe["st_direction_4h"] == -1)
            & ema_cross_down
            & (dataframe["close"] < dataframe["ema_slow"])
        )

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "supertrend_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "supertrend_short"]

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = dataframe["supertrend_turn_down"]
        exit_short = dataframe["supertrend_turn_up"]

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "st_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "st_exit_short"]

        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        if trade.is_short and last_candle.get("supertrend_up", False):
            return -0.005
        if not trade.is_short and last_candle.get("supertrend_down", False):
            return -0.005

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

        atr_move = atr_value * self.atr_multiplier.value

        if trade.is_short:
            if last_candle.get("supertrend_up", False):
                return "st_reversal_short"
            target_profit_pct = (atr_move * self.risk_reward.value) / current_rate
            if current_profit >= target_profit_pct:
                return f"short_tp_{self.risk_reward.value}r"
        else:
            if last_candle.get("supertrend_down", False):
                return "st_reversal_long"
            tp_distance = atr_move * self.risk_reward.value
            tp_price = trade.open_rate + tp_distance
            if current_rate >= tp_price:
                return f"long_tp_{self.risk_reward.value}r"

        return None
