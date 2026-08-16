"""
Regime-Aware Strategy Selector — maps detected market regime to best strategy.

Uses ChromaDB (via strategy_db modules) for strategy lookup, outcome history
for performance ranking, and the DataManager for state reads/writes.

Default mapping:
  trending_up   → EmaTrendFollowing
  trending_down → EmaTrendFollowing (short mode) / BollingerMeanReversion
  ranging       → BollingerMeanReversion / DmiAdxStrategy
  volatile      → AroonMomentumEngine_Hybrid
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.data_manager import DataManager
from core.event_bus import EventTypes

logger = logging.getLogger(__name__)

REGIME_STRATEGY_DEFAULTS = {
    "trending_up": [
        {"strategy": "EmaTrendFollowing", "reason": "Trend-following EMA crossover for uptrend"},
        {"strategy": "SupertrendEmaStrategy", "reason": "Supertrend+EMA combo for strong trends"},
        {"strategy": "AroonMomentumEngine_Hybrid", "reason": "Aroon momentum with trend confirmation"},
    ],
    "trending_down": [
        {"strategy": "EmaTrendFollowing", "reason": "EMA trend following in short mode"},
        {"strategy": "BollingerMeanReversion", "reason": "Mean reversion on overextended downside"},
        {"strategy": "RsiDivergenceStrategy", "reason": "RSI divergence catches reversal setups"},
    ],
    "ranging": [
        {"strategy": "BollingerMeanReversion", "reason": "Bollinger bands capture range-bound mean reversion"},
        {"strategy": "DmiAdxStrategy", "reason": "DMI/ADX filters low-trend periods"},
        {"strategy": "MacdRsiStrategy", "reason": "MACD+RSI combo for choppy markets"},
    ],
    "volatile": [
        {"strategy": "AroonMomentumEngine_Hybrid", "reason": "Aroon hybrid adapts to volatility spikes"},
        {"strategy": "VectorOmni_LiquidTrap", "reason": "Liquidity trap detection in volatile regimes"},
        {"strategy": "VectorOmni_ATRBoost", "reason": "ATR-boosted sizing for volatile swings"},
    ],
}

OUTCOME_HISTORY_PATH = Path(__file__).parent.parent / "strategy_db" / "outcome_history.json"
PERFORMANCE_DB_PATH = Path(__file__).parent.parent / "user_data" / "strategy_performance_db.json"


class RegimeSelector:
    """
    Selects best strategy for current market regime using:
    1. HMM regime detection (via strategy_db/regime_query.py)
    2. Outcome history performance ranking
    3. Fallback to default mapping
    4. ChromaDB semantic lookup for advanced queries
    """

    def __init__(self, data_manager: Optional[DataManager] = None):
        self._dm = data_manager or DataManager()
        self._outcome_data: Optional[dict] = None
        self._perf_data: Optional[dict] = None
        self._switch_log: list[dict] = []

    def detect_regime(self) -> dict:
        """
        Detect current market regime using DataManager (reads from
        shared_config/market_regime.json which is updated by HMM detector).
        """
        regime_data = self._dm.get_regime()
        if regime_data is None:
            return {"regime": "unknown", "regime_probs": {},
                    "regime_stability": 0.0, "regime_multiplier": 1.0}
        return regime_data

    def detect_regime_hmm(self, pair: str = "BTC/USDT",
                          timeframe: str = "1h") -> dict:
        """
        Detect regime via HMM detector from strategy_db/regime_query.py.
        Falls back to DataManager cached regime on failure.
        """
        try:
            from strategy_db.regime_query import RegimeDetector
            import pandas as pd

            data_dir = Path(__file__).parent.parent / "data"
            feather_files = list(data_dir.glob(f"{pair.replace('/', '_')}*{timeframe}*.feather"))
            if not feather_files:
                feather_files = list(data_dir.glob(f"*{pair.split('/')[0]}*{timeframe}*.feather"))

            if feather_files:
                df = pd.read_feather(feather_files[0])
                regime, metrics = RegimeDetector.detect(df)
                self._dm.set_regime(regime, extra={
                    "pair": pair,
                    "regime_probs": metrics,
                    "source": "hmm_detector",
                })
                return {"regime": regime, **metrics}

        except Exception as e:
            logger.info("HMM regime detection unavailable, falling back to cached: %s", e)

        return self.detect_regime()

    def select_strategy(self, regime: Optional[str] = None) -> dict:
        """
        Select the best strategy for the given (or current) regime.
        Priority: outcome history > performance DB > default mapping.
        """
        if regime is None:
            regime_data = self.detect_regime()
            regime = regime_data.get("regime", "ranging")

        candidates = REGIME_STRATEGY_DEFAULTS.get(regime,
                       REGIME_STRATEGY_DEFAULTS["ranging"])

        outcome_winner = self._pick_from_outcomes(regime, candidates)
        if outcome_winner:
            return outcome_winner

        perf_winner = self._pick_from_performance(regime, candidates)
        if perf_winner:
            return perf_winner

        return {
            "strategy": candidates[0]["strategy"],
            "regime": regime,
            "source": "default_mapping",
            "reason": candidates[0]["reason"],
            "candidates": candidates,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def hotswap_strategy(self, strategy_name: str,
                         reason: str = "manual_switch") -> dict:
        """
        Switch to a new strategy: writes to active_strategy.json and
        publishes STRATEGY_SWITCH event via EventBus.
        """
        current = self._dm.get_active_strategy() or {}
        old_strategy = current.get("strategy", current.get("name", ""))

        result = self._dm.set_active_strategy(strategy_name, extra={
            "switch_reason": reason,
            "previous_strategy": old_strategy,
        })

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "old_strategy": old_strategy,
            "new_strategy": strategy_name,
            "reason": reason,
            "regime_at_switch": (self.detect_regime().get("regime", "unknown")),
        }
        self._switch_log.append(log_entry)
        logger.info("Strategy switched: %s -> %s (reason: %s)",
                     old_strategy, strategy_name, reason)

        return result

    def get_switch_log(self, limit: int = 50) -> list[dict]:
        return list(self._switch_log[-limit:])

    # ── Internals ──────────────────────────────────────────────────────

    def _load_outcomes(self) -> dict:
        if self._outcome_data is not None:
            return self._outcome_data
        if OUTCOME_HISTORY_PATH.exists():
            try:
                self._outcome_data = json.loads(OUTCOME_HISTORY_PATH.read_text())
                return self._outcome_data
            except (json.JSONDecodeError, OSError):
                pass
        self._outcome_data = {}
        return {}

    def _load_performance(self) -> dict:
        if self._perf_data is not None:
            return self._perf_data
        if PERFORMANCE_DB_PATH.exists():
            try:
                self._perf_data = json.loads(PERFORMANCE_DB_PATH.read_text())
                return self._perf_data
            except (json.JSONDecodeError, OSError):
                pass
        self._perf_data = {}
        return {}

    def _pick_from_outcomes(self, regime: str,
                            candidates: list[dict]) -> Optional[dict]:
        outcomes = self._load_outcomes()
        chunk_stats = outcomes.get("chunk_stats", {})
        if not chunk_stats:
            return None

        best_name = None
        best_wr = -1.0
        candidate_names = {c["strategy"] for c in candidates}

        for name, stats in chunk_stats.items():
            total = stats.get("total_trades", 0)
            if total < 3:
                continue
            regime_data = stats.get("regime_breakdown", {}).get(regime, {})
            regime_trades = regime_data.get("trades", 0)
            if regime_trades < 2:
                continue
            wr = regime_data.get("wins", 0) / regime_trades
            fuzzy_matched = self._fuzzy_match_strategy(name, candidate_names)
            if fuzzy_matched and wr > best_wr:
                best_wr = wr
                best_name = fuzzy_matched

        if best_name:
            return {
                "strategy": best_name,
                "regime": regime,
                "source": "outcome_history",
                "reason": f"Best win rate for {regime}: {best_wr:.1%}",
                "win_rate": best_wr,
                "candidates": candidates,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return None

    def _pick_from_performance(self, regime: str,
                               candidates: list[dict]) -> Optional[dict]:
        perf = self._load_performance()
        if not perf:
            return None

        best_name = None
        best_wr = -1.0
        candidate_names = {c["strategy"] for c in candidates}

        for key, data in perf.items():
            if isinstance(data, dict):
                wr = data.get("win_rate", 0)
                trades = data.get("trades", 0)
                if trades < 3:
                    continue
                matched = self._fuzzy_match_strategy(key, candidate_names)
                if matched and wr > best_wr:
                    best_wr = wr
                    best_name = matched

        if best_name:
            return {
                "strategy": best_name,
                "regime": regime,
                "source": "performance_db",
                "reason": f"Best recorded win rate: {best_wr:.1%}",
                "win_rate": best_wr,
                "candidates": candidates,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return None

    @staticmethod
    def _fuzzy_match_strategy(name: str, candidates: set[str]) -> Optional[str]:
        name_lower = name.lower().replace(" ", "").replace("_", "")
        for c in candidates:
            c_lower = c.lower().replace(" ", "").replace("_", "")
            if name_lower == c_lower or name_lower in c_lower or c_lower in name_lower:
                return c
        return None