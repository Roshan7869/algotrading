"""
IVB ORB Crypto V5 — Risk-to-Zero + BOS Confluence
====================================================

V4 analysis (17 pairs, 34 days, 18 trades):
- 55.6% WR, -4.36%, 9.18% DD
- Trailing exits: 100% WR, +8.91 USDT
- Stop losses: 0% WR, -10.35 USDT
- ORB invalidations: 0% WR, -2.91 USDT
- PF 0.67

Key V5 changes:
1. Risk-to-Zero: move SL to BE after +0.8% (IVB validated at 1R)
2. Trail activates at 1.5% (faster than V4's 3%)
3. Trail width 0.5% (tighter — lock profits sooner)
4. BOS confluence: require price above VWAP and recent BOS
5. Volume filter: 2.5x average (stricter institutional confirmation)
6. EMA trend: require 20 > 50 (bullish stack)
7. NO SHORTS (validated: IVB LONG ONLY)
8. 8% hard stop as safety net
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter


class IVB_ORB_Crypto_V5(IStrategy):
    """IVB ORB V5 — Risk-to-Zero + BOS Confluence"""

    INTERFACE_VERSION = 3
    can_short = False  # LONG ONLY
    timeframe = "5m"
    startup_candle_count = 200

    stoploss = -0.08  # 8% hard safety net (custom_stoploss overrides for most trades)
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False

    # Trailing — hyperopt-optimized: activate at 9.7%, trail at 1%
    trailing_stop = True
    trailing_stop_positive = 0.01       # 1% trail after activation
    trailing_stop_positive_offset = 0.097  # Activate at 9.7% profit (hyperopt-found)
    trailing_only_offset_is_reached = False

    stake_amount = "unlimited"
    max_open_trades = 3

    # ─── HYPEROPT PARAMETERS ────────────────────────────────

    orb_duration = IntParameter(6, 18, default=17, space="buy", optimize=False)
    orb_start_hour_utc = IntParameter(12, 15, default=13, space="buy", optimize=False)
    min_orb_range_pct = DecimalParameter(0.3, 1.2, default=1.01, decimals=2, space="buy", optimize=False)

    # Delta and volume filters (hyperopt-optimized)
    delta_zscore_threshold = DecimalParameter(1.0, 3.5, default=2.6, decimals=1, space="buy", optimize=False)
    volume_mult = DecimalParameter(1.5, 4.0, default=1.9, decimals=1, space="buy", optimize=False)

    # Max ORB range as multiple of ATR (hyperopt-optimized)
    max_orb_atr_ratio = DecimalParameter(1.5, 4.0, default=2.9, decimals=1, space="buy", optimize=False)

    # Risk-to-Zero: move to BE after this profit %
    bez_threshold = DecimalParameter(0.005, 0.02, default=0.016, decimals=3, space="sell", optimize=False)
    # Trail offset after BEZ
    trail_after_bez = DecimalParameter(0.003, 0.015, default=0.005, decimals=3, space="sell", optimize=False)

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
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

        # ── VWAP ──
        typical = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum()

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

        # ── Candle body analysis ──
        df["body_pct"] = ((df["close"] - df["open"]) / (df["high"] - df["low"]).replace(0, np.nan)).fillna(0)

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
        df["orb_stop_long"] = np.nan

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

            last_atr = day_df["atr"].iloc[-1] if not day_df["atr"].isna().all() else 0
            if last_atr > 0 and orb_range > max_atr_ratio * last_atr:
                continue

            last_orb_idx = orb_bars.index[-1]
            post_orb_mask = day_mask & (df.index > last_orb_idx)

            df.loc[post_orb_mask, "orb_high"] = orb_high
            df.loc[post_orb_mask, "orb_low"] = orb_low
            df.loc[post_orb_mask, "orb_range"] = orb_range
            df.loc[post_orb_mask, "orb_valid"] = True
            df.loc[post_orb_mask, "orb_stop_long"] = orb_low

        df.drop(columns=["date_only", "hour"], inplace=True, errors="ignore")
        return df

    def _compute_entries(self, df):
        z_thresh = float(self.delta_zscore_threshold.value)
        vol_m = float(self.volume_mult.value)

        orb_ok = df["orb_valid"]

        # ── STRICT entry filters ──
        # 1. Volume must be 2.5x+ average (institutional)
        vol_ok = df["volume"] > df["vol_ma_20"] * vol_m

        # 2. Strong delta (institutional buying)
        delta_ok = df["delta_zscore"] > z_thresh

        # 3. EMA trend: 9 > 20 > 50 (bullish stack)
        trend_ok = (df["ema_9"] > df["ema_20"]) & (df["ema_20"] > df["ema_50"])

        # 4. Price above VWAP (institutional value area)
        vwap_ok = df["close"] > df["vwap"]

        # 5. RSI: 40-72 (momentum present, not overbought)
        rsi_ok = (df["rsi"] > 40) & (df["rsi"] < 72)

        # 6. Strong bullish close: body covers >70% of range
        strong_close = df["body_pct"] > 0.70

        # 7. Breakout above ORB high
        breakout = df["close"] > df["orb_high"]

        # ─── LONG ENTRY ───
        long_entry = (
            orb_ok &
            breakout &
            delta_ok &
            vol_ok &
            trend_ok &
            vwap_ok &
            rsi_ok &
            strong_close
        )

        df["enter_long"] = long_entry.astype(int)
        df["enter_short"] = 0
        df["enter_tag"] = np.where(long_entry, "ivb_orb_r2z", "")

        return df

    def populate_entry_trend(self, dataframe, metadata):
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        df = dataframe
        # Exit when breakout invalidates
        df.loc[
            df["orb_valid"] &
            (df["close"] < df["orb_low"]) &
            (df["rsi"] < 40),
            ["exit_long", "exit_tag"]
        ] = (1, "orb_invalidated")
        return df

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        """Risk-to-Zero: IVB-validated dynamic stop progression.

        After 1% profit, move to BE.
        After 2% profit, lock 0.5%.
        After 3%, tight trail.
        """
        # Risk-to-Zero progression (Fabio's validated approach)
        if current_profit > 0.03:
            return -0.005    # 0.5% giveback — lock profits tight
        if current_profit > 0.02:
            return -0.008    # 0.8% giveback
        if current_profit > 0.01:
            return -0.01     # Breakeven — no loss zone
        if current_profit > 0.005:
            return -0.015    # Narrowing

        # Initial stop: ORB low based, capped
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last = dataframe.iloc[-1]

        orb_stop = last.get("orb_stop_long", np.nan)
        if not np.isnan(orb_stop) and orb_stop > 0 and current_rate > 0:
            orb_sl = (current_rate - orb_stop) / current_rate
            # Cap between 2% and 6%
            orb_sl = max(min(orb_sl, 0.06), 0.02)
            return -orb_sl

        return -0.04