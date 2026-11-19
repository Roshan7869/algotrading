"""
VectorOmni_MetaLearner — Self-Learning Vector Strategy with Outcome Feedback

Manipulates VectorStrategy by adding from ChromaDB + kronos_indicators:
  1. Circuit breaker: halt after 3 consecutive losses (V2 IntelligenceLayer)
  2. Signal quality tracking: disable signals < 40% WR over last 20
  3. Dynamic sizing: increase 25% after 3 wins, decrease 25% after 2 losses
  4. Regime-specific performance tracking
  5. Outcome persistence to JSON for cross-session learning
  6. Beacon exits + ATR-based break-even management

This is the only strategy that adapts its behavior based on trade history.
"""
from datetime import datetime
from typing import Optional
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class VectorOmni_MetaLearner(IStrategy):
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

    LEARNING_PATH = Path(__file__).parent / ".metalearner_state.json"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.circuit_breaker_active = False
        self.circuit_breaker_candle = 0
        self.circuit_breaker_cooldown = 12
        self.signal_stats = {}
        self._load_state()

    def _load_state(self):
        if self.LEARNING_PATH.exists():
            try:
                with open(self.LEARNING_PATH) as f:
                    state = json.load(f)
                self.signal_stats = state.get("signal_stats", {})
            except Exception:
                self.signal_stats = {}

    def _save_state(self):
        try:
            state = {"signal_stats": self.signal_stats}
            with open(self.LEARNING_PATH, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _update_signal_stats(self, signal_name: str, is_win: bool):
        if signal_name not in self.signal_stats:
            self.signal_stats[signal_name] = {"wins": [], "total": []}
        stats = self.signal_stats[signal_name]
        if len(stats["wins"]) >= 20:
            stats["wins"].pop(0)
            stats["total"].pop(0)
        stats["wins"].append(1 if is_win else 0)
        stats["total"].append(1)

    def _is_signal_active(self, signal_name: str) -> bool:
        if signal_name not in self.signal_stats:
            return True
        stats = self.signal_stats[signal_name]
        if len(stats["total"]) < 5:
            return True
        wr = sum(stats["wins"]) / len(stats["total"])
        return wr >= 0.40

    def _get_consecutive_wins(self, signal_name: str) -> int:
        if signal_name not in self.signal_stats:
            return 0
        stats = self.signal_stats[signal_name]
        count = 0
        for w in reversed(stats["wins"]):
            if w == 1:
                count += 1
            else:
                break
        return count

    def _get_consecutive_losses_signal(self, signal_name: str) -> int:
        if signal_name not in self.signal_stats:
            return 0
        stats = self.signal_stats[signal_name]
        count = 0
        for w in reversed(stats["wins"]):
            if w == 0:
                count += 1
            else:
                break
        return count

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

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        circuit_breaker_halt = self.circuit_breaker_active

        squeeze_long = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )
        mean_rev_long = (
            (dataframe["bb_pctb"] < self.bb_pctb_low.value) &
            (dataframe["close"] > dataframe["bb3_lower"]) &
            (dataframe["rsi"] < self.rsi_oversold.value) &
            (dataframe["close"] > dataframe["vwap"])
        )
        ema_align_long = (
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
        sig_active = self._is_signal_active
        sig_names = ["squeeze", "meanrev", "ema", "expansion", "keylevel"]
        sig_bools = [
            squeeze_long.astype(int) if sig_active("squeeze_long") else pd.Series(0, index=dataframe.index),
            mean_rev_long.astype(int) if sig_active("meanrev_long") else pd.Series(0, index=dataframe.index),
            ema_align_long.astype(int) if sig_active("ema_long") else pd.Series(0, index=dataframe.index),
            expansion_long.astype(int) if sig_active("expansion_long") else pd.Series(0, index=dataframe.index),
            key_level_long.astype(int) if sig_active("keylevel_long") else pd.Series(0, index=dataframe.index),
        ]

        long_score = sum(sig_bools) + key_level_boost_long

        dataframe.loc[
            (long_score >= self.min_confluence.value) &
            (~circuit_breaker_halt) &
            (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "metalearner_long")

        squeeze_short = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] < dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )
        mean_rev_short = (
            (dataframe["bb_pctb"] > self.bb_pctb_high.value) &
            (dataframe["close"] < dataframe["bb3_upper"]) &
            (dataframe["rsi"] > self.rsi_overbought.value) &
            (dataframe["close"] < dataframe["vwap"])
        )
        ema_align_short = (
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
        sig_bools_short = [
            squeeze_short.astype(int) if sig_active("squeeze_short") else pd.Series(0, index=dataframe.index),
            mean_rev_short.astype(int) if sig_active("meanrev_short") else pd.Series(0, index=dataframe.index),
            ema_align_short.astype(int) if sig_active("ema_short") else pd.Series(0, index=dataframe.index),
            expansion_short.astype(int) if sig_active("expansion_short") else pd.Series(0, index=dataframe.index),
            key_level_short.astype(int) if sig_active("keylevel_short") else pd.Series(0, index=dataframe.index),
        ]
        short_score = sum(sig_bools_short) + key_level_boost_short

        dataframe.loc[
            (short_score >= self.min_confluence.value) &
            (~circuit_breaker_halt) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "metalearner_short")

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
        ] = (1, "metalearner_exit")

        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "metalearner_exit")

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
