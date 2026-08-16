import os
from datetime import datetime, timezone
from typing import Optional, Union
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    IntParameter,
    DecimalParameter,
    BooleanParameter,
)

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import merge_informative_pair

from vdb_mixin import VDBMixin
try:
    from shared_config.signal_bus import get_bus
except ImportError:
    def get_bus():
        class _StubBus:
            def read(self, filename, max_age=None, default=None):
                return default
        return _StubBus()


class EnsembleStrategy(IStrategy, VDBMixin):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    minimal_roi = {
        "0": 0.20,
        "120": 0.10,
        "360": 0.05,
        "720": 0.02,
    }

    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.06
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count: int = 200

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    vote_threshold = IntParameter(1, 4, default=2, space="buy", optimize=True, load=True)
    min_vdb_confidence = DecimalParameter(0.0, 0.5, default=0.0, decimals=1, space="buy", optimize=True, load=True)
    atr_multiplier = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)

    use_macd_rsi = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    use_bollinger = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    use_ema_trend = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    use_dmi_adx = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    use_supertrend = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    use_rsi_div = BooleanParameter(default=True, space="buy", optimize=False, load=True)

    _circuit_breaker_triggered = False
    custom_startup_sent = False

    def bot_loop_start(self, **kwargs) -> None:
        import json
        from pathlib import Path

        shared = Path(os.getenv("SHARED_CONFIG_DIR", "shared_config"))
        kill_path = shared / "kill_signal.json"
        breaker_path = shared / "circuit_breaker.json"

        if kill_path.exists():
            try:
                sig = json.loads(kill_path.read_text())
                age = __import__("time").time() - __import__("datetime").datetime.fromisoformat(sig["timestamp"]).timestamp()
                if age < 300 and not self._circuit_breaker_triggered:
                    self._circuit_breaker_triggered = True
                    msg = (
                        f"🚨 CIRCUIT BREAKER TRIPPED\\n"
                        f"Reason: {sig.get('reason', 'emergency')}\\n"
                        f"Action: {sig.get('action', 'stop')}\\n"
                        f"Trading halted. Manual restart required."
                    )
                    try:
                        self.dp.send_msg(msg)
                    except Exception:
                        pass
            except Exception:
                pass

        if self._circuit_breaker_triggered:
            return

        if not self.custom_startup_sent:
            try:
                state = "HEALTHY"
                if breaker_path.exists():
                    state = json.loads(breaker_path.read_text()).get("state", "HEALTHY")
                msg = (
                    f"EnsembleStrategy ACTIVE\\n"
                    f"Members: 6 strategies\\n"
                    f"Vote threshold: {self.vote_threshold.value}\\n"
                    f"Circuit Breaker: {state}\\n"
                    f"VDB runtime: {'ON' if self._vdb_is_available() else 'OFF'}\\n"
                    f"Status: 🟢 LIVE"
                )
                self.dp.send_msg(msg)
            except Exception:
                pass
            self.custom_startup_sent = True

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "1h"))
        return informative_pairs

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ── Shared indicators (used by multiple members) ──
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # ── MACD ──
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # ── Bollinger Bands ──
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_width"] = (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]
        dataframe["bb_lower_distance"] = (dataframe["close"] - dataframe["bb_lowerband"]) / dataframe["bb_lowerband"]
        dataframe["bb_upper_distance"] = (dataframe["close"] - dataframe["bb_upperband"]) / dataframe["bb_upperband"]

        # ── EMA Trend ──
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_trend_line"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema_slope"] = dataframe["ema_slow"] - dataframe["ema_slow"].shift(5)
        dataframe["dist_to_trend"] = (dataframe["close"] - dataframe["ema_trend_line"]) / dataframe["ema_trend_line"]

        # ── DMI/ADX ──
        dataframe["plus_di"] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe["minus_di"] = ta.MINUS_DI(dataframe, timeperiod=14)
        dataframe["di_strength"] = abs(dataframe["plus_di"] - dataframe["minus_di"])
        dataframe["adx_slope"] = dataframe["adx"] - dataframe["adx"].shift(5)

        # ── Aroon ──
        aroon = ta.AROON(dataframe, timeperiod=14)
        dataframe["aroonup"] = aroon["aroonup"]
        dataframe["aroondown"] = aroon["aroondown"]
        dataframe["aroon_osc"] = dataframe["aroonup"] - dataframe["aroondown"]

        # ── StochRSI ──
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=14, fastk_period=5, fastd_period=3)
        dataframe["stoch_rsi_k"] = stoch_rsi["fastk"]
        dataframe["stoch_rsi_d"] = stoch_rsi["fastd"]

        # ── 4H MTF ──
        if self.dp:
            inf_tf = "4h"
            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=inf_tf)
            if len(informative) > 0:
                informative["ema_50_4h"] = ta.EMA(informative, timeperiod=50)
                informative["ema_slope_4h"] = informative["ema_50_4h"] - informative["ema_50_4h"].shift(5)
                informative["adx_4h"] = ta.ADX(informative, timeperiod=14)
                informative["plus_di_4h"] = ta.PLUS_DI(informative, timeperiod=14)
                informative["minus_di_4h"] = ta.MINUS_DI(informative, timeperiod=14)
                informative = informative[["date", "ema_50_4h", "ema_slope_4h", "adx_4h", "plus_di_4h", "minus_di_4h"]].copy()
                dataframe = merge_informative_pair(
                    dataframe, informative, self.timeframe, inf_tf, ffill=True
                )
            else:
                dataframe["ema_50_4h"] = dataframe["ema_50"]
                dataframe["ema_slope_4h"] = dataframe["ema_slope"]
                dataframe["adx_4h"] = dataframe["adx"]
                dataframe["plus_di_4h"] = dataframe["plus_di"]
                dataframe["minus_di_4h"] = dataframe["minus_di"]

        # ── BTC Regime ──
        if self.dp and metadata["pair"] != "BTC/USDT:USDT":
            try:
                btc_data = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1h")
                if len(btc_data) > 0:
                    btc_data["ema_50"] = ta.EMA(btc_data, timeperiod=50)
                    btc_data["ema_200"] = ta.EMA(btc_data, timeperiod=200)
                    btc_data["rsi"] = ta.RSI(btc_data, timeperiod=14)
                    btc_data = btc_data[["date", "ema_50", "ema_200", "rsi"]].copy()
                    btc_data.columns = ["date", "btc_ema_50", "btc_ema_200", "btc_rsi"]
                    dataframe = pd.merge(dataframe, btc_data, on="date", how="left")
                    dataframe["btc_ema_50"] = dataframe["btc_ema_50"].ffill()
                    dataframe["btc_ema_200"] = dataframe["btc_ema_200"].ffill()
                    dataframe["btc_rsi"] = dataframe["btc_rsi"].fillna(50)
                    dataframe["btc_bullish"] = (dataframe["btc_ema_50"] > dataframe["btc_ema_200"])
                else:
                    dataframe["btc_bullish"] = True
            except Exception:
                dataframe["btc_bullish"] = True
        else:
            dataframe["btc_bullish"] = True

        # ── VDB Runtime ──
        if self._vdb_is_available():
            matches = self._vdb_entry_setups(metadata["pair"], top_k=3)
            for i, m in enumerate(matches):
                dataframe[f"vdb_match_{i}_score"] = m["score"]
                dataframe[f"vdb_match_{i}_name"] = m["setup_name"]
            dataframe["vdb_top_score"] = matches[0]["score"] if matches else 0.5
        else:
            dataframe["vdb_top_score"] = 0.5

        return dataframe

    def _load_signal_bus(self) -> dict:
        """Read external signals from AtomicFileBus."""
        bus = get_bus()
        ta_signal = bus.read("tradingagents_signal.json", max_age=600) or {}
        sentiment = bus.read("sentiment_signal.json", max_age=600) or {}
        regime = bus.read("market_regime.json", max_age=600) or {}
        leverage = bus.read("leverage_signal.json", max_age=600) or {}

        return {
            "ta_rating": ta_signal.get("rating", "Hold"),
            "ta_approval": ta_signal.get("risk_assessment", {}).get("approval", True),
            "sentiment_score": sentiment.get("sentiment_score", 0.0),
            "market_regime": regime.get("regime", "ranging"),
            "leverage": leverage.get("leverage", 3.0),
        }

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        signals = self._load_signal_bus()
        dataframe["signal_rating"] = 1 if signals["ta_rating"] in ("Buy", "Overweight") else (
            -1 if signals["ta_rating"] in ("Sell", "Underweight") else 0
        )
        dataframe["signal_sentiment"] = signals["sentiment_score"]
        dataframe["signal_leverage"] = signals["leverage"]

        threshold = self.vote_threshold.value

        if self.use_macd_rsi.value:
            macd_bull = qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"])
            macd_bear = qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"])
            dataframe["v_macdrsi_long"] = macd_bull & (dataframe["rsi"] < 45) & (dataframe["rsi"] > 20)
            dataframe["v_macdrsi_short"] = macd_bear & (dataframe["rsi"] > 55) & (dataframe["rsi"] < 80)

        if self.use_bollinger.value:
            touch_lower = dataframe["close"] <= dataframe["bb_lowerband"] * 1.005
            touch_upper = dataframe["close"] >= dataframe["bb_upperband"] * 0.995
            bb_wide = (dataframe["bb_width"] > 0.03) & (dataframe["bb_width"] < 0.25)
            dataframe["v_bb_long"] = touch_lower & (dataframe["rsi"] < 35) & bb_wide & dataframe["btc_bullish"]
            dataframe["v_bb_short"] = touch_upper & (dataframe["rsi"] > 65) & bb_wide

        if self.use_ema_trend.value:
            gc = qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
            dc = qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_slow"])
            fast_bull = (dataframe["ema_fast"] > dataframe["ema_medium"]) & (dataframe["ema_slope"] > 0)
            fast_bear = (dataframe["ema_fast"] < dataframe["ema_medium"]) & (dataframe["ema_slope"] < 0)
            vol_ok = dataframe["volume"] > dataframe["volume_ma"]
            adx_ok = dataframe["adx"] > 20
            dataframe["v_ema_long"] = (gc | fast_bull) & vol_ok & adx_ok
            dataframe["v_ema_short"] = (dc | fast_bear) & vol_ok & adx_ok

        if self.use_dmi_adx.value:
            trending = dataframe["adx"] > 25
            di_up = qtpylib.crossed_above(dataframe["plus_di"], dataframe["minus_di"])
            di_down = qtpylib.crossed_below(dataframe["plus_di"], dataframe["minus_di"])
            dataframe["v_dmi_long"] = trending & di_up & (dataframe["plus_di"] > 20)
            dataframe["v_dmi_short"] = trending & di_down & (dataframe["minus_di"] > 20)

        if self.use_supertrend.value:
            hl2 = (dataframe["high"] + dataframe["low"]) / 2
            sup_atr = ta.ATR(dataframe, timeperiod=10)
            sup_upper = hl2 + (3.0 * sup_atr)
            sup_lower = hl2 - (3.0 * sup_atr)
            direction = np.full(len(dataframe), 1)
            for j in range(10, len(dataframe)):
                if direction[j - 1] == 1:
                    direction[j] = 1 if dataframe["close"].iloc[j] >= sup_lower.iloc[j - 1] else -1
                else:
                    direction[j] = -1 if dataframe["close"].iloc[j] <= sup_upper.iloc[j - 1] else 1
            sup_turn_up = (pd.Series(direction) == 1) & (pd.Series(direction).shift(1) == -1)
            sup_turn_down = (pd.Series(direction) == -1) & (pd.Series(direction).shift(1) == 1)
            dataframe["v_st_long"] = sup_turn_up
            dataframe["v_st_short"] = sup_turn_down

        if self.use_rsi_div.value:
            close_low = dataframe["close"].rolling(14).min()
            rsi_low = dataframe["rsi"].rolling(14).min()
            close_high = dataframe["close"].rolling(14).max()
            rsi_high = dataframe["rsi"].rolling(14).max()
            dataframe["v_div_long"] = (dataframe["close"] == close_low) & (dataframe["rsi"] > rsi_low.shift(1))
            dataframe["v_div_short"] = (dataframe["close"] == close_high) & (dataframe["rsi"] < rsi_high.shift(1))

        vote_cols_long = [c for c in dataframe.columns if c.startswith("v_") and c.endswith("_long")]
        vote_cols_short = [c for c in dataframe.columns if c.startswith("v_") and c.endswith("_short")]

        if vote_cols_long:
            votes_long = sum(dataframe[c].astype(int) for c in vote_cols_long)
            long_threshold = threshold
            if signals["sentiment_score"] > 0.3:
                long_threshold = max(1, threshold - 1)
            elif signals["sentiment_score"] < -0.3:
                long_threshold = threshold + 1
            if signals["ta_rating"] in ("Buy", "Overweight") and signals.get("ta_approval", True):
                long_threshold = max(1, long_threshold - 1)
            dataframe.loc[votes_long >= long_threshold, "enter_long"] = 1

        if vote_cols_short:
            votes_short = sum(dataframe[c].astype(int) for c in vote_cols_short)
            short_threshold = threshold
            if signals["sentiment_score"] < -0.3:
                short_threshold = max(1, threshold - 1)
            elif signals["sentiment_score"] > 0.3:
                short_threshold = threshold + 1
            if signals["ta_rating"] in ("Sell", "Underweight") and signals.get("ta_approval", True):
                short_threshold = max(1, short_threshold - 1)
            dataframe.loc[votes_short >= short_threshold, "enter_short"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.stoploss

        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)
        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle.get("atr", 0)
        except (IndexError, KeyError):
            return self.stoploss

        if pd.isna(atr_value) or atr_value <= 0:
            return self.stoploss

        stop_distance = atr_value * self.atr_multiplier.value
        if trade.is_short:
            stop_price = trade.open_rate + stop_distance
            stop_loss_pct = -((stop_price - current_rate) / current_rate)
        else:
            stop_price = trade.open_rate - stop_distance
            stop_loss_pct = -((current_rate - stop_price) / current_rate)

        return max(stop_loss_pct, self.stoploss)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs) -> Optional[Union[str, bool]]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)
        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle.get("atr", 0)
        except (IndexError, KeyError):
            return None

        if pd.isna(atr_value) or atr_value <= 0:
            return None

        atr_move = atr_value * self.atr_multiplier.value
        if trade.is_short:
            target_profit_pct = (atr_move * self.risk_reward.value) / current_rate
            if current_profit >= target_profit_pct:
                return f"short_tp_{self.risk_reward.value}r"
        else:
            tp_distance = atr_move * self.risk_reward.value
            tp_price = trade.open_rate + tp_distance
            if current_rate >= tp_price:
                return f"long_tp_{self.risk_reward.value}r"

        return None
