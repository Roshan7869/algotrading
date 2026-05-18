"""Auto-generated strategy: Trading News Events — Manipulation Sweep then Continuation Trade
  ID: C015 | Tier: tier1 | Source: composed
  Components: entry: 1, exit: 1, filter: 1, risk_management: 1, market_structure: 1, psychology: 1 | Chunks: 6
"""
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import timezone
from typing import Optional, Union

from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class GenStrategy_C015(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.05, "30": 0.025, "60": 0.01}
    stoploss = -0.03
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 200

    order_types = {"entry": "limit", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False}
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    atr_multiplier = DecimalParameter(1.5, 3.5, default=2.0, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(1.5, max_leverage)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", self.timeframe))
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lower"] = bb["lower"]
        dataframe["bb_middle"] = bb["mid"]
        dataframe["bb_upper"] = bb["upper"]
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_middle"]
        dataframe["bb_pctb"] = (dataframe["close"] - dataframe["bb_lower"]) / (dataframe["bb_upper"] - dataframe["bb_lower"])
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_ma"]

        # BTC macro filter
        if self.dp and metadata.get('pair') != 'BTC/USDT:USDT':
            try:
                btc = self.dp.get_pair_dataframe("BTC/USDT:USDT", self.timeframe)
                if len(btc) > 0:
                    btc['ema_50'] = ta.EMA(btc, timeperiod=50)
                    btc['ema_200'] = ta.EMA(btc, timeperiod=200)
                    btc = btc[['date', 'ema_50', 'ema_200']].copy()
                    btc.columns = ['date', 'btc_ema_50', 'btc_ema_200']
                    dataframe = pd.merge(dataframe, btc, on='date', how='left')
                    dataframe['btc_ema_50'] = dataframe['btc_ema_50'].ffill()
                    dataframe['btc_ema_200'] = dataframe['btc_ema_200'].ffill()
                    dataframe['btc_bullish'] = dataframe['btc_ema_50'] > dataframe['btc_ema_200']
                else:
                    dataframe['btc_bullish'] = True
            except Exception:
                dataframe['btc_bullish'] = True
        else:
            dataframe['btc_bullish'] = True
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        volume_ok = dataframe["volume"] > dataframe["volume_ma"]
        trend_ok = dataframe["adx"] > 20
        above_trend = dataframe["close"] > dataframe["ema_trend"]
        below_trend = dataframe["close"] < dataframe["ema_trend"]

        # Entry: breakout
        long_conditions = (dataframe["close"] > dataframe["bb_upper"]) & (dataframe["volume"] > dataframe["volume_ma"]) & (dataframe["adx"] > 20)

        # Short:
        short_conditions = (dataframe["close"] < dataframe["bb_lower"]) & (dataframe["volume"] > dataframe["volume_ma"]) & (dataframe["adx"] > 20)

        long_conditions = long_conditions & volume_ok & trend_ok & above_trend & dataframe["btc_bullish"]
        short_conditions = short_conditions & volume_ok & trend_ok & below_trend

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "C015_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "C015_short"]
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = qtpylib.crossed_below(dataframe["close"], dataframe["ema_medium"])
        exit_short = qtpylib.crossed_above(dataframe["close"], dataframe["ema_medium"])

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "ema_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "ema_exit_short"]
        return dataframe

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
            tp_price = trade.open_rate + (atr_move * self.risk_reward.value)
            if current_rate >= tp_price:
                return f"long_tp_{self.risk_reward.value}r"
        return None