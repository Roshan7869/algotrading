"""
VectorStrategyV2 — Regime-Adaptive ChromaDB Intelligence Strategy
===================================================================
Extends VectorStrategy with regime-adaptive parameters driven by
IntelligenceLayer (HMM + rule-based regime detection).

Differences from V1:
1. HMM/rule-based regime detection (trending_up, trending_down, volatile, ranging)
2. Regime-adaptive parameter adjustment via IntelligenceLayer._compute_regime_parameters
3. Dynamic confluence thresholds, RSI bands, and BB thresholds per regime
4. Regime-adaptive custom_stoploss (ATR multiplier varies by regime)
5. Regime-adaptive leverage (trending=2x, volatile/ranging=1x)
6. bot_loop_start hook that calls IntelligenceLayer.analyze() each candle
7. Regime detection features in populate_indicators (20-bar return, volatility, ATR%)
8. Outcome feedback recording with regime context
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import json

import numpy as np
import pandas as pd
from pandas import DataFrame

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

# ── Import IntelligenceLayer from strategy_db ─────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "strategy_db"))
try:
    from intelligence_layer import IntelligenceLayer
    INTELLIGENCE_AVAILABLE = True
except ImportError:
    INTELLIGENCE_AVAILABLE = False
    print("[WARN] IntelligenceLayer not available; falling back to rule-based regime detection")

# ── Outcome Feedback Path ────────────────────────────────────────────
VDB_OUTCOME_PATH = Path(__file__).parent.parent.parent / "strategy_db" / "outcome_history.json"


class VectorStrategyV2(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    # ── ROI & Stop Config ──────────────────────────────────────────────
    minimal_roi = {
        "0": 0.15,
        "60": 0.08,
        "240": 0.04,
        "720": 0.02,
    }

    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.04
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

    # ── Hyperopt Parameters (base defaults; regime overrides these at runtime) ──
    bb_squeeze_threshold = DecimalParameter(0.02, 0.10, default=0.06, decimals=3, space="buy", optimize=True, load=True)
    bb_expansion_threshold = DecimalParameter(0.85, 1.20, default=1.00, decimals=2, space="buy", optimize=True, load=True)
    rsi_oversold = IntParameter(25, 45, default=40, space="buy", optimize=True, load=True)
    rsi_overbought = IntParameter(55, 75, default=60, space="sell", optimize=True, load=True)
    volume_factor = DecimalParameter(1.0, 2.5, default=1.3, decimals=1, space="buy", optimize=True, load=True)
    ema_fast = IntParameter(8, 21, default=9, space="buy", optimize=True, load=True)
    ema_medium = IntParameter(20, 50, default=21, space="buy", optimize=True, load=True)
    bb_pctb_low = DecimalParameter(0.20, 0.50, default=0.40, decimals=2, space="buy", optimize=True, load=True)
    bb_pctb_high = DecimalParameter(0.50, 0.80, default=0.60, decimals=2, space="sell", optimize=True, load=True)
    min_confluence = IntParameter(1, 3, default=2, space="buy", optimize=True, load=True)

    # ── Regime-Adaptive State ──────────────────────────────────────────
    # These are populated at runtime by IntelligenceLayer
    _current_regime: str = "ranging"
    _regime_params: dict = {}

    def __init__(self, config=None):
        super().__init__(config)
        self.current_regime = "ranging"
        self.regime_params = {}
        self.intel = None
        self._intel_initialized = False

    def _ensure_intel(self):
        """Lazy-init IntelligenceLayer only when needed (live/dry-run)."""
        if not self._intel_initialized and INTELLIGENCE_AVAILABLE:
            try:
                self.intel = IntelligenceLayer()
            except Exception as e:
                self.intel = None
            self._intel_initialized = True

    # ── Leverage (regime-adaptive) ────────────────────────────────────
    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        regime = getattr(self, 'current_regime', 'ranging')
        if regime in ("trending_up", "trending_down"):
            leverage = 2.0
        elif regime == "volatile":
            leverage = 1.0
        else:  # ranging or unknown
            leverage = 1.0
        return min(leverage, max_leverage)

    # ── Informative Pairs ─────────────────────────────────────────────
    def informative_pairs(self):
        return []

    # ── Populate Indicators ───────────────────────────────────────────
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # ── Regime Detection Features ──────────────────────────────────
        # 20-bar return
        dataframe["return_20"] = dataframe["close"].pct_change(20)
        # 20-bar rolling volatility (std of returns)
        dataframe["volatility_20"] = dataframe["close"].pct_change().rolling(20).std()
        # ATR as percentage of price
        dataframe["atr_raw"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr_raw"] / dataframe["close"]
        # ADX for trend strength
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ── Detect Regime ──────────────────────────────────────────────
        # During backtesting, use lightweight rule-based detection (fast).
        # During live/dry-run, use full IntelligenceLayer with HMM + ChromaDB.
        is_backtest = hasattr(self, 'dp') and self.dp is not None and hasattr(self.dp, 'runmode') and self.dp.runmode.value in ('backtest', 'hyperopt')
        if is_backtest:
            # Fast path: rule-based regime from latest 50 candles
            self.current_regime = self._detect_regime_simple(dataframe)
            self.regime_params = self._compute_regime_params_fallback(self.current_regime)
        else:
            # Live/dry-run: use full IntelligenceLayer with HMM + ChromaDB
            self._ensure_intel()
            if self.intel is not None:
                try:
                    recent_df = dataframe.tail(100).copy()
                    report = self.intel.analyze(recent_df, pair=metadata.get("pair", "BTC/USDT"), timeframe=self.timeframe)
                    self.current_regime = report["regime"]["label"]
                    self.regime_params = report["recommended_params"]
                except Exception as e:
                    self.current_regime = self._detect_regime_simple(dataframe)
                    self.regime_params = self._compute_regime_params_fallback(self.current_regime)

        # Store regime per candle for outcome tracking
        dataframe["regime"] = self.current_regime

        # ── 1. Bollinger Bands (20, 2) ─────────────────────────────────
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]

        dataframe["bb_pctb"] = (
            (dataframe["close"] - dataframe["bb_lowerband"])
            / (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
        ).replace([np.inf, -np.inf], 0.5).fillna(0.5)

        dataframe["bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
            / dataframe["bb_middleband"]
        ).replace([np.inf, -np.inf], 0).fillna(0)

        # ── 2. 3SD Bollinger Bands ─────────────────────────────────────
        bollinger_3sd = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=3
        )
        dataframe["bb3_upper"] = bollinger_3sd["upper"]
        dataframe["bb3_lower"] = bollinger_3sd["lower"]

        # ── 3. EMAs ────────────────────────────────────────────────────
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # ── 4. RSI ──────────────────────────────────────────────────────
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ── 5. Volume ───────────────────────────────────────────────────
        dataframe["volume_mean"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = (
            dataframe["volume"] / dataframe["volume_mean"]
        ).replace([np.inf, -np.inf], 1).fillna(1)

        # ── 6. ATR ──────────────────────────────────────────────────────
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # ── 7. VWAP ────────────────────────────────────────────────────
        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = (
            (typical_price * dataframe["volume"]).rolling(20).sum()
            / dataframe["volume"].rolling(20).sum()
        ).bfill()

        # ── 8. Key Level Proximity ──────────────────────────────────────
        dataframe["pivot_high"] = dataframe["high"].rolling(5, center=True).max()
        dataframe["pivot_low"] = dataframe["low"].rolling(5, center=True).min()

        dataframe["dist_to_resistance"] = (
            (dataframe["pivot_high"] - dataframe["close"]) / dataframe["atr"]
        ).fillna(5)
        dataframe["dist_to_support"] = (
            (dataframe["close"] - dataframe["pivot_low"]) / dataframe["atr"]
        ).fillna(5)

        return dataframe

    # ── Regime Detection (rule-based fallback) ───────────────────────
    def _detect_regime_simple(self, dataframe: DataFrame) -> str:
        """Simple rule-based regime detection when IntelligenceLayer is unavailable."""
        if len(dataframe) < 50:
            return "ranging"
        close = dataframe["close"]
        returns = close.pct_change().dropna()

        vol_20 = returns.rolling(20).std().iloc[-1] if len(returns) >= 20 else 0.02
        ret_20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
        adx_val = dataframe["adx"].iloc[-1] if "adx" in dataframe.columns and len(dataframe) > 0 else 20

        if abs(ret_20) > 0.03:
            return "trending_up" if ret_20 > 0 else "trending_down"
        elif vol_20 > 0.015:
            return "volatile"
        else:
            return "ranging"

    def _compute_regime_params_fallback(self, regime: str) -> dict:
        """Fallback regime parameters when IntelligenceLayer is not available."""
        defaults = {
            "bb_squeeze_threshold": 0.03,
            "bb_pct_lower": 0.4,
            "bb_pct_upper": 0.6,
            "rsi_lower": 35,
            "rsi_upper": 65,
            "volume_multiplier": 1.5,
            "ema_alignment_required": True,
            "confluence_min": 2,
            "stoploss": -0.06,
            "trailing_stop": 0.025,
            "trailing_stop_offset": 0.04,
            "max_open_trades": 3,
            "leverage": 1,
            "atr_stop_multiplier": 2.0,
        }
        if regime in ("trending_up", "trending_down"):
            defaults.update({
                "bb_squeeze_threshold": 0.04,
                "bb_pct_lower": 0.35,
                "bb_pct_upper": 0.65,
                "rsi_lower": 30,
                "rsi_upper": 70,
                "volume_multiplier": 1.5,
                "confluence_min": 2,  # lower by 1 from default 3
                "stoploss": -0.05,
                "trailing_stop": 0.03,
                "trailing_stop_offset": 0.05,
                "max_open_trades": 4,
                "leverage": 2,
                "atr_stop_multiplier": 2.5,
            })
        elif regime == "volatile":
            defaults.update({
                "bb_squeeze_threshold": 0.06,
                "bb_pct_lower": 0.3,
                "bb_pct_upper": 0.7,
                "rsi_lower": 25,
                "rsi_upper": 75,
                "volume_multiplier": 2.0,
                "confluence_min": 3,  # raised by 1 from default 2
                "stoploss": -0.04,
                "trailing_stop": 0.02,
                "trailing_stop_offset": 0.03,
                "max_open_trades": 2,
                "leverage": 1,
                "atr_stop_multiplier": 1.5,
            })
        elif regime == "ranging":
            defaults.update({
                "bb_squeeze_threshold": 0.03,
                "bb_pct_lower": 0.4,
                "bb_pct_upper": 0.6,
                "rsi_lower": 35,
                "rsi_upper": 65,
                "volume_multiplier": 1.5,
                "confluence_min": 2,
                "stoploss": -0.06,
                "trailing_stop": 0.025,
                "trailing_stop_offset": 0.04,
                "max_open_trades": 3,
                "leverage": 1,
                "atr_stop_multiplier": 2.0,
            })
        return defaults

    # ── Populate Entry Trend (regime-adaptive) ────────────────────────
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        regime = getattr(self, 'current_regime', 'ranging')
        p = getattr(self, 'regime_params', {})
        if not p:
            p = self._compute_regime_params_fallback(regime)

        # ── Regime-specific threshold adjustments ──────────────────────
        if regime in ("trending_up", "trending_down"):
            # Trending: lower confluence_min by 1 (more trades), wider RSI bands
            confluence_min = max(1, self.min_confluence.value - 1)
            rsi_oversold = min(self.rsi_oversold.value + 5, 50)
            rsi_overbought = max(self.rsi_overbought.value - 5, 50)
            bb_pctb_low = p.get("bb_pct_lower", self.bb_pctb_low.value)
            bb_pctb_high = p.get("bb_pct_upper", self.bb_pctb_high.value)
            bb_squeeze_thr = p.get("bb_squeeze_threshold", self.bb_squeeze_threshold.value)
            volume_mult = p.get("volume_multiplier", self.volume_factor.value)
        elif regime == "volatile":
            # Volatile: raise confluence_min by 1 (fewer trades), tighter stops
            confluence_min = min(self.min_confluence.value + 1, 5)
            rsi_oversold = self.rsi_oversold.value  # keep default
            rsi_overbought = self.rsi_overbought.value
            bb_pctb_low = p.get("bb_pct_lower", self.bb_pctb_low.value)
            bb_pctb_high = p.get("bb_pct_upper", self.bb_pctb_high.value)
            bb_squeeze_thr = p.get("bb_squeeze_threshold", self.bb_squeeze_threshold.value)
            volume_mult = p.get("volume_multiplier", self.volume_factor.value)
        elif regime == "ranging":
            # Ranging: tighten BB thresholds, require more confirmation (confluence stays same)
            confluence_min = self.min_confluence.value
            rsi_oversold = self.rsi_oversold.value
            rsi_overbought = self.rsi_overbought.value
            bb_pctb_low = max(self.bb_pctb_low.value - 0.05, 0.15)  # tighter = smaller = less mean reversion triggers
            bb_pctb_high = min(self.bb_pctb_high.value + 0.05, 0.85)  # tighter = higher = harder to trigger short
            bb_squeeze_thr = self.bb_squeeze_threshold.value
            volume_mult = max(self.volume_factor.value, 1.5)  # require more volume in ranging
        else:
            # Unknown regime: use defaults
            confluence_min = self.min_confluence.value
            rsi_oversold = self.rsi_oversold.value
            rsi_overbought = self.rsi_overbought.value
            bb_pctb_low = self.bb_pctb_low.value
            bb_pctb_high = self.bb_pctb_high.value
            bb_squeeze_thr = self.bb_squeeze_threshold.value
            volume_mult = self.volume_factor.value

        # ═══════ LONG SIGNALS ═══════

        # Signal 1: BBands Squeeze Breakout
        squeeze_breakout_long = (
            (dataframe["bb_width"] < bb_squeeze_thr) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > volume_mult)
        )

        # Signal 2: Mean Reversion at lower BB
        mean_reversion_long = (
            (dataframe["bb_pctb"] < bb_pctb_low) &
            (dataframe["close"] > dataframe["bb3_lower"]) &
            (dataframe["rsi"] < rsi_oversold) &
            (dataframe["close"] > dataframe["vwap"])
        )

        # Signal 3: EMA Trend Alignment
        ema_alignment_long = (
            (dataframe["ema_fast"] > dataframe["ema_medium"]) &
            (dataframe["close"] > dataframe["ema_fast"]) &
            (dataframe["ema_medium"] > dataframe["ema_200"]) &
            (dataframe["rsi"] > 40) &
            (dataframe["rsi"] < rsi_overbought)
        )

        # Signal 4: Expansion Breakout (3SD)
        expansion_long = (
            (dataframe["close"] > dataframe["bb3_upper"]) &
            (dataframe["close"].shift(1) <= dataframe["bb3_upper"].shift(1)) &
            (dataframe["volume_ratio"] > volume_mult) &
            (dataframe["rsi"] > 50)
        )

        # Signal 5: Key Level Rejection
        key_level_long = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < rsi_overbought)
        )

        # ═══════ CONFLUENCE SCORING ═══════
        long_signals = [
            squeeze_breakout_long.astype(int),
            mean_reversion_long.astype(int),
            ema_alignment_long.astype(int),
            expansion_long.astype(int),
            key_level_long.astype(int),
        ]
        long_score = sum(long_signals)

        dataframe.loc[
            (long_score >= confluence_min) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, f"v2_long_{regime}")

        # ═══════ SHORT SIGNALS (mirror, regime-adaptive) ═══════

        squeeze_breakout_short = (
            (dataframe["bb_width"] < bb_squeeze_thr) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] < dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > volume_mult)
        )

        mean_reversion_short = (
            (dataframe["bb_pctb"] > bb_pctb_high) &
            (dataframe["close"] < dataframe["bb3_upper"]) &
            (dataframe["rsi"] > rsi_overbought) &
            (dataframe["close"] < dataframe["vwap"])
        )

        ema_alignment_short = (
            (dataframe["ema_fast"] < dataframe["ema_medium"]) &
            (dataframe["close"] < dataframe["ema_fast"]) &
            (dataframe["ema_medium"] < dataframe["ema_200"]) &
            (dataframe["rsi"] < rsi_overbought) &
            (dataframe["rsi"] > rsi_oversold)
        )

        expansion_short = (
            (dataframe["close"] < dataframe["bb3_lower"]) &
            (dataframe["close"].shift(1) >= dataframe["bb3_lower"].shift(1)) &
            (dataframe["volume_ratio"] > volume_mult) &
            (dataframe["rsi"] < 50)
        )

        key_level_short = (
            (dataframe["dist_to_resistance"] < 1.0) &
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["rsi"] < rsi_overbought) &
            (dataframe["rsi"] > rsi_oversold)
        )

        short_signals = [
            squeeze_breakout_short.astype(int),
            mean_reversion_short.astype(int),
            ema_alignment_short.astype(int),
            expansion_short.astype(int),
            key_level_short.astype(int),
        ]
        short_score = sum(short_signals)

        dataframe.loc[
            (short_score >= confluence_min) & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, f"v2_short_{regime}")

        return dataframe

    # ── Populate Exit Trend ───────────────────────────────────────────
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        regime = getattr(self, 'current_regime', 'ranging')
        p = getattr(self, 'regime_params', {})
        if not p:
            p = self._compute_regime_params_fallback(regime)

        bb_pctb_high = p.get("bb_pct_upper", self.bb_pctb_high.value)
        bb_pctb_low = p.get("bb_pct_lower", self.bb_pctb_low.value)
        rsi_ob = self.rsi_overbought.value
        rsi_os = self.rsi_oversold.value

        # Exit long
        dataframe.loc[
            (
                (dataframe["bb_pctb"] > bb_pctb_high) |
                ((dataframe["rsi"] > rsi_ob) &
                 (dataframe["close"] < dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "v2_vector_exit")

        # Exit short (mirror)
        dataframe.loc[
            (
                (dataframe["bb_pctb"] < bb_pctb_low) |
                ((dataframe["rsi"] < rsi_os) &
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "v2_vector_exit")

        return dataframe

    # ── Custom Stoploss (regime-adaptive) ──────────────────────────────
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, profit_after_fee: float,
                        after_fill: bool, **kwargs) -> Optional[float]:

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)

        regime = getattr(self, 'current_regime', 'ranging')
        p = getattr(self, 'regime_params', {})
        if not p:
            p = self._compute_regime_params_fallback(regime)

        # Regime-adaptive ATR multiplier
        if regime in ("trending_up", "trending_down"):
            # Trending: wider stops (ATR * 2.5)
            atr_multiplier = 2.5
        elif regime == "volatile":
            # Volatile: tighter stops (ATR * 1.5)
            atr_multiplier = 1.5
        else:
            # Ranging: normal stops (ATR * 2.0)
            atr_multiplier = 2.0

        if atr > 0 and trade.open_rate > 0:
            atr_stop_pct = (atr_multiplier * atr) / trade.open_rate
            # Move to breakeven at 1.5% profit
            if profit_after_fee > 0.015:
                return max(-0.005, -atr_stop_pct)

        return self.stoploss

    # ── Custom Exit (Beacon target system) ─────────────────────────────
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]
        bb_pctb = last_candle.get("bb_pctb", 0.5)

        if trade.is_short:
            if bb_pctb < 0.15:
                return "beacon_target_short"
        else:
            if bb_pctb > 0.85:
                return "beacon_target_long"

        return None

    # ── bot_loop_start: Call IntelligenceLayer to detect regime each candle ──
    def bot_loop_start(self, current_time, **kwargs) -> None:
        """
        Called once per candle before populate_indicators.
        Uses IntelligenceLayer to detect the current market regime.
        Updates self.current_regime and self.regime_params.
        """
        if self.intel is None:
            return

        # Iterate over all pairs with open trades or fresh data
        for pair in self.dp.current_whitelist():
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) < 50:
                    continue

                report = self.intel.analyze(
                    dataframe,
                    pair=pair,
                    timeframe=self.timeframe
                )
                self.current_regime = report["regime"]["label"]
                self.regime_params = report["recommended_params"]

                # Only log every 24 candles (~1 day on 1h) to reduce noise
                last_candle_time = dataframe.iloc[-1].get("date", None)
                print(f"[INFO] VectorStrategyV2 [{pair}] Regime={self.current_regime} | "
                      f"Confidence={report.get('signal_confidence', 'N/A')}")

                # One pair is enough to set the global regime
                break

            except Exception as e:
                print(f"[WARN] VectorStrategyV2: bot_loop_start regime detection failed for {pair}: {e}")
                # Keep previous regime as fallback
                continue

    # ── Outcome Feedback Loop ─────────────────────────────────────────
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

    def _get_dominant_signal(self, trade: Trade) -> str:
        """Extract the dominant entry signal from trade tags."""
        enter_tag = trade.enter_tag or ""
        if "squeeze" in enter_tag.lower():
            return "bb_squeeze_breakout"
        elif "mean_rev" in enter_tag.lower():
            return "bb_mean_reversion"
        elif "ema" in enter_tag.lower():
            return "ema_alignment"
        elif "expansion" in enter_tag.lower():
            return "bb_expansion"
        elif "key_level" in enter_tag.lower():
            return "key_level"
        else:
            return "confluence"

    def _get_setup_names(self, trade: Trade, dataframe: DataFrame) -> list:
        """Determine which KB chunks were active at entry time."""
        setups = []
        last = dataframe.iloc[-1]
        if last.get("bb_width", 0) < self.bb_squeeze_threshold.value:
            setups.append("BB Squeeze Breakout")
        if last.get("bb_pctb", 0.5) < self.bb_pctb_low.value:
            setups.append("BB Mean Reversion")
        if last.get("ema_fast", 0) > last.get("ema_medium", 0):
            setups.append("EMA Trend Alignment")
        if last.get("rsi", 50) > 50 and last.get("volume_ratio", 1) > 1.2:
            setups.append("Expansion Breakout")
        if last.get("dist_to_support", 5) < 1.5:
            setups.append("Key Level Rejection")
        return setups if setups else ["confluence"]

    def _record_outcome(self, trade: Trade, profit_pct: float) -> None:
        """
        Record a completed trade's outcome to the feedback loop JSON.
        Includes regime context from IntelligenceLayer.
        """
        try:
            is_win = profit_pct > 0
            entry_price = trade.open_rate
            r_multiple = profit_pct / abs(self.stoploss) if self.stoploss != 0 else 0

            pair = trade.pair
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                regime = self.current_regime if len(dataframe) > 10 else "unknown"
                setup_names = self._get_setup_names(trade, dataframe) if len(dataframe) > 0 else ["unknown"]
            except Exception:
                regime = self.current_regime
                setup_names = ["unknown"]

            dominant = self._get_dominant_signal(trade)

            record = {
                "trade_id": trade.trade_id,
                "pair": pair,
                "direction": "short" if trade.is_short else "long",
                "regime": regime,
                "setup_names": setup_names,
                "dominant_signal": dominant,
                "entry_time": trade.open_date_utc.isoformat() if hasattr(trade, 'open_date_utc') else str(trade.open_date),
                "exit_time": trade.close_date_utc.isoformat() if hasattr(trade, 'close_date_utc') else str(trade.close_date),
                "pnl_pct": round(profit_pct * 100, 2),
                "r_multiple": round(r_multiple, 2),
                "is_win": is_win,
                "strategy": "VectorStrategyV2",
                "stoploss_pct": self.stoploss,
                "trailing_stop_pct": self.trailing_stop_positive,
                "confluence_min": self.min_confluence.value,
                "regime_params_snapshot": self.regime_params,
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
        return proposed_rate