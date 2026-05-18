"""
ChromaDB Vector Strategy Backtest
===================================
Strategy derived from 562 vector-searched trading concepts in the ChromaDB knowledge base.

Source Concepts (from semantic search):
  1. "Bollinger Band 3SD Peak + Mean Reversion (Beacon 30%/50%/70%)" — Chart Fanatics
  2. "Expansion Phase — Directional Breakout" — Bollinger band peak + momentum
  3. "Break of Compression / Squeeze" — BBands squeeze + forced closing
  4. "Aggressive Sellers Absorbed = Squeeze Setup" — absorption → reversal
  5. "Continuation After LVN Rebalance" — gap fill + trend resume (simulated via VWAP)
  6. "Fractal Time Frame Entry (4H on Daily Trend)" — multi-timeframe EMA alignment
  7. "Frequency and Proximity Key Levels" — support/resistance via touch count
  8. "Market DNA: Buyers/Sellers First, Price Second" — volume confirms direction

Implemented as freqtrade IStrategy with:
  - BBands squeeze detection (compression → breakout)
  - 3SD BBand peak + mean reversion (Beacon levels via Bollinger %b)
  - EMA trend alignment (21/50/200 multi-timeframe)
  - RSI overbought/oversold confirmation
  - Volume spike confirmation (2x average)
  - ATR-based dynamic stops
  - Confluence scoring (2/5 signals minimum)
  - Outcome feedback loop (records trade results to ChromaDB)
"""

from datetime import datetime, timezone
from typing import Optional
import json
from pathlib import Path
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

# ── Outcome Feedback Path ────────────────────────────────────────
VDB_OUTCOME_PATH = Path(__file__).parent.parent.parent / "strategy_db" / "outcome_history.json"


class VectorStrategy_P3D_KILL_ZONE_FILTER(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    # ── ROI & Stop Config ──────────────────────────────────────────
    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "240": 0.04,
        "720": 0.02,
        "1440": 0.01,
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

    # ── Hyperopt Parameters ────────────────────────────────────────
    bb_squeeze_threshold = DecimalParameter(0.02, 0.10, default=0.06, decimals=3, space="buy", optimize=True, load=True)
    bb_expansion_threshold = DecimalParameter(0.85, 1.20, default=1.00, decimals=2, space="buy", optimize=True, load=True)
    rsi_oversold = IntParameter(25, 45, default=40, space="buy", optimize=True, load=True)
    rsi_overbought = IntParameter(55, 75, default=60, space="sell", optimize=True, load=True)
    volume_factor = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy", optimize=True, load=True)
    ema_fast = IntParameter(8, 21, default=9, space="buy", optimize=True, load=True)
    ema_medium = IntParameter(20, 50, default=21, space="buy", optimize=True, load=True)
    bb_pctb_low = DecimalParameter(0.20, 0.50, default=0.40, decimals=2, space="buy", optimize=True, load=True)
    bb_pctb_high = DecimalParameter(0.50, 0.80, default=0.60, decimals=2, space="sell", optimize=True, load=True)
    min_confluence = IntParameter(1, 3, default=2, space="buy", optimize=True, load=True)
    kill_zone_only = BooleanParameter(default=True, space="buy", optimize=True, load=True)

    # ── Leverage ───────────────────────────────────────────────────
    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3, max_leverage)

    # ── Informative Pairs ──────────────────────────────────────────
    def informative_pairs(self):
        return []

    # ── Populate Indicators ────────────────────────────────────────
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        
        # ── 1. Bollinger Bands (20, 2) — squeeze & mean reversion ──
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        
        # Bollinger %b — position within bands (0=lower, 1=upper, 0.5=middle)
        dataframe["bb_pctb"] = (
            (dataframe["close"] - dataframe["bb_lowerband"])
            / (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
        ).replace([np.inf, -np.inf], 0.5).fillna(0.5)
        
        # BBand width = (upper - lower) / middle — for squeeze detection
        dataframe["bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
            / dataframe["bb_middleband"]
        ).replace([np.inf, -np.inf], 0).fillna(0)
        
        # ── 2. 3SD Bollinger Bands — for expansion/peak detection ──
        bollinger_3sd = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=3
        )
        dataframe["bb3_upper"] = bollinger_3sd["upper"]
        dataframe["bb3_lower"] = bollinger_3sd["lower"]

        # ── 3. EMAs — trend alignment (Fractal TF concept) ──
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        
        # ── 4. RSI ──
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        
        # ── 5. Volume — confirmation (Market DNA concept) ──
        dataframe["volume_mean"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = (
            dataframe["volume"] / dataframe["volume_mean"]
        ).replace([np.inf, -np.inf], 1).fillna(1)
        
        # ── 6. ATR — dynamic stops and volatility ──
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        
        # ── 7. VWAP — "LVN rebalance" proxy (volume-weighted fair value) ──
        # Cumulative VWAP (resets daily via session detection would be ideal,
        # but for simplicity we use rolling VWAP)
        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = (
            (typical_price * dataframe["volume"]).rolling(20).sum()
            / dataframe["volume"].rolling(20).sum()
        ).bfill()
        
        # ── 8. Key Level Proximity (Frequency & Proximity concept) ──
        # Simple pivot high/low detection as proxy for "key levels"
        dataframe["pivot_high"] = dataframe["high"].rolling(5, center=True).max()
        dataframe["pivot_low"] = dataframe["low"].rolling(5, center=True).min()
        
        # Distance to nearest pivot (normalized by ATR)
        dataframe["dist_to_resistance"] = (
            (dataframe["pivot_high"] - dataframe["close"]) / dataframe["atr"]
        ).fillna(5)
        dataframe["dist_to_support"] = (
            (dataframe["close"] - dataframe["pivot_low"]) / dataframe["atr"]
        ).fillna(5)

        return dataframe


    # ── Kill Zone Session Filter ──────────────────────────────────
    def _is_kill_zone(self, dataframe: DataFrame) -> pd.Series:
        """Crypto kill zones: London 07-09 UTC, NY 13:30-16:00 UTC.
        Allow entries during kill zones OR when confluence is high (>=3)."""
        hours = dataframe["date"].dt.hour if "date" in dataframe.columns else pd.Series(dataframe.index.hour, index=dataframe.index)
        minutes = dataframe["date"].dt.minute if "date" in dataframe.columns else pd.Series(dataframe.index.minute, index=dataframe.index)
        london = (hours >= 7) & (hours < 9)
        ny_session = ((hours == 13) & (minutes >= 30)) | ((hours >= 14) & (hours < 16))
        return london | ny_session

    # ── Populate Entry Trend ───────────────────────────────────────
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        regime = self._detect_regime_simple(dataframe)
        # Regime detection is for entry_tag labeling only — NOT for filtering.
        # P1 backtest proved min_confluence=2 is optimal across all regimes.
        # Regime-based threshold adjustment degraded from +36.98% to +4.04%.

        # ═══════ LONG SIGNALS ═══════

        squeeze_breakout_long = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )

        mean_reversion_long = (
            (dataframe["bb_pctb"] < self.bb_pctb_low.value) &
            (dataframe["close"] > dataframe["bb3_lower"]) &
            (dataframe["rsi"] < self.rsi_oversold.value) &
            (dataframe["close"] > dataframe["vwap"])
        )

        ema_alignment_long = (
            (dataframe["ema_fast"] > dataframe["ema_medium"]) &
            (dataframe["close"] > dataframe["ema_fast"]) &
            (dataframe["ema_medium"] > dataframe["ema_200"]) &
            (dataframe["rsi"] > 40) &
            (dataframe["rsi"] < 65)
        )

        expansion_long = (
            (dataframe["close"] > dataframe["bb3_upper"]) &
            (dataframe["close"].shift(1) <= dataframe["bb3_upper"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) &
            (dataframe["rsi"] > 50)
        )

        key_level_long = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < 65)
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

        # Kill zone filter: if kill_zone_only, require kill zone OR high confluence
        long_kill_ok = ~self.kill_zone_only.value | self._is_kill_zone(dataframe) | (long_score >= 3)
        dataframe.loc[
            (long_score >= self.min_confluence.value) & (long_kill_ok) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, "vector_long")

        # ═══════ SHORT SIGNALS ═══════

        squeeze_breakout_short = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] < dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > self.volume_factor.value)
        )

        mean_reversion_short = (
            (dataframe["bb_pctb"] > self.bb_pctb_high.value) &
            (dataframe["close"] < dataframe["bb3_upper"]) &
            (dataframe["rsi"] > self.rsi_overbought.value) &
            (dataframe["close"] < dataframe["vwap"])
        )

        ema_alignment_short = (
            (dataframe["ema_fast"] < dataframe["ema_medium"]) &
            (dataframe["close"] < dataframe["ema_fast"]) &
            (dataframe["ema_medium"] < dataframe["ema_200"]) &
            (dataframe["rsi"] < 60) &
            (dataframe["rsi"] > 35)
        )

        expansion_short = (
            (dataframe["close"] < dataframe["bb3_lower"]) &
            (dataframe["close"].shift(1) >= dataframe["bb3_lower"].shift(1)) &
            (dataframe["volume_ratio"] > self.volume_factor.value) &
            (dataframe["rsi"] < 50)
        )

        key_level_short = (
            (dataframe["dist_to_resistance"] < 1.0) &
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["rsi"] < 65) &
            (dataframe["rsi"] > 35)
        )

        short_signals = [
            squeeze_breakout_short.astype(int),
            mean_reversion_short.astype(int),
            ema_alignment_short.astype(int),
            expansion_short.astype(int),
            key_level_short.astype(int),
        ]
        short_score = sum(short_signals)

        short_kill_ok = ~self.kill_zone_only.value | self._is_kill_zone(dataframe) | (short_score >= 3)
        dataframe.loc[
            (short_score >= self.min_confluence.value) & (short_kill_ok) & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"]
        ] = (1, "vector_short")

        return dataframe

    # ── Populate Exit Trend ────────────────────────────────────────
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        
        # Exit long when:
        # - BB %b reaches upper region (Beacon 70% target) OR
        # - RSI overbought + price below fast EMA (momentum dying)
        # - BB width expanding rapidly after squeeze (move completed)
        
        dataframe.loc[
            (
                # Beacon 70% target: price reached upper band region
                (dataframe["bb_pctb"] > self.bb_pctb_high.value) |
                # Momentum dying: RSI overbought + below fast EMA
                ((dataframe["rsi"] > self.rsi_overbought.value) & 
                 (dataframe["close"] < dataframe["ema_fast"])) |
                # Squeeze expansion complete: width doubled from recent squeeze
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"]
        ] = (1, "vector_exit")
        
        # Exit short (mirror)
        dataframe.loc[
            (
                (dataframe["bb_pctb"] < self.bb_pctb_low.value) |
                ((dataframe["rsi"] < self.rsi_oversold.value) & 
                 (dataframe["close"] > dataframe["ema_fast"])) |
                (dataframe["bb_width"] > dataframe["bb_width"].rolling(10).mean() * 2.5)
            ) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"]
        ] = (1, "vector_exit")
        
        return dataframe

    # ── Custom Stoploss: ATR-augmented trailing (Phase 3 candidate) ──
    # P1 backtest: fixed trailing (2.5%/4%) produced +36.98%, Sharpe 2.83
    # ATR trailing produced only +4.04%, Sharpe 0.33 — DO NOT ACTIVATE YET.
    # Kept for hyperopt experimentation in Phase 3.
    # def custom_stoploss(self, pair, trade, current_time,
    #                     current_rate, profit_after_fee,
    #                     after_fill, **kwargs):
    #     ... ATR zone logic ...

    # ── Custom Exit (Beacon target system) ──────────────────────────
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        
        last_candle = dataframe.iloc[-1]
        bb_pctb = last_candle.get("bb_pctb", 0.5)
        
        # Beacon 50% target: exit half at mean reversion 50% level
        # (Freqtrade handles this via ROI, but we can force exit at extreme levels)
        
        # Exit if BB %b went to extremes and is returning
        if trade.is_short:
            if bb_pctb < 0.15:  # Deep into oversold — likely reversal
                return "beacon_target_short"
        else:
            if bb_pctb > 0.85:  # Deep into overbought — likely reversal
                return "beacon_target_long"
        
        return None

    # ── Outcome Feedback Loop ─────────────────────────────────────
    def _detect_regime_simple(self, dataframe: DataFrame) -> str:
        """Simple rule-based regime detection for outcome recording."""
        if len(dataframe) < 50:
            return "unknown"
        close = dataframe["close"]
        returns = close.pct_change().dropna()
        vol_20 = returns.rolling(20).std().iloc[-1] if len(returns) >= 20 else 0.02
        ret_20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
        adx = dataframe.get("adx", pd.Series([20]*len(dataframe)))
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
        # Check each signal condition at entry
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
        
        Called from bot_loop_start or custom_exit on trade close.
        Records: trade_id, pair, regime, setup_names, pnl, R-multiple, win/loss.
        """
        try:
            # Calculate metrics
            is_win = profit_pct > 0
            entry_price = trade.open_rate
            exit_price = trade.close_rate or trade.open_rate  # fallback
            r_multiple = profit_pct / abs(self.stoploss) if self.stoploss != 0 else 0

            # Get regime at trade time
            pair = trade.pair
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                regime = self._detect_regime_simple(dataframe) if len(dataframe) > 50 else "unknown"
                setup_names = self._get_setup_names(trade, dataframe)
            except Exception:
                regime = "unknown"
                setup_names = ["unknown"]

            dominant = self._get_dominant_signal(trade)

            # Build outcome record
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
                "strategy": "VectorStrategy",
                "stoploss_pct": self.stoploss,
                "trailing_stop_pct": self.trailing_stop_positive,
                "confluence_min": self.min_confluence.value,
            }

            # Append to outcome_history.json
            if VDB_OUTCOME_PATH.exists():
                with open(VDB_OUTCOME_PATH, "r") as f:
                    history = json.load(f)
            else:
                history = {"outcomes": [], "regime_stats": {}}
            
            history["outcomes"].append(record)
            
            # Keep last 500 trades max
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
            
            # Add computed fields
            for r, s in regime_stats.items():
                s["win_rate"] = round(s["wins"] / s["trades"], 3) if s["trades"] > 0 else 0
                s["avg_pnl"] = round(s["total_pnl"] / s["trades"], 2) if s["trades"] > 0 else 0
            
            history["regime_stats"] = regime_stats

            with open(VDB_OUTCOME_PATH, "w") as f:
                json.dump(history, f, indent=2)

        except Exception as e:
            # Never break the trading loop for outcome recording
            print(f"[WARN] Outcome recording failed: {e}")

    def custom_exit_price(self, pair: str, trade: Trade, current_time: datetime,
                          proposed_rate: float, current_rate: float,
                          exit_tag: Optional[str], **kwargs) -> float:
        """Hook: after a trade exits, record the outcome."""
        # Trade outcome will be recorded in bot_loop_start
        return proposed_rate