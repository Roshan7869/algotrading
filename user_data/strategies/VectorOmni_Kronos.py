"""
VectorOmni_Kronos — Ultimate Hybrid: Kronos ATR Dynamic Stoploss + FVG/OB/MSS + Key Level Boost

Combines:
  1. Kronos_RiskManaged — ATR-based dynamic stoploss, 5-base signal confluence, beacon exit
  2. VectorOmni_FVG_OB  — Fair Value Gap (FVG), Order Block (OB), Market Structure Shift (MSS)
  3. P3E_KEY_LEVEL_BOOST — Key level proximity boost (+1 confluence when dist_to_support < 0.5)

Architecture:
  - 8 signal types + key_level_boost = 9 max confluence points
  - ATR dynamic stoploss (wider for volatile, tighter for calm)
  - ATR trailing once in profit (3%+)
  - Beacon target exit (BB %b extremes)
  - min_confluence=2 default (matching P1 optimal)
  - can_short=True (fully symmetric long/short)

Sources:
  - Kronos_RiskManaged: user_data/strategies/kronos_chromadb/Kronos_RiskManaged.py
  - VectorOmni_FVG_OB:  user_data/strategies/VectorOmni_FVG_OB.py
  - P3E_KEY_LEVEL_BOOST: user_data/strategies/VectorStrategy_P3E_KEY_LEVEL_BOOST.py
"""
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class VectorOmni_Kronos(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short: bool = True  # Fully symmetric long/short

    # ── Stoploss: ATR dynamic (overridden in custom_stoploss) ──
    stoploss = -0.06  # fallback
    trailing_stop = False        # ATR handles trailing dynamically
    use_custom_stoploss = True

    # ── ROI ──
    minimal_roi = {"0": 0.15, "60": 0.08, "240": 0.05, "720": 0.03, "1440": 0.01}

    process_only_new_candles = True
    startup_candle_count: int = 200
    order_types = {"entry": "limit", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False}
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ── Hyperopt Parameters ──
    bb_squeeze_threshold = DecimalParameter(0.02, 0.10, default=0.06, decimals=3, space="buy")
    rsi_oversold = IntParameter(25, 45, default=40, space="buy")
    rsi_overbought = IntParameter(55, 75, default=60, space="sell")
    volume_factor = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy")
    ema_fast = IntParameter(8, 21, default=9, space="buy")
    ema_medium = IntParameter(20, 50, default=21, space="buy")
    bb_pctb_low = DecimalParameter(0.20, 0.50, default=0.40, decimals=2, space="buy")
    bb_pctb_high = DecimalParameter(0.50, 0.80, default=0.60, decimals=2, space="sell")
    min_confluence = IntParameter(1, 3, default=2, space="buy")
    # ATR risk params
    atr_stop_mult = DecimalParameter(1.5, 4.0, default=2.5, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="sell")
    # FVG params
    fvg_min_bps = IntParameter(5, 30, default=10, space="buy")

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3, max_leverage)

    def informative_pairs(self):
        return []

    # ═══════════════════════════════════════════════════════════
    # INDICATORS — 3 layers: Base + Kronos ATR + SMC (FVG/OB/MSS)
    # ═══════════════════════════════════════════════════════════
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ── Layer 1: Base Indicators (BBands, EMAs, RSI, Volume, VWAP, Pivots) ──
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

        # ── Layer 2: ATR + Key Levels (Kronos Risk Management) ──
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = ((typical_price * dataframe["volume"]).rolling(20).sum()
                             / dataframe["volume"].rolling(20).sum()).bfill()
        dataframe["pivot_high"] = dataframe["high"].rolling(5, center=True).max()
        dataframe["pivot_low"] = dataframe["low"].rolling(5, center=True).min()
        dataframe["dist_to_resistance"] = ((dataframe["pivot_high"] - dataframe["close"]) / dataframe["atr"]).fillna(5)
        dataframe["dist_to_support"] = ((dataframe["close"] - dataframe["pivot_low"]) / dataframe["atr"]).fillna(5)

        # ── Layer 3: SMC Concepts (FVG + OB + MSS from VectorOmni_FVG_OB) ──
        # Fair Value Gap (ICT)
        dataframe["fvg_bull"] = (
            (dataframe["low"].shift(1) > dataframe["high"].shift(2)) &
            ((dataframe["low"].shift(1) - dataframe["high"].shift(2)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)
        dataframe["fvg_bear"] = (
            (dataframe["high"].shift(1) < dataframe["low"].shift(2)) &
            ((dataframe["low"].shift(2) - dataframe["high"].shift(1)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)

        # Order Block (ICT)
        dataframe["ob_bull"] = (
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["close"].shift(-1) > dataframe["open"].shift(-1)) &
            (dataframe["close"].shift(-1) > dataframe["high"]) &
            (dataframe["volume_ratio"] > 1.3)
        ).astype(int)
        dataframe["ob_bear"] = (
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["close"].shift(-1) < dataframe["open"].shift(-1)) &
            (dataframe["close"].shift(-1) < dataframe["low"]) &
            (dataframe["volume_ratio"] > 1.3)
        ).astype(int)

        # Market Structure Shift
        dataframe["mss_long"] = (
            (dataframe["low"] < dataframe["low"].shift(1)) &
            (dataframe["close"] > dataframe["high"].shift(1))
        ).astype(int)
        dataframe["mss_short"] = (
            (dataframe["high"] > dataframe["high"].shift(1)) &
            (dataframe["close"] < dataframe["low"].shift(1))
        ).astype(int)

        # Zigzag swing points for structure
        dataframe["swing_high"] = (
            (dataframe["high"] > dataframe["high"].shift(1)) &
            (dataframe["high"] > dataframe["high"].shift(2)) &
            (dataframe["high"] >= dataframe["high"].shift(-1)) &
            (dataframe["high"] >= dataframe["high"].shift(-2))
        ).astype(int)
        dataframe["swing_low"] = (
            (dataframe["low"] < dataframe["low"].shift(1)) &
            (dataframe["low"] < dataframe["low"].shift(2)) &
            (dataframe["low"] <= dataframe["low"].shift(-1)) &
            (dataframe["low"] <= dataframe["low"].shift(-2))
        ).astype(int)

        return dataframe

    # ═══════════════════════════════════════════════════════════
    # ENTRY — 8 signals + key_level_boost = 9 max confluence
    # ═══════════════════════════════════════════════════════════
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # ═══ LONG ═══

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
        # SMC signals
        fvg_active_long = dataframe["fvg_bull"].astype(int)
        ob_active_long = dataframe["ob_bull"].astype(int)
        mss_active_long = dataframe["mss_long"].astype(int)

        key_level_boost_long = (dataframe["dist_to_support"] < 0.5).astype(int)
        long_signals = [
            squeeze_breakout_long.astype(int), mean_reversion_long.astype(int),
            ema_alignment_long.astype(int), expansion_long.astype(int),
            key_level_long.astype(int),
            fvg_active_long, ob_active_long, mss_active_long,
        ]
        long_score = sum(long_signals) + key_level_boost_long

        dataframe.loc[
            (long_score >= self.min_confluence.value) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "omni_kronos_long")

        # ═══ SHORT ═══

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
        # SMC signals
        fvg_active_short = dataframe["fvg_bear"].astype(int)
        ob_active_short = dataframe["ob_bear"].astype(int)
        mss_active_short = dataframe["mss_short"].astype(int)

        key_level_boost_short = (dataframe["dist_to_resistance"] < 0.5).astype(int)
        short_signals = [
            squeeze_breakout_short.astype(int), mean_reversion_short.astype(int),
            ema_alignment_short.astype(int), expansion_short.astype(int),
            key_level_short.astype(int),
            fvg_active_short, ob_active_short, mss_active_short,
        ]
        short_score = sum(short_signals) + key_level_boost_short

        dataframe.loc[
            (short_score >= self.min_confluence.value) & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "omni_kronos_short")

        return dataframe

    # ═══════════════════════════════════════════════════════════
    # EXIT — BB %b Beacon Targets + width expansion stop
    # ═══════════════════════════════════════════════════════════
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["bb_pctb"] > self.bb_pctb_high.value) |
                ((dataframe["rsi"] > self.rsi_overbought.value) &
                 (dataframe["close"] < dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "omni_kronos_exit")

        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "omni_kronos_exit")
        return dataframe

    # ═══════════════════════════════════════════════════════════
    # CUSTOM STOPLOSS — ATR Dynamic (from Kronos_RiskManaged)
    # ═══════════════════════════════════════════════════════════
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> Optional[float]:
        """ATR-based dynamic stoploss: wider for volatile, tighter for calm."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 2:
            return self.stoploss

        last = dataframe.iloc[-1]
        atr = last.get("atr", 0)
        close = last.get("close", current_rate)
        if atr <= 0 or close <= 0:
            return self.stoploss

        # Base ATR stop
        atr_stop = atr * self.atr_stop_mult.value / close
        atr_stop = max(min(atr_stop, 0.12), 0.02)

        # Trail tighter once in profit
        if current_profit > 0.03:
            trail = atr * self.atr_trail_mult.value / close
            trail = max(min(trail, 0.06), 0.01)
            return max(atr_stop, trail)

        return atr_stop

    # ═══════════════════════════════════════════════════════════
    # CUSTOM EXIT — Beacon target at BB %b extremes
    # ═══════════════════════════════════════════════════════════
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
