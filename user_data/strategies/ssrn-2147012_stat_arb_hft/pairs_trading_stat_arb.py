"""
Cointegration Pairs Trading — Statistical Arbitrage (Paper 2: ssrn-2147012)
============================================================================
Based on Gatev, Goetzmann & Rouwenhorst (2006) distance method:
  1. Pick two cointegrated tokens (e.g. OP/ARB, corr=0.971)
  2. Compute ratio = price_A / price_B over lookback window
  3. Entry: ratio > 2σ above mean → short A / long B (short the spread)
          ratio < 2σ below mean → long A / long B (long the spread)
  4. Exit: ratio reverts to mean (z-score crosses 0)
  5. Stop: ratio hits 3σ (widening beyond mean-reversion tolerance)

Paper finding: HFT increases cointegration. High-volume pairs have more
reliable mean reversion (0.971 corr for OP/ARB).

Config: companion_pair, lookback_period, entry_z, stop_z
Default: OP/USDT:USDT with ARB/USDT:USDT companion, 168h lookback (7 days)
"""

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter


class PairsTradingStatArb(IStrategy):
    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 200

    stoploss = -0.15
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False

    trailing_stop = False
    stake_amount = "unlimited"
    max_open_trades = 3

    companion_pair = "ARB/USDT:USDT"

    lookback_period = IntParameter(84, 336, default=168, space="buy")
    entry_z = DecimalParameter(1.5, 3.0, default=1.8, decimals=1, space="buy")
    stop_z = DecimalParameter(2.5, 4.0, default=3.0, decimals=1, space="sell")

    leverage_num = DecimalParameter(5, 15, default=10.0, decimals=0, space="buy", optimize=False)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return float(self.leverage_num.value)

    def informative_pairs(self):
        return [(self.companion_pair, self.timeframe, self.trading_mode)]

    def populate_indicators(self, dataframe, metadata):
        companion = self.dp.get_pair_dataframe(self.companion_pair, self.timeframe)
        if companion is None or len(companion) < self.startup_candle_count:
            return dataframe

        merged = dataframe.merge(
            companion[["date", "close"]].rename(columns={"close": "close_comp"}),
            on="date", how="left"
        )
        merged["close_comp"] = merged["close_comp"].ffill()

        merged["ratio"] = merged["close"] / merged["close_comp"].replace(0, np.nan)

        lookback = int(self.lookback_period.value)
        merged["ratio_ma"] = merged["ratio"].rolling(lookback).mean()
        merged["ratio_std"] = merged["ratio"].rolling(lookback).std()
        merged["ratio_zscore"] = (
            (merged["ratio"] - merged["ratio_ma"]) / merged["ratio_std"].replace(0, np.nan)
        )

        merged["ratio_zscore_lag1"] = merged["ratio_zscore"].shift(1)

        dataframe["ratio_zscore"] = merged["ratio_zscore"]
        dataframe["ratio_zscore_lag1"] = merged["ratio_zscore_lag1"]
        dataframe["ratio"] = merged["ratio"]
        dataframe["ratio_ma"] = merged["ratio_ma"]
        dataframe["ratio_std"] = merged["ratio_std"]

        entry = float(self.entry_z.value)
        dataframe["enter_long_signal"] = (
            (dataframe["ratio_zscore_lag1"] < -entry) &
            (dataframe["ratio_zscore"] < -entry * 0.7)
        ).astype(int)

        dataframe["enter_short_signal"] = (
            (dataframe["ratio_zscore_lag1"] > entry) &
            (dataframe["ratio_zscore"] > entry * 0.7)
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["enter_long_signal"] == 1) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "spread_long")

        dataframe.loc[
            (dataframe["enter_short_signal"] == 1) & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "spread_short")

        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        stop_z = float(self.stop_z.value)
        exit_long = (
            (dataframe["ratio_zscore"] >= 0) |
            (dataframe["ratio_zscore"] < -stop_z)
        ).astype(int)
        exit_short = (
            (dataframe["ratio_zscore"] <= 0) |
            (dataframe["ratio_zscore"] > stop_z)
        ).astype(int)

        dataframe.loc[exit_long == 1, ["exit_long", "exit_tag"]] = (1, "spread_reversion_or_stop")
        dataframe.loc[exit_short == 1, ["exit_short", "exit_tag"]] = (1, "spread_reversion_or_stop")

        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 1:
            return None

        last = dataframe.iloc[-1]
        z = last.get("ratio_zscore", None)
        if z is None or np.isnan(z):
            return None

        if trade.is_short and z <= 0 and current_profit > 0:
            return "spread_reverted_profit"
        if not trade.is_short and z >= 0 and current_profit > 0:
            return "spread_reverted_profit"

        return None

        last = dataframe.iloc[-1]
        z = last.get("ratio_zscore", None)
        if z is None or np.isnan(z):
            return None

        stop_z = float(self.stop_z.value)
        if trade.is_short and z <= 0 and current_profit > 0:
            return "spread_reverted_profit"
        if not trade.is_short and z >= 0 and current_profit > 0:
            return "spread_reverted_profit"

        return None
