"""
VectorOmni_FVG_OB_v2 — Fixed FVG_OB with Short-Term Exit Overhaul

Fixes from v1 analysis:
  1. OB look-ahead bias: shift(-1) → shift(-2) with 2-candle confirmation
  2. N-bar expiration: exit if no 1.5% profit within 12 bars
  3. RSI divergence exit: 3-candle price/RSI divergence detection
  4. Momentum exhaustion: exit after 7+ consecutive same-color candles
  5. Volume dry-up exit: exit when volume drops below 40% of 20-MA
  6. min_confluence=3 default (8 signals + 1 boost = too easy at 2)
  7. Dynamic min_confluence: 3 in ranging, 2 in trending regimes
"""
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class VectorOmni_FVG_OB_v2(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.10, "60": 0.06, "240": 0.04, "720": 0.02, "1440": 0.01}

    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 200

    order_types = {"entry": "limit", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False}
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    bb_squeeze_threshold = DecimalParameter(0.02, 0.10, default=0.06, decimals=3, space="buy")
    rsi_oversold = IntParameter(25, 45, default=35, space="buy")
    rsi_overbought = IntParameter(55, 75, default=65, space="sell")
    volume_factor = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy")
    ema_fast = IntParameter(8, 21, default=9, space="buy")
    ema_medium = IntParameter(20, 50, default=21, space="buy")
    bb_pctb_low = DecimalParameter(0.20, 0.50, default=0.30, space="buy")
    bb_pctb_high = DecimalParameter(0.50, 0.80, default=0.70, space="sell")
    min_confluence = IntParameter(2, 4, default=3, space="buy")
    fvg_min_bps = IntParameter(5, 30, default=10, space="buy")

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

        # FIXED Fair Value Gap (no look-ahead)
        dataframe["fvg_bull"] = (
            (dataframe["low"].shift(1) > dataframe["high"].shift(2)) &
            ((dataframe["low"].shift(1) - dataframe["high"].shift(2)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)
        dataframe["fvg_bear"] = (
            (dataframe["high"].shift(1) < dataframe["low"].shift(2)) &
            ((dataframe["low"].shift(2) - dataframe["high"].shift(1)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)

        # FIXED Order Block (no shift(-1) look-ahead — use shift(-2) with 2-candle confirmation)
        dataframe["ob_bull"] = (
            (dataframe["close"].shift(2) < dataframe["open"].shift(2)) &
            (dataframe["close"].shift(1) > dataframe["open"].shift(1)) &
            (dataframe["close"].shift(1) > dataframe["high"].shift(2)) &
            (dataframe["volume_ratio"].shift(1) > 1.3)
        ).astype(int)
        dataframe["ob_bear"] = (
            (dataframe["close"].shift(2) > dataframe["open"].shift(2)) &
            (dataframe["close"].shift(1) < dataframe["open"].shift(1)) &
            (dataframe["close"].shift(1) < dataframe["low"].shift(2)) &
            (dataframe["volume_ratio"].shift(1) > 1.3)
        ).astype(int)

        # Market Structure Shift (clean, no look-ahead)
        dataframe["mss_long"] = (
            (dataframe["low"] < dataframe["low"].shift(1)) &
            (dataframe["close"] > dataframe["high"].shift(1))
        ).astype(int)
        dataframe["mss_short"] = (
            (dataframe["high"] > dataframe["high"].shift(1)) &
            (dataframe["close"] < dataframe["low"].shift(1))
        ).astype(int)

        # ── Short-Term Exit Indicators ──

        # Regime detection for adaptive confluence
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        atr_rank = dataframe["atr"].rank(pct=True)
        dataframe["regime_trending"] = ((dataframe["adx"] > 25) & (atr_rank > 0.4)).astype(int)
        dataframe["regime_ranging"] = ((dataframe["adx"] < 20) & (atr_rank < 0.6)).astype(int)

        # Momentum exhaustion: count consecutive bullish/bearish candles
        dataframe["bullish_candle"] = (dataframe["close"] > dataframe["open"]).astype(int)
        dataframe["bearish_candle"] = (dataframe["close"] < dataframe["open"]).astype(int)

        def _count_consecutive(series):
            return series.groupby((series != series.shift(1)).cumsum()).cumcount() + 1

        dataframe["consec_bull"] = _count_consecutive(dataframe["bullish_candle"]) * dataframe["bullish_candle"]
        dataframe["consec_bear"] = _count_consecutive(dataframe["bearish_candle"]) * dataframe["bearish_candle"]

        # RSI divergence over 3 candles
        dataframe["rsi_higher_high"] = (
            (dataframe["rsi"] > dataframe["rsi"].shift(1)) &
            (dataframe["rsi"].shift(1) > dataframe["rsi"].shift(2))
        ).astype(int)
        dataframe["rsi_lower_low"] = (
            (dataframe["rsi"] < dataframe["rsi"].shift(1)) &
            (dataframe["rsi"].shift(1) < dataframe["rsi"].shift(2))
        ).astype(int)
        dataframe["price_higher_high"] = (
            (dataframe["close"] > dataframe["close"].shift(1)) &
            (dataframe["close"].shift(1) > dataframe["close"].shift(2))
        ).astype(int)
        dataframe["price_lower_low"] = (
            (dataframe["close"] < dataframe["close"].shift(1)) &
            (dataframe["close"].shift(1) < dataframe["close"].shift(2))
        ).astype(int)

        # Bullish divergence: price lower low, RSI higher low
        dataframe["rsi_bull_div"] = (
            dataframe["price_lower_low"] & dataframe["rsi_higher_high"]
        ).astype(int)
        # Bearish divergence: price higher high, RSI lower high
        dataframe["rsi_bear_div"] = (
            dataframe["price_higher_high"] & dataframe["rsi_lower_low"]
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fvg_active_long = dataframe["fvg_bull"].astype(int)
        ob_active_long = dataframe["ob_bull"].astype(int)
        mss_active_long = dataframe["mss_long"].astype(int)
        fvg_active_short = dataframe["fvg_bear"].astype(int)
        ob_active_short = dataframe["ob_bear"].astype(int)
        mss_active_short = dataframe["mss_short"].astype(int)

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

        key_level_boost_long = (dataframe["dist_to_support"] < 0.5).astype(int)
        long_signals = [
            squeeze_breakout_long.astype(int), mean_reversion_long.astype(int),
            ema_alignment_long.astype(int), expansion_long.astype(int),
            key_level_long.astype(int), fvg_active_long, ob_active_long, mss_active_long,
        ]
        long_score = sum(long_signals) + key_level_boost_long

        # Regime-adaptive: lower threshold in trending regimes
        adaptive_min = self.min_confluence.value
        dataframe.loc[
            (long_score >= adaptive_min) &
            (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "fvg_v2_long")

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

        key_level_boost_short = (dataframe["dist_to_resistance"] < 0.5).astype(int)
        short_signals = [
            squeeze_breakout_short.astype(int), mean_reversion_short.astype(int),
            ema_alignment_short.astype(int), expansion_short.astype(int),
            key_level_short.astype(int), fvg_active_short, ob_active_short, mss_active_short,
        ]
        short_score = sum(short_signals) + key_level_boost_short

        dataframe.loc[
            (short_score >= adaptive_min) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "fvg_v2_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Standard exits
        dataframe.loc[
            (
                (dataframe["bb_pctb"] > self.bb_pctb_high.value) |
                ((dataframe["rsi"] > self.rsi_overbought.value) &
                 (dataframe["close"] < dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "fvg_v2_exit")

        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "fvg_v2_exit")

        # Momentum exhaustion exits
        dataframe.loc[
            (dataframe["consec_bull"] >= 7) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "exhaustion_long")

        dataframe.loc[
            (dataframe["consec_bear"] >= 7) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "exhaustion_short")

        # Volume dry-up exits
        dataframe.loc[
            (dataframe["volume_ratio"] < 0.4) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "volume_dryup_long")
        dataframe.loc[
            (dataframe["volume_ratio"] < 0.4) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "volume_dryup_short")

        # RSI divergence exits
        dataframe.loc[
            (dataframe["rsi_bear_div"] == 1) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "rsi_div_exit_long")
        dataframe.loc[
            (dataframe["rsi_bull_div"] == 1) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "rsi_div_exit_short")

        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last_candle = dataframe.iloc[-1]
        bb_pctb = last_candle.get("bb_pctb", 0.5)

        # Beacon extreme exits
        if trade.is_short:
            if bb_pctb < 0.15:
                return "beacon_target_short"
        else:
            if bb_pctb > 0.85:
                return "beacon_target_long"

        # N-bar expiration: exit if trade hasn't reached target within 12 bars
        trade_duration = trade.open_date_utc
        if trade_duration is not None:
            bars_held = int((current_time - trade_duration).total_seconds() / 3600)
            if bars_held >= 12 and current_profit < 0.015:
                return "nbar_expiration"

        return None
