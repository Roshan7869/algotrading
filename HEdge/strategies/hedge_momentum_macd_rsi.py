"""
HEDGE MOMENTUM — MACD + RSI Confluence Hedge
==============================================
Entry: MACD > 0.02 AND RSI > 75
Direction: BOTH long AND short (delta-neutral hedge)
Stop Loss: -10%
Take Profit: +30%

Logic:
  When MACD is above 0.02 and RSI shows overbought (>75),
  momentum is extreme. Instead of guessing direction:
  - Open LONG: profits if breakout continues (+30% target)
  - Open SHORT: profits if overbought reverses (-10% risk)
  The winning side captures +30%, the losing side loses -10%.
  Net if right on direction: +30% - 10% = +20% effective.
  Worst case whipsaw: -10% - 10% = -20% (both stopped out).

ChromaDB Sources:
  - "Risk to Zero ASAP" (risk_management)
  - "MACD Momentum Entry" confirmation signals
  - "RSI Overbought/Oversold" market structure

Pairs: XRP + P2 tokens (18+ pairs)
Timeframe: 1h
Leverage: 10x
"""

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, Trade


class HedgeMomentumMacdRsi(IStrategy):
    """
    MACD > 0.02 + RSI > 75 momentum hedge.
    Opens both long AND short when conditions met.
    """

    # Strategy metadata
    can_short: bool = True
    timeframe = "1h"
    startup_candle_count: int = 100

    # Risk parameters
    stoploss = -0.10  # -10% hard stop

    # Take profit via ROI table
    minimal_roi = {"0": 0.30}

    # Trailing stop — Risk to Zero style
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # Position sizing: 50% per direction
    stake_amount = "unlimited"
    tradable_balance_ratio = 0.5

    # Max trades: 7 long + 7 short
    max_open_trades = 14

    # Configurable parameters
    macd_threshold = DecimalParameter(
        -0.1, 0.2, default=0.02, decimals=4,
        space="buy", optimize=False
    )
    rsi_threshold = IntParameter(
        50, 90, default=75, space="buy", optimize=False
    )
    rsi_period = IntParameter(
        7, 21, default=14, space="buy", optimize=False
    )
    macd_fast = IntParameter(8, 21, default=12, space="buy", optimize=False)
    macd_slow = IntParameter(21, 52, default=26, space="buy", optimize=False)
    macd_signal_period = IntParameter(5, 13, default=9, space="buy", optimize=False)
    leverage_num = DecimalParameter(
        1, 20, default=10.0, decimals=1,
        space="buy", optimize=False
    )

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float,
                 entry_tag: Optional[str], side: str, **kwargs) -> float:
        return float(self.leverage_num.value)

    # ── Custom indicator calculations ───────────────────────────
    @staticmethod
    def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Wilders RSI."""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
                   signal: int = 9) -> pd.DataFrame:
        """MACD indicator: returns DataFrame with macd, signal, histogram."""
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return pd.DataFrame({
            "macd": macd_line,
            "macdsignal": signal_line,
            "macdhist": histogram
        })

    @staticmethod
    def _calc_bollinger(series: pd.Series, window: int = 20,
                        stds: float = 2.0) -> pd.DataFrame:
        """Bollinger Bands."""
        mid = series.rolling(window).mean()
        std = series.rolling(window).std()
        return pd.DataFrame({
            "middleband": mid,
            "upperband": mid + stds * std,
            "lowerband": mid - stds * std,
        })

    @staticmethod
    def _calc_ema(series: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    # ── Indicators ─────────────────────────────────────────────
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        period = int(self.rsi_period.value)
        dataframe["rsi"] = self._calc_rsi(dataframe["close"], period)

        # MACD
        fast = int(self.macd_fast.value)
        slow = int(self.macd_slow.value)
        sig = int(self.macd_signal_period.value)
        macd_df = self._calc_macd(dataframe, fast, slow, sig)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]

        # Bollinger Bands
        bb = self._calc_bollinger(dataframe["close"], 20, 2.0)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_mid"] = bb["middleband"]

        # EMA trend
        dataframe["ema_50"] = self._calc_ema(dataframe["close"], 50)
        dataframe["ema_200"] = self._calc_ema(dataframe["close"], 200)

        # Volume
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ratio"] = (
            dataframe["volume"] / dataframe["volume_mean_20"]
        ).replace([np.inf, -np.inf], 0).fillna(1)

        return dataframe

    # ── Entry signals ──────────────────────────────────────────
    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        macd_above = dataframe["macd"] > float(self.macd_threshold.value)
        rsi_above = dataframe["rsi"] > int(self.rsi_threshold.value)

        # LONG: MACD > 0.02 AND RSI > 75 (breakout momentum)
        dataframe.loc[
            (macd_above) &
            (rsi_above) &
            (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "macd_rsi_momentum_long")

        # SHORT: Same conditions (overbought reversal hedge)
        dataframe.loc[
            (macd_above) &
            (rsi_above) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_rsi_momentum_short")

        return dataframe

    # ── Exit signals ───────────────────────────────────────────
    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # Exit long when MACD drops below 0 or RSI below 50
        dataframe.loc[
            (dataframe["macd"] < 0) |
            (dataframe["rsi"] < 50),
            ["exit_long", "exit_tag"]
        ] = (1, "macd_rsi_exit_long")

        # Exit short when RSI drops below 50
        dataframe.loc[
            (dataframe["rsi"] < 50),
            ["exit_short", "exit_tag"]
        ] = (1, "macd_rsi_exit_short")

        return dataframe

    # ── Custom stoploss — Risk to Zero ──────────────────────────
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        # If profit > 3%, move stop to breakeven
        if current_profit > 0.03:
            return -0.005
        return None

    # ── Trade info ──────────────────────────────────────────────
    def custom_trade_info(self, pair: str, current_time: datetime, **kwargs) -> dict:
        return {
            "macd_threshold": float(self.macd_threshold.value),
            "rsi_threshold": int(self.rsi_threshold.value),
            "strategy_type": "momentum_hedge",
        }