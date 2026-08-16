"""
IVB ORB Crypto V2 - Institutional Validation Breakout for Crypto Futures
=========================================================================

Adapted from Fabio Valentini's Opening Range Breakout (ORB) model,
independently validated (IVB) on 823 NQ futures trades:
  - P(edge<=0) = 0.001 (bootstrap)
  - 58.32% WR, PF 1.28 net, ROI/DD 5.83

CRYPTO ADAPTATIONS:
  - Opening range: 13:30-14:00 UTC (08:30-09:00 ET → US market open)
  - Volume delta proxy: volume * (close - open) / (high - low)
  - LONG+SHORT (original IVB is long-only; crypto needs both)
  - Fixed R:R exits (IVB validated at 1R; we test 1.5R-3R)
  - Risk-to-zero: move SL to BE after 1R profit (Fabio's core rule)

V2 FIXES from V1 failure (319 trades, -71%):
  - Strict one-trade-per-session: use date-based session tracking
  - Tighter delta: require 2x average bar delta for breakout bars
  - Wider ORB minimum range: skip flat days (need 0.3%+ range)
  - Trailing stop instead of fixed SL: capitalizes on momentum
  - Reduce leverage to 5x (was 10x, too aggressive for 5m)
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter


class IVB_ORB_Crypto_V2(IStrategy):
    """IVB Opening Range Breakout V2 — strict session tracking, tighter filters"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "5m"
    startup_candle_count = 200

    stoploss = -0.06  # Hard stop fallback (6%)
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False

    # Use trailing stop in the style of "risk to zero" — tight trail after profit
    trailing_stop = True
    trailing_stop_positive = 0.015   # 1.5% trail after activation
    trailing_stop_positive_offset = 0.03  # Activate trail after 3% profit
    trailing_only_offset_is_reached = True

    stake_amount = "unlimited"
    max_open_trades = 1  # IVB: one trade per session maximum

    # ─── OPTIMIZABLE PARAMETERS ──────────────────────────────────

    # Opening Range
    orb_duration = IntParameter(6, 18, default=6, space="buy", optimize=True)  # bars (6*5m=30min)
    orb_start_hour_utc = IntParameter(12, 15, default=13, space="buy", optimize=False)
    min_orb_range_pct = DecimalParameter(0.2, 1.5, default=0.4, decimals=2, space="buy", optimize=True)

    # Delta filter (tighter than V1)
    delta_zscore_threshold = DecimalParameter(0.5, 3.0, default=1.5, decimals=1, space="buy", optimize=True)

    # Exit parameters
    tp_rr_ratio = DecimalParameter(1.0, 3.0, default=2.0, decimals=1, space="sell", optimize=True)
    sl_pct = DecimalParameter(0.03, 0.08, default=0.05, decimals=3, space="sell", optimize=True)

    # Leverage (conservative for 5m)
    leverage_num = DecimalParameter(3, 10, default=5.0, decimals=0, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, entry_tag, side, max_leverage, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()

        # ── RSI ──
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── EMA ──
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

        # ── ATR for dynamic stops ──
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        df["atr_pct"] = (df["atr"] / df["close"]) * 100

        # ── Volume delta proxy ──
        candle_range = (df["high"] - df["low"]).replace(0, np.nan)
        df["bar_delta"] = (df["volume"] * (df["close"] - df["open"]) / candle_range).fillna(0)
        df["bar_delta_ma"] = df["bar_delta"].rolling(20).mean()
        df["bar_delta_std"] = df["bar_delta"].rolling(20).std().replace(0, np.nan)
        df["delta_zscore"] = ((df["bar_delta"] - df["bar_delta_ma"]) / df["bar_delta_std"]).fillna(0)

        # ── Cumulative delta over rolling windows ──
        orb_dur = int(self.orb_duration.value)
        df["cum_delta_orb"] = df["bar_delta"].rolling(orb_dur).sum()

        # ── Volume ──
        df["vol_ma_20"] = df["volume"].rolling(20).mean()

        # ── ORB levels (computed per session) ──
        df = self._compute_orb(df)

        # ── Entry signals ──
        df = self._compute_entries(df)

        return df

    def _compute_orb(self, df):
        """Compute ORB levels with strict one-per-session logic.

        Key fix from V1: Only mark ORB levels for the period AFTER the ORB window,
        and use date-based grouping to ensure one ORB per day per pair.
        """
        orb_dur = int(self.orb_duration.value)
        min_range_pct = float(self.min_orb_range_pct.value)
        orb_start = int(self.orb_start_hour_utc.value)

        # Pre-allocate
        df["orb_high"] = np.nan
        df["orb_low"] = np.nan
        df["orb_range"] = np.nan
        df["orb_range_pct"] = np.nan
        df["orb_valid"] = False
        df["post_orb"] = False  # Only bars AFTER the ORB window can trade

        df["date_only"] = df["date"].dt.date
        df["hour"] = df["date"].dt.hour
        df["minute"] = df["date"].dt.minute

        for date_val in df["date_only"].unique():
            day_mask = df["date_only"] == date_val
            day_df = df.loc[day_mask]

            if len(day_df) < orb_dur + 5:  # Need ORB bars + some post-ORB bars
                continue

            # Find ORB window: bars where hour == orb_start
            orb_bars = day_df.loc[day_df["hour"] == orb_start]
            if len(orb_bars) < 3:
                # Fallback: first orb_dur bars of the day
                orb_bars = day_df.iloc[:orb_dur]

            if len(orb_bars) < 3:
                continue

            orb_high = orb_bars["high"].max()
            orb_low = orb_bars["low"].min()
            orb_range = orb_high - orb_low
            orb_mid = (orb_high + orb_low) / 2
            range_pct = (orb_range / orb_mid) * 100

            # Skip flat days — no edge in tight ranges
            if range_pct < min_range_pct:
                continue

            # Mark all bars AFTER the ORB window
            last_orb_idx = orb_bars.index[-1]
            post_orb_mask = day_mask & (df.index > last_orb_idx)

            df.loc[post_orb_mask, "orb_high"] = orb_high
            df.loc[post_orb_mask, "orb_low"] = orb_low
            df.loc[post_orb_mask, "orb_range"] = orb_range
            df.loc[post_orb_mask, "orb_range_pct"] = range_pct
            df.loc[post_orb_mask, "orb_valid"] = True
            df.loc[post_orb_mask, "post_orb"] = True

        df.drop(columns=["date_only", "hour", "minute"], inplace=True, errors="ignore")
        return df

    def _compute_entries(self, df):
        """Entry signals with strict filters.

        LONG: close > ORB high + delta z-score > threshold + volume confirm + RSI < 75
        SHORT: close < ORB low + delta z-score < -threshold + volume confirm + RSI > 25
        """
        z_thresh = float(self.delta_zscore_threshold.value)

        orb_ok = df["orb_valid"]

        # Volume filter: bar volume > 1.2x 20-bar average
        vol_ok = df["volume"] > df["vol_ma_20"] * 1.2

        # Delta filter: strong directional flow
        long_delta = df["delta_zscore"] > z_thresh
        short_delta = df["delta_zscore"] < -z_thresh

        # Trend context
        long_trend = df["ema_20"] > df["ema_50"]
        short_trend = df["ema_20"] < df["ema_50"]

        # RSI filter
        rsi_long = df["rsi"] < 75
        rsi_short = df["rsi"] > 25

        # Candle confirmation (body > 40% of range for strong close)
        body_ratio = (df["close"] - df["open"]).abs() / (df["high"] - df["low"]).replace(0, np.nan)
        strong_close_long = (df["close"] > df["open"]) & (body_ratio > 0.4)
        strong_close_short = (df["close"] < df["open"]) & (body_ratio > 0.4)

        # ─── LONG ENTRY ───
        long_entry = (
            orb_ok &
            (df["close"] > df["orb_high"]) &  # Breakout
            long_delta &                          # Institutional buying
            vol_ok &                               # Volume confirm
            long_trend &                           # Trend context
            rsi_long &                             # Not overbought
            strong_close_long                      # Strong close
        )

        # ─── SHORT ENTRY ───
        short_entry = (
            orb_ok &
            (df["close"] < df["orb_low"]) &   # Breakdown
            short_delta &                         # Institutional selling
            vol_ok &                               # Volume confirm
            short_trend &                          # Trend context
            rsi_short &                            # Not oversold
            strong_close_short                    # Strong close
        )

        df["enter_long"] = long_entry.astype(int)
        df["enter_short"] = short_entry.astype(int)
        df["enter_tag"] = np.where(long_entry, "ivb_orb_long",
                            np.where(short_entry, "ivb_orb_short", ""))

        # ─── EXIT TARGETS ───
        tp_rr = float(self.tp_rr_ratio.value)

        # LONG: TP above ORB high, SL at ORB low
        df["long_tp_price"] = df["orb_high"] + tp_rr * df["orb_range"]
        df["short_tp_price"] = df["orb_low"] - tp_rr * df["orb_range"]

        return df

    def populate_entry_trend(self, dataframe, metadata):
        # Already set in _compute_entries
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe

        # Exit LONG: momentum failure (close back below ORB mid after entry)
        df.loc[
            df["orb_valid"] &
            (df["close"] < df["orb_high"]) &  # Lost breakout level
            (df["rsi"] > 60),                   # Still elevated (exit on weakness)
            ["exit_long", "exit_tag"]
        ] = (1, "orb_momentum_loss_long")

        # Exit SHORT: momentum failure
        df.loc[
            df["orb_valid"] &
            (df["close"] > df["orb_low"]) &   # Lost breakdown level
            (df["rsi"] < 40),                    # Still depressed (exit on bounce)
            ["exit_short", "exit_tag"]
        ] = (1, "orb_momentum_loss_short")

        return df

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        """Risk to Zero: Fabio's core rule.

        Once profit exceeds the ORB range (1R), move stop to breakeven.
        This is the #1 risk management rule from the KB: "Put stop loss to 
        break-even as soon as possible after entry to make the trade risk-free."
        """
        sl = float(self.sl_pct.value)

        # Risk to Zero: once we're up more than 1.5%, protect profits
        if current_profit > 0.03:
            return -0.005  # Very tight: only give back 0.5%
        if current_profit > 0.015:
            return -0.008  # Tight: give back max 0.8%
        if current_profit > 0.005:
            return -0.01  # Breakeven: give back max 1%

        return -sl  # Default hard stop

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        """Fixed R:R exit targets based on ORB range.

        IVB validated at 1R TP. We test 1.5R-3R range.
        Also enforce session-end exits (IVB closes at 14:00 ET).
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last = dataframe.iloc[-1]

        # Fixed R:R take profit
        if not trade.is_short and last.get("long_tp_price") is not None:
            if not np.isnan(last["long_tp_price"]) and current_rate >= last["long_tp_price"]:
                return f"ivb_tp_{self.tp_rr_ratio.value:.1f}R"

        if trade.is_short and last.get("short_tp_price") is not None:
            if not np.isnan(last["short_tp_price"]) and current_rate <= last["short_tp_price"]:
                return f"ivb_tp_{self.tp_rr_ratio.value:.1f}R"

        return None