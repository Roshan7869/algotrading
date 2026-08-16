"""
HEDGE CHAMPION — P3F/P3E Key Level Boost + Tight Trail Hedge
=============================================================
Built on the project's champion strategies (VectorStrategy P3F/P3E):

  - P3E_KEY_LEVEL_BOOST: +934%/84.1%WR/0.93%DD (6yr futures)
  - P3F_KEY_LEVEL_TIGHT_TRAIL: +901%/84.8%WR/0.96%DD
  Source: batch_results_futures_6yr.json

Core Structure:
  - Capital split: 50% long, 50% short on top P2★ pairs
  - Leverage: 10x
  - Stop Loss: -10%
  - Profit Target: +30%
  - Uses P3F's key level boost + tighter trail + squeeze breakout signals

Champion Enhancements Applied:
  a) Key Level Boost: +1 confluence when dist_to_support < 0.5 (longs)
     or dist_to_resistance < 0.5 (shorts) — ChromaDB score 0.612
  b) Tighter trail: trailing_stop_positive_offset 0.03 (was 0.04)
     "Risk to Zero ASAP" concept from ChromaDB
  c) Confluence scoring with minimum 2/5 signals

Risk Mgmt (ChromaDB): P3F proven structure
  - Five signal categories: squeeze_breakout, mean_reversion,
    ema_alignment, expansion, key_level
  - +1 key_level_boost when very close to pivots
  - Minimum 2/5 confluence for entry
  - Tighter trail at +3% activates breakeven-style protection
"""

from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import (IStrategy, Trade, Order,
                                 DecimalParameter, IntParameter, informative)
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import merge_informative_pair


class HedgeChampionP3F(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = True

    # ── Stop & Target ──
    stoploss = -0.10

    # 30% profit target with P3F tighter trail
    minimal_roi = {"0": 0.30}

    # Tighter trail (P3F upgrade: 0.03 vs 0.04 base)
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 200

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ── P3F Hyperopt Parameters ──
    bb_squeeze_threshold = DecimalParameter(0.02, 0.10, default=0.06, decimals=3, space="buy")
    bb_expansion_threshold = DecimalParameter(0.85, 1.20, default=1.00, decimals=2, space="buy")
    rsi_oversold = IntParameter(25, 45, default=40, space="buy")
    rsi_overbought = IntParameter(55, 75, default=60, space="sell")
    volume_factor = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy")
    ema_fast = IntParameter(8, 21, default=9, space="buy")
    ema_medium = IntParameter(20, 50, default=21, space="buy")
    bb_pctb_low = DecimalParameter(0.20, 0.50, default=0.40, decimals=2, space="buy")
    bb_pctb_high = DecimalParameter(0.50, 0.80, default=0.60, decimals=2, space="sell")
    min_confluence = IntParameter(1, 3, default=2, space="buy")
    key_level_boost_dist = DecimalParameter(0.30, 0.70, default=0.50, decimals=2, space="buy")

    # ── Leverage ──
    def leverage(self, pair, current_time, current_rate,
                 proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(10.0, max_leverage)

    # ── Indicators (P3F champion spec) ──
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1. Bollinger Bands (20, 2)
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_pctb"] = (
            (dataframe["close"] - dataframe["bb_lowerband"])
            / (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
        ).replace([np.inf, -np.inf], 0.5).fillna(0.5)
        dataframe["bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
            / dataframe["bb_middleband"]
        ).replace([np.inf, -np.inf], 0).fillna(0)

        # 2. 3SD Bollinger Bands
        bollinger_3sd = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=3
        )
        dataframe["bb3_upper"] = bollinger_3sd["upper"]
        dataframe["bb3_lower"] = bollinger_3sd["lower"]

        # 3. EMAs
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # 4. RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # 5. Volume
        dataframe["volume_mean"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = (
            dataframe["volume"] / dataframe["volume_mean"]
        ).replace([np.inf, -np.inf], 1).fillna(1)

        # 6. ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # 7. VWAP
        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = (
            (typical_price * dataframe["volume"]).rolling(20).sum()
            / dataframe["volume"].rolling(20).sum()
        ).bfill()

        # 8. Key Level Proximity
        dataframe["pivot_high"] = dataframe["high"].rolling(5, center=True).max()
        dataframe["pivot_low"] = dataframe["low"].rolling(5, center=True).min()
        dataframe["dist_to_resistance"] = (
            (dataframe["pivot_high"] - dataframe["close"]) / dataframe["atr"]
        ).fillna(5)
        dataframe["dist_to_support"] = (
            (dataframe["close"] - dataframe["pivot_low"]) / dataframe["atr"]
        ).fillna(5)

        # 9. Top gainer momentum (for hedging on gainers)
        dataframe["roc_1h"] = dataframe["close"].pct_change(1) * 100
        dataframe["roc_4h"] = dataframe["close"].pct_change(4) * 100
        dataframe["roc_24h"] = dataframe["close"].pct_change(24) * 100

        return dataframe

    # ── Entry ──
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ═══ LONG: P3F signals + top gainer momentum ═══
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
            (dataframe["rsi"] > 40) &
            (dataframe["rsi"] < 65)
        )

        expansion_long = (
            (dataframe["close"] > dataframe["bb3_upper"]) &
            (dataframe["close"].shift(1) <= dataframe["bb3_upper"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) &
            (dataframe["rsi"] > 50)
        )

        key_level_long = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < 65)
        )

        # P3F Key Level Boost: +1 when very close to support
        key_level_boost_long = (
            dataframe["dist_to_support"] < self.key_level_boost_dist.value
        ).astype(int)

        long_signals = [
            squeeze_breakout_long.astype(int),
            mean_reversion_long.astype(int),
            ema_alignment_long.astype(int),
            expansion_long.astype(int),
            key_level_long.astype(int),
        ]
        long_score = sum(long_signals) + key_level_boost_long

        # Additional top-gainer filter for hedge setup
        top_gainer_long = dataframe["roc_4h"] > 2.0

        dataframe.loc[
            (long_score >= self.min_confluence.value) &
            (top_gainer_long) &
            (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "champion_hedge_long")

        # ═══ SHORT: overextended gainer hedge ═══
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
            (dataframe["rsi"] < 60) &
            (dataframe["rsi"] > 35)
        )

        expansion_short = (
            (dataframe["close"] < dataframe["bb3_lower"]) &
            (dataframe["close"].shift(1) >= dataframe["bb3_lower"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) &
            (dataframe["rsi"] < 50)
        )

        key_level_short = (
            (dataframe["dist_to_resistance"] < 1.0) &
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["rsi"] < 65) &
            (dataframe["rsi"] > 35)
        )

        key_level_boost_short = (
            dataframe["dist_to_resistance"] < self.key_level_boost_dist.value
        ).astype(int)

        short_signals = [
            squeeze_breakout_short.astype(int),
            mean_reversion_short.astype(int),
            ema_alignment_short.astype(int),
            expansion_short.astype(int),
            key_level_short.astype(int),
        ]
        short_score = sum(short_signals) + key_level_boost_short

        # Overextended top gainer filter for short hedge
        overextended_gainer = (
            (dataframe["roc_24h"] > 10.0) &
            (dataframe["roc_1h"] < 0)
        )

        dataframe.loc[
            (short_score >= self.min_confluence.value) &
            (overextended_gainer) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "champion_hedge_short")

        return dataframe

    # ── Exit ──
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["bb_pctb"] > self.bb_pctb_high.value) |
                ((dataframe["rsi"] > self.rsi_overbought.value) &
                 (dataframe["close"] < dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "champion_exit_long")

        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "champion_exit_short")

        return dataframe

    # ── Custom Exit: beacon targets ──
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
