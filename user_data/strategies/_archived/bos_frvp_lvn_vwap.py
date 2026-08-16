"""
BOS + FRVP + LVN + VWAP Confluence Strategy for Freqtrade
=========================================================
Adapted from PDF: BOS_FRVP_LVN_VWAP_Strategy.pdf

4-Pillar Entry (requires 3-of-4 minimum):
  1. BOS (Break of Structure) — price breaks key swing high/low
  2. LVN (Low Volume Node) — price in thin volume zone (retracement)
  3. VWAP (Volume Weighted Average Price) — price near VWAP
  4. Confirmation candle — directional body >= 40% of range

Exit: Structure-based (BOS reversal) + RSI exhaustion + trailing

Key adaptations for 1h crypto:
 - VWAP proximity relaxed to 0.5% (0.05% is too tight for crypto)
 - Tiered entry: ALL 4 = "full_confluence", ANY 3-of-4 = "partial_confluence"  
 - Separate long/short with can_short=True
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter


class BOS_FRVP_LVN_VWAP(IStrategy):
    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    # Hard stop at 8%, but custom_stoploss takes over earlier
    stoploss = -0.08
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False

    # Trailing: 2.5% trail after 12% (let winners run)
    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.12
    trailing_only_offset_is_reached = True

    stake_amount = "unlimited"
    max_open_trades = 10

    # ─── TUNABLE PARAMETERS ──────────────────────────────────────────
    swing_lookback = IntParameter(10, 40, default=20, space="buy", optimize=False)
    volume_bins = IntParameter(15, 50, default=25, space="buy", optimize=False)
    lvn_threshold = DecimalParameter(0.2, 0.7, default=0.5, decimals=2, space="buy", optimize=False)

    # VWAP proximity — 0.5% for 1h crypto (0.05% was too tight)
    vwap_proximity_pct = DecimalParameter(0.3, 1.5, default=0.5, decimals=2, space="buy", optimize=False)

    min_body_ratio = DecimalParameter(0.3, 0.7, default=0.4, decimals=2, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=12.0, decimals=1, space="buy", optimize=False)

    # Required confluences: 3 = 3-of-4, 4 = all-4
    min_confluences = IntParameter(3, 4, default=3, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    # ─── INDICATORS ──────────────────────────────────────────────────

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe.copy()

        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()

        # EMAs for trend context
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

        # VWAP (daily reset)
        df = self._compute_vwap(df)

        # Swing detection + BOS
        df = self._compute_bos(df)

        # Volume profile + LVN
        df = self._compute_volume_profile(df)

        # Confluence scoring
        df = self._compute_confluence(df)

        return df

    def _compute_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap_tp_vol"] = typical_price * df["volume"]
        df["date_only"] = df["date"].dt.date
        cum_tp_vol = df.groupby("date_only")["vwap_tp_vol"].cumsum()
        cum_vol = df.groupby("date_only")["volume"].cumsum()
        df["vwap"] = cum_tp_vol / cum_vol.replace(0, np.nan)
        df["vwap"] = df["vwap"].ffill()
        df["vwap_dist_pct"] = ((df["close"] - df["vwap"]) / df["vwap"]) * 100
        df["vwap_slope"] = df["vwap"].diff(3) / df["vwap"].shift(3) * 100
        df.drop(columns=["date_only", "vwap_tp_vol"], inplace=True)
        return df

    def _compute_bos(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.swing_lookback.value)
        half = lookback // 2

        highs = df["high"].values
        lows = df["low"].values
        n = len(df)

        # Swing detection
        is_sh = np.zeros(n, dtype=bool)
        is_sl = np.zeros(n, dtype=bool)
        for i in range(half, n - half):
            window_h = highs[i - half:i + half + 1]
            window_l = lows[i - half:i + half + 1]
            if highs[i] == np.max(window_h):
                is_sh[i] = True
            if lows[i] == np.min(window_l):
                is_sl[i] = True

        df["is_swing_high"] = is_sh.astype(int)
        df["is_swing_low"] = is_sl.astype(int)

        # Forward-fill last swing levels
        last_sh = np.full(n, np.nan)
        last_sl = np.full(n, np.nan)
        sh_val = np.nan
        sl_val = np.nan
        for i in range(n):
            if is_sh[i]:
                sh_val = highs[i]
            if is_sl[i]:
                sl_val = lows[i]
            last_sh[i] = sh_val
            last_sl[i] = sl_val

        df["last_swing_high"] = last_sh
        df["last_swing_low"] = last_sl

        # BOS state machine
        bullish_bos = ((df["close"] > pd.Series(last_sh).shift(1)) & pd.Series(last_sh).shift(1).notna()).astype(int)
        bearish_bos = ((df["close"] < pd.Series(last_sl).shift(1)) & pd.Series(last_sl).shift(1).notna()).astype(int)

        bos_trend = np.zeros(n, dtype=int)
        state = 0
        for i in range(n):
            if bullish_bos.iloc[i] == 1:
                state = 1
            elif bearish_bos.iloc[i] == 1:
                state = -1
            bos_trend[i] = state
        df["bos_trend"] = bos_trend

        # EMA trend alignment (stronger BOS)
        df["ema_trend_bullish"] = (df["close"] > df["ema_50"]).astype(int)
        df["ema_trend_bearish"] = (df["close"] < df["ema_50"]).astype(int)

        return df

    def _compute_volume_profile(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.swing_lookback.value)
        n_bins = int(self.volume_bins.value)
        lvn_thresh = float(self.lvn_threshold.value)
        vwap_prox = float(self.vwap_proximity_pct.value)
        n = len(df)
        lvn_top = np.full(n, np.nan)
        lvn_bottom = np.full(n, np.nan)
        poc_level = np.full(n, np.nan)

        highs = df["high"].values
        lows = df["low"].values
        volumes = df["volume"].values
        closes = df["close"].values

        for i in range(lookback, n):
            win_low = lows[i - lookback:i + 1].min()
            win_high = highs[i - lookback:i + 1].max()
            if win_high == win_low:
                continue

            bin_edges = np.linspace(win_low, win_high, n_bins + 1)
            vol_per_bin = np.zeros(n_bins)

            for j in range(i - lookback, i + 1):
                if volumes[j] <= 0:
                    continue
                candle_range = highs[j] - lows[j]
                if candle_range <= 0:
                    continue
                overlaps = np.maximum(0, np.minimum(highs[j], bin_edges[1:]) - np.maximum(lows[j], bin_edges[:-1]))
                vol_per_bin += volumes[j] * (overlaps / candle_range)

            total_vol = vol_per_bin.sum()
            if total_vol == 0:
                continue

            poc_bin = np.argmax(vol_per_bin)
            poc_volume = vol_per_bin[poc_bin]
            poc_level[i] = (bin_edges[poc_bin] + bin_edges[poc_bin + 1]) / 2

            lvn_bins = np.where((vol_per_bin > 0) & (vol_per_bin < lvn_thresh * poc_volume))[0]
            if len(lvn_bins) > 0:
                zones = []
                start = lvn_bins[0]
                for k in range(1, len(lvn_bins)):
                    if lvn_bins[k] != lvn_bins[k - 1] + 1:
                        zones.append((start, lvn_bins[k - 1]))
                        start = lvn_bins[k]
                zones.append((start, lvn_bins[-1]))

                current_close = closes[i]
                best_zone = None
                best_dist = float("inf")
                for zs, ze in zones:
                    zone_mid = (bin_edges[zs] + bin_edges[ze + 1]) / 2
                    dist = abs(zone_mid - current_close)
                    if dist < best_dist:
                        best_dist = dist
                        best_zone = (zs, ze)

                if best_zone is not None:
                    lvn_bottom[i] = bin_edges[best_zone[0]]
                    lvn_top[i] = bin_edges[best_zone[1] + 1]

        df["lvn_top"] = lvn_top
        df["lvn_bottom"] = lvn_bottom
        df["poc_level"] = poc_level

        # Price in LVN zone
        df["price_in_lvn"] = (
            df["lvn_bottom"].notna() &
            (df["close"] >= df["lvn_bottom"]) &
            (df["close"] <= df["lvn_top"])
        ).astype(int)

        # Price near VWAP (relaxed for crypto volatility)
        df["near_vwap"] = (df["vwap_dist_pct"].abs() <= vwap_prox).astype(int)

        return df

    def _compute_confluence(self, df: pd.DataFrame) -> pd.DataFrame:
        min_br = float(self.min_body_ratio.value)

        # Candle body ratio + confirmation
        df["body"] = (df["close"] - df["open"]).abs()
        df["candle_range"] = df["high"] - df["low"]
        df["body_ratio"] = df["body"] / df["candle_range"].replace(0, np.nan)

        df["bearish_candle"] = ((df["close"] < df["open"]) & (df["body_ratio"] >= min_br)).astype(int)
        df["bullish_candle"] = ((df["close"] > df["open"]) & (df["body_ratio"] >= min_br)).astype(int)

        df["vwap_declining"] = (df["vwap_slope"] < 0).astype(int)
        df["vwap_rising"] = (df["vwap_slope"] > 0).astype(int)

        # ── SHORT confluences ──
        df["short_bos"] = (df["bos_trend"] == -1).astype(int)
        df["short_lvn"] = df["price_in_lvn"]
        df["short_vwap"] = (df["near_vwap"] & df["vwap_declining"]).astype(int)
        # Relaxed: VWAP near even without slope (just near VWAP is supportive)
        df["short_vwap_relaxed"] = df["near_vwap"]
        df["short_confirm"] = df["bearish_candle"]

        # Score: sum of 4 pillars
        df["short_pillars"] = df["short_bos"] + df["short_lvn"] + df["short_vwap_relaxed"] + df["short_confirm"]
        # Full confluence needs: BOS + at least 2 others
        df["short_full_confluence"] = (
            (df["short_bos"] == 1) &
            (df["short_pillars"] >= 4)  # ALL 4 pillars
        ).astype(int)
        df["short_partial_confluence"] = (
            (df["short_bos"] == 1) &
            (df["short_pillars"] >= 3)  # 3-of-4 pillars
        ).astype(int)

        # ── LONG confluences ──
        df["long_bos"] = (df["bos_trend"] == 1).astype(int)
        df["long_lvn"] = df["price_in_lvn"]
        df["long_vwap"] = (df["near_vwap"] & df["vwap_rising"]).astype(int)
        df["long_vwap_relaxed"] = df["near_vwap"]
        df["long_confirm"] = df["bullish_candle"]

        df["long_pillars"] = df["long_bos"] + df["long_lvn"] + df["long_vwap_relaxed"] + df["long_confirm"]
        df["long_full_confluence"] = (
            (df["long_bos"] == 1) &
            (df["long_pillars"] >= 4)
        ).astype(int)
        df["long_partial_confluence"] = (
            (df["long_bos"] == 1) &
            (df["long_pillars"] >= 3)
        ).astype(int)

        return df

    # ─── ENTRY / EXIT ────────────────────────────────────────────────

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        min_conf = int(self.min_confluences.value)

        # Use 3-of-4 (partial) or 4-of-4 (full) based on parameter
        if min_conf >= 4:
            long_cond = dataframe["long_full_confluence"] == 1
            short_cond = dataframe["short_full_confluence"] == 1
        else:
            long_cond = dataframe["long_partial_confluence"] == 1
            short_cond = dataframe["short_partial_confluence"] == 1

        dataframe.loc[
            long_cond & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "bos_frvp_lvn_vwap_long")

        dataframe.loc[
            short_cond & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "bos_frvp_lvn_vwap_short")

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # Exit long: RSI > 70 or BOS turns bearish
        dataframe.loc[
            (dataframe["rsi"] > 70) | (dataframe["bos_trend"] == -1),
            ["exit_long", "exit_tag"]
        ] = (1, "rsi_ob_or_bearish_bos")

        # Exit short: RSI < 30 or BOS turns bullish
        dataframe.loc[
            (dataframe["rsi"] < 30) | (dataframe["bos_trend"] == 1),
            ["exit_short", "exit_tag"]
        ] = (1, "rsi_os_or_bullish_bos")

        return dataframe

    # ─── CUSTOM STOP / EXIT ───────────────────────────────────────────

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        if current_profit > 0.05:
            return -0.01  # Breakeven+ after 5%
        if current_profit > 0.03:
            return -0.02  # Tight after 3%
        return None

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last = dataframe.iloc[-1]

        # Structure reversal exits (only if in profit)
        if not trade.is_short and last.get("bos_trend", 0) == -1 and current_profit > 0.02:
            return "bearish_bos_reversal"
        if trade.is_short and last.get("bos_trend", 0) == 1 and current_profit > 0.02:
            return "bullish_bos_reversal"

        return None