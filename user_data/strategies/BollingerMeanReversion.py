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


class BollingerMeanReversion(IStrategy, SignalBusMixin):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    minimal_roi = {
        "0": 0.15,
        "60": 0.08,
        "240": 0.04,
        "720": 0.02,
    }

    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.05
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

    bb_period = IntParameter(15, 30, default=20, space="buy", optimize=True, load=True)
    bb_std = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="buy", optimize=True, load=True)
    rsi_oversold = IntParameter(20, 40, default=30, space="buy", optimize=True, load=True)
    rsi_overbought = IntParameter(60, 80, default=70, space="sell", optimize=True, load=True)
    bb_width_min = DecimalParameter(0.02, 0.08, default=0.04, decimals=3, space="buy", optimize=True, load=True)
    bb_width_max = DecimalParameter(0.10, 0.30, default=0.20, decimals=2, space="buy", optimize=True, load=True)
    ema_trend_period = IntParameter(50, 200, default=100, space="buy", optimize=True, load=True)
    atr_multiplier = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "1h"))
        return informative_pairs

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe),
            window=self.bb_period.value,
            stds=self.bb_std.value,
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_width"] = (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]
        dataframe["bb_lower_distance"] = (dataframe["close"] - dataframe["bb_lowerband"]) / dataframe["bb_lowerband"]
        dataframe["bb_upper_distance"] = (dataframe["close"] - dataframe["bb_upperband"]) / dataframe["bb_upperband"]

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=14, fastk_period=5, fastd_period=3)
        dataframe["stoch_rsi_k"] = stoch_rsi["fastk"]
        dataframe["stoch_rsi_d"] = stoch_rsi["fastd"]

        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend_period.value)

        if self.dp and metadata["pair"] != "BTC/USDT:USDT":
            try:
                btc_data = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1h")
                if len(btc_data) > 0:
                    btc_data["ema_50"] = ta.EMA(btc_data, timeperiod=50)
                    btc_data["ema_200"] = ta.EMA(btc_data, timeperiod=200)
                    btc_data = btc_data[["date", "ema_50", "ema_200"]].copy()
                    btc_data.columns = ["date", "btc_ema_50", "btc_ema_200"]
                    dataframe = pd.merge(dataframe, btc_data, on="date", how="left")
                    dataframe["btc_ema_50"] = dataframe["btc_ema_50"].ffill()
                    dataframe["btc_ema_200"] = dataframe["btc_ema_200"].ffill()
                    dataframe["btc_trend_up"] = dataframe["btc_ema_50"] > dataframe["btc_ema_200"]
                else:
                    dataframe["btc_trend_up"] = True
            except Exception:
                dataframe["btc_trend_up"] = True
        else:
            dataframe["btc_trend_up"] = True

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
        bb_width_ok = (dataframe["bb_width"] > self.bb_width_min.value) & (dataframe["bb_width"] < self.bb_width_max.value)

        touch_lower = dataframe["close"] <= dataframe["bb_lowerband"] * 1.005
        touch_upper = dataframe["close"] >= dataframe["bb_upperband"] * 0.995

        stoch_rsi_oversold = dataframe["stoch_rsi_k"] < 20
        stoch_rsi_overbought = dataframe["stoch_rsi_k"] > 80

        trend_up = dataframe["close"] > dataframe["ema_trend"]
        trend_down = dataframe["close"] < dataframe["ema_trend"]

        long_conditions = (
            touch_lower
            & (dataframe["rsi"] < self.rsi_oversold.value)
            & bb_width_ok
            & volume_ok
            & trend_up
            & dataframe["btc_trend_up"]
        )

        short_conditions = (
            touch_upper
            & (dataframe["rsi"] > self.rsi_overbought.value)
            & bb_width_ok
            & volume_ok
            & trend_down
        )

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "bb_mean_rev_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "bb_mean_rev_short"]

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = (dataframe["close"] >= dataframe["bb_middleband"]) | (dataframe["rsi"] > 50)
        exit_short = (dataframe["close"] <= dataframe["bb_middleband"]) | (dataframe["rsi"] < 50)

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "bb_reversion_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "bb_reversion_exit_short"]

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
