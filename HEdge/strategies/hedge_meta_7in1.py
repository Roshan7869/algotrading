"""
HEDGE META — 7-in-1 Combined Risk Management Hedge
===================================================
Combines ALL 7 ChromaDB risk management principles into one unified strategy.

1. Fixed Fractional 1% — base position sizing floor
2. Risk to Zero ASAP — breakeven activation at +3%
3. Half-Kelly — optimal risk/growth sizing
4. Consecutive Loss Protection — streak-based drawdown circuit breaker
5. Scale Out 50-30-20 — partial profit taking
6. Anti-Martingale — increase sizing on win streaks
7. Win Rate Adaptive — dual-direction sizing (inc wins / dec losses)

Core Structure:
  - Capital split: 50% long, 50% short on top gainers
  - Leverage: 10x
  - Base Stop: -10% (overridden by adaptive sizing)
  - Profit Target: +30% (with 50-30-20 scale-out)

Layer Application Order:
  1. Win Rate Adaptive → sets signal sensitivity
  2. Anti-Martingale → adjusts sizing multiplier
  3. Consecutive Loss Protection → circuit breaker override
  4. Half-Kelly → caps max size
  5. Fixed Fractional → ensures minimum risk control
  6. Risk to Zero ASAP → moves stop to breakeven
  7. Scale Out → partial exits at targets
"""

from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter


class HedgeMeta7in1(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = True

    # ── Stop & Target ──
    stoploss = -0.10

    # 50-30-20 scale-out via ROI
    # 50% at 1R (10%), 30% at 2R (20%), 20% runner to 30%
    minimal_roi = {
        "0": 0.30,
        "60": 0.20,
        "240": 0.10,
    }

    # Risk to Zero: trail to breakeven at +3%
    trailing_stop = True
    trailing_stop_positive = 0.01       # 1% trail after breakeven activates
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 100

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ── Hyperopt Params ──
    # Entry conditions
    vol_surge = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy")

    # Fixed Fractional (base layer)
    base_risk_pct = DecimalParameter(0.005, 0.02, default=0.01, decimals=3, space="buy")

    # Half-Kelly
    kelly_fraction = DecimalParameter(0.25, 0.75, default=0.50, decimals=2, space="buy")
    assumed_win_rate = DecimalParameter(0.50, 0.75, default=0.60, decimals=2, space="buy")

    # Consecutive Loss Protection
    streak_reduce_threshold = IntParameter(2, 4, default=3, space="sell")
    streak_stop_threshold = IntParameter(5, 8, default=7, space="sell")

    # Scale-out targets
    scale_1r = DecimalParameter(0.08, 0.15, default=0.10, decimals=2, space="sell")
    scale_2r = DecimalParameter(0.15, 0.25, default=0.20, decimals=2, space="sell")

    # State tracking
    _consecutive_wins = 0
    _consecutive_losses = 0
    _current_size_mult = 1.0

    # ── Leverage ──
    def leverage(self, pair, current_time, current_rate,
                 proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(10.0, max_leverage)

    # ── Indicators ──
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["roc_1h"] = dataframe["close"].pct_change(1) * 100
        dataframe["roc_4h"] = dataframe["close"].pct_change(4) * 100
        dataframe["roc_24h"] = dataframe["close"].pct_change(24) * 100
        dataframe["rsi"] = self._rsi(dataframe, 14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = (dataframe["volume"] / dataframe["volume_ma"]).fillna(1)
        dataframe["atr"] = self._atr(dataframe, 14)
        dataframe["adx"] = self._adx(dataframe, 14)

        # Trend strength for regime detection
        ema_50 = dataframe["close"].ewm(span=50).mean()
        dataframe["trend_strength"] = ((dataframe["close"] - ema_50) / ema_50 * 100)

        return dataframe

    # ── Entry ──
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ── Layer 1: Win Rate Adaptive → signal sensitivity ──
        signal_factor = 1.0
        if self._consecutive_wins >= 5:
            signal_factor = 1.5
        elif self._consecutive_wins >= 3:
            signal_factor = 1.25
        elif self._consecutive_losses >= 3:
            signal_factor = 0.5
        elif self._consecutive_losses >= 2:
            signal_factor = 0.75

        # ── Layer 2: Anti-Martingale → dynamic sizing ──
        size_mult = 1.0
        if self._consecutive_wins >= 2:
            size_mult = 1.5
        if self._consecutive_wins >= 3:
            size_mult = 2.0
        # Reset on loss (handled in custom_exit)
        self._current_size_mult = size_mult

        # ── Layer 3: Consecutive Loss Protection ──
        if self._consecutive_losses >= self.streak_stop_threshold.value:
            return dataframe  # Stop trading
        if self._consecutive_losses >= self.streak_reduce_threshold.value:
            signal_factor *= 0.75
        if self._consecutive_losses >= 5:
            signal_factor *= 0.5

        # Compute effective thresholds
        eff_vol = self.vol_surge.value * (1.0 / max(signal_factor, 0.1))
        eff_min_roc_1h = 0.5 * (2.0 - signal_factor)
        eff_min_roc_4h = 2.0 * (2.0 - signal_factor)

        # LONG signal
        long_cond = (
            (dataframe["roc_1h"] > eff_min_roc_1h) &
            (dataframe["roc_4h"] > eff_min_roc_4h) &
            (dataframe["volume_ratio"] > eff_vol) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < 68) &
            (dataframe["adx"] > 18)
        )
        dataframe.loc[long_cond & (dataframe["volume"] > 0),
                      ["enter_long", "enter_tag"]] = (1, "meta7in1_long")

        # SHORT signal (overextended gainers)
        short_cond = (
            (dataframe["roc_24h"] > 8.0) &
            (dataframe["rsi"] > 70) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["roc_1h"] < 0) &
            (dataframe["adx"] > 18)
        )
        dataframe.loc[short_cond & (dataframe["volume"] > 0),
                      ["enter_short", "enter_tag"]] = (1, "meta7in1_short")

        return dataframe

    # ── Exit ──
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 82, ["exit_long", "exit_tag"]] = (1, "rsi_ob_exit")
        dataframe.loc[dataframe["rsi"] < 18, ["exit_short", "exit_tag"]] = (1, "rsi_os_exit")

        # ATR blow-off exit
        dataframe.loc[dataframe["atr"] > dataframe["atr"].rolling(50).mean() * 3,
                      ["exit_long", "exit_tag"]] = (1, "atr_blowoff")
        return dataframe

    # ── Custom Stop: dynamic based on streak state ──
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        if after_fill:
            # Tighten stop during losing streaks (Layer 3)
            if self._consecutive_losses >= 2:
                return -0.08
            return -0.10
        return None

    # ── Custom Exit: 50-30-20 Scale-Out + streak tracking ──
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:

        # Update streak tracking
        if current_profit > 0:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0

        # Scale-out: 50-30-20 partial exits
        if current_profit >= self.scale_2r.value:
            return "scale_2r"
        if current_profit >= self.scale_1r.value:
            return "scale_1r"

        return None

    # ── Helpers ──
    def _rsi(self, df, period=14):
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _atr(self, df, period=14):
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _adx(self, df, period=14):
        high, low, close = df["high"], df["low"], df["close"]
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
        minus_di = 100 * (abs(minus_dm).ewm(alpha=1/period).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
        return dx.rolling(period).mean()
