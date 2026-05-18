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

from datetime import datetime, timezone, timedelta
from typing import Optional
import json
import os
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

FUTURES_DATA_DIR = Path(__file__).parent.parent.parent / "user_data" / "data" / "binance" / "futures"

FUTURES_DATA_DIR = Path(__file__).parent.parent.parent / "user_data" / "data" / "binance" / "futures"

# ── Position Sizer ────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.risk_management.position_sizer import PositionSizer

# ── Outcome Feedback Path ────────────────────────────────────────
VDB_OUTCOME_PATH = Path(__file__).parent.parent.parent / "strategy_db" / "outcome_history.json"
VDB_SYNC_PATH = Path(__file__).parent.parent.parent / "strategy_db"

# Lazy import outcome_sync to avoid ChromaDB dependency during backtest init
_outcome_sync = None
def _get_outcome_sync():
    global _outcome_sync
    if _outcome_sync is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("outcome_sync", VDB_SYNC_PATH / "outcome_sync.py")
        _outcome_sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_outcome_sync)
    return _outcome_sync

# ── HMM Regime Detector ─────────────────────────────────────────
HMM_MODEL_PATH = Path(__file__).parent.parent.parent / "strategy_db" / "regime_hmm.pkl"

_hmm_detector = None
def _get_hmm_detector():
    global _hmm_detector
    if _hmm_detector is None:
        from strategy_db.regime_detector_hmm import HMMRegimeDetector
        _hmm_detector = HMMRegimeDetector()
        if HMM_MODEL_PATH.exists():
            _hmm_detector.load(str(HMM_MODEL_PATH))
    return _hmm_detector

# ── Circuit Breaker Path ─────────────────────────────────────────
CB_PATH = Path(__file__).parent.parent.parent / "shared_config" / "circuit_breaker.json"

# Circuit breaker thresholds
CB_DAILY_DD_PCT = 2.0       # Daily drawdown threshold (%)
CB_WEEKLY_DD_PCT = 4.0      # Weekly drawdown threshold (%)
CB_MONTHLY_DD_PCT = 8.0     # Monthly drawdown threshold (%)
CB_COOLING_HOURS = 4        # Hours before COOLING → HEALTHY
CB_PAUSED_COOLING_HOURS = 24  # Hours before PAUSED → COOLING


class VectorStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short: bool = False

    # ── ATR Position Sizing & Stoploss ─────────────────────────────
    RISK_PER_TRADE = 0.01
    ATR_STOP_MULTIPLIER = 3.0  # ATR * 3.0 = ~4.5% stop on BTC 1h (was 1.5 too tight)
    REGIME_MULTIPLIERS = {
        "trending_up": 1.0,
        "trending_down": 1.0,
        "ranging": 0.7,
        "volatile": 0.5,
        "unknown": 1.0,
    }

    # ── HMM Regime Signal Matrix ────────────────────────────────────
    # Maps each regime to which signals are enabled + confluence adjustments
    SIGNAL_MATRIX = {
        "trending_up": {
            "enabled": ["expansion", "squeeze_breakout", "key_level"],
            "disabled": ["mean_reversion", "ema_alignment"],
        },
        "trending_down": {
            "enabled": ["squeeze_breakout", "mean_reversion"],
            "disabled": ["expansion", "ema_alignment", "key_level"],
        },
        "ranging": {
            "enabled": ["mean_reversion", "key_level"],
            "disabled": ["expansion", "squeeze_breakout", "ema_alignment"],
        },
        "volatile": {
            "enabled": ["squeeze_breakout", "expansion"],
            "disabled": ["mean_reversion", "ema_alignment", "key_level"],
        },
        "unknown": {
            "enabled": ["squeeze_breakout", "mean_reversion", "ema_alignment", "expansion", "key_level"],
            "disabled": [],
        },
    }

    # Map user-facing signal key to internal boolean Series key
    _SIGNAL_KEY_MAP = {
        "squeeze_breakout": "squeeze_breakout",
        "mean_reversion": "mean_reversion",
        "ema_alignment": "ema_alignment",
        "expansion": "expansion",
        "key_level": "key_level",
    }

    # ── ROI & Stop Config ──────────────────────────────────────────
    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "240": 0.04,
        "720": 0.02,
        "1440": 0.01,
    }

    stoploss = -0.06
    trailing_stop = False  # ATR custom_stoploss replaces trailing
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 200

    def __init__(self, config: dict = None) -> None:
        super().__init__(config)
        self._funding_cache: dict[str, pd.DataFrame] = {}
        self._oi_cache: dict[str, pd.DataFrame] = {}
        self._volume_cache: dict[str, pd.DataFrame] = {}
        self._atr_cache: dict[str, float] = {}
        self._position_sizer = PositionSizer(
            total_capital=float(config.get("available_capital", config.get("stake_amount", 1000))) if config else 1000.0,
            max_positions=config.get("max_open_trades", 5) if config else 5,
        )

        FUNDING_FILE = FUTURES_DATA_DIR / "BTC_USDT_USDT-1h-funding_rate.feather"
        OI_FILE = FUTURES_DATA_DIR / "BTC_USDT_USDT-1h-futures.feather"

        if FUNDING_FILE.exists():
            df = pd.read_feather(FUNDING_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ms, UTC]")
            df.rename(columns={"open": "funding_rate"}, inplace=True)
            df = df[["date", "funding_rate"]].dropna()
            self._funding_cache["BTC/USDT:USDT"] = df

        if OI_FILE.exists():
            df_oi = pd.read_feather(OI_FILE)
            df_oi["date"] = pd.to_datetime(df_oi["date"], utc=True).astype("datetime64[ms, UTC]")
            df_oi.rename(columns={"volume": "open_interest"}, inplace=True)
            df_oi = df_oi[["date", "open_interest"]].dropna()
            self._oi_cache["BTC/USDT:USDT"] = df_oi
            # Also cache real volume from futures data (mark data has zero volume)
            df_vol = pd.read_feather(OI_FILE)
            df_vol["date"] = pd.to_datetime(df_vol["date"], utc=True).astype("datetime64[ms, UTC]")
            df_vol.rename(columns={"volume": "real_volume"}, inplace=True)
            df_vol = df_vol[["date", "real_volume"]].dropna()
            self._volume_cache["BTC/USDT:USDT"] = df_vol

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ── Signal Weights for Weighted Confluence ─────────────────────
    SIGNAL_WEIGHTS = {
        "bb_expansion": 0.30,
        "rsi_oversold": 0.20,
        "volume_factor": 0.15,
        "key_level": 0.20,
        "bb_squeeze": 0.15,
    }

    # ── Regime-Adjusted Confluence Thresholds ──────────────────────
    REGIME_THRESHOLDS = {
        "trending_up": 0.35,
        "trending_down": 0.40,
        "ranging": 0.45,
        "volatile": 0.55,
        "unknown": 0.45,
    }

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
    confluence_weight = DecimalParameter(0.30, 0.65, default=0.45, decimals=2, space="buy", optimize=True, load=True)
    # DEPRECATED: min_confluence kept for backward compatibility — use confluence_weight instead
    min_confluence = IntParameter(1, 3, default=2, space="buy", optimize=False, load=True)

    # ── Leverage ───────────────────────────────────────────────────
    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3, max_leverage)

    # ── ATR Position Sizing ──────────────────────────────────────
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: Optional[float], max_stake: float,
                            leverage: float, entry_tag: Optional[str], side: str,
                            **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 2:
            return proposed_stake

        last = dataframe.iloc[-1]
        atr = last.get("atr", 0)
        if atr is None or atr <= 0:
            return proposed_stake

        self._atr_cache[pair] = atr

        regime = last.get("regime", "unknown")
        regime_mult = self.REGIME_MULTIPLIERS.get(regime, 1.0)

        stop_distance = atr * self.ATR_STOP_MULTIPLIER
        if stop_distance <= 0:
            return proposed_stake

        equity = proposed_stake
        risk_amount = equity * self.RISK_PER_TRADE
        atr_stake = risk_amount / (stop_distance / current_rate) if current_rate > 0 else proposed_stake
        atr_stake *= regime_mult

        if self._position_sizer is not None and len(self._atr_cache) > 0:
            iv_weight = self._position_sizer.calculate_position_size(
                pair=pair, atr_value=atr,
                all_pair_atrs=dict(self._atr_cache),
                base_stake=atr_stake,
            )
            atr_stake = max(atr_stake * 0.5, min(iv_weight, atr_stake * 1.5))

        return max(min_stake or atr_stake, min(atr_stake, max_stake))

    # ── Confirm Trade Entry (funding rate gate) ──────────────────
    def confirm_trade_entry(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: Optional[float], max_stake: float,
                            leverage: float, entry_tag: Optional[str], side: str,
                            **kwargs) -> bool:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 1:
            return True

        last = dataframe.iloc[-1]
        funding_regime = last.get("funding_regime", "neutral")
        oi_signal = last.get("oi_signal", "neutral")
        funding_rate = last.get("funding_rate", 0.0)

        # Block trades against extreme crowding
        if side == "long" and funding_regime == "crowded_long":
            if oi_signal == "oi_surge":
                return False
        if side == "short" and funding_regime == "crowded_short":
            if oi_signal == "oi_dump":
                return False

        # Write funding signal to shared_config
        self._write_funding_signal(pair, funding_rate, funding_regime, oi_signal, side)

        return True

    def _write_funding_signal(self, pair: str, funding_rate: float,
                              funding_regime: str, oi_signal: str,
                              trade_side: str) -> None:
        try:
            signal_path = Path(__file__).resolve().parent.parent.parent / "shared_config" / "sentiment_signal.json"
            payload = {
                "pair": pair,
                "funding_rate": round(funding_rate, 8),
                "funding_regime": funding_regime,
                "oi_signal": oi_signal,
                "trade_side": trade_side,
                "signal_type": "funding_rate_filter",
                "_timestamp": datetime.now(timezone.utc).isoformat(),
                "_written_by": "VectorStrategy_Phase5",
            }
            signal_path.parent.mkdir(parents=True, exist_ok=True)
            with open(signal_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[WARN] Funding signal write failed: {e}")

    def _write_regime_json(self, dataframe: DataFrame, pair: str) -> None:
        try:
            last = dataframe.iloc[-1]
            regime = str(last.get("regime", "unknown"))
            probs = {}
            for col in dataframe.columns:
                if col.startswith("regime_prob_"):
                    probs[col.replace("regime_prob_", "")] = round(float(last[col]), 4)
            payload = {
                "pair": pair,
                "regime": regime,
                "regime_probs": probs,
                "regime_duration_hours": int(last.get("regime_duration", 1)),
                "regime_stability": round(float(last.get("regime_stability", 1.0)), 3),
                "volatility_20": round(float(last.get("volatility_20", 0)), 4),
                "returns_20": round(float(last.get("returns_20", 0)), 4),
                "regime_multiplier": self.REGIME_MULTIPLIERS.get(regime, 1.0),
                "_timestamp": datetime.now(timezone.utc).isoformat(),
                "_written_by": "VectorStrategy_HMM_Phase2",
            }
            regime_path = Path(__file__).resolve().parent.parent.parent / "shared_config" / "market_regime.json"
            regime_path.parent.mkdir(parents=True, exist_ok=True)
            with open(regime_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[WARN] Regime JSON write failed: {e}")

    # ── ATR Custom Stoploss ──────────────────────────────────────
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> Optional[float]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 2:
            return None

        last = dataframe.iloc[-1]
        atr = last.get("atr", 0)
        if atr is None or atr <= 0:
            return None

        stop_distance_pct = (atr * self.ATR_STOP_MULTIPLIER) / current_rate

        # Freqtrade custom_stoploss always returns NEGATIVE value
        # For shorts, freqtrade internally flips the comparison direction
        # so both directions use -stop_distance_pct
        new_stop = -stop_distance_pct

        if after_fill:
            return new_stop

        if current_profit > self.trailing_stop_positive_offset and self.trailing_stop_positive is not None:
            new_stop = max(new_stop, -self.trailing_stop_positive)

        return new_stop

    # ── Informative Pairs ──────────────────────────────────────────
    def informative_pairs(self):
        return [("BTC/USDT:USDT", "1h")]

    # ── Populate Indicators ────────────────────────────────────────
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        
        # ── 0. Replace volume with real futures volume (mark has zero) ──
        pair_key = metadata.get("pair", "")
        vol_df = self._volume_cache.get(pair_key)
        if vol_df is not None:
            vol_merged = pd.merge_asof(
                dataframe[["date"]].sort_values("date"),
                vol_df.sort_values("date"),
                on="date",
                direction="backward",
            )
            dataframe["volume"] = vol_merged["real_volume"].fillna(dataframe["volume"])
        
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

        # ── 7. HMM Regime Detection ──
        try:
            detector = _get_hmm_detector()
            if detector._trained:
                series = detector.predict_series(dataframe)
                dataframe["regime"] = "unknown"
                dataframe.loc[series.index, "regime"] = series.values
                dataframe["regime"] = dataframe["regime"].fillna("unknown")
            else:
                dataframe["regime"] = "unknown"
        except Exception:
            dataframe["regime"] = "unknown"
        
        # ── 8. VWAP — "LVN rebalance" proxy (volume-weighted fair value) ──
        # Cumulative VWAP (resets daily via session detection would be ideal,
        # but for simplicity we use rolling VWAP)
        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        dataframe["vwap"] = (
            (typical_price * dataframe["volume"]).rolling(20).sum()
            / dataframe["volume"].rolling(20).sum()
        ).bfill()
        
        # ── 9. Key Level Proximity (Frequency & Proximity concept) ──
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

        # ── 10. Funding Rate Signal ─────────────────────────────────
        pair_key = metadata.get("pair", "")
        fund_df = self._funding_cache.get(pair_key)
        if fund_df is not None:
            # Ensure date types match (ms vs ns resolution)
            fund_df = fund_df.copy()
            fund_df["date"] = fund_df["date"].astype(dataframe["date"].dtype)
            dataframe = pd.merge_asof(
                dataframe.sort_values("date"),
                fund_df.sort_values("date"),
                on="date",
                direction="backward",
            )
        else:
            dataframe["funding_rate"] = 0.0

        # Annualized funding rate from 8h rate
        dataframe["funding_annualized"] = (
            abs(dataframe["funding_rate"]) * 3 * 365
        )

        dataframe["funding_regime"] = "neutral"
        dataframe.loc[dataframe["funding_rate"] > 0.0001, "funding_regime"] = "crowded_long"
        dataframe.loc[dataframe["funding_rate"] < -0.0001, "funding_regime"] = "crowded_short"

        # ── 11. Open Interest Regime ────────────────────────────────
        oi_df = self._oi_cache.get(pair_key)
        if oi_df is not None:
            oi_df = oi_df.copy()
            oi_df["date"] = oi_df["date"].astype(dataframe["date"].dtype)
            dataframe = pd.merge_asof(
                dataframe.sort_values("date"),
                oi_df.sort_values("date"),
                on="date",
                direction="backward",
            )
        else:
            dataframe["open_interest"] = 0.0

        dataframe["oi_4h_pct"] = (
            dataframe["open_interest"].pct_change(periods=4).fillna(0)
        )

        dataframe["oi_signal"] = "neutral"
        dataframe.loc[dataframe["oi_4h_pct"] > 0.05, "oi_signal"] = "oi_surge"
        dataframe.loc[dataframe["oi_4h_pct"] < -0.05, "oi_signal"] = "oi_dump"

        dataframe["position_adjustment"] = 1.0
        dataframe.loc[
            (dataframe["funding_regime"] == "crowded_long"),
            "position_adjustment"
        ] = 0.7
        dataframe.loc[
            (dataframe["funding_regime"] == "crowded_short"),
            "position_adjustment"
        ] = 0.7

        # ── 12. HMM Regime Metrics Columns ──
        try:
            detector = _get_hmm_detector()
            if detector._trained:
                feat_df = detector._compute_features(dataframe)
                X, _ = detector._prepare_matrix(feat_df)
                X_scaled = (X - detector.feature_means) / detector.feature_stds
                states = detector.model.predict(X_scaled)
                probs = detector.model.predict_proba(X_scaled)

                aligned = dataframe.copy()
                aligned["_hmm_state"] = pd.NA
                aligned.loc[feat_df.index, "_hmm_state"] = states
                aligned["_hmm_state"] = aligned["_hmm_state"].astype("Int64")

                for state_idx, label in detector.regime_labels.items():
                    col = f"regime_prob_{label}"
                    aligned[col] = 0.0
                    aligned.loc[feat_df.index, col] = probs[:, state_idx]
                dataframe["_hmm_state"] = aligned["_hmm_state"]

                regime_duration = np.zeros(len(dataframe))
                for i in range(1, len(dataframe)):
                    s = int(aligned["_hmm_state"].iloc[i]) if pd.notna(aligned["_hmm_state"].iloc[i]) else -1
                    s_prev = int(aligned["_hmm_state"].iloc[i-1]) if pd.notna(aligned["_hmm_state"].iloc[i-1]) else -1
                    if s == s_prev and s >= 0:
                        regime_duration[i] = regime_duration[i-1] + 1
                    else:
                        regime_duration[i] = 1
                dataframe["regime_duration"] = regime_duration

                stability = np.zeros(len(dataframe))
                for i in range(50, len(dataframe)):
                    seg = aligned["_hmm_state"].iloc[i-49:i+1]
                    seg_valid = seg[seg.notna()]
                    if len(seg_valid) > 1:
                        trans = (seg_valid.values[:-1] != seg_valid.values[1:]).sum()
                        stability[i] = 1.0 - (trans / (len(seg_valid) - 1))
                stability[:50] = 1.0
                dataframe["regime_stability"] = stability

                dataframe["volatility_20"] = dataframe["close"].pct_change().rolling(20).std().fillna(0) * 100
                rets_20 = dataframe["close"].pct_change().rolling(20).mean().fillna(0) * 100
                dataframe["returns_20"] = rets_20
        except Exception:
            pass

        # ── Write regime JSON for downstream consumption ──
        self._write_regime_json(dataframe, metadata.get("pair", ""))

        return dataframe

    # ── Populate Entry Trend ───────────────────────────────────────
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # ── Performance-weighted setup scoring ─────────────────────
        setup_perf = self._get_setup_performance()
        setup_weights = {}
        boosted = []
        suppressed = []

        # Map signal names to setup names used in outcome_history.json
        signal_setup_map = {
            "squeeze_breakout": "BB Squeeze Breakout",
            "mean_reversion": "BB Mean Reversion",
            "ema_alignment": "EMA Trend Alignment",
            "expansion": "Expansion Breakout",
            "key_level": "Key Level Rejection",
        }

        for signal_key, setup_name in signal_setup_map.items():
            perf = setup_perf.get(setup_name, {})
            win_rate = perf.get("win_rate", 0.0)
            trades = perf.get("total_trades", 0)

            if trades >= 3:
                if win_rate > 0.60:
                    setup_weights[signal_key] = 1.2
                    boosted.append(f"{setup_name} (WR={win_rate:.0%}, ×1.2)")
                elif win_rate < 0.40:
                    setup_weights[signal_key] = 0.5
                    suppressed.append(f"{setup_name} (WR={win_rate:.0%}, ×0.5)")
                else:
                    setup_weights[signal_key] = 1.0
            else:
                setup_weights[signal_key] = 1.0

        if boosted or suppressed:
            print(f"\n[VectorStrategy] Performance-weighted confluence active for {metadata.get('pair', 'unknown')}:")
            for b in boosted:
                print(f"  ▲ BOOSTED:   {b}")
            for s in suppressed:
                print(f"  ▼ SUPPRESSED: {s}")
            print()

        # ═══════ INDIVIDUAL SIGNAL DETECTION ═══════

        bb_expansion_long = (
            (dataframe["close"] > dataframe["bb3_upper"]) &
            (dataframe["close"].shift(1) <= dataframe["bb3_upper"].shift(1)) &
            (dataframe["rsi"] > 50)
        )
        bb_expansion_short = (
            (dataframe["close"] < dataframe["bb3_lower"]) &
            (dataframe["close"].shift(1) >= dataframe["bb3_lower"].shift(1)) &
            (dataframe["rsi"] < 50)
        )

        rsi_oversold_long = (
            (dataframe["bb_pctb"] < self.bb_pctb_low.value) &
            (dataframe["rsi"] < self.rsi_oversold.value)
        )
        rsi_overbought_short = (
            (dataframe["bb_pctb"] > self.bb_pctb_high.value) &
            (dataframe["rsi"] > self.rsi_overbought.value)
        )

        volume_long = (dataframe["volume_ratio"] > self.volume_factor.value)
        volume_short = (dataframe["volume_ratio"] > self.volume_factor.value)

        key_level_long = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < 65)
        )
        key_level_short = (
            (dataframe["dist_to_resistance"] < 1.0) &
            (dataframe["close"] < dataframe["open"]) &
            (dataframe["rsi"] < 65) &
            (dataframe["rsi"] > 35)
        )

        bb_squeeze_long = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"])
        )
        bb_squeeze_short = (
            (dataframe["bb_width"] < self.bb_squeeze_threshold.value) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] < dataframe["bb_middleband"])
        )

        # ═══════ REGIME SIGNAL MATRIX GATING ═══════
        # Zero out signals disabled per-regime via SIGNAL_MATRIX
        signal_masks_long = {
            "expansion": bb_expansion_long,
            "mean_reversion": rsi_oversold_long,
            "ema_alignment": volume_long,
            "squeeze_breakout": bb_squeeze_long,
            "key_level": key_level_long,
        }
        signal_masks_short = {
            "expansion": bb_expansion_short,
            "mean_reversion": rsi_overbought_short,
            "ema_alignment": volume_short,
            "squeeze_breakout": bb_squeeze_short,
            "key_level": key_level_short,
        }

        regime_col = dataframe.get("regime", pd.Series(["unknown"] * len(dataframe)))
        gated_long = {}
        gated_short = {}
        for skey in signal_masks_long:
            disabled_for = {r for r, cfg in self.SIGNAL_MATRIX.items() if skey in cfg["disabled"]}
            disabled_mask = regime_col.isin(list(disabled_for))
            gated_long[skey] = signal_masks_long[skey] & ~disabled_mask
            gated_short[skey] = signal_masks_short[skey] & ~disabled_mask

        # ═══════ FUNDING + OI FILTERS ═══════
        skip_long = dataframe["oi_signal"] == "oi_surge"
        skip_short = dataframe["oi_signal"] == "oi_dump"

        # ═══════ REGIME-ADJUSTED CONFLUENCE ═══════
        # Use RAW SIGNAL COUNT + REGIME THRESHOLD to avoid mathematical impossibility
        # (weighted scores + disabled signals made some regimes impossible to enter)
        weights = self.SIGNAL_WEIGHTS
        signal_keys = ["expansion", "mean_reversion", "ema_alignment", "key_level", "squeeze_breakout"]

        # Raw signal count (how many signals fire, regardless of weight)
        long_signal_count = sum(gated_long[k].astype(int) for k in signal_keys)
        short_signal_count = sum(gated_short[k].astype(int) for k in signal_keys)

        # Weighted score for ranking (not as primary threshold)
        long_score = (
            gated_long["expansion"].astype(float) * weights["bb_expansion"] +
            gated_long["mean_reversion"].astype(float) * weights["rsi_oversold"] +
            gated_long["ema_alignment"].astype(float) * weights["volume_factor"] +
            gated_long["key_level"].astype(float) * weights["key_level"] +
            gated_long["squeeze_breakout"].astype(float) * weights["bb_squeeze"]
        )
        short_score = (
            gated_short["expansion"].astype(float) * weights["bb_expansion"] +
            gated_short["mean_reversion"].astype(float) * weights["rsi_oversold"] +
            gated_short["ema_alignment"].astype(float) * weights["volume_factor"] +
            gated_short["key_level"].astype(float) * weights["key_level"] +
            gated_short["squeeze_breakout"].astype(float) * weights["bb_squeeze"]
        )

        # Regime-adaptive min_confluence: 2 normally, 3 in volatile
        min_signals = 2
        is_volatile = regime_col == "volatile"
        # In volatile regime, require 3 signals (more noise = need more confirmation)
        min_signals_volatile = pd.Series(2, index=dataframe.index)
        min_signals_volatile[is_volatile] = 3

        dataframe["long_signal_count"] = long_signal_count
        dataframe["short_signal_count"] = short_signal_count
        dataframe["long_weighted_score"] = long_score
        dataframe["short_weighted_score"] = short_score

        long_mask = (long_signal_count >= min_signals_volatile) & (dataframe["volume"] > 0) & ~skip_long
        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = dataframe.loc[long_mask].apply(
            lambda r: f"long_hmm_{r['long_weighted_score']:.2f}_sig{r['long_signal_count']}", axis=1
        )

        short_mask = (short_signal_count >= min_signals_volatile) & (dataframe["volume"] > 0) & ~skip_short
        dataframe.loc[short_mask, "enter_short"] = 1
        dataframe.loc[short_mask, "enter_tag"] = dataframe.loc[short_mask].apply(
            lambda r: f"short_hmm_{r['short_weighted_score']:.2f}_sig{r['short_signal_count']}", axis=1
        )

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

    # ── Custom Exit (Beacon target system + Circuit Breaker) ──────────────────────────
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        
        # ── Circuit Breaker: force exit all if daily loss > 2% ──
        cb = self._read_circuit_breaker()
        daily_pnl = cb.get("daily_pnl_pct", 0.0)
        if daily_pnl < -CB_DAILY_DD_PCT and cb.get("state") != "COOLING":
            cb["state"] = "COOLING"
            cb["transition_reason"] = f"Daily drawdown {daily_pnl:.2f}% triggered emergency exit"
            self._write_circuit_breaker(cb)
            print(f"[CIRCUIT_BREAKER] Emergency exit all: daily PnL {daily_pnl:.2f}% < -{CB_DAILY_DD_PCT}%")
            return "circuit_breaker_daily_dd"
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None
        
        last_candle = dataframe.iloc[-1]
        bb_pctb = last_candle.get("bb_pctb", 0.5)
        
        # Beacon 50% target: exit half at mean reversion 50% level
        # (Freqtrade handles this via ROI, but we can force exit at extreme levels)
        
        # ── Beacon Target Exit ──
        # Only exit if trade has been open for >= 4 hours AND is in profit.
        # The beacon_target was causing instant exits because entries trigger
        # on the same bb_pctb extremes that the exit checks (e.g., short enters
        # when oversold bb_pctb < 0.2, then exit also checks bb_pctb < 0.15).
        min_hold_hours = 4
        trade_age = (current_time - trade.open_date_utc).total_seconds() / 3600
        if trade_age >= min_hold_hours:
            if trade.is_short and bb_pctb < 0.15 and current_profit > 0:
                return "beacon_target_short"
            if not trade.is_short and bb_pctb > 0.85 and current_profit > 0:
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
        if "confluence_" in enter_tag.lower():
            return "weighted_confluence"
        elif "squeeze" in enter_tag.lower():
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

    def _get_setup_performance(self) -> dict[str, dict]:
        """
        Read outcome_history.json chunk_stats and return {setup_name: {win_rate, total_trades, wins, losses, avg_pnl}}.

        Used to weight confluence scores by historical setup performance.
        """
        if not VDB_OUTCOME_PATH.exists():
            return {}
        try:
            with open(VDB_OUTCOME_PATH, "r") as f:
                data = json.load(f)
            chunk_stats = data.get("chunk_stats", {})
            result = {}
            for name, stats in chunk_stats.items():
                total = stats.get("total_trades", 0)
                wins = stats.get("wins", 0)
                losses = stats.get("losses", 0)
                total_pnl = stats.get("total_pnl", 0)
                win_rate = round(wins / total, 4) if total > 0 else 0.0
                avg_pnl = round(total_pnl / total, 4) if total > 0 else 0.0
                result[name] = {
                    "win_rate": win_rate,
                    "total_trades": total,
                    "wins": wins,
                    "losses": losses,
                    "avg_pnl": avg_pnl,
                }
            return result
        except Exception:
            return {}

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
                "confluence_min": self.confluence_weight.value,
                "confluence_score": enter_tag.split("_")[-1] if "confluence_" in (enter_tag or "") else None,
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

            # Sync outcome win rates to ChromaDB metadata
            try:
                sync_mod = _get_outcome_sync()
                sync_mod.sync_to_chromadb(verbose=False)
            except Exception as e:
                print(f"[WARN] Outcome sync to ChromaDB failed: {e}")

        except Exception as e:
            # Never break the trading loop for outcome recording
            print(f"[WARN] Outcome recording failed: {e}")

    def custom_exit_price(self, pair: str, trade: Trade, current_time: datetime,
                          proposed_rate: float, current_rate: float,
                          exit_tag: Optional[str], **kwargs) -> float:
        """Hook: after a trade exits, record the outcome."""
        # Trade outcome will be recorded in bot_loop_start
        return proposed_rate

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        """Check circuit breaker thresholds, manage state transitions, sync outcomes to ChromaDB."""
        # ── Circuit breaker ──
        cb = self._read_circuit_breaker()
        now = current_time if current_time.tzinfo else current_time.replace(tzinfo=timezone.utc)

        try:
            from freqtrade.persistence import Trade
            closed_trades = Trade.get_trades_proxy(is_open=False)
        except Exception:
            closed_trades = []

        daily_start = now - timedelta(days=1)
        weekly_start = now - timedelta(weeks=1)
        monthly_start = now - timedelta(days=30)

        daily_pnl, daily_count = self._calculate_period_pnl(closed_trades, daily_start)
        weekly_pnl, weekly_count = self._calculate_period_pnl(closed_trades, weekly_start)
        monthly_pnl, monthly_count = self._calculate_period_pnl(closed_trades, monthly_start)

        cb["daily_pnl_pct"] = round(daily_pnl, 2)
        cb["weekly_pnl_pct"] = round(weekly_pnl, 2)
        cb["monthly_pnl_pct"] = round(monthly_pnl, 2)
        cb["daily_trades"] = daily_count
        cb["weekly_trades"] = weekly_count
        cb["monthly_trades"] = monthly_count

        state = cb.get("state", "HEALTHY")
        ts_str = cb.get("_timestamp", cb.get("timestamp", ""))

        try:
            last_ts = datetime.fromisoformat(ts_str)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
        except Exception:
            last_ts = now

        hours_since_transition = (now - last_ts).total_seconds() / 3600

        if state == "PAUSED" and hours_since_transition >= CB_PAUSED_COOLING_HOURS:
            cb = self._transition_state(cb, "COOLING", f"24h cooldown elapsed ({hours_since_transition:.1f}h)")
        elif state == "COOLING" and hours_since_transition >= CB_COOLING_HOURS and daily_pnl >= 0:
            cb = self._transition_state(cb, "HEALTHY", f"4h cooldown elapsed, daily PnL recovered ({daily_pnl:.2f}%)")
        elif state == "HEALTHY" and daily_pnl < -CB_DAILY_DD_PCT:
            cb = self._transition_state(cb, "COOLING", f"Daily drawdown {daily_pnl:.2f}% > {CB_DAILY_DD_PCT}%")
        elif state in ("HEALTHY", "COOLING"):
            if weekly_pnl < -CB_WEEKLY_DD_PCT:
                cb = self._transition_state(cb, "PAUSED", f"Weekly drawdown {weekly_pnl:.2f}% > {CB_WEEKLY_DD_PCT}%")
            elif monthly_pnl < -CB_MONTHLY_DD_PCT:
                cb = self._transition_state(cb, "PAUSED", f"Monthly drawdown {monthly_pnl:.2f}% > {CB_MONTHLY_DD_PCT}%")

        self._write_circuit_breaker(cb)

        # ── Outcome sync to ChromaDB ──
        try:
            sync_mod = _get_outcome_sync()
            sync_mod.sync_to_chromadb(verbose=False)
        except Exception:
            pass

    # ── Circuit Breaker Helpers ──────────────────────────────────

    def _read_circuit_breaker(self) -> dict:
        try:
            if CB_PATH.exists():
                with open(CB_PATH, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[CIRCUIT_BREAKER] Failed to read state: {e}")
        return {"state": "HEALTHY", "drawdown_pct": 0.0, "timestamp": datetime.now(timezone.utc).isoformat()}

    def _write_circuit_breaker(self, state: dict) -> None:
        try:
            CB_PATH.parent.mkdir(parents=True, exist_ok=True)
            state["_timestamp"] = datetime.now(timezone.utc).isoformat()
            state["_written_by"] = "VectorStrategy"
            with open(CB_PATH, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[CIRCUIT_BREAKER] Failed to write state: {e}")

    def _transition_state(self, cb: dict, new_state: str, reason: str) -> dict:
        old_state = cb.get("state", "HEALTHY")
        if old_state != new_state:
            print(f"[CIRCUIT_BREAKER] {old_state} \u2192 {new_state}: {reason}")
            cb["state"] = new_state
            cb["transition_reason"] = reason
            self._write_circuit_breaker(cb)
        return cb

    def _calculate_period_pnl(self, trades: list, start_time: datetime) -> tuple:
        total_pnl = 0.0
        count = 0
        for t in trades:
            close_date = t.close_date_utc if hasattr(t, 'close_date_utc') else t.close_date
            if close_date and close_date >= start_time:
                total_pnl += t.close_profit or 0.0
                count += 1
        return total_pnl * 100, count