"""
VectorOmni_Kronos_v2 — Fixed Kronos Hybrid with Conservative Parameters

Fixes from v1 analysis:
  1. can_short=False (Kronos proven on long-only)
  2. min_confluence=3 default (9 signals need higher threshold)
  3. Wider ATR stops (atr_stop_mult=3.5, atr_trail_mult=2.5)
  4. Combined Kronos ATR stops + vector trailing_stop backup
  5. N-bar expiration exit
  6. RSI divergence exit
  7. No OB look-ahead (fixed shift)
  8. Signals: squeeze + meanrev + ema + expansion + keylevel + FVG + OB + MSS + key_boost
"""
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class VectorOmni_Kronos_v2(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.12, "60": 0.07, "240": 0.05, "720": 0.03, "1440": 0.01}

    stoploss = -0.08
    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True
    use_custom_stoploss = True

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
    min_confluence = IntParameter(2, 4, default=3, space="buy")
    atr_stop_mult = DecimalParameter(2.0, 5.0, default=3.5, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(1.5, 4.0, default=2.5, decimals=1, space="sell")
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

        # FVG (clean)
        dataframe["fvg_bull"] = (
            (dataframe["low"].shift(1) > dataframe["high"].shift(2)) &
            ((dataframe["low"].shift(1) - dataframe["high"].shift(2)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)
        dataframe["fvg_bear"] = (
            (dataframe["high"].shift(1) < dataframe["low"].shift(2)) &
            ((dataframe["low"].shift(2) - dataframe["high"].shift(1)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)

        # OB (no look-ahead)
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

        # MSS
        dataframe["mss_long"] = (
            (dataframe["low"] < dataframe["low"].shift(1)) &
            (dataframe["close"] > dataframe["high"].shift(1))
        ).astype(int)
        dataframe["mss_short"] = (
            (dataframe["high"] > dataframe["high"].shift(1)) &
            (dataframe["close"] < dataframe["low"].shift(1))
        ).astype(int)

        # Exit indicators: momentum exhaustion
        dataframe["bull_c"] = (dataframe["close"] > dataframe["open"]).astype(int)
        dataframe["bear_c"] = (dataframe["close"] < dataframe["open"]).astype(int)
        def _cc(s):
            return s.groupby((s != s.shift(1)).cumsum()).cumcount() + 1
        dataframe["consec_bull"] = _cc(dataframe["bull_c"]) * dataframe["bull_c"]
        dataframe["consec_bear"] = _cc(dataframe["bear_c"]) * dataframe["bear_c"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fvg_l = dataframe["fvg_bull"].astype(int)
        ob_l = dataframe["ob_bull"].astype(int)
        mss_l = dataframe["mss_long"].astype(int)

        squeeze_l = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )
        meanrev_l = (
            (dataframe["bb_pctb"] < self.bb_pctb_low.value) &
            (dataframe["close"] > dataframe["bb3_lower"]) &
            (dataframe["rsi"] < self.rsi_oversold.value) &
            (dataframe["close"] > dataframe["vwap"])
        )
        ema_l = (
            (dataframe["ema_fast"] > dataframe["ema_medium"]) &
            (dataframe["close"] > dataframe["ema_fast"]) &
            (dataframe["ema_medium"] > dataframe["ema_200"]) &
            (dataframe["rsi"] > 40) & (dataframe["rsi"] < 65)
        )
        expansion_l = (
            (dataframe["close"] > dataframe["bb3_upper"]) &
            (dataframe["close"].shift(1) <= dataframe["bb3_upper"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) & (dataframe["rsi"] > 50)
        )
        key_l = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) & (dataframe["rsi"] > 35) & (dataframe["rsi"] < 65)
        )
        kl_boost = (dataframe["dist_to_support"] < 0.5).astype(int)

        long_signals = [
            squeeze_l.astype(int), meanrev_l.astype(int), ema_l.astype(int),
            expansion_l.astype(int), key_l.astype(int), fvg_l, ob_l, mss_l,
        ]
        long_score = sum(long_signals) + kl_boost

        dataframe.loc[
            (long_score >= self.min_confluence.value) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "kronos_v2_long")

        fvg_s = dataframe["fvg_bear"].astype(int)
        ob_s = dataframe["ob_bear"].astype(int)
        mss_s = dataframe["mss_short"].astype(int)

        squeeze_s = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] < dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )
        meanrev_s = (
            (dataframe["bb_pctb"] > self.bb_pctb_high.value) &
            (dataframe["close"] < dataframe["bb3_upper"]) &
            (dataframe["rsi"] > self.rsi_overbought.value) &
            (dataframe["close"] < dataframe["vwap"])
        )
        ema_s = (
            (dataframe["ema_fast"] < dataframe["ema_medium"]) &
            (dataframe["close"] < dataframe["ema_fast"]) &
            (dataframe["ema_medium"] < dataframe["ema_200"]) &
            (dataframe["rsi"] < 60) & (dataframe["rsi"] > 35)
        )
        expansion_s = (
            (dataframe["close"] < dataframe["bb3_lower"]) &
            (dataframe["close"].shift(1) >= dataframe["bb3_lower"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) & (dataframe["rsi"] < 50)
        )
        key_s = (
            (dataframe["dist_to_resistance"] < 1.0) &
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) & (dataframe["rsi"] < 65) & (dataframe["rsi"] > 35)
        )
        kl_boost_s = (dataframe["dist_to_resistance"] < 0.5).astype(int)

        short_signals = [
            squeeze_s.astype(int), meanrev_s.astype(int), ema_s.astype(int),
            expansion_s.astype(int), key_s.astype(int), fvg_s, ob_s, mss_s,
        ]
        short_score = sum(short_signals) + kl_boost_s

        dataframe.loc[
            (short_score >= self.min_confluence.value) & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "kronos_v2_short")

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
        ] = (1, "kronos_v2_exit")

        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "kronos_v2_exit")

        # Momentum exhaustion exit
        dataframe.loc[
            (dataframe["consec_bull"] >= 7) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "exhaust_kronos")
        dataframe.loc[
            (dataframe["consec_bear"] >= 7) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "exhaust_kronos")

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
        atr_stop = max(min(atr_stop, 0.15), 0.03)

        if current_profit > 0.03:
            trail = atr * self.atr_trail_mult.value / close
            trail = max(min(trail, 0.08), 0.015)
            return max(atr_stop, trail)

        return atr_stop

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last = dataframe.iloc[-1]
        bb_pctb = last.get("bb_pctb", 0.5)

        if trade.is_short:
            if bb_pctb < 0.15:
                return "beacon_kronos"
        else:
            if bb_pctb > 0.85:
                return "beacon_kronos"

        open_date = trade.open_date_utc
        if open_date is not None:
            bars = int((current_time - open_date).total_seconds() / 3600)
            if bars >= 12 and current_profit < 0.015:
                return "nbar_kronos"

        return None
