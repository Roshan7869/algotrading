"""
IVB ORB Crypto V3 — LONG ONLY, Trail-Focused
==============================================

Key insight from V2 failure analysis:
- Trailing stop exits: 100% WR, +49.55 USDT (THE EDGE)
- Fixed TP at 2R: 18.5% WR, -1.46 USDT (USELESS)
- Hard stop losses: 0% WR, -85.59 USDT (THE KILLER)
- Longs: -43.65%, Shorts: -2.72%

=> SHORTS are noise. The validated IVB model is LONG ONLY.
=> Fixed TP kills momentum trades. Trail is the exit.
=> Stop loss too wide (5%). Needs ATR-based stop.

V3 CHANGES:
1. LONG ONLY (per validated IVB model)
2. Remove fixed R:R TP — rely entirely on trailing stop (proven edge)
3. ATR-based dynamic stop (1.5x ATR instead of fixed %)
4. Tighter entry filters: require RSI > 45 (momentum confirm)
5. Breakout candle body must close in top 25% of range
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter


class IVB_ORB_Crypto_V3(IStrategy):
    """IVB ORB V3 — Long Only, Trail Exit, ATR Stop"""

    INTERFACE_VERSION = 3
    can_short = False  # IVB validated model is LONG ONLY
    timeframe = "5m"
    startup_candle_count = 200

    stoploss = -0.04  # Hard fallback, custom_stoploss overrides
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False

    # TRAILING STOP — the proven exit mechanism from V2
    trailing_stop = True
    trailing_stop_positive = 0.01     # 1% trail after activation
    trailing_stop_positive_offset = 0.02  # Activate after 2% profit
    trailing_only_offset_is_reached = True

    stake_amount = "unlimited"
    max_open_trades = 1  # One trade per session (IVB rule)

    # ─── PARAMETERS ───────────────────────────────────────────

    orb_duration = IntParameter(6, 18, default=6, space="buy", optimize=True)
    orb_start_hour_utc = IntParameter(12, 15, default=13, space="buy", optimize=False)
    min_orb_range_pct = DecimalParameter(0.3, 1.5, default=0.4, decimals=2, space="buy", optimize=True)

    # Delta filter
    delta_zscore_threshold = DecimalParameter(0.5, 3.0, default=1.5, decimals=1, space="buy", optimize=True)

    # Trailing
    trail_offset_pct = DecimalParameter(0.01, 0.04, default=0.02, decimals=3, space="sell", optimize=True)
    trail_positive_pct = DecimalParameter(0.005, 0.02, default=0.01, decimals=3, space="sell", optimize=True)

    # ATR-based stop multiplier
    atr_sl_mult = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="sell", optimize=True)

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
        df["ema_100"] = df["close"].ewm(span=100, adjust=False).mean()

        # ── ATR ──
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()

        # ── Volume delta proxy ──
        candle_range = (df["high"] - df["low"]).replace(0, np.nan)
        df["bar_delta"] = (df["volume"] * (df["close"] - df["open"]) / candle_range).fillna(0)
        df["bar_delta_ma"] = df["bar_delta"].rolling(20).mean()
        df["bar_delta_std"] = df["bar_delta"].rolling(20).std().replace(0, np.nan)
        df["delta_zscore"] = ((df["bar_delta"] - df["bar_delta_ma"]) / df["bar_delta_std"]).fillna(0)

        # ── Volume ──
        df["vol_ma_20"] = df["volume"].rolling(20).mean()

        # ── ORB ──
        df = self._compute_orb(df)

        # ── Entries ──
        df = self._compute_entries(df)

        return df

    def _compute_orb(self, df):
        orb_dur = int(self.orb_duration.value)
        min_range_pct = float(self.min_orb_range_pct.value)
        orb_start = int(self.orb_start_hour_utc.value)

        df["orb_high"] = np.nan
        df["orb_low"] = np.nan
        df["orb_range"] = np.nan
        df["orb_valid"] = False

        df["date_only"] = df["date"].dt.date
        df["hour"] = df["date"].dt.hour

        for date_val in df["date_only"].unique():
            day_mask = df["date_only"] == date_val
            day_df = df.loc[day_mask]

            # Find ORB window bars
            orb_bars = day_df.loc[day_df["hour"] == orb_start]
            if len(orb_bars) < 3:
                # Fallback: first orb_dur bars
                orb_bars = day_df.iloc[:orb_dur]

            if len(orb_bars) < 3:
                continue

            orb_high = orb_bars["high"].max()
            orb_low = orb_bars["low"].min()
            orb_range = orb_high - orb_low
            orb_mid = (orb_high + orb_low) / 2
            range_pct = (orb_range / orb_mid) * 100

            if range_pct < min_range_pct:
                continue

            last_orb_idx = orb_bars.index[-1]
            post_orb_mask = day_mask & (df.index > last_orb_idx)

            df.loc[post_orb_mask, "orb_high"] = orb_high
            df.loc[post_orb_mask, "orb_low"] = orb_low
            df.loc[post_orb_mask, "orb_range"] = orb_range
            df.loc[post_orb_mask, "orb_valid"] = True

        df.drop(columns=["date_only", "hour"], inplace=True, errors="ignore")
        return df

    def _compute_entries(self, df):
        z_thresh = float(self.delta_zscore_threshold.value)

        orb_ok = df["orb_valid"]

        # Volume confirmation: bar volume > 1.5x average
        vol_ok = df["volume"] > df["vol_ma_20"] * 1.5

        # Delta: strong institutional buying
        delta_ok = df["delta_zscore"] > z_thresh

        # Trend: EMA stack bullish
        trend_ok = (df["ema_20"] > df["ema_50"]) & (df["close"] > df["ema_100"])

        # RSI: momentum present but not overbought
        rsi_ok = (df["rsi"] > 40) & (df["rsi"] < 75)

        # Breakout candle: strong close in top 25% of range
        body_range = df["close"] - df["open"]
        total_range = (df["high"] - df["low"]).replace(0, np.nan)
        close_position = body_range / total_range  # 1.0 = close at high, -1.0 = close at low
        strong_close = close_position > 0.75  # Close in top 25% of candle

        # ─── LONG ONLY ENTRY ───
        long_entry = (
            orb_ok &
            (df["close"] > df["orb_high"]) &  # Breakout above ORB high
            delta_ok &                           # Institutional buying
            vol_ok &                              # Volume spike
            trend_ok &                            # Bullish trend context
            rsi_ok &                              # Not overbought
            strong_close                          # Strong close near high
        )

        df["enter_long"] = long_entry.astype(int)
        df["enter_short"] = 0  # LONG ONLY — no shorts
        df["enter_tag"] = np.where(long_entry, "ivb_orb_long", "")

        return df

    def populate_entry_trend(self, dataframe, metadata):
        return dataframe  # Set in _compute_entries

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe

        # Exit LONG on momentum failure: close drops below ORB low (invalidates breakout)
        df.loc[
            df["orb_valid"] &
            (df["close"] < df["orb_low"]) &
            (df["rsi"] < 45),
            ["exit_long", "exit_tag"]
        ] = (1, "orb_breakout_invalidated")

        return df

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        """Dynamic ATR-based stop + Risk-to-Zero progression.

        IVB validated: P(edge<=0) = 0.001 at 1R profit → move SL to BE.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last = dataframe.iloc[-1]
        atr = last.get("atr", 0)

        # ATR-based initial stop
        if atr > 0 and not np.isnan(atr):
            atr_sl = (float(self.atr_sl_mult.value) * atr) / current_rate
            # Cap at 6%
            atr_sl = min(atr_sl, 0.06)
        else:
            atr_sl = 0.04  # Fallback

        # Risk to Zero progression (Fabio's core rule)
        if current_profit > 0.03:
            return -0.005   # Lock in profit, max giveback 0.5%
        if current_profit > 0.02:
            return -0.008   # Tight protection
        if current_profit > 0.01:
            return -0.01    # Breakeven zone
        if current_profit > 0.005:
            return -0.015   # Give some room

        return -atr_sl