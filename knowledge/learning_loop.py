"""
Learning Loop — pre-trade ChromaDB query + risk gate.

Before every trade:
  1. Encode current market conditions into a search query
  2. Query ChromaDB for similar past setups
  3. Look up outcome_history.json for win rates on matched setups
  4. Block trade if aggregate win rate < threshold (default 40%)

After every trade:
  1. Record outcome to outcome_history.json
  2. Sync updated win rates to ChromaDB metadata
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.trade_encoder import encode_trade_query, encode_trade_outcome

STRATEGY_DB_DIR = Path(__file__).parent.parent / "strategy_db"
OUTCOME_PATH = STRATEGY_DB_DIR / "outcome_history.json"
CHROMA_DB_DIR = str(STRATEGY_DB_DIR / "chroma_db")
COLLECTION_NAME = "trading_strategies"
MIN_WIN_RATE = 0.40
CACHE_TTL = 60


class LearningLoop:
    def __init__(self, min_win_rate: float = MIN_WIN_RATE):
        self._collection = None
        self._client = None
        self._initialized = False
        self.min_win_rate = min_win_rate
        self._cache = {}
        self._cache_ts = 0

    def _lazy_init(self):
        if self._initialized:
            return
        try:
            import chromadb
            from chromadb.config import Settings
            self._client = chromadb.PersistentClient(
                path=CHROMA_DB_DIR, settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_collection(name=COLLECTION_NAME)
        except Exception:
            self._collection = None
        self._initialized = True

    def pre_trade_check(
        self,
        pair: str,
        side: str,
        market_condition: str = "",
        signal_type: str = "",
        strategy: str = "",
    ) -> dict:
        self._lazy_init()
        query = encode_trade_query(pair, side, market_condition, signal_type, strategy)
        similar = self._query_chromadb(query)
        win_rate, total_trades, matched_names = self._aggregate_win_rate(similar)
        approved = win_rate >= self.min_win_rate
        return {
            "approved": approved,
            "win_rate": round(win_rate, 2),
            "min_win_rate": self.min_win_rate,
            "total_historical_trades": total_trades,
            "similar_setups": matched_names,
            "query": query,
            "block_reason": (
                f"Win rate {win_rate:.0%} < {self.min_win_rate:.0%} threshold "
                f"({total_trades} similar trade(s))"
            ) if not approved else "",
        }

    def record_outcome(
        self,
        pair: str,
        side: str,
        pnl: float,
        r_multiple: float = 0.0,
        setup_name: str = "",
        market_condition: str = "",
        strategy: str = "",
    ):
        outcome = encode_trade_outcome(pair, side, pnl, r_multiple, setup_name, market_condition, strategy)
        history = self._load_outcome_history()
        history.setdefault("trades", []).append(outcome)
        self._update_chunk_stats(history, setup_name, pnl > 0, pnl, r_multiple, market_condition)
        self._save_outcome_history(history)
        self._feed_to_nexus(pair, pnl, strategy)
        self._update_strategy_performance(strategy, pnl > 0, pnl)
        self._sync_chromadb()

    def _update_strategy_performance(self, strategy: str, won: bool, pnl: float):
        if not strategy:
            return
        try:
            from engine.strategy_registry import StrategyRegistry
            registry = StrategyRegistry()
            registry.update_performance(strategy, won, pnl)
        except Exception as e:
            print(f"[learning_loop] StrategyRegistry update error: {e}")

    def _sync_chromadb(self):
        try:
            from strategy_db.outcome_sync import sync_to_chromadb
            sync_to_chromadb(verbose=False)
        except Exception as e:
            print(f"[learning_loop] ChromaDB sync error: {e}")

    def _feed_to_nexus(self, pair: str, pnl: float, strategy: str):
        try:
            from nexus.bridge import get_bridge
            bridge = get_bridge()
            bridge.feed_outcome_to_nexus({
                "pair": pair,
                "pnl_pct": pnl,
                "win": pnl > 0,
                "strategy": strategy or "unknown",
            })
        except Exception as e:
            print(f"[learning_loop] NEXUS feed error: {e}")

    def get_setup_win_rate(self, setup_name: str) -> Optional[float]:
        history = self._load_outcome_history()
        stats = history.get("chunk_stats", {}).get(setup_name, {})
        total = stats.get("total_trades", 0)
        if total == 0:
            return None
        return stats.get("wins", 0) / total

    def _query_chromadb(self, query: str, top_k: int = 5) -> list:
        if self._collection is None:
            return []
        try:
            results = self._collection.query(
                query_texts=[query], n_results=top_k
            )
            entries = []
            for i in range(len(results["ids"][0])):
                meta = results["metadatas"][0][i]
                entries.append({
                    "score": round(1.0 - results["distances"][0][i], 4),
                    "setup_name": meta.get("setup_name", ""),
                    "setup_type": meta.get("setup_type", ""),
                    "market_condition": meta.get("market_condition", ""),
                    "risk_reward": meta.get("risk_reward", ""),
                })
            return entries
        except Exception:
            return []

    def _aggregate_win_rate(self, similar_setups: list) -> tuple:
        history = self._load_outcome_history()
        chunk_stats = history.get("chunk_stats", {})
        total_wins = 0
        total_trades = 0
        matched_names = []
        seen = set()
        for s in similar_setups:
            name = s.get("setup_name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            stats = chunk_stats.get(name, {})
            t = stats.get("total_trades", 0)
            w = stats.get("wins", 0)
            if t > 0:
                total_wins += w
                total_trades += t
                matched_names.append(name)
        if total_trades == 0:
            return 0.0, 0, matched_names
        return total_wins / total_trades, total_trades, matched_names

    def _load_outcome_history(self) -> dict:
        if not OUTCOME_PATH.exists():
            return {"trades": [], "chunk_stats": {}}
        try:
            return json.loads(OUTCOME_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {"trades": [], "chunk_stats": {}}

    def _save_outcome_history(self, data: dict):
        OUTCOME_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTCOME_PATH.write_text(json.dumps(data, indent=2))

    def _update_chunk_stats(self, history: dict, setup_name: str,
                             won: bool, pnl: float, r_multiple: float,
                             market_condition: str):
        if not setup_name:
            return
        stats = history.setdefault("chunk_stats", {})
        entry = stats.setdefault(setup_name, {
            "total_trades": 0, "wins": 0, "losses": 0,
            "total_pnl": 0.0, "total_r_multiple": 0.0,
            "regime_breakdown": {},
        })
        entry["total_trades"] += 1
        if won:
            entry["wins"] += 1
        else:
            entry["losses"] += 1
        entry["total_pnl"] += pnl
        entry["total_r_multiple"] += r_multiple
        if market_condition:
            regime = entry.setdefault("regime_breakdown", {})
            r_entry = regime.setdefault(market_condition, {
                "trades": 0, "wins": 0, "pnl": 0.0, "r_multiple": 0.0,
            })
            r_entry["trades"] += 1
            if won:
                r_entry["wins"] += 1
            r_entry["pnl"] += pnl
            r_entry["r_multiple"] += r_multiple

    def is_available(self) -> bool:
        self._lazy_init()
        return self._collection is not None

    def get_summary(self) -> dict:
        history = self._load_outcome_history()
        stats = history.get("chunk_stats", {})
        total_trades = history.get("trades", [])
        total_wins = sum(s.get("wins", 0) for s in stats.values())
        total_losses = sum(s.get("losses", 0) for s in stats.values())
        total_pnl = sum(s.get("total_pnl", 0) for s in stats.values())
        grand_total = total_wins + total_losses
        return {
            "total_trades": grand_total,
            "trades_in_log": len(total_trades),
            "total_wins": total_wins,
            "total_losses": total_losses,
            "win_rate": round(total_wins / grand_total, 4) if grand_total > 0 else 0.0,
            "total_pnl": round(total_pnl, 2),
            "unique_setups": len(stats),
            "chromadb_available": self.is_available(),
        }
