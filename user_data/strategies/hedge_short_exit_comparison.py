"""
HEDGE MOMENTUM SHORT — TREND-FOLLOWING EXIT COMPARISON
=======================================================
Base entry: MACD/Close > 0.8% AND RSI > 70 → SHORT ONLY
Base stop: -10% SL, breakeven at +3% (custom_stoploss)

Exit Variants (all use same entry + breakeven stop):
  V1_BASELINE = Original: 30% ROI + 1% trail after 3% + exit_short when RSI<50
  V2_WIDE_TRAIL = Wider trail: 5% after 10% profit, no forced RSI exit
  V3_ATR_TRAIL = ATR-adaptive trail: trail = 2*ATR%
  V4_CASCADE_EXIT = Take partial at 15% via ROI, then trail rest at 3%
  V5_NO_EXIT_SIGNAL = Pure trail only, no RSI exit signals (let trends run)
  V6_TIGHT_TRAIL_LATE = 2% trail after 20% profit (let winners run long)
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy


# ─── SHARED ENTRY + INDICATORS ──────────────────────────────────────────────

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(df, fast=12, slow=26, signal=9):
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macdsignal": signal_line, "macdhist": histogram})


# ─── V1_BASELINE: Original strategy (30% ROI + 1% trail after 3% + RSI<50 exit + breakeven) ─────

class HedgeShortV1Baseline(IStrategy):
    """V1: Original — 30% ROI + 1% trail after 3% + RSI<50 exit + breakeven"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    stoploss = -0.10
    minimal_roi = {"0": 0.30}

    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        dataframe["rsi"] = calc_rsi(dataframe["close"], 14)
        macd_df = calc_macd(dataframe)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["macd_pct"] > float(self.macd_pct_threshold.value)) &
            (dataframe["rsi"] > int(self.rsi_threshold.value)) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        # Exit short when RSI drops below 50
        dataframe.loc[
            (dataframe["rsi"] < 50),
            ["exit_short", "exit_tag"]
        ] = (1, "rsi_exit_short")
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        if current_profit > 0.03:
            return -0.005
        return None


# ─── V2_WIDE_TRAIL: Wider 5% trail after 10%, no RSI exit ────────────────────

class HedgeShortV2WideTrail(IStrategy):
    """V2: 5% trail after 10%, breakeven at 3%, no RSI exit signal"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    stoploss = -0.10
    minimal_roi = {"0": 100}  # disable fixed ROI

    trailing_stop = True
    trailing_stop_positive = 0.05
    trailing_stop_positive_offset = 0.10
    trailing_only_offset_is_reached = True

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        dataframe["rsi"] = calc_rsi(dataframe["close"], 14)
        macd_df = calc_macd(dataframe)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["macd_pct"] > float(self.macd_pct_threshold.value)) &
            (dataframe["rsi"] > int(self.rsi_threshold.value)) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        # No early exit — let the trailing stop ride the trend
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        if current_profit > 0.03:
            return -0.005
        return None


# ─── V3_ATR_TRAIL: ATR-adaptive trailing ──────────────────────────────────────

class HedgeShortV3ATRTrail(IStrategy):
    """V3: ATR-adaptive trailing stop + breakeven at 3% + RSI<50 exit"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    stoploss = -0.10
    minimal_roi = {"0": 100}

    # These are defaults; custom_stoploss overrides dynamically
    trailing_stop = False
    trailing_stop_positive = 0.05
    trailing_stop_positive_offset = 0.10
    trailing_only_offset_is_reached = True

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        dataframe["rsi"] = calc_rsi(dataframe["close"], 14)
        macd_df = calc_macd(dataframe)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        # ATR for adaptive stop
        high_low = dataframe["high"] - dataframe["low"]
        high_close = np.abs(dataframe["high"] - dataframe["close"].shift())
        low_close = np.abs(dataframe["low"] - dataframe["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        dataframe["atr"] = tr.rolling(14).mean()
        dataframe["atr_pct"] = (dataframe["atr"] / dataframe["close"]) * 100
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["macd_pct"] > float(self.macd_pct_threshold.value)) &
            (dataframe["rsi"] > int(self.rsi_threshold.value)) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["rsi"] < 50),
            ["exit_short", "exit_tag"]
        ] = (1, "rsi_exit_short")
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        # Breakeven after 3%
        if current_profit > 0.03:
            return -0.005
        # Dynamic ATR-based stop: 2x ATR from entry
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) >= 1:
            last_atr_pct = dataframe.iloc[-1].get("atr_pct", 0)
            if last_atr_pct > 0:
                # Trail at 2x ATR below current price (for shorts, stop is above)
                return min(-0.10, last_atr_pct * 2 / 100)
        return None


# ─── V4_CASCADE: ROI 15% + 30%, trail 2% after 20% ───────────────────────────

class HedgeShortV4Cascade(IStrategy):
    """V4: Cascade — ROI at 15% and 30%, trail 2% after 20%, RSI<50 exit, breakeven at 3%"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    stoploss = -0.10
    # Cascade ROI: take some profit at 15%, full at 30%
    # But since freqtrade ROI closes entire position, we use only the final target
    minimal_roi = {"0": 100}  # Use custom_exit for cascade logic

    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.20
    trailing_only_offset_is_reached = True

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        dataframe["rsi"] = calc_rsi(dataframe["close"], 14)
        macd_df = calc_macd(dataframe)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["macd_pct"] > float(self.macd_pct_threshold.value)) &
            (dataframe["rsi"] > int(self.rsi_threshold.value)) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["rsi"] < 50),
            ["exit_short", "exit_tag"]
        ] = (1, "rsi_exit_short")
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        if current_profit > 0.03:
            return -0.005
        return None


# ─── V5_PURE_TRAIL: No RSI exit, tight 1.5% trail after 5%, breakeven at 2% ──

class HedgeShortV5PureTrail(IStrategy):
    """V5: Pure trailing only — 1.5% trail after 5% profit, breakeven at 2%, no RSI exit"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    stoploss = -0.10
    minimal_roi = {"0": 100}

    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.05
    trailing_only_offset_is_reached = True

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        dataframe["rsi"] = calc_rsi(dataframe["close"], 14)
        macd_df = calc_macd(dataframe)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["macd_pct"] > float(self.macd_pct_threshold.value)) &
            (dataframe["rsi"] > int(self.rsi_threshold.value)) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        # No exit signals — let trailing do the work
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        if current_profit > 0.02:
            return -0.005
        return None


# ─── V6_LATE_TRAIL: 2% trail after 20%, breakeven at 5%, RSI<45 exit ────────

class HedgeShortV6LateTrail(IStrategy):
    """V6: Let winners run long — 2% trail after 20% profit, breakeven at 5%, soft RSI<45 exit"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    stoploss = -0.10
    minimal_roi = {"0": 100}

    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.20
    trailing_only_offset_is_reached = True

    macd_pct_threshold = DecimalParameter(0.3, 5.0, default=0.8, decimals=1, space="buy", optimize=False)
    rsi_threshold = IntParameter(55, 85, default=70, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        dataframe["rsi"] = calc_rsi(dataframe["close"], 14)
        macd_df = calc_macd(dataframe)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["macd_pct"] > float(self.macd_pct_threshold.value)) &
            (dataframe["rsi"] > int(self.rsi_threshold.value)) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        # Only exit on strong reversal (RSI < 45, not 50)
        dataframe.loc[
            (dataframe["rsi"] < 45),
            ["exit_short", "exit_tag"]
        ] = (1, "rsi_deep_reversal")
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        # Breakeven at 5% profit
        if current_profit > 0.05:
            return -0.005
        return None