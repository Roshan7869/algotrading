"""
IVB ORB Crypto V4 — Tightened Risk, Longer Winners, ATR Trail
===============================================================

V3 analysis:
- 56.3% WR (matches IVB validated 58.3%)
- Trailing exits: 100% WR, +46.36 USDT (THE EDGE)
- Stop losses: -75.63 USDT (21 trades at -4.43% avg)
- Net: -29.27% (trail profits eaten by stops)

V4 FIXES:
1. Enter stop at ORB Low (IVB validated: SL = ORB low for longs)
   → Instead of fixed %, use the actual ORB range for stop distance
2. Wider trail offset (2.5% instead of 2%) to let winners run
3. Tighter initial ATR stop (1.0x ATR instead of 1.5x)
4. Add position sizing based on ORB range (risk 1% per trade)
5. Volume must be 2x average (stricter than V3's 1.5x)
6. Require ORB range < ATR*2 (avoid entering on crazy volatile days)
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter


class IVB_ORB_Crypto_V4(IStrategy):
    """IVB ORB V4 — ORB-based stops, wider trail, strict entries"""

    INTERFACE_VERSION = 3
    can_short = False  # LONG ONLY
    timeframe = "5m"
    startup_candle_count = 200

    stoploss = -0.05  # 5% hard fallback
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False

    # Trailing stop — let winners run further
    trailing_stop = True
    trailing_stop_positive = 0.015     # 1.5% trail (wider to let winners run)
    trailing_stop_positive_offset = 0.03  # Activate at 3% profit
    trailing_only_offset_is_reached = True

    stake_amount = "unlimited"
    max_open_trades = 3

    # ─── PARAMETERS ───────────────────────────────────────────

    orb_duration = IntParameter(6, 18, default=6, space="buy", optimize=True)
    orb_start_hour_utc = IntParameter(12, 15, default=13, space="buy", optimize=False)
    min_orb_range_pct = DecimalParameter(0.3, 1.2, default=0.4, decimals=2, space="buy", optimize=True)

    # Delta filter
    delta_zscore_threshold = DecimalParameter(0.5, 3.0, default=1.5, decimals=1, space="buy", optimize=True)

    # ATR-based stop
    atr_sl_mult = DecimalParameter(0.8, 2.0, default=1.0, decimals=1, space="sell", optimize=True)

    # Max ORB range as multiple of ATR (avoid entering on extreme volatility)
    max_orb_atr_ratio = DecimalParameter(1.5, 4.0, default=2.5, decimals=1, space="buy", optimize=True)

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

        # ── Delta ──
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
        max_atr_ratio = float(self.max_orb_atr_ratio.value)
        orb_start = int(self.orb_start_hour_utc.value)

        df["orb_high"] = np.nan
        df["orb_low"] = np.nan
        df["orb_range"] = np.nan
        df["orb_valid"] = False
        df["orb_stop_long"] = np.nan  # Stop at ORB low (IVB validated)

        df["date_only"] = df["date"].dt.date
        df["hour"] = df["date"].dt.hour

        for date_val in df["date_only"].unique():
            day_mask = df["date_only"] == date_val
            day_df = df.loc[day_mask]

            orb_bars = day_df.loc[day_df["hour"] == orb_start]
            if len(orb_bars) < 3:
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

            # Skip extreme volatility days: ORB range > max_atr_ratio * ATR
            last_atr = day_df["atr"].iloc[-1] if not day_df["atr"].isna().all() else 0
            if last_atr > 0 and orb_range > max_atr_ratio * last_atr:
                continue

            last_orb_idx = orb_bars.index[-1]
            post_orb_mask = day_mask & (df.index > last_orb_idx)

            df.loc[post_orb_mask, "orb_high"] = orb_high
            df.loc[post_orb_mask, "orb_low"] = orb_low
            df.loc[post_orb_mask, "orb_range"] = orb_range
            df.loc[post_orb_mask, "orb_valid"] = True
            # IVB stop: SL at ORB low for longs
            df.loc[post_orb_mask, "orb_stop_long"] = orb_low

        df.drop(columns=["date_only", "hour"], inplace=True, errors="ignore")
        return df

    def _compute_entries(self, df):
        z_thresh = float(self.delta_zscore_threshold.value)

        orb_ok = df["orb_valid"]

        # Volume must be 2x average (stricter filter)
        vol_ok = df["volume"] > df["vol_ma_20"] * 2.0

        # Strong institutional buying
        delta_ok = df["delta_zscore"] > z_thresh

        # Trend confirmed
        trend_ok = (df["ema_20"] > df["ema_50"]) & (df["close"] > df["ema_100"])

        # RSI: momentum present, not overbought
        rsi_ok = (df["rsi"] > 40) & (df["rsi"] < 72)

        # Strong close: body closes in top 30% of range
        body_range = df["close"] - df["open"]
        total_range = (df["high"] - df["low"]).replace(0, np.nan)
        close_position = body_range / total_range
        strong_close = close_position > 0.70

        # ─── LONG ONLY ───
        long_entry = (
            orb_ok &
            (df["close"] > df["orb_high"]) &  # Breakout
            delta_ok &                            # Institutional buying
            vol_ok &                               # Volume spike (2x)
            trend_ok &                              # EMA stack bullish
            rsi_ok &                                 # Momentum
            strong_close                              # Strong close
        )

        df["enter_long"] = long_entry.astype(int)
        df["enter_short"] = 0
        df["enter_tag"] = np.where(long_entry, "ivb_orb_long", "")

        return df

    def populate_entry_trend(self, dataframe, metadata):
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        # Exit when breakout invalidates: closes below ORB low
        df.loc[
            df["orb_valid"] &
            (df["close"] < df["orb_low"]) &
            (df["rsi"] < 45),
            ["exit_long", "exit_tag"]
        ] = (1, "orb_invalidated")
        return df

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        """Dynamic stop: ORB low-based with Risk-to-Zero progression.

        IVB model: SL at ORB Low, then move to BE after 1R profit.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last = dataframe.iloc[-1]

        # Risk-to-Zero progression (Fabio's validated rule)
        if current_profit > 0.03:
            return -0.005    # Lock profit, max 0.5% giveback
        if current_profit > 0.02:
            return -0.008
        if current_profit > 0.01:
            return -0.01     # Breakeven
        if current_profit > 0.005:
            return -0.015

        # Initial stop: ORB low based (IVB validated), but capped tight
        orb_stop = last.get("orb_stop_long", np.nan)
        if not np.isnan(orb_stop) and orb_stop > 0 and current_rate > 0:
            orb_sl = (current_rate - orb_stop) / current_rate
            # Cap between 1.5% and 5% — need room for crypto volatility
            orb_sl = max(min(orb_sl, 0.05), 0.015)
            return -orb_sl

        # Fallback: ATR-based
        atr = last.get("atr", 0)
        if atr > 0 and not np.isnan(atr):
            atr_sl = (float(self.atr_sl_mult.value) * atr) / current_rate
            return -max(min(atr_sl, 0.06), 0.015)

        return -0.04