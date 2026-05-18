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
from vdb_mixin import VDBMixin


class DmiAdxStrategy(IStrategy, VDBMixin):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    minimal_roi = {
        "0": 0.30,
        "120": 0.15,
        "360": 0.08,
        "720": 0.04,
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

    adx_period = IntParameter(10, 20, default=14, space="buy", optimize=True, load=True)
    adx_threshold = IntParameter(20, 35, default=25, space="buy", optimize=True, load=True)
    di_threshold = IntParameter(15, 30, default=20, space="buy", optimize=True, load=True)
    adx_slope_period = IntParameter(3, 8, default=5, space="buy", optimize=True, load=True)

    rsi_filter = BooleanParameter(default=True, space="buy", optimize=True, load=True)
    rsi_overbought = IntParameter(65, 80, default=70, space="sell", optimize=True, load=True)
    rsi_oversold = IntParameter(20, 35, default=30, space="buy", optimize=True, load=True)

    atr_multiplier = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "1h"))
        return informative_pairs

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        adx = ta.ADX(dataframe, timeperiod=self.adx_period.value)
        dataframe["adx"] = adx

        plus_di = ta.PLUS_DI(dataframe, timeperiod=self.adx_period.value)
        dataframe["plus_di"] = plus_di

        minus_di = ta.MINUS_DI(dataframe, timeperiod=self.adx_period.value)
        dataframe["minus_di"] = minus_di

        dataframe["dx"] = abs(dataframe["plus_di"] - dataframe["minus_di"]) / (dataframe["plus_di"] + dataframe["minus_di"]) * 100
        dataframe["adx_slope"] = dataframe["adx"] - dataframe["adx"].shift(self.adx_slope_period.value)

        dataframe["di_cross"] = dataframe["plus_di"] - dataframe["minus_di"]
        dataframe["di_strength"] = abs(dataframe["plus_di"] - dataframe["minus_di"])

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        multi_di_threshold = self.di_threshold.value
        dataframe["trending"] = dataframe["adx"] > self.adx_threshold.value
        dataframe["plus_di_strong"] = dataframe["plus_di"] > multi_di_threshold
        dataframe["minus_di_strong"] = dataframe["minus_di"] > multi_di_threshold
        dataframe["adx_rising"] = dataframe["adx_slope"] > 0

        if self.dp:
            inf_tf = "4h"
            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=inf_tf)
            if len(informative) > 0:
                informative_adx = ta.ADX(informative, timeperiod=self.adx_period.value)
                informative["adx"] = informative_adx
                informative_pdi = ta.PLUS_DI(informative, timeperiod=self.adx_period.value)
                informative["plus_di"] = informative_pdi
                informative_mdi = ta.MINUS_DI(informative, timeperiod=self.adx_period.value)
                informative["minus_di"] = informative_mdi
                informative = informative[["date", "adx", "plus_di", "minus_di"]].copy()
                dataframe = merge_informative_pair(
                    dataframe, informative, self.timeframe, inf_tf, ffill=True
                )
            else:
                dataframe["adx_4h"] = dataframe["adx"]
                dataframe["plus_di_4h"] = dataframe["plus_di"]
                dataframe["minus_di_4h"] = dataframe["minus_di"]

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
                    dataframe["btc_bullish"] = dataframe["btc_ema_50"] > dataframe["btc_ema_200"]
                else:
                    dataframe["btc_bullish"] = True
            except Exception:
                dataframe["btc_bullish"] = True
        else:
            dataframe["btc_bullish"] = True

        # VDB runtime confidence score
        if self._vdb_is_available():
            matches = self._vdb_entry_setups(metadata["pair"], top_k=1)
            dataframe["vdb_confidence"] = matches[0]["score"] if matches else 0.5
        else:
            dataframe["vdb_confidence"] = 0.5

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        volume_ok = dataframe["volume"] > dataframe["volume_ma"]

        di_cross_up = qtpylib.crossed_above(dataframe["plus_di"], dataframe["minus_di"])
        di_cross_down = qtpylib.crossed_below(dataframe["plus_di"], dataframe["minus_di"])

        mtf_uptrend = (dataframe["plus_di_4h"] > dataframe["minus_di_4h"]) & (dataframe["adx_4h"] > self.adx_threshold.value)
        mtf_downtrend = (dataframe["minus_di_4h"] > dataframe["plus_di_4h"]) & (dataframe["adx_4h"] > self.adx_threshold.value)

        long_conditions = (
            dataframe["trending"]
            & dataframe["plus_di_strong"]
            & di_cross_up
            & volume_ok
            & dataframe["adx_rising"]
            & mtf_uptrend
            & (dataframe["rsi"] < 50 if self.rsi_filter.value else True)
            & dataframe["btc_bullish"]
        )

        short_conditions = (
            dataframe["trending"]
            & dataframe["minus_di_strong"]
            & di_cross_down
            & volume_ok
            & dataframe["adx_rising"]
            & mtf_downtrend
            & (dataframe["rsi"] > 50 if self.rsi_filter.value else True)
        )

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "dmi_adx_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "dmi_adx_short"]

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = (dataframe["adx"] < 20) | qtpylib.crossed_below(dataframe["plus_di"], dataframe["minus_di"])
        exit_short = (dataframe["adx"] < 20) | qtpylib.crossed_above(dataframe["plus_di"], dataframe["minus_di"])

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "dmi_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "dmi_exit_short"]

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

        atr_move = atr_value * self.atr_multiplier.value

        if trade.is_short:
            if last_candle.get("plus_di", 0) > last_candle.get("minus_di", 0):
                return "dmi_reversal_short"
            target_profit_pct = (atr_move * self.risk_reward.value) / current_rate
            if current_profit >= target_profit_pct:
                return f"short_tp_{self.risk_reward.value}r"
        else:
            if last_candle.get("minus_di", 0) > last_candle.get("plus_di", 0):
                return "dmi_reversal_long"
            tp_distance = atr_move * self.risk_reward.value
            tp_price = trade.open_rate + tp_distance
            if current_rate >= tp_price:
                return f"long_tp_{self.risk_reward.value}r"

        return None
