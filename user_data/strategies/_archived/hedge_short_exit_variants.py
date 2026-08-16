"""
HEDGE MOMENTUM — SHORT ONLY — 5 EXIT VARIANTS FOR COMPARISON
=============================================================
Entry: MACD/Close > 0.8% AND RSI > 70 → SHORT ONLY
Base: -10% Stop Loss

Exit Variants:
  V1 = Fixed 30% TP (baseline)
  V2 = Trailing stop 5% after 10% offset
  V3 = ATR-based TP (3x ATR)
  V4 = MACD momentum exit (MACD% drops below 0.3%)
  V5 = RSI reversal exit (RSI drops below 50)
  V6 = Hybrid: RSI<55 OR MACD%<0.3 OR trail 5% after 15%

All share same entry logic, same stop loss = -10%
"""

from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import talib
import numpy as np


# ─── SHARED MIXIN: Entry Logic ──────────────────────────────────────────────

class MomentumEntryMixin:
    """Shared entry: MACD% > 0.8 AND RSI > 70 → SHORT"""

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = talib.RSI(dataframe["close"], timeperiod=14)
        macd_result = talib.MACD(dataframe["close"], fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd_result[0]
        dataframe["macd_signal"] = macd_result[1]
        dataframe["macd_hist"] = macd_result[2]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        dataframe["atr"] = talib.ATR(dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=14)
        dataframe["atr_pct"] = (dataframe["atr"] / dataframe["close"]) * 100
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["macd_pct"] > self.macd_pct_threshold.value) &
            (dataframe["rsi"] > self.rsi_threshold.value),
            "enter_short"
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit trend handled by custom_exit or stoploss
        return dataframe


# ─── V1: FIXED 30% TP (BASELINE) ────────────────────────────────────────────

class HedgeShortV1FixedTP(MomentumEntryMixin, IStrategy):
    """Baseline: Fixed 30% TP, 10% SL"""
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.10
    roi = {"0": 0.30}
    trailing_stop = False

    position_adjustment_enable = False


# ─── V2: TRAILING STOP (5% trail after 10% profit) ──────────────────────────

class HedgeShortV2Trail(MomentumEntryMixin, IStrategy):
    """Trailing: 5% trail after 10% offset reached"""
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.10
    roi = {"0": 100}  # disable ROI, let trailing handle exits
    trailing_stop = True
    trailing_stop_positive = 0.05
    trailing_stop_positive_offset = 0.10
    trailing_only_offset_is_reached = True

    position_adjustment_enable = False


# ─── V3: ATR-BASED TP (TP = 3x ATR) ────────────────────────────────────────

class HedgeShortV3ATRTP(MomentumEntryMixin, IStrategy):
    """ATR TP: Take profit at 3x ATR from entry, 10% SL"""
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.10
    roi = {"0": 100}  # disable fixed ROI
    trailing_stop = False

    position_adjustment_enable = False

    def custom_exit(self, pair: str, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]
        atr_pct = last_candle.get("atr_pct", 0)

        if atr_pct > 0:
            tp_pct = 3.0 * atr_pct  # 3x ATR take profit
            if current_profit >= tp_pct / 100:
                return f"atr_tp_{tp_pct:.1f}%"

        return None


# ─── V4: MACD MOMENTUM EXIT ─────────────────────────────────────────────────

class HedgeShortV4MACDExit(MomentumEntryMixin, IStrategy):
    """MACD Exit: Exit short when MACD% drops below 0.3% (momentum fading)"""
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.10
    roi = {"0": 100}
    trailing_stop = False

    position_adjustment_enable = False

    def custom_exit(self, pair: str, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]
        macd_pct = last_candle.get("macd_pct", 0)

        # Only exit if we're in profit AND MACD momentum is fading
        if current_profit > 0.02 and macd_pct < 0.3:
            return f"macd_momentum_fade_{macd_pct:.2f}%"

        return None


# ─── V5: RSI REVERSAL EXIT ───────────────────────────────────────────────────

class HedgeShortV5RSIExit(MomentumEntryMixin, IStrategy):
    """RSI Exit: Exit short when RSI drops below 50 (trend reversal confirmed)"""
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.10
    roi = {"0": 100}
    trailing_stop = False

    position_adjustment_enable = False

    def custom_exit(self, pair: str, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]
        rsi = last_candle.get("rsi", 50)

        # Only exit if we're in profit AND RSI has reversed
        if current_profit > 0.02 and rsi < 50:
            return f"rsi_reversal_{rsi:.0f}"

        return None


# ─── V6: HYBRID (RSI<55 OR MACD%<0.3 OR Trail 5% after 15%) ────────────────

class HedgeShortV6Hybrid(MomentumEntryMixin, IStrategy):
    """Hybrid: RSI<55 OR MACD%<0.3 exit + trailing 5% after 15% profit"""
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.10
    roi = {"0": 100}
    trailing_stop = True
    trailing_stop_positive = 0.05
    trailing_stop_positive_offset = 0.15
    trailing_only_offset_is_reached = True

    position_adjustment_enable = False

    def custom_exit(self, pair: str, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]
        macd_pct = last_candle.get("macd_pct", 0)
        rsi = last_candle.get("rsi", 50)

        # Exit if in profit AND (RSI reversed OR MACD momentum gone)
        if current_profit > 0.03:
            if rsi < 55:
                return f"hybrid_rsi_{rsi:.0f}"
            if macd_pct < 0.3:
                return f"hybrid_macd_{macd_pct:.2f}%"

        return None