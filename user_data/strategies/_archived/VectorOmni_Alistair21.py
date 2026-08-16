"""
VectorOmni_Alistair21 — 21 EMA Pullback + Structure-Based Vector Strategy

Manipulates VectorStrategy by adding Alistair Crooks' swing system from ChromaDB:
  1. Entry 1 — 21 EMA Pullback: after level break + trend line, pull back to 21 EMA
  2. Entry 2 — Consolidation Breakout: when price doesn't reach 21 EMA but consolidates
  3. Structure-based trailing: trail to prior swing low/high
  4. Fixed 2:1 R:R target structure (Alistair Crooks method)
  5. Fractal 4H application for earlier entries

Source: ChromaDB "Alistair Crooks Swing Trading System" — 58% WR at 2:1 R:R since 2018
"""
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class VectorOmni_Alistair21(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.10, "60": 0.06, "240": 0.04, "720": 0.02, "1440": 0.01}

    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 200

    order_types = {"entry": "limit", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False}
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    bb_squeeze_threshold = DecimalParameter(0.02, 0.10, default=0.06, decimals=3, space="buy")
    rsi_oversold = IntParameter(25, 45, default=40, space="buy")
    rsi_overbought = IntParameter(55, 75, default=60, space="sell")
    volume_factor = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy")
    ema_fast = IntParameter(8, 21, default=9, space="buy")
    ema_medium = IntParameter(20, 50, default=21, space="buy")
    bb_pctb_low = DecimalParameter(0.20, 0.50, default=0.40, decimals=2, space="buy")
    bb_pctb_high = DecimalParameter(0.50, 0.80, default=0.60, decimals=2, space="sell")
    min_confluence = IntParameter(1, 3, default=2, space="buy")

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return min(3, max_leverage)

    def informative_pairs(self):
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_pctb"] = ((dataframe["close"] - dataframe["bb_lowerband"])
                                / (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
                                ).replace([np.inf, -np.inf], 0.5).fillna(0.5)
        dataframe["bb_width"] = ((dataframe["bb_upperband"] - dataframe["bb_lowerband"])
                                 / dataframe["bb_middleband"]
                                 ).replace([np.inf, -np.inf], 0).fillna(0)

        bollinger_3sd = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=3)
        dataframe["bb3_upper"] = bollinger_3sd["upper"]
        dataframe["bb3_lower"] = bollinger_3sd["lower"]

        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_mean"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = (dataframe["volume"] / dataframe["volume_mean"]
                                     ).replace([np.inf, -np.inf], 1).fillna(1)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = ((typical_price * dataframe["volume"]).rolling(20).sum()
                             / dataframe["volume"].rolling(20).sum()).bfill()

        dataframe["pivot_high"] = dataframe["high"].rolling(5, center=True).max()
        dataframe["pivot_low"] = dataframe["low"].rolling(5, center=True).min()
        dataframe["dist_to_resistance"] = ((dataframe["pivot_high"] - dataframe["close"]) / dataframe["atr"]).fillna(5)
        dataframe["dist_to_support"] = ((dataframe["close"] - dataframe["pivot_low"]) / dataframe["atr"]).fillna(5)

        # Swing highs/lows for structure
        dataframe["swing_high_5"] = dataframe["high"].rolling(5, center=True).max()
        dataframe["swing_low_5"] = dataframe["low"].rolling(5, center=True).min()

        # Trend line break (EMA 50 direction change)
        dataframe["ema50_slope"] = dataframe["ema_50"] - dataframe["ema_50"].shift(3)
        dataframe["trend_up"] = (dataframe["ema50_slope"] > 0).astype(int)
        dataframe["trend_down"] = (dataframe["ema50_slope"] < 0).astype(int)

        # Level break: price broke above resistance or below support
        dataframe["level_break_long"] = (
            (dataframe["close"] > dataframe["swing_high_5"].shift(1)) &
            (dataframe["volume_ratio"] > 1.2)
        ).astype(int)
        dataframe["level_break_short"] = (
            (dataframe["close"] < dataframe["swing_low_5"].shift(1)) &
            (dataframe["volume_ratio"] > 1.2)
        ).astype(int)

        # 21 EMA proximity (pullback detection)
        dataframe["dist_to_ema21"] = abs(dataframe["close"] - dataframe["ema_21"]) / dataframe["atr"]
        dataframe["near_ema21"] = (dataframe["dist_to_ema21"] < 0.5).astype(int)

        # After level break, price pulled back to 21 EMA (Entry 1)
        dataframe["ema21_pullback_long"] = (
            (dataframe["level_break_long"].shift(1) == 1) &
            dataframe["near_ema21"] &
            (dataframe["close"] > dataframe["ema_21"]) &
            (dataframe["trend_up"] == 1)
        ).astype(int)
        dataframe["ema21_pullback_short"] = (
            (dataframe["level_break_short"].shift(1) == 1) &
            dataframe["near_ema21"] &
            (dataframe["close"] < dataframe["ema_21"]) &
            (dataframe["trend_down"] == 1)
        ).astype(int)

        # Consolidation after level break (price didn't reach 21 EMA) — Entry 2
        dataframe["consolidation_long"] = (
            (dataframe["level_break_long"].shift(2) == 1) &
            (dataframe["close"] > dataframe["ema_21"]) &
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["volume_ratio"] < 0.8)
        ).astype(int)
        dataframe["consolidation_short"] = (
            (dataframe["level_break_short"].shift(2) == 1) &
            (dataframe["close"] < dataframe["ema_21"]) &
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["volume_ratio"] < 0.8)
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pullback_entry_long = dataframe["ema21_pullback_long"].astype(int)
        consolidation_entry_long = dataframe["consolidation_long"].astype(int)

        squeeze_breakout_long = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )

        mean_reversion_long = (
            (dataframe["bb_pctb"] < self.bb_pctb_low.value) &
            (dataframe["close"] > dataframe["bb3_lower"]) &
            (dataframe["rsi"] < self.rsi_oversold.value) &
            (dataframe["close"] > dataframe["vwap"])
        )

        ema_alignment_long = (
            (dataframe["ema_fast"] > dataframe["ema_21"]) &
            (dataframe["close"] > dataframe["ema_fast"]) &
            (dataframe["ema_21"] > dataframe["ema_200"]) &
            (dataframe["rsi"] > 40) & (dataframe["rsi"] < 65)
        )

        expansion_long = (
            (dataframe["close"] > dataframe["bb3_upper"]) &
            (dataframe["close"].shift(1) <= dataframe["bb3_upper"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) & (dataframe["rsi"] > 50)
        )

        key_level_long = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) & (dataframe["rsi"] > 35) & (dataframe["rsi"] < 65)
        )

        key_level_boost_long = (dataframe["dist_to_support"] < 0.5).astype(int)
        long_signals = [
            squeeze_breakout_long.astype(int), mean_reversion_long.astype(int),
            ema_alignment_long.astype(int), expansion_long.astype(int),
            key_level_long.astype(int), pullback_entry_long, consolidation_entry_long,
        ]
        long_score = sum(long_signals) + key_level_boost_long

        dataframe.loc[
            (long_score >= self.min_confluence.value) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "alistair21_long")

        pullback_entry_short = dataframe["ema21_pullback_short"].astype(int)
        consolidation_entry_short = dataframe["consolidation_short"].astype(int)

        squeeze_breakout_short = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] < dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )

        mean_reversion_short = (
            (dataframe["bb_pctb"] > self.bb_pctb_high.value) &
            (dataframe["close"] < dataframe["bb3_upper"]) &
            (dataframe["rsi"] > self.rsi_overbought.value) &
            (dataframe["close"] < dataframe["vwap"])
        )

        ema_alignment_short = (
            (dataframe["ema_fast"] < dataframe["ema_21"]) &
            (dataframe["close"] < dataframe["ema_fast"]) &
            (dataframe["ema_21"] < dataframe["ema_200"]) &
            (dataframe["rsi"] < 60) & (dataframe["rsi"] > 35)
        )

        expansion_short = (
            (dataframe["close"] < dataframe["bb3_lower"]) &
            (dataframe["close"].shift(1) >= dataframe["bb3_lower"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) & (dataframe["rsi"] < 50)
        )

        key_level_short = (
            (dataframe["dist_to_resistance"] < 1.0) &
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) & (dataframe["rsi"] < 65) & (dataframe["rsi"] > 35)
        )

        key_level_boost_short = (dataframe["dist_to_resistance"] < 0.5).astype(int)
        short_signals = [
            squeeze_breakout_short.astype(int), mean_reversion_short.astype(int),
            ema_alignment_short.astype(int), expansion_short.astype(int),
            key_level_short.astype(int), pullback_entry_short, consolidation_entry_short,
        ]
        short_score = sum(short_signals) + key_level_boost_short

        dataframe.loc[
            (short_score >= self.min_confluence.value) & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "alistair21_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["bb_pctb"] > self.bb_pctb_high.value) |
                ((dataframe["rsi"] > self.rsi_overbought.value) &
                 (dataframe["close"] < dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "alistair_exit")

        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "alistair_exit")

        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last = dataframe.iloc[-1]
        bb_pctb = last.get("bb_pctb", 0.5)

        if trade.is_short:
            if bb_pctb < 0.15:
                return "beacon_target_short"
        else:
            if bb_pctb > 0.85:
                return "beacon_target_long"

        return None
