# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
"""
AroonMomentumEngine V2 — Confluence Scoring Model
====================================================

FIX: Original Hybrid produced 0 trades due to 13+ simultaneous AND conditions.
ChromaDB research: >2 confirmations kills trade frequency ("Over-Confirmation Avoidance Rule").

Solution: Confluence scoring model (borrowed from champion VectorStrategy_P3E)
- 5 independent signal pillars, each scored 0 or 1
- Entry triggers when confluence_score >= min_confluence (default 2)
- External signals (sentiment, regime, TradingAgents) are SCORERS, not GATES
- No more 9-way AND cascade

Signal Pillars:
  1. AROON CROSS — Aroon Up/Down crossover (directional shift)
  2. AROON MOMENTUM — Aroon oscillator sign + direction (trend quality)
  3. MACD MOMENTUM — MACD vs signal alignment (momentum confirmation)
  4. TREND ALIGNMENT — Price vs EMA200 + 4h EMA slope (multi-TF alignment)
  5. TREND STRENGTH — ADX > threshold (move has force)

External Boosters (add to score, never gate):
  +1 volume_confirmed  (volume > 20-period MA)
  +1 sentiment_aligned (sentiment agrees with direction)
  +1 ta_aligned        (TradingAgents rating agrees)

min_confluence default=2, hyperoptable 1-4.
"""

import sys
import os
from datetime import datetime, timezone
from typing import Optional, Union
import numpy as np
import pandas as pd
from pandas import DataFrame

# PYTHONPATH fix: freqtrade doesn't add strategy dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    DecimalParameter,
    IntParameter,
    BooleanParameter,
    informative,
)

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import merge_informative_pair

# ── Outcome Feedback Path ────────────────────────────────────────
from pathlib import Path
VDB_OUTCOME_PATH = Path(__file__).parent.parent.parent / "strategy_db" / "outcome_history.json"


class AroonMomentumEngine_V2(IStrategy):
    """
    Aroon Momentum Engine V2 — Confluence Scoring Model.

    Fixed from Hybrid: replaces 13+ AND gates with confluence scoring.
    Any 2 of 5 core signals + boosters trigger entry.
    """

    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    # ROI: Aggressive decay — capture moves, kill zombies
    minimal_roi = {
        "0": 0.15,
        "60": 0.08,
        "240": 0.05,
        "720": 0.02,
        "1440": 0.01,
    }

    # Stoploss: 5% hard stop (works for 3x leverage = 15% position loss)
    stoploss = -0.05

    # Trailing stop: protect profits
    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.05
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

    custom_startup_sent = False

    # ══════════════════════════════════════════════
    # HYPEROPTABLE PARAMETERS
    # ══════════════════════════════════════════════

    aroon_period = IntParameter(10, 25, default=14, space="buy", optimize=True, load=True)

    # Confluence threshold — the KEY parameter
    min_confluence = IntParameter(1, 4, default=2, space="buy", optimize=True, load=True)

    # ATR-based dynamic stop
    atr_multiplier = DecimalParameter(1.5, 3.5, default=2.0, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)

    # ADX threshold
    adx_threshold = IntParameter(15, 30, default=20, space="buy", optimize=True, load=True)

    # MTF parameters
    mtf_ema_period = IntParameter(50, 100, default=50, space="buy", optimize=True, load=True)
    mtf_slope_lookback = IntParameter(3, 10, default=5, space="buy", optimize=False, load=True)

    # RSI bounds (wider than original — don't over-filter)
    rsi_upper = IntParameter(60, 75, default=70, space="buy", optimize=True, load=True)
    rsi_lower = IntParameter(25, 45, default=30, space="sell", optimize=True, load=True)

    # Volume factor
    volume_factor = DecimalParameter(0.8, 2.0, default=1.0, decimals=1, space="buy", optimize=True, load=True)

    # ══════════════════════════════════════════════
    # INFORMATIVE PAIRS
    # ══════════════════════════════════════════════

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "1h"))
        return informative_pairs

    # ══════════════════════════════════════════════
    # LEVERAGE
    # ══════════════════════════════════════════════

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        import json
        from pathlib import Path as P
        signal_path = P(os.getenv("SHARED_CONFIG_DIR", "/freqtrade/shared_config")) / "leverage_signal.json"
        try:
            if signal_path.exists():
                data = json.loads(signal_path.read_text())
                lev = float(data.get("leverage", 2.0))
            else:
                lev = 2.0
        except Exception:
            lev = 2.0
        return min(lev, 5.0, max_leverage)

    # ══════════════════════════════════════════════
    # BOT LOOP START
    # ══════════════════════════════════════════════

    def bot_loop_start(self, **kwargs) -> None:
        if not self.custom_startup_sent:
            msg = (
                "🚀 AroonMomentumEngine V2 (Confluence)\\n\\n"
                "Model: 5-pillar confluence scoring\\n"
                f"min_confluence: {self.min_confluence.value}\\n"
                "Leverage: Dynamic (2-5x)\\n"
                "Status: 🟢 ACTIVE"
            )
            try:
                self.dp.send_msg(msg)
            except Exception:
                pass
            self.custom_startup_sent = True

    # ══════════════════════════════════════════════
    # POPULATE INDICATORS
    # ══════════════════════════════════════════════

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators."""

        # ── 1. AROON ──
        aroon = ta.AROON(dataframe, timeperiod=self.aroon_period.value)
        dataframe["aroonup"] = aroon["aroonup"]
        dataframe["aroondown"] = aroon["aroondown"]
        dataframe["aroon_osc"] = dataframe["aroonup"] - dataframe["aroondown"]

        # ── 2. MACD ──
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macd_hist"] = dataframe["macd"] - dataframe["macdsignal"]

        # ── 3. ATR ──
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # ── 4. EMAs ──
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema_slope"] = dataframe["ema_200"] - dataframe["ema_200"].shift(5)
        dataframe["dist_to_ema"] = (
            dataframe["close"] - dataframe["ema_200"]
        ) / dataframe["ema_200"]

        # ── 5. ADX ──
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ── 6. RSI ──
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ── 7. Volume ──
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["volume_ratio"] = (
            dataframe["volume"] / dataframe["volume_ma"]
        ).replace([np.inf, -np.inf], 1).fillna(1)

        # ── 8. 4H MTF DATA MERGE ──
        if self.dp:
            inf_tf = "4h"
            informative = self.dp.get_pair_dataframe(
                pair=metadata["pair"], timeframe=inf_tf
            )
            if len(informative) > 0:
                informative["ema_50"] = ta.EMA(
                    informative, timeperiod=self.mtf_ema_period.value
                )
                informative["ema_slope"] = informative["ema_50"] - informative[
                    "ema_50"
                ].shift(self.mtf_slope_lookback.value)
                dataframe = merge_informative_pair(
                    dataframe, informative, self.timeframe, inf_tf, ffill=True
                )
            else:
                dataframe["ema_50_4h"] = dataframe["ema_200"]
                dataframe["ema_slope_4h"] = dataframe["ema_slope"]
        else:
            dataframe["ema_50_4h"] = dataframe["ema_200"]
            dataframe["ema_slope_4h"] = dataframe["ema_slope"]

        # ── 9. BTC REGIME (informational — NOT a gate) ──
        if self.dp and metadata["pair"] != "BTC/USDT:USDT":
            try:
                btc_dataframe = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1h")
                if len(btc_dataframe) > 0:
                    btc_dataframe["ema_50"] = ta.EMA(btc_dataframe, timeperiod=50)
                    btc_dataframe["ema_200"] = ta.EMA(btc_dataframe, timeperiod=200)
                    btc_dataframe = btc_dataframe[
                        ["date", "ema_50", "ema_200"]
                    ].copy()
                    btc_dataframe.columns = [
                        "date", "btc_ema_50", "btc_ema_200",
                    ]
                    dataframe = pd.merge(
                        dataframe, btc_dataframe, on="date", how="left"
                    )
                    dataframe["btc_ema_50"] = dataframe["btc_ema_50"].ffill()
                    dataframe["btc_ema_200"] = dataframe["btc_ema_200"].ffill()
                    # BTC golden cross = bullish bias
                    dataframe["btc_bullish"] = (
                        dataframe["btc_ema_50"] > dataframe["btc_ema_200"]
                    ).astype(int)
                else:
                    dataframe["btc_bullish"] = 0
            except Exception:
                dataframe["btc_bullish"] = 0
        else:
            dataframe["btc_bullish"] = 0

        return dataframe

    # ══════════════════════════════════════════════
    # EXTERNAL SIGNAL LOADING (soft — used as boosters, never gates)
    # ══════════════════════════════════════════════

    def _load_tradingagents_signal(self) -> dict:
        """Read TradingAgents signal — returns direction: +1/0/-1."""
        import json
        from pathlib import Path as P
        shared = P(os.getenv("SHARED_CONFIG_DIR", "/freqtrade/shared_config"))
        try:
            data = json.loads((shared / "tradingagents_signal.json").read_text())
            rating = data.get("rating", "Hold")
            approval = data.get("risk_assessment", {}).get("approval", True)
            if not approval:
                return {"direction": 0, "rating": rating}
            if rating in ("Buy", "Overweight"):
                return {"direction": 1, "rating": rating}
            elif rating in ("Sell", "Underweight"):
                return {"direction": -1, "rating": rating}
            return {"direction": 0, "rating": rating}
        except Exception:
            return {"direction": 0, "rating": "Hold"}

    def _load_sentiment(self) -> tuple:
        """Read sentiment score and regime — soft info only."""
        import json
        from pathlib import Path as P
        shared = P(os.getenv("SHARED_CONFIG_DIR", "/freqtrade/shared_config"))
        try:
            sentiment = json.loads((shared / "sentiment_signal.json").read_text())
            regime = json.loads((shared / "market_regime.json").read_text())
            return (
                float(sentiment.get("sentiment_score", 0.0)),
                str(regime.get("regime", "ranging")),
            )
        except Exception:
            return 0.0, "ranging"

    # ══════════════════════════════════════════════
    # POPULATE ENTRY TREND — CONFLUENCE SCORING
    # ══════════════════════════════════════════════

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Confluence scoring entry model.

        5 CORE PILLARS (each scores 0 or 1):
          P1: AROON CROSS  — directional crossover happened recently
          P2: AROON MOMENTUM — oscillator aligned with direction + increasing
          P3: MACD MOMENTUM — MACD vs signal aligned with direction
          P4: TREND ALIGNMENT — price vs EMA200 + 4h slope agree
          P5: TREND STRENGTH — ADX confirms move has force

        BOOSTERS (each adds +1 to score):
          B1: VOLUME CONFIRMED — volume > MA * factor
          B2: SENTIMENT ALIGNED — sentiment score agrees with direction
          B3: TA ALIGNED — TradingAgents rating agrees

        Entry: long_score >= min_confluence OR short_score >= min_confluence
        """

        # Load external signals ONCE (constant across dataframe in backtest)
        sentiment_score, market_regime = self._load_sentiment()
        ta_signal = self._load_tradingagents_signal()

        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        # ══════════════════════════════════════════
        # LONG CONFLUENCE SCORING
        # ══════════════════════════════════════════

        # P1: AROON CROSS — AroonUp crossed above AroonDown in last 3 candles
        #    (crosswind=3 for V2, always allow 3-bar window)
        p1_aroon_cross_long = (
            qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"]) |
            qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"]).shift(1) |
            qtpylib.crossed_above(dataframe["aroonup"], dataframe["aroondown"]).shift(2)
        ).astype(int)

        # P2: AROON MOMENTUM — oscillator > 0 (bullish) AND rising
        p2_aroon_momentum_long = (
            (dataframe["aroon_osc"] > 0) &
            (dataframe["aroon_osc"] > dataframe["aroon_osc"].shift(1))
        ).astype(int)

        # P3: MACD MOMENTUM — MACD > signal (macd_hist > 0) OR crossed recently
        p3_macd_momentum_long = (
            (dataframe["macd_hist"] > 0) |
            qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"]) |
            qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"]).shift(1)
        ).astype(int)

        # P4: TREND ALIGNMENT — Close > EMA200 OR (4h slope > 0)
        #    Softened: either 1h OR 4h alignment is enough (not both required)
        p4_trend_aligned_long = (
            (dataframe["close"] > dataframe["ema_200"]) |
            (dataframe["ema_slope_4h"] > 0)
        ).astype(int)

        # P5: TREND STRENGTH — ADX > threshold (move has force)
        p5_trend_strength_long = (
            dataframe["adx"] > self.adx_threshold.value
        ).astype(int)

        # ── BOOSTERS ──

        # B1: VOLUME CONFIRMED — volume above moving average * factor
        b1_volume_long = (
            dataframe["volume_ratio"] > self.volume_factor.value
        ).astype(int)

        # B2: SENTIMENT ALIGNED — positive sentiment (soft gate)
        b2_sentiment_long = 1 if sentiment_score > 0.15 else 0

        # B3: TA ALIGNED — TradingAgents bullish
        b3_ta_long = 1 if ta_signal["direction"] > 0 else 0

        # ── CONFLUENCE SCORE ──
        long_score = (
            p1_aroon_cross_long +
            p2_aroon_momentum_long +
            p3_macd_momentum_long +
            p4_trend_aligned_long +
            p5_trend_strength_long +
            b1_volume_long +
            b2_sentiment_long +
            b3_ta_long
        )

        # Store score for diagnostics
        dataframe["long_confluence"] = long_score

        # Entry: score >= threshold + volume > 0 (basic sanity)
        long_entry_mask = (long_score >= self.min_confluence.value) & (dataframe["volume"] > 0)

        dataframe.loc[long_entry_mask, "enter_long"] = 1
        dataframe.loc[long_entry_mask, "enter_tag"] = (
            "aroon_long_c" + long_score[long_entry_mask].astype(str)
        )

        # ══════════════════════════════════════════
        # SHORT CONFLUENCE SCORING
        # ══════════════════════════════════════════

        # P1: AROON CROSS — AroonDown crossed above AroonUp in last 3 candles
        p1_aroon_cross_short = (
            qtpylib.crossed_above(dataframe["aroondown"], dataframe["aroonup"]) |
            qtpylib.crossed_above(dataframe["aroondown"], dataframe["aroonup"]).shift(1) |
            qtpylib.crossed_above(dataframe["aroondown"], dataframe["aroonup"]).shift(2)
        ).astype(int)

        # P2: AROON MOMENTUM — oscillator < 0 (bearish) AND falling
        p2_aroon_momentum_short = (
            (dataframe["aroon_osc"] < 0) &
            (dataframe["aroon_osc"] < dataframe["aroon_osc"].shift(1))
        ).astype(int)

        # P3: MACD MOMENTUM — MACD < signal (bearish) OR crossed below recently
        p3_macd_momentum_short = (
            (dataframe["macd_hist"] < 0) |
            qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"]) |
            qtpylib.crossed_below(dataframe["macd"], dataframe["macdsignal"]).shift(1)
        ).astype(int)

        # P4: TREND ALIGNMENT — Close < EMA200 OR (4h slope < 0)
        p4_trend_aligned_short = (
            (dataframe["close"] < dataframe["ema_200"]) |
            (dataframe["ema_slope_4h"] < 0)
        ).astype(int)

        # P5: TREND STRENGTH — ADX > threshold
        p5_trend_strength_short = (
            dataframe["adx"] > self.adx_threshold.value
        ).astype(int)

        # ── BOOSTERS ──

        # B1: VOLUME CONFIRMED
        b1_volume_short = (
            dataframe["volume_ratio"] > self.volume_factor.value
        ).astype(int)

        # B2: SENTIMENT ALIGNED — negative sentiment
        b2_sentiment_short = 1 if sentiment_score < -0.15 else 0

        # B3: TA ALIGNED — TradingAgents bearish
        b3_ta_short = 1 if ta_signal["direction"] < 0 else 0

        # ── CONFLUENCE SCORE ──
        short_score = (
            p1_aroon_cross_short +
            p2_aroon_momentum_short +
            p3_macd_momentum_short +
            p4_trend_aligned_short +
            p5_trend_strength_short +
            b1_volume_short +
            b2_sentiment_short +
            b3_ta_short
        )

        dataframe["short_confluence"] = short_score

        # Entry: score >= threshold + volume > 0
        short_entry_mask = (short_score >= self.min_confluence.value) & (dataframe["volume"] > 0)

        dataframe.loc[short_entry_mask, "enter_short"] = 1
        dataframe.loc[short_entry_mask, "enter_tag"] = (
            "aroon_short_c" + short_score[short_entry_mask].astype(str)
        )

        return dataframe

    # ══════════════════════════════════════════════
    # POPULATE EXIT TREND
    # ══════════════════════════════════════════════

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals — primarily handled by custom_exit, but add basic exits."""

        # Exit long when Aroon oscillator flips bearish AND MACD crosses below
        dataframe.loc[
            (
                (dataframe["aroon_osc"] < 0) &
                (dataframe["macd_hist"] < 0)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "aroon_momentum_reversal")

        # Exit short when Aroon oscillator flips bullish AND MACD crosses above
        dataframe.loc[
            (
                (dataframe["aroon_osc"] > 0) &
                (dataframe["macd_hist"] > 0)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "aroon_momentum_reversal")

        return dataframe

    # ══════════════════════════════════════════════
    # CUSTOM STAKE AMOUNT
    # ══════════════════════════════════════════════

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        MAX_POSITION_USDT = 5000
        if proposed_stake > MAX_POSITION_USDT:
            return MAX_POSITION_USDT
        return proposed_stake

    # ══════════════════════════════════════════════
    # CUSTOM STOPLOSS — ATR-based dynamic
    # ══════════════════════════════════════════════

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """ATR-based dynamic stop loss."""

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.stoploss

        # Zombie killer: trades open > 6h and losing > 2% → tight stop
        if not trade.is_short:
            trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
            if trade_duration > 360 and current_profit < -0.02:
                return -0.01

        # Get ATR at entry
        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)
        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle["atr"]
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

    # ══════════════════════════════════════════════
    # CUSTOM EXIT
    # ══════════════════════════════════════════════

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[Union[str, bool]]:
        """R:R target exits + sentiment reversal detection."""

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]
        trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)

        try:
            entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
            atr_value = entry_candle["atr"]
        except (IndexError, KeyError):
            return None

        if pd.isna(atr_value) or atr_value <= 0:
            return None

        atr_move = atr_value * self.atr_multiplier.value
        exit_reason = None

        # Dynamic R:R extension if Aroon is strong
        risk_reward_ratio = self.risk_reward.value
        if trade.is_short and last_candle.get("aroondown", 0) > 80:
            risk_reward_ratio += 0.5
        elif not trade.is_short and last_candle.get("aroonup", 0) > 80:
            risk_reward_ratio += 0.5

        # Target profit based on R:R
        target_profit_pct = (atr_move * risk_reward_ratio) / current_rate
        if current_profit >= target_profit_pct:
            exit_reason = f"take_profit_{risk_reward_ratio}R"

        # Sentiment reversal (soft check — only if sentiment is very strong opposite)
        sentiment_score, _ = self._load_sentiment()
        if not exit_reason:
            if trade.is_short and sentiment_score > 0.5:
                exit_reason = "sentiment_reversal_bullish"
            elif not trade.is_short and sentiment_score < -0.5:
                exit_reason = "sentiment_reversal_bearish"

        return exit_reason

    # ══════════════════════════════════════════════
    # REGIME DETECTION (for diagnostics/outcome tracking)
    # ══════════════════════════════════════════════

    def _detect_regime_simple(self, dataframe: DataFrame) -> str:
        """Simple rule-based regime detection for outcome recording."""
        if len(dataframe) < 50:
            return "unknown"
        close = dataframe["close"]
        returns = close.pct_change().dropna()
        vol_20 = returns.rolling(20).std().iloc[-1] if len(returns) >= 20 else 0.02
        ret_20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
        adx = dataframe.get("adx", pd.Series([20] * len(dataframe)))
        adx_val = adx.iloc[-1] if len(adx) > 0 else 20

        if abs(ret_20) > 0.03:
            return "trending_up" if ret_20 > 0 else "trending_down"
        elif vol_20 > 0.015:
            return "volatile"
        else:
            return "ranging"

    # ══════════════════════════════════════════════
    # OUTCOME FEEDBACK LOOP
    # ══════════════════════════════════════════════

    def _record_outcome(self, trade: Trade, profit_pct: float) -> None:
        """Record a completed trade's outcome to the feedback loop JSON."""
        import json
        try:
            is_win = profit_pct > 0
            r_multiple = profit_pct / abs(self.stoploss) if self.stoploss != 0 else 0
            pair = trade.pair
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                regime = self._detect_regime_simple(dataframe) if len(dataframe) > 50 else "unknown"
            except Exception:
                regime = "unknown"

            record = {
                "trade_id": trade.trade_id,
                "pair": pair,
                "direction": "short" if trade.is_short else "long",
                "regime": regime,
                "entry_time": trade.open_date_utc.isoformat() if hasattr(trade, "open_date_utc") else str(trade.open_date),
                "exit_time": trade.close_date_utc.isoformat() if hasattr(trade, "close_date_utc") else str(trade.close_date),
                "pnl_pct": round(profit_pct * 100, 2),
                "r_multiple": round(r_multiple, 2),
                "is_win": is_win,
                "strategy": "AroonMomentumEngine_V2",
                "confluence_min": self.min_confluence.value,
            }

            if VDB_OUTCOME_PATH.exists():
                with open(VDB_OUTCOME_PATH, "r") as f:
                    history = json.load(f)
            else:
                history = {"outcomes": [], "regime_stats": {}}

            history["outcomes"].append(record)
            if len(history["outcomes"]) > 500:
                history["outcomes"] = history["outcomes"][-500:]

            # Recompute regime stats
            regime_stats = {}
            for o in history["outcomes"]:
                r = o.get("regime", "unknown")
                if r not in regime_stats:
                    regime_stats[r] = {"wins": 0, "losses": 0, "total_pnl": 0, "trades": 0}
                regime_stats[r]["trades"] += 1
                if o["is_win"]:
                    regime_stats[r]["wins"] += 1
                else:
                    regime_stats[r]["losses"] += 1
                regime_stats[r]["total_pnl"] += o["pnl_pct"]

            for r, s in regime_stats.items():
                s["win_rate"] = round(s["wins"] / s["trades"], 3) if s["trades"] > 0 else 0
                s["avg_pnl"] = round(s["total_pnl"] / s["trades"], 2) if s["trades"] > 0 else 0

            history["regime_stats"] = regime_stats

            with open(VDB_OUTCOME_PATH, "w") as f:
                json.dump(history, f, indent=2)

        except Exception as e:
            print(f"[WARN] Outcome recording failed: {e}")

    def custom_exit_price(self, pair: str, trade: Trade, current_time: datetime,
                          proposed_rate: float, current_rate: float,
                          exit_tag: Optional[str], **kwargs) -> float:
        """Hook: after a trade exits, record the outcome."""
        try:
            profit_pct = trade.calc_profit(proposed_rate)
            self._record_outcome(trade, profit_pct)
        except Exception:
            pass
        return proposed_rate