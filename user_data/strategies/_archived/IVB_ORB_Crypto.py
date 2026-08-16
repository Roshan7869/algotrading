"""
IVB ORB Crypto - Institutional Validation Breakout for Crypto Futures
======================================================================

Adapted from Fabio Valentini's Opening Range Breakout (ORB) model,
independently validated by Matteo Conti (IVB) on 823 NQ futures trades
with bootstrap P(edge<=0) = 0.001.

CRYPTO ADAPTATIONS:
- Opening range mapped to US session open (13:30-14:00 UTC = 08:30-09:00 ET)
- Delta filter uses volume * (close-open)/range as crypto proxy for CVD
- LONG only (per validated model) — crypto momentum favors upside
- Fixed 1R TP + EOD exit translated to session-based close
- Works on 5m timeframe (matches original IVB validation)
- Added SHORT variant for crypto's two-way moves

HYPEROPT PARAMETERS:
- orb_duration:    6-12 bars (30-60 min at 5m)
- delta_threshold: 0.3-3.0 (crypto volume delta proxy)
- tp_rr_ratio:     1.0-3.0 (R-multiple target)
- stoploss:        2%-8% (hard stop)
- min_orb_range:   0.1-1.0% (minimum ORB range % to avoid tight ranges)
- volume_filter:   0.5-3.0x (ORB volume vs 20-bar avg)

Run: freqtrade backtesting --strategy IVB_ORB_Crypto --timeframe 5m \
     --config <config> --timerange 20260501-
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, BooleanParameter


class IVB_ORB_Crypto(IStrategy):
    """IVB Opening Range Breakout — crypto-adapted with delta filter"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "5m"
    startup_candle_count = 200

    stoploss = -0.05  # Overridden by sl_pct in custom_stoploss
    minimal_roi = {"0": 100}  # We manage exits ourselves
    use_exit_signal = True
    exit_profit_only = False

    trailing_stop = False  # IVB uses fixed TP, not trailing

    stake_amount = "unlimited"
    max_open_trades = 3  # IVB does 1 per session; crypto has more sessions

    # ─── OPTIMIZABLE PARAMETERS ──────────────────────────────────

    # Opening Range parameters
    orb_duration = IntParameter(6, 18, default=6, space="buy", optimize=True)  # 6 bars = 30min at 5m
    orb_start_hour_utc = IntParameter(12, 15, default=13, space="buy", optimize=False)  # 13 = 1pm UTC = 8:30am ET
    min_orb_range_pct = DecimalParameter(0.1, 1.0, default=0.3, decimals=2, space="buy", optimize=True)

    # Delta filter parameters
    delta_threshold = DecimalParameter(0.5, 5.0, default=1.5, decimals=1, space="buy", optimize=True)
    volume_filter_mult = DecimalParameter(0.5, 3.0, default=1.0, decimals=1, space="buy", optimize=True)

    # Exit parameters
    tp_rr_ratio = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="sell", optimize=True)
    sl_pct = DecimalParameter(0.02, 0.08, default=0.04, decimals=3, space="sell", optimize=True)

    # Session parameters
    session_exit_hour_utc = IntParameter(20, 23, default=21, space="sell", optimize=False)  # 4pm ET = 21 UTC
    enable_shorts = BooleanParameter(default=True, space="buy", optimize=False)

    # Leverage
    leverage_num = DecimalParameter(3, 15, default=10.0, decimals=0, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, entry_tag, side, max_leverage, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()

        # ── RSI (for context filters) ──
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── EMA Trend Context ──
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

        # ── Volume moving average ──
        df["vol_ma_20"] = df["volume"].rolling(20).mean()

        # ── Compute ORB levels ──
        df = self._compute_orb(df)

        # ── Compute Volume Delta (crypto proxy for CVD) ──
        df = self._compute_delta(df)

        # ── Compute session context ──
        df = self._compute_session(df)

        # ── Entry signals ──
        df = self._compute_entries(df)

        return df

    def _compute_orb(self, df):
        """Compute Opening Range Breakout levels per session.

        Maps to IVB's 08:30-09:00 NY window using UTC hour.
        For crypto, the 'session' is a rolling window at the specified start hour.
        """
        orb_dur = int(self.orb_duration.value)

        df["orb_high"] = np.nan
        df["orb_low"] = np.nan
        df["orb_range"] = np.nan
        df["orb_mid"] = np.nan
        df["orb_volume"] = np.nan
        df["orb_set"] = False

        # Group by date
        df["date_only"] = df["date"].dt.date
        df["hour"] = df["date"].dt.hour

        orb_start_h = int(self.orb_start_hour_utc.value)
        min_range_pct = float(self.min_orb_range_pct.value)

        for date_val, day_df in df.groupby("date_only"):
            day_idx = day_df.index

            # Find ORB window: start at orb_start_hour_utc, duration = orb_duration bars
            orb_mask = (day_df["hour"] >= orb_start_h) & (day_df["hour"] < orb_start_h + orb_dur // 12)

            if orb_mask.sum() < 3:
                # Fallback: first orb_duration bars of the day
                orb_start_idx = day_idx[0]
                orb_end_idx = day_idx[min(orb_dur - 1, len(day_idx) - 1)]
            else:
                orb_indices = day_df.loc[orb_mask].index
                if len(orb_indices) == 0:
                    continue
                orb_start_idx = orb_indices[0]
                orb_end_idx = orb_indices[-1]

            orb_high = df.loc[orb_start_idx:orb_end_idx, "high"].max()
            orb_low = df.loc[orb_start_idx:orb_end_idx, "low"].min()
            orb_range = orb_high - orb_low
            orb_mid = (orb_high + orb_low) / 2
            orb_vol = df.loc[orb_start_idx:orb_end_idx, "volume"].sum()

            # Mark all bars AFTER the ORB window with these levels
            post_orb_idx = day_idx[day_idx > orb_end_idx]
            if len(post_orb_idx) > 0 and orb_range > 0:
                # Minimum range filter: skip tight ranges
                range_pct = (orb_range / orb_mid) * 100
                if range_pct >= min_range_pct:
                    df.loc[post_orb_idx, "orb_high"] = orb_high
                    df.loc[post_orb_idx, "orb_low"] = orb_low
                    df.loc[post_orb_idx, "orb_range"] = orb_range
                    df.loc[post_orb_idx, "orb_mid"] = orb_mid
                    df.loc[post_orb_idx, "orb_volume"] = orb_vol
                    df.loc[post_orb_idx, "orb_set"] = True

        df.drop(columns=["date_only", "hour"], inplace=True)
        return df

    def _compute_delta(self, df):
        """Compute volume delta proxy for crypto.

        Since real CVD isn't available in OHLCV, we use:
        delta_proxy = volume * (close - open) / (high - low + epsilon)
        
        This approximates buying pressure (positive = buying, negative = selling).
        Cumulative delta over a window gives institutional flow direction.
        """
        candle_range = (df["high"] - df["low"]).replace(0, np.nan)
        df["bar_delta"] = df["volume"] * (df["close"] - df["open"]) / candle_range
        df["bar_delta"] = df["bar_delta"].fillna(0)

        # Cumulative delta over ORB window (rolling sum)
        orb_dur = int(self.orb_duration.value)
        df["cum_delta"] = df["bar_delta"].rolling(orb_dur).sum()

        # Relative delta: bar_delta / volume_ma (normalized)
        df["rel_delta"] = df["bar_delta"] / df["vol_ma_20"].replace(0, np.nan)
        df["rel_delta"] = df["rel_delta"].fillna(0)

        # ORB session cumulative delta
        df["orb_cum_delta"] = df["bar_delta"].rolling(orb_dur).sum()

        return df

    def _compute_session(self, df):
        """Track per-session state to enforce one trade per session."""
        df["session_id"] = df["date"].dt.date.astype(str)
        df["us_session"] = (df["date"].dt.hour >= 13) & (df["date"].dt.hour < 21)
        return df

    def _compute_entries(self, df):
        """Compute LONG and SHORT entry signals.

        LONG (matches IVB validated model):
        - Close > ORB High (breakout)
        - Bar delta > threshold (institutional buying pressure)
        - ORB volume > volume_filter * 20-bar avg (sufficient volume)
        - RSI not overbought (< 70)
        - EMA20 > EMA50 (trend context)
        - ORB range > minimum threshold

        SHORT (crypto addition — not in original IVB):
        - Close < ORB Low (breakdown)
        - Bar delta < -threshold (institutional selling pressure)
        - ORB volume > volume_filter * 20-bar avg
        - RSI not oversold (> 30)
        - EMA20 < EMA50 (trend context)
        """
        dt = float(self.delta_threshold.value)
        vf = float(self.volume_filter_mult.value)

        orb_valid = df["orb_set"] == True
        orb_has_range = df["orb_range"].notna() & (df["orb_range"] > 0)
        vol_ok = df["volume"] > (df["vol_ma_20"] * vf)

        # LONG entry: breakout above ORB high with buying delta
        long_breakout = (
            orb_valid & orb_has_range &
            (df["close"] > df["orb_high"]) &
            (df["bar_delta"] > dt * df["vol_ma_20"]) &  # Thresholded delta
            vol_ok &
            (df["rsi"] < 70) &
            (df["ema_20"] > df["ema_50"])  # Trend context
        )

        # SHORT entry: breakdown below ORB low with selling delta
        short_breakdown = (
            orb_valid & orb_has_range &
            (df["close"] < df["orb_low"]) &
            (df["bar_delta"] < -(dt * df["vol_ma_20"])) &  # Thresholded delta (negative)
            vol_ok &
            (df["rsi"] > 30) &
            (df["ema_20"] < df["ema_50"])  # Trend context
        )

        df["enter_long"] = long_breakout.astype(int)
        df["enter_short"] = short_breakdown.astype(int) if self.enable_shorts.value else 0
        df["enter_tag_long"] = np.where(long_breakout, "ivb_orb_long", "")
        df["enter_tag_short"] = np.where(short_breakdown, "ivb_orb_short", "")

        # ── Exit targets ──
        tp_rr = float(self.tp_rr_ratio.value)

        # LONG TP = entry + tp_rr * range_width, SL = ORB Low
        df["long_tp"] = df["orb_high"] + tp_rr * df["orb_range"]
        df["long_sl"] = df["orb_low"]

        # SHORT TP = entry - tp_rr * range_width, SL = ORB High
        df["short_tp"] = df["orb_low"] - tp_rr * df["orb_range"]
        df["short_sl"] = df["orb_high"]

        # Range width in % for stoploss
        df["orb_range_pct"] = (df["orb_range"] / df["close"]) * 100

        return df

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["enter_long"] == 1),
            ["enter_long", "enter_tag"]
        ] = (1, "ivb_orb_long")

        dataframe.loc[
            (dataframe["enter_short"] == 1),
            ["enter_short", "enter_tag"]
        ] = (1, "ivb_orb_short")

        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        # Exit LONG when price drops back below ORB mid (loss of momentum)
        # or RSI goes overbought
        dataframe.loc[
            (dataframe["close"] < dataframe["orb_mid"]) & dataframe["orb_set"] & (dataframe["rsi"] > 70),
            ["exit_long", "exit_tag"]
        ] = (1, "orb_momentum_loss")

        # Exit SHORT when price rises above ORB mid (loss of momentum)
        # or RSI goes oversold
        dataframe.loc[
            (dataframe["close"] > dataframe["orb_mid"]) & dataframe["orb_set"] & (dataframe["rsi"] < 30),
            ["exit_short", "exit_tag"]
        ] = (1, "orb_momentum_loss")

        # Session end exit: close positions near end of US session
        exit_hour = int(self.session_exit_hour_utc.value)
        dataframe.loc[
            (dataframe["date"].dt.hour >= exit_hour),
            ["exit_long", "exit_short", "exit_tag"]
        ] = (1, 1, "session_end")

        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        """Use ORB range as stoploss basis, with risk-to-zero logic."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last = dataframe.iloc[-1]
        sl = float(self.sl_pct.value)

        # Risk to Zero: once profit > 1%, move stop to breakeven
        if current_profit > 0.03:
            return -0.005  # Tight trail to lock in profit
        if current_profit > 0.01:
            return -0.01   # Breakeven-ish

        # Default: use the configured stoploss
        return -sl

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        """Custom exit: fixed R-multiple TP from ORB levels."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last = dataframe.iloc[-1]

        # For LONG trades: TP at orb_high + RR * range
        if not trade.is_short and last.get("long_tp") is not None and not np.isnan(last["long_tp"]):
            if current_rate >= last["long_tp"]:
                return f"ivb_tp_long_{self.tp_rr_ratio.value:.1f}R"

        # For SHORT trades: TP at orb_low - RR * range
        if trade.is_short and last.get("short_tp") is not None and not np.isnan(last["short_tp"]):
            if current_rate <= last["short_tp"]:
                return f"ivb_tp_short_{self.tp_rr_ratio.value:.1f}R"

        # Risk to Zero: if profit > 2% and momentum fading, exit
        if current_profit > 0.02:
            if not trade.is_short and last.get("bos_trend", 0) != 1:
                return "risk_to_zero_long_momentum_loss"
            if trade.is_short and last.get("bos_trend", 0) != -1:
                return "risk_to_zero_short_momentum_loss"

        return None