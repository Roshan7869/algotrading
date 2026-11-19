"""
V3: BOS+LVN+VWAP Entry + V6 Late Trail Exit (BEST OF BOTH)
============================================================
Entry: 3-of-4 BOS+LVN+VWAP+Confirmation confluence (SHORT only)
Exit: V6 Late Trail logic from MACD hedge study champion:
  - 2% trailing stop after 20% profit (let winners RUN)
  - Breakeven at 5% profit
  - RSI < 45 deep reversal exit (not RSI<30 which kills winners)
  - BOS reversal exit (structure flip)
  - Hard stop 8%

This merges the best entry signal (BOS confluence) with the best
exit logic (V6 Late Trail — +13.48% in hedge study, 100% WR on trailing exits).
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter


class BOS_V3_LateTrailMerge(IStrategy):
    """BOS+LVN+VWAP entry + V6 Late Trail exit — the fusion strategy"""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 100

    stoploss = -0.08
    minimal_roi = {"0": 100}  # No ROI exit — let trailing do the work
    use_exit_signal = True
    exit_profit_only = False

    # V6 Late Trail: 2% trail after 20% profit
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.20
    trailing_only_offset_is_reached = True

    stake_amount = "unlimited"
    max_open_trades = 5

    # Entry parameters
    swing_lookback = IntParameter(10, 40, default=20, space="buy", optimize=False)
    volume_bins = IntParameter(15, 50, default=25, space="buy", optimize=False)
    lvn_threshold = DecimalParameter(0.2, 0.7, default=0.5, decimals=2, space="buy", optimize=False)
    vwap_proximity_pct = DecimalParameter(0.3, 1.5, default=0.5, decimals=2, space="buy", optimize=False)
    min_body_ratio = DecimalParameter(0.3, 0.7, default=0.4, decimals=2, space="buy", optimize=False)
    leverage_num = DecimalParameter(1, 20, default=10.0, decimals=1, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def populate_indicators(self, dataframe, metadata):
        df = dataframe.copy()
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

        df = self._compute_vwap(df)
        df = self._compute_bos(df)
        df = self._compute_volume_profile(df)
        df = self._compute_confluence(df)
        return df

    def _compute_vwap(self, df):
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

    def _compute_bos(self, df):
        lookback = int(self.swing_lookback.value)
        half = lookback // 2
        highs = df["high"].values
        lows = df["low"].values
        n = len(df)
        is_sh = np.zeros(n, dtype=bool)
        is_sl = np.zeros(n, dtype=bool)
        for i in range(half, n - half):
            if highs[i] == np.max(highs[i - half:i + half + 1]):
                is_sh[i] = True
            if lows[i] == np.min(lows[i - half:i + half + 1]):
                is_sl[i] = True

        last_sh = np.full(n, np.nan)
        last_sl = np.full(n, np.nan)
        sh_val = sl_val = np.nan
        for i in range(n):
            if is_sh[i]: sh_val = highs[i]
            if is_sl[i]: sl_val = lows[i]
            last_sh[i] = sh_val
            last_sl[i] = sl_val

        df["last_swing_high"] = last_sh
        df["last_swing_low"] = last_sl

        bullish_bos = ((df["close"] > pd.Series(last_sh).shift(1)) & pd.Series(last_sh).shift(1).notna()).astype(int)
        bearish_bos = ((df["close"] < pd.Series(last_sl).shift(1)) & pd.Series(last_sl).shift(1).notna()).astype(int)
        bos_trend = np.zeros(n, dtype=int)
        state = 0
        for i in range(n):
            if bullish_bos.iloc[i] == 1: state = 1
            elif bearish_bos.iloc[i] == 1: state = -1
            bos_trend[i] = state
        df["bos_trend"] = bos_trend
        return df

    def _compute_volume_profile(self, df):
        lookback = int(self.swing_lookback.value)
        n_bins = int(self.volume_bins.value)
        lvn_thresh = float(self.lvn_threshold.value)
        vwap_prox = float(self.vwap_proximity_pct.value)
        n = len(df)
        lvn_top = np.full(n, np.nan)
        lvn_bottom = np.full(n, np.nan)
        highs = df["high"].values
        lows = df["low"].values
        volumes = df["volume"].values
        closes = df["close"].values

        for i in range(lookback, n):
            win_low = lows[i - lookback:i + 1].min()
            win_high = highs[i - lookback:i + 1].max()
            if win_high == win_low: continue
            bin_edges = np.linspace(win_low, win_high, n_bins + 1)
            vol_per_bin = np.zeros(n_bins)
            for j in range(i - lookback, i + 1):
                if volumes[j] <= 0: continue
                candle_range = highs[j] - lows[j]
                if candle_range <= 0: continue
                overlaps = np.maximum(0, np.minimum(highs[j], bin_edges[1:]) - np.maximum(lows[j], bin_edges[:-1]))
                vol_per_bin += volumes[j] * (overlaps / candle_range)
            total_vol = vol_per_bin.sum()
            if total_vol == 0: continue
            poc_bin = np.argmax(vol_per_bin)
            poc_volume = vol_per_bin[poc_bin]
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
                if best_zone:
                    lvn_bottom[i] = bin_edges[best_zone[0]]
                    lvn_top[i] = bin_edges[best_zone[1] + 1]

        df["lvn_top"] = lvn_top
        df["lvn_bottom"] = lvn_bottom
        df["price_in_lvn"] = (
            df["lvn_bottom"].notna() &
            (df["close"] >= df["lvn_bottom"]) &
            (df["close"] <= df["lvn_top"])
        ).astype(int)
        df["near_vwap"] = (df["vwap_dist_pct"].abs() <= vwap_prox).astype(int)
        return df

    def _compute_confluence(self, df):
        min_br = float(self.min_body_ratio.value)
        df["body"] = (df["close"] - df["open"]).abs()
        df["candle_range"] = df["high"] - df["low"]
        df["body_ratio"] = df["body"] / df["candle_range"].replace(0, np.nan)
        df["bearish_candle"] = ((df["close"] < df["open"]) & (df["body_ratio"] >= min_br)).astype(int)
        df["vwap_declining"] = (df["vwap_slope"] < 0).astype(int)

        df["short_bos"] = (df["bos_trend"] == -1).astype(int)
        df["short_lvn"] = df["price_in_lvn"]
        df["short_vwap_relaxed"] = df["near_vwap"]
        df["short_confirm"] = df["bearish_candle"]

        df["short_pillars"] = df["short_bos"] + df["short_lvn"] + df["short_vwap_relaxed"] + df["short_confirm"]
        df["short_partial"] = ((df["short_bos"] == 1) & (df["short_pillars"] >= 3)).astype(int)
        df["rsi_not_oversold"] = (df["rsi"] > 30).astype(int)
        return df

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["short_partial"] == 1) &
            (dataframe["rsi_not_oversold"] == 1) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "bos_late_trail_short")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        # V6 Late Trail: RSI < 45 deep reversal (NOT 30 — too early)
        dataframe.loc[
            (dataframe["rsi"] < 45),
            ["exit_short", "exit_tag"]
        ] = (1, "rsi_deep_reversal_45")
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        # V6 Late Trail: breakeven at 5% (not 3%)
        if current_profit > 0.05:
            return -0.005  # Very tight breakeven
        return None

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last = dataframe.iloc[-1]

        # BOS structure reversal — only if in profit
        if trade.is_short and last.get("bos_trend", 0) == 1 and current_profit > 0.02:
            return "bullish_bos_reversal"

        return None