"""
HEDGE MOMENTUM — MACD% + RSI Confluence Hedge (v2 — Normalized)
================================================================
Entry: MACD/Close > 1.3% (i.e., MACD > 1.3% of price) AND RSI > 70
Direction: BOTH long AND short (delta-neutral hedge)
Stop Loss: -10%
Take Profit: +30%

Why normalized:
  - Absolute MACD > 0.02 works for ~$1-2 coins (XRP) but misses
    higher-priced ones (LINK at $15 has MACD ~0.10)
  - MACD/Close > 1.3% normalizes across all price levels
  - This matches XRP at $1.5 where MACD > 0.02 = 1.3% of price

Also lowered RSI from 75 to 70 for more entry signals.

ChromaDB Sources:
  - "Risk to Zero ASAP" (risk_management)
  - "MACD Momentum Entry" (confirmation)
  - "RSI Overbought/Oversold" (market structure)
"""

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, Trade


class HedgeMomentumMacdRsiV2(IStrategy):
    """
    MACD% > 1.3% + RSI > 70 momentum hedge.
    Opens both long AND short when conditions met.
    Normalized MACD to work across all price levels.
    """

    can_short: bool = True
    timeframe = "1h"
    startup_candle_count: int = 100

    # Risk: -10% SL, +30% TP
    stoploss = -0.10
    minimal_roi = {"0": 0.30}

    # Trailing: Risk-to-Zero breakeven after +3%
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # Position sizing: 50% per direction
    stake_amount = "unlimited"
    tradable_balance_ratio = 0.5
    max_open_trades = 14

    # Configurable thresholds
    macd_pct_threshold = DecimalParameter(
        0.3, 5.0, default=0.8, decimals=1,
        space="buy", optimize=False
    )
    rsi_threshold = IntParameter(
        55, 85, default=70, space="buy", optimize=False
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
    def _calc_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    # ── Indicators ─────────────────────────────────────────────
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        period = int(self.rsi_period.value)
        dataframe["rsi"] = self._calc_rsi(dataframe["close"], period)

        fast = int(self.macd_fast.value)
        slow = int(self.macd_slow.value)
        sig = int(self.macd_signal_period.value)
        macd_df = self._calc_macd(dataframe, fast, slow, sig)
        dataframe["macd"] = macd_df["macd"]
        dataframe["macd_signal"] = macd_df["macdsignal"]
        dataframe["macd_hist"] = macd_df["macdhist"]

        # MACD as percentage of close price (NORMALIZED across price levels)
        dataframe["macd_pct"] = (dataframe["macd"] / dataframe["close"]) * 100

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
        macd_pct_above = dataframe["macd_pct"] > float(self.macd_pct_threshold.value)
        rsi_above = dataframe["rsi"] > int(self.rsi_threshold.value)

        # LONG: MACD% > 1.3 AND RSI > 70 (momentum breakout)
        dataframe.loc[
            (macd_pct_above) &
            (rsi_above) &
            (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "macd_pct_rsi_momentum_long")

        # SHORT: Same conditions (overbought reversal hedge)
        dataframe.loc[
            (macd_pct_above) &
            (rsi_above) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "macd_pct_rsi_momentum_short")

        return dataframe

    # ── Exit signals ───────────────────────────────────────────
    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # Exit long: MACD% drops below 0 OR RSI drops below 50
        dataframe.loc[
            (dataframe["macd_pct"] < 0) |
            (dataframe["rsi"] < 50),
            ["exit_long", "exit_tag"]
        ] = (1, "macd_pct_rsi_exit_long")

        # Exit short: RSI drops below 50
        dataframe.loc[
            (dataframe["rsi"] < 50),
            ["exit_short", "exit_tag"]
        ] = (1, "macd_pct_rsi_exit_short")

        return dataframe

    # ── Custom stoploss — Risk to Zero ──────────────────────────
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        # Breakeven after +3%
        if current_profit > 0.03:
            return -0.005
        return None

    # ── Confirm trade entry — prevent duplicate hedge on same pair ──
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                           rate: float, time_in_force: str, current_time: datetime,
                           entry_tag: Optional[str], side: str, **kwargs) -> bool:
        return True

    def custom_trade_info(self, pair: str, current_time: datetime, **kwargs) -> dict:
        return {
            "macd_pct_threshold": float(self.macd_pct_threshold.value),
            "rsi_threshold": int(self.rsi_threshold.value),
            "strategy_type": "momentum_hedge_v2",
        }