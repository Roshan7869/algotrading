"""
Kronos+ChromaDB — Full Integration.

Combines: candlestick patterns (Kronos) + session/regime filters + ATR risk management.
All ChromaDB concepts integrated into a single strategy.
"""
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

from kronos_indicators import (
    detect_candle_patterns, candle_score,
    add_session_filters, add_regime_filter,
    atr_stoploss_pct,
)


class Kronos_Full(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short: bool = False

    stoploss = -0.06
    use_custom_stoploss = True
    trailing_stop = False

    minimal_roi = {"0": 0.15, "60": 0.08, "240": 0.05, "720": 0.03, "1440": 0.01}

    process_only_new_candles = True
    startup_candle_count: int = 200
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
    candle_weight = IntParameter(0, 2, default=1, space="buy")
    allow_low_prob = IntParameter(0, 1, default=0, space="buy")
    atr_stop_mult = DecimalParameter(1.5, 4.0, default=2.5, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="sell")

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3, max_leverage)

    def informative_pairs(self):
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ── Core Bollinger ──
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

        # ── EMAs / RSI / Volume / ATR / VWAP / Pivots ──
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
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

        # ── Kronos: Candlestick Patterns ──
        dataframe = detect_candle_patterns(dataframe)
        dataframe = candle_score(dataframe)

        # ── ChromaDB: Session Filters + Regime ──
        dataframe = add_session_filters(dataframe)
        dataframe = add_regime_filter(dataframe)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ── Filters from ChromaDB ──
        session_ok = (
            (dataframe["session_high_prob"] == 1) |
            (dataframe["session_med_prob"] == 1) |
            (self.allow_low_prob.value == 1)
        )
        regime_ok = (dataframe["regime_high_vol"] == 0)
        vol_ok = (dataframe["volume_anemic"] == 0)
        filters_ok = session_ok & regime_ok & vol_ok & (dataframe["volume"] > 0)

        # ── LONG SIGNALS ──
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
            (dataframe["ema_fast"] > dataframe["ema_medium"]) &
            (dataframe["close"] > dataframe["ema_fast"]) &
            (dataframe["ema_medium"] > dataframe["ema_200"]) &
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

        candle_bullish = (dataframe["candle_signal"] > 0).astype(int)
        candle_strong = (dataframe["candle_signal"] >= 2).astype(int)

        key_level_boost_long = (dataframe["dist_to_support"] < 0.5).astype(int)
        long_signals = [
            squeeze_breakout_long.astype(int), mean_reversion_long.astype(int),
            ema_alignment_long.astype(int), expansion_long.astype(int),
            key_level_long.astype(int), candle_bullish * self.candle_weight.value,
        ]
        long_score = sum(long_signals) + key_level_boost_long + candle_strong

        dataframe.loc[
            (long_score >= self.min_confluence.value) & filters_ok,
            ["enter_long", "enter_tag"]
        ] = (1, "kronos_full_long")

        # ── SHORT SIGNALS ──
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
            (dataframe["ema_fast"] < dataframe["ema_medium"]) &
            (dataframe["close"] < dataframe["ema_fast"]) &
            (dataframe["ema_medium"] < dataframe["ema_200"]) &
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

        candle_bearish = (-dataframe["candle_signal"].clip(-1, 0)).astype(int)
        candle_strong_short = (-dataframe["candle_signal"].clip(-2, 0) >= 2).astype(int)

        key_level_boost_short = (dataframe["dist_to_resistance"] < 0.5).astype(int)
        short_signals = [
            squeeze_breakout_short.astype(int), mean_reversion_short.astype(int),
            ema_alignment_short.astype(int), expansion_short.astype(int),
            key_level_short.astype(int), candle_bearish * self.candle_weight.value,
        ]
        short_score = sum(short_signals) + key_level_boost_short + candle_strong_short

        dataframe.loc[
            (short_score >= self.min_confluence.value) & filters_ok,
            ["enter_short", "enter_tag"]
        ] = (1, "kronos_full_short")

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
        ] = (1, "kronos_exit")
        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "kronos_exit")
        return dataframe

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> Optional[float]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 2:
            return self.stoploss
        last = dataframe.iloc[-1]
        atr = last.get("atr", 0)
        close = last.get("close", current_rate)
        if atr <= 0 or close <= 0:
            return self.stoploss
        atr_stop = atr * self.atr_stop_mult.value / close
        atr_stop = max(min(atr_stop, 0.12), 0.02)
        if current_profit > 0.03:
            trail = atr * self.atr_trail_mult.value / close
            trail = max(min(trail, 0.06), 0.01)
            return max(atr_stop, trail)
        return atr_stop

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last_candle = dataframe.iloc[-1]
        bb_pctb = last_candle.get("bb_pctb", 0.5)
        if trade.is_short:
            if bb_pctb < 0.15:
                return "beacon_target_short"
        else:
            if bb_pctb > 0.85:
                return "beacon_target_long"
        return None
