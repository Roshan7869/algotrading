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


class EmaTrendFollowing(IStrategy, SignalBusMixin):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    minimal_roi = {
        "0": 0.35,
        "120": 0.20,
        "360": 0.10,
        "720": 0.05,
        "1440": 0.02,
    }

    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.03
    trailing_stop_positive_offset = 0.08
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count: int = 200

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    ema_fast = IntParameter(5, 15, default=9, space="buy", optimize=True, load=True)
    ema_medium = IntParameter(15, 30, default=21, space="buy", optimize=True, load=True)
    ema_slow = IntParameter(40, 60, default=50, space="buy", optimize=True, load=True)
    ema_trend = IntParameter(150, 250, default=200, space="buy", optimize=True, load=True)

    adx_threshold = IntParameter(20, 35, default=25, space="buy", optimize=True, load=True)
    ema_slope_period = IntParameter(3, 10, default=5, space="buy", optimize=True, load=True)

    atr_multiplier = DecimalParameter(1.5, 3.5, default=2.0, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.5, decimals=1, space="sell", optimize=True, load=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "1h"))
        return informative_pairs

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        dataframe["ema_trend_line"] = ta.EMA(dataframe, timeperiod=self.ema_trend.value)

        dataframe["ema_slope"] = dataframe["ema_slow"] - dataframe["ema_slow"].shift(self.ema_slope_period.value)
        dataframe["dist_to_trend"] = (dataframe["close"] - dataframe["ema_trend_line"]) / dataframe["ema_trend_line"]

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()

        if self.dp:
            inf_tf = "4h"
            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=inf_tf)
            if len(informative) > 0:
                ema_slow = ta.EMA(informative, timeperiod=self.ema_slow.value)
                informative["ema_slow"] = ema_slow
                informative["ema_slope"] = ema_slow - ema_slow.shift(self.ema_slope_period.value)
                informative = informative[["date", "ema_slow", "ema_slope"]].copy()
                dataframe = merge_informative_pair(
                    dataframe, informative, self.timeframe, inf_tf, ffill=True
                )
            else:
                dataframe["ema_slow_4h"] = dataframe["ema_slow"]
                dataframe["ema_slope_4h"] = dataframe["ema_slope"]

        if self.dp and metadata["pair"] != "BTC/USDT:USDT":
            try:
                btc_data = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1h")
                if len(btc_data) > 0:
                    btc_data["ema_50"] = ta.EMA(btc_data, timeperiod=50)
                    btc_data["ema_200"] = ta.EMA(btc_data, timeperiod=200)
                    btc_data["rsi"] = ta.RSI(btc_data, timeperiod=14)
                    btc_data = btc_data[["date", "ema_50", "ema_200", "rsi"]].copy()
                    btc_data.columns = ["date", "btc_ema_50", "btc_ema_200", "btc_rsi"]
                    dataframe = pd.merge(dataframe, btc_data, on="date", how="left")
                    dataframe["btc_ema_50"] = dataframe["btc_ema_50"].ffill()
                    dataframe["btc_ema_200"] = dataframe["btc_ema_200"].ffill()
                    dataframe["btc_rsi"] = dataframe["btc_rsi"].fillna(50)
                    dataframe["btc_bullish"] = (dataframe["btc_ema_50"] > dataframe["btc_ema_200"])
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

        golden_cross = qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
        death_cross = qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_slow"])

        fast_over_medium = dataframe["ema_fast"] > dataframe["ema_medium"]
        fast_under_medium = dataframe["ema_fast"] < dataframe["ema_medium"]
        slope_up = dataframe["ema_slope"] > 0
        slope_down = dataframe["ema_slope"] < 0

        mtf_bullish = (dataframe["close"] > dataframe["ema_slow_4h"]) & (dataframe["ema_slope_4h"] > 0)
        mtf_bearish = (dataframe["close"] < dataframe["ema_slow_4h"]) & (dataframe["ema_slope_4h"] < 0)

        long_conditions = (
            (golden_cross | (fast_over_medium & slope_up))
            & volume_ok
            & trend_ok
            & mtf_bullish
            & (dataframe["close"] > dataframe["ema_trend_line"])
            & (dataframe["rsi"] < 70)
            & dataframe["btc_bullish"]
        )

        short_conditions = (
            (death_cross | (fast_under_medium & slope_down))
            & volume_ok
            & trend_ok
            & mtf_bearish
            & (dataframe["close"] < dataframe["ema_trend_line"])
            & (dataframe["rsi"] > 30)
        )

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "ema_trend_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "ema_trend_short"]

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_medium"]) & (dataframe["adx"] < 20)
        exit_short = qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_medium"]) & (dataframe["adx"] < 20)

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "ema_trend_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "ema_trend_exit_short"]

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
            target_profit_pct = (atr_move * self.risk_reward.value) / current_rate
            if current_profit >= target_profit_pct:
                return f"short_tp_{self.risk_reward.value}r"
        else:
            tp_distance = atr_move * self.risk_reward.value
            tp_price = trade.open_rate + tp_distance
            if current_rate >= tp_price:
                return f"long_tp_{self.risk_reward.value}r"

        return None
