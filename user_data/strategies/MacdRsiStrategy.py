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


class MacdRsiStrategy(IStrategy, SignalBusMixin):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    minimal_roi = {
        "0": 0.25,
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

    macd_fast = IntParameter(8, 20, default=12, space="buy", optimize=True, load=True)
    macd_slow = IntParameter(20, 40, default=26, space="buy", optimize=True, load=True)
    macd_signal = IntParameter(5, 15, default=9, space="buy", optimize=True, load=True)

    rsi_buy_threshold = IntParameter(25, 45, default=35, space="buy", optimize=True, load=True)
    rsi_sell_threshold = IntParameter(55, 75, default=65, space="sell", optimize=True, load=True)

    rsi_overbought = IntParameter(70, 85, default=75, space="sell", optimize=True, load=True)
    rsi_oversold = IntParameter(15, 30, default=25, space="buy", optimize=True, load=True)

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
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value,
        )
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()

        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["dist_to_ema200"] = (dataframe["close"] - dataframe["ema_200"]) / dataframe["ema_200"]

        if self.dp:
            inf_tf = "4h"
            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=inf_tf)
            if len(informative) > 0:
                informative["rsi"] = ta.RSI(informative, timeperiod=14)
                informative["ema_200"] = ta.EMA(informative, timeperiod=200)
                informative = informative[["date", "rsi", "ema_200"]].copy()
                informative.columns = ["date", "rsi_4h", "ema_200_4h"]
                dataframe = pd.merge(dataframe, informative, on="date", how="left")
                dataframe["rsi_4h"] = dataframe["rsi_4h"].ffill()
                dataframe["ema_200_4h"] = dataframe["ema_200_4h"].ffill()
            else:
                dataframe["rsi_4h"] = dataframe["rsi"]
                dataframe["ema_200_4h"] = dataframe["ema_200"]

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
                    dataframe["btc_bullish"] = (dataframe["btc_ema_50"] > dataframe["btc_ema_200"]) & (dataframe["btc_rsi"] > 50)
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

        macd_cross_long = qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"])
        macd_cross_short = qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"])

        volume_ok = dataframe["volume"] > dataframe["volume_ma"]

        long_conditions = (
            macd_cross_long
            & volume_ok
            & (dataframe["rsi"] < self.rsi_buy_threshold.value)
            & (dataframe["rsi"] > self.rsi_oversold.value)
            & (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["adx"] > 20)
            & dataframe["btc_bullish"]
        )

        short_conditions = (
            macd_cross_short
            & volume_ok
            & (dataframe["rsi"] > self.rsi_sell_threshold.value)
            & (dataframe["rsi"] < self.rsi_overbought.value)
            & (dataframe["close"] < dataframe["ema_200"])
            & (dataframe["adx"] > 20)
        )

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "macd_rsi_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "macd_rsi_short"]

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"]) & (dataframe["rsi"] > self.rsi_overbought.value)
        exit_short = qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"]) & (dataframe["rsi"] < self.rsi_oversold.value)

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "macd_rsi_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "macd_rsi_exit_short"]

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
