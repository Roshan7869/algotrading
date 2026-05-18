"""
VectorOmni_ShortTerm_15m — 15-Minute Short-Term Trading Strategy

First strategy in the repo to use <1h timeframe.
Key innovations from the gap analysis:
  1. 15m execution timeframe (5-10x trade frequency)
  2. 1h informative pair for EMA trend filter
  3. FVG + OB + MSS on 15m with 1h confluence
  4. Tighter stops (0.04, 0.015/0.025 offset)
  5. N-bar expiration (16 bars = 4 hours)
  6. Session kill-zone filter (London/NY overlap)
  7. Momentum exhaustion exit
  8. RSI divergence exit on 15m
  9. Volume dry-up exit
"""
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, Trade, DecimalParameter, IntParameter, informative
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import merge_informative_pair


class VectorOmni_ShortTerm_15m(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False

    minimal_roi = {"0": 0.05, "30": 0.03, "60": 0.02, "120": 0.01}

    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 200

    order_types = {"entry": "limit", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False}
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    bb_squeeze_threshold = DecimalParameter(0.02, 0.10, default=0.05, decimals=3, space="buy")
    rsi_oversold = IntParameter(25, 45, default=35, space="buy")
    rsi_overbought = IntParameter(55, 75, default=65, space="sell")
    volume_factor = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy")
    ema_fast = IntParameter(8, 21, default=9, space="buy")
    ema_medium = IntParameter(20, 50, default=21, space="buy")
    bb_pctb_low = DecimalParameter(0.20, 0.50, default=0.30, space="buy")
    bb_pctb_high = DecimalParameter(0.50, 0.80, default=0.70, space="sell")
    min_confluence = IntParameter(2, 4, default=3, space="buy")
    fvg_min_bps = IntParameter(5, 20, default=8, space="buy")

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return min(3, max_leverage)

    def informative_pairs(self):
        pairs = self.config["exchange"]["pair_whitelist"]
        return [(p, "1h", self.timeframe) for p in pairs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ── 1h Trend Filter (informative) ──
        if self.dp:
            inf_pair = metadata["pair"]
            informative = self.dp.get_pair_dataframe(pair=inf_pair, timeframe="1h")
            informative["ema_200"] = ta.EMA(informative, timeperiod=200)
            informative["ema_50"] = ta.EMA(informative, timeperiod=50)
            informative["rsi"] = ta.RSI(informative, timeperiod=14)
            dataframe = merge_informative_pair(dataframe, informative, self.timeframe, "1h", ffill=True)

        dataframe["ema_200_1h"] = dataframe["ema_200_1h"].ffill()
        dataframe["ema_50_1h"] = dataframe["ema_50_1h"].ffill()
        dataframe["rsi_1h"] = dataframe["rsi_1h"].ffill()

        # ── Bollinger Bands (15m) ──
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_pctb"] = ((dataframe["close"] - dataframe["bb_lowerband"])
                                / (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
                                ).replace([np.inf, -np.inf], 0.5).fillna(0.5)
        dataframe["bb_width"] = ((dataframe["bb_upperband"] - dataframe["bb_lowerband"])
                                 / dataframe["bb_middleband"]
                                 ).replace([np.inf, -np.inf], 0).fillna(0)

        bollinger_3sd = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=3)
        dataframe["bb3_upper"] = bollinger_3sd["upper"]
        dataframe["bb3_lower"] = bollinger_3sd["lower"]

        # ── 15m Indicators ──
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_mean"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = (dataframe["volume"] / dataframe["volume_mean"]
                                     ).replace([np.inf, -np.inf], 1).fillna(1)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = ((typical_price * dataframe["volume"]).rolling(20).sum()
                             / dataframe["volume"].rolling(20).sum()).bfill()

        # Pivot points
        dataframe["pivot_high"] = dataframe["high"].rolling(10, center=True).max()
        dataframe["pivot_low"] = dataframe["low"].rolling(10, center=True).min()
        dataframe["dist_to_resistance"] = ((dataframe["pivot_high"] - dataframe["close"]) / dataframe["atr"]).fillna(5)
        dataframe["dist_to_support"] = ((dataframe["close"] - dataframe["pivot_low"]) / dataframe["atr"]).fillna(5)

        # ── FVG (15m specific) ──
        dataframe["fvg_bull"] = (
            (dataframe["low"].shift(1) > dataframe["high"].shift(2)) &
            ((dataframe["low"].shift(1) - dataframe["high"].shift(2)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)
        dataframe["fvg_bear"] = (
            (dataframe["high"].shift(1) < dataframe["low"].shift(2)) &
            ((dataframe["low"].shift(2) - dataframe["high"].shift(1)) / dataframe["close"] * 10000 > self.fvg_min_bps.value)
        ).astype(int)

        # ── OB (no look-ahead: shift(-2) → shift(1/2)) ──
        dataframe["ob_bull"] = (
            (dataframe["close"].shift(2) < dataframe["open"].shift(2)) &
            (dataframe["close"].shift(1) > dataframe["open"].shift(1)) &
            (dataframe["close"].shift(1) > dataframe["high"].shift(2)) &
            (dataframe["volume_ratio"].shift(1) > 1.3)
        ).astype(int)
        dataframe["ob_bear"] = (
            (dataframe["close"].shift(2) > dataframe["open"].shift(2)) &
            (dataframe["close"].shift(1) < dataframe["open"].shift(1)) &
            (dataframe["close"].shift(1) < dataframe["low"].shift(2)) &
            (dataframe["volume_ratio"].shift(1) > 1.3)
        ).astype(int)

        # ── MSS ──
        dataframe["mss_long"] = (
            (dataframe["low"] < dataframe["low"].shift(1)) &
            (dataframe["close"] > dataframe["high"].shift(1))
        ).astype(int)
        dataframe["mss_short"] = (
            (dataframe["high"] > dataframe["high"].shift(1)) &
            (dataframe["close"] < dataframe["low"].shift(1))
        ).astype(int)

        # ── Momentum Exhaustion ──
        dataframe["bull_c"] = (dataframe["close"] > dataframe["open"]).astype(int)
        dataframe["bear_c"] = (dataframe["close"] < dataframe["open"]).astype(int)
        def _cc(series):
            return series.groupby((series != series.shift(1)).cumsum()).cumcount() + 1
        dataframe["consec_bull"] = _cc(dataframe["bull_c"]) * dataframe["bull_c"]
        dataframe["consec_bear"] = _cc(dataframe["bear_c"]) * dataframe["bear_c"]

        # ── RSI Divergence ──
        dataframe["rsi_rising"] = ((dataframe["rsi"] > dataframe["rsi"].shift(1)) & (dataframe["rsi"].shift(1) > dataframe["rsi"].shift(2))).astype(int)
        dataframe["rsi_falling"] = ((dataframe["rsi"] < dataframe["rsi"].shift(1)) & (dataframe["rsi"].shift(1) < dataframe["rsi"].shift(2))).astype(int)
        dataframe["price_rising"] = ((dataframe["close"] > dataframe["close"].shift(1)) & (dataframe["close"].shift(1) > dataframe["close"].shift(2))).astype(int)
        dataframe["price_falling"] = ((dataframe["close"] < dataframe["close"].shift(1)) & (dataframe["close"].shift(1) < dataframe["close"].shift(2))).astype(int)
        dataframe["rsi_bull_div"] = (dataframe["price_falling"] & dataframe["rsi_rising"]).astype(int)
        dataframe["rsi_bear_div"] = (dataframe["price_rising"] & dataframe["rsi_falling"]).astype(int)

        # ── Session Filter (UTC → crypto market) ──
        hour = dataframe["date"].dt.hour
        dataframe["session_kill"] = (((hour >= 7) & (hour < 9)) | ((hour >= 13) & (hour < 17))).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1h trend filter: only long if 1h EMA50 > 1h EMA200
        h1_trend_up = dataframe["ema_50_1h"] > dataframe["ema_200_1h"]
        h1_trend_dn = dataframe["ema_50_1h"] < dataframe["ema_200_1h"]

        fvg_l = dataframe["fvg_bull"].astype(int)
        ob_l = dataframe["ob_bull"].astype(int)
        mss_l = dataframe["mss_long"].astype(int)
        fvg_s = dataframe["fvg_bear"].astype(int)
        ob_s = dataframe["ob_bear"].astype(int)
        mss_s = dataframe["mss_short"].astype(int)

        squeeze_l = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )
        meanrev_l = (
            (dataframe["bb_pctb"] < self.bb_pctb_low.value) &
            (dataframe["close"] > dataframe["bb3_lower"]) &
            (dataframe["rsi"] < self.rsi_oversold.value) &
            (dataframe["close"] > dataframe["vwap"])
        )
        ema_l = (
            (dataframe["ema_fast"] > dataframe["ema_medium"]) &
            (dataframe["close"] > dataframe["ema_fast"]) &
            (dataframe["rsi"] > 40) & (dataframe["rsi"] < 65)
        )
        expansion_l = (
            (dataframe["close"] > dataframe["bb3_upper"]) &
            (dataframe["close"].shift(1) <= dataframe["bb3_upper"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) & (dataframe["rsi"] > 50)
        )
        key_l = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) & (dataframe["rsi"] > 35) & (dataframe["rsi"] < 65)
        )
        kl_boost_l = (dataframe["dist_to_support"] < 0.5).astype(int)

        long_signals = [
            squeeze_l.astype(int), meanrev_l.astype(int), ema_l.astype(int),
            expansion_l.astype(int), key_l.astype(int), fvg_l, ob_l, mss_l,
        ]
        long_score = sum(long_signals) + kl_boost_l

        dataframe.loc[
            (long_score >= self.min_confluence.value) &
            h1_trend_up &
            (dataframe["session_kill"] == 1) &
            (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "st_15m_long")

        squeeze_s = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] < dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )
        meanrev_s = (
            (dataframe["bb_pctb"] > self.bb_pctb_high.value) &
            (dataframe["close"] < dataframe["bb3_upper"]) &
            (dataframe["rsi"] > self.rsi_overbought.value) &
            (dataframe["close"] < dataframe["vwap"])
        )
        ema_s = (
            (dataframe["ema_fast"] < dataframe["ema_medium"]) &
            (dataframe["close"] < dataframe["ema_fast"]) &
            (dataframe["rsi"] < 60) & (dataframe["rsi"] > 35)
        )
        expansion_s = (
            (dataframe["close"] < dataframe["bb3_lower"]) &
            (dataframe["close"].shift(1) >= dataframe["bb3_lower"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) & (dataframe["rsi"] < 50)
        )
        key_s = (
            (dataframe["dist_to_resistance"] < 1.0) &
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) & (dataframe["rsi"] < 65) & (dataframe["rsi"] > 35)
        )
        kl_boost_s = (dataframe["dist_to_resistance"] < 0.5).astype(int)

        short_signals = [
            squeeze_s.astype(int), meanrev_s.astype(int), ema_s.astype(int),
            expansion_s.astype(int), key_s.astype(int), fvg_s, ob_s, mss_s,
        ]
        short_score = sum(short_signals) + kl_boost_s

        dataframe.loc[
            (short_score >= self.min_confluence.value) &
            h1_trend_dn &
            (dataframe["session_kill"] == 1) &
            (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "st_15m_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["bb_pctb"] > self.bb_pctb_high.value) |
                ((dataframe["rsi"] > self.rsi_overbought.value) &
                 (dataframe["close"] < dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(20).mean() * 2.0)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "st15m_exit")

        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(20).mean() * 2.0)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "st15m_exit")

        # Momentum exhaustion (15m: 12+ consecutive = ~3 hours)
        dataframe.loc[
            (dataframe["consec_bull"] >= 12) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "exhaust_15m_long")
        dataframe.loc[
            (dataframe["consec_bear"] >= 12) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "exhaust_15m_short")

        # Volume dry-up
        dataframe.loc[
            (dataframe["volume_ratio"] < 0.4) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "vol_dry_15m")
        dataframe.loc[
            (dataframe["volume_ratio"] < 0.4) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "vol_dry_15m")

        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        last = dataframe.iloc[-1]

        if trade.is_short:
            if last.get("bb_pctb", 0.5) < 0.15:
                return "beacon_15m_short"
        else:
            if last.get("bb_pctb", 0.5) > 0.85:
                return "beacon_15m_long"

        # N-bar expiration: 16 bars on 15m = 4 hours
        open_date = trade.open_date_utc
        if open_date is not None:
            bars = int((current_time - open_date).total_seconds() / 900)
            if bars >= 16 and current_profit < 0.01:
                return "nbar_expire_15m"

        return None
