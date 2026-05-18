"""
Regime-Conditioned ChromaDB Query Engine.
Maps detected market regime to adaptive strategy queries.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import existing search module
import sys
sys.path.insert(0, str(Path(__file__).parent))
from search import _get_collection

# Regime → query templates mapping
REGIME_QUERIES = {
    "trending_up": {
        "entry": [
            "momentum breakout entry with volume confirmation uptrend",
            "EMA crossover alignment continuation entry higher high",
            "higher high higher low structure entry trending market"
        ],
        "confirmation": [
            "volume spike confirms breakout uptrend",
            "close above resistance momentum confirmation"
        ],
        "filter": [
            "trending market session filter kill zone",
            "remove low probability signals in strong uptrend"
        ],
        "exit": [
            "trailing stop profit locking uptrend",
            "taking profit at resistance level trending market"
        ],
        "risk_management": [
            "risk reward ratio trending market position sizing",
            "risk to zero breakeven move stop quickly"
        ]
    },
    "trending_down": {
        "entry": [
            "short selling bearish market structure entry",
            "lower low continuation short setup breakdown",
            "bearish liquidity trap entry short"
        ],
        "confirmation": [
            "volume confirmation bearish breakdown distribution",
            "negative delta divergence selling pressure"
        ],
        "filter": [
            "avoid longs in downtrend filter confirmation",
            "kill zone short entry session London NY"
        ],
        "exit": [
            "profit target support level short covering",
            "risk zero breakeven short trade protection"
        ],
        "risk_management": [
            "2% daily max loss in bear market",
            "smaller position size downtrend conservative"
        ]
    },
    "ranging": {
        "entry": [
            "mean reversion support resistance level entry ranging",
            "Bollinger Band squeeze breakout ranging market",
            "absorption pattern passive order detection range"
        ],
        "confirmation": [
            "CVD divergence range bound confirmation",
            "volume profile value area range accumulation"
        ],
        "filter": [
            "no trade zone consolidation filter chop",
            "range bound market session filter low volume"
        ],
        "exit": [
            "scale out at resistance ranging market take profit",
            "auction cap too expensive rejection reversal"
        ],
        "risk_management": [
            "tight stop loss ranging market small risk",
            "reduced position size chop range bound"
        ]
    },
    "volatile": {
        "entry": [
            "confirmation before entry high volatility filter",
            "circuit breaker flash crash protection wait"
        ],
        "confirmation": [
            "full candle close confirmation volatile market",
            "multiple timeframe confirmation volatility high"
        ],
        "filter": [
            "low probability day filter post large expansion",
            "FOMC news event filter skip volatile"
        ],
        "exit": [
            "adaptive stop loss volatile market protection",
            "risk to zero quickly high volatility breakeven"
        ],
        "risk_management": [
            "reduce leverage volatile regime small position",
            "circuit breaker drawdown protection maximum loss"
        ]
    }
}

# Fallback for unknown regimes
DEFAULT_QUERIES = REGIME_QUERIES["ranging"]


class OutcomeTracker:
    """
    Track trade outcomes mapped to ChromaDB strategy chunks.
    Every trade records which chunks informed the decision and whether it won.
    This closes the feedback loop: ChromaDB → Strategy → Trade → Outcome → ChromaDB.
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent / "outcome_history.json")
        self.db_path = Path(db_path)
        self.history = self._load()
    
    def _load(self) -> dict:
        if self.db_path.exists():
            with open(self.db_path) as f:
                return json.load(f)
        return {"trades": [], "chunk_stats": {}}
    
    def _save(self):
        with open(self.db_path, "w") as f:
            json.dump(self.history, f, indent=2, default=str)
    
    def record_trade(self, trade_id: str, pair: str, regime: str,
                     setup_names: list, pnl_pct: float, r_multiple: float,
                     is_win: bool, strategy_type: str = "VectorStrategy",
                     dominant_signal: str = "") -> dict:
        """
        Record a completed trade with its ChromaDB strategy context.
        
        Args:
            trade_id: Unique trade identifier
            pair: Trading pair (e.g., "BTC/USDT")
            regime: Market regime at entry (trending_up/down/ranging/volatile)
            setup_names: List of ChromaDB chunk names that informed this trade
            pnl_pct: Trade P&L as percentage (e.g., +5.2, -3.1)
            r_multiple: Reward-to-risk ratio achieved
            is_win: Whether trade was profitable
            strategy_type: Strategy name (default: VectorStrategy)
            dominant_signal: Which indicator prompted entry (bb_squeeze, rsi, etc.)
        """
        from datetime import datetime
        
        trade = {
            "trade_id": trade_id,
            "pair": pair,
            "timestamp": datetime.utcnow().isoformat(),
            "regime": regime,
            "setup_names": setup_names,
            "pnl_pct": pnl_pct,
            "r_multiple": r_multiple,
            "is_win": is_win,
            "strategy_type": strategy_type,
            "dominant_signal": dominant_signal
        }
        self.history["trades"].append(trade)
        
        # Update per-chunk statistics
        for name in setup_names:
            if name not in self.history["chunk_stats"]:
                self.history["chunk_stats"][name] = {
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_pnl": 0.0,
                    "total_r_multiple": 0.0,
                    "regime_breakdown": {}
                }
            stats = self.history["chunk_stats"][name]
            stats["total_trades"] += 1
            stats["wins" if is_win else "losses"] += 1
            stats["total_pnl"] += pnl_pct
            stats["total_r_multiple"] += r_multiple
            
            # Track by regime
            if regime not in stats["regime_breakdown"]:
                stats["regime_breakdown"][regime] = {
                    "trades": 0, "wins": 0, "pnl": 0.0, "r_multiple": 0.0
                }
            rb = stats["regime_breakdown"][regime]
            rb["trades"] += 1
            if is_win:
                rb["wins"] += 1
            rb["pnl"] += pnl_pct
            rb["r_multiple"] += r_multiple
        
        self._save()
        return trade
    
    def get_win_rate(self, setup_name: str, regime: str = None) -> Optional[float]:
        """Get win rate for a strategy chunk, optionally filtered by regime."""
        stats = self.history["chunk_stats"].get(setup_name)
        if not stats or stats["total_trades"] < 3:
            return None  # Not enough data yet
        
        if regime and regime in stats.get("regime_breakdown", {}):
            r = stats["regime_breakdown"][regime]
            return r["wins"] / r["trades"] if r["trades"] > 0 else None
        
        return stats["wins"] / stats["total_trades"]
    
    def get_best_chunks_for_regime(self, regime: str, top_k: int = 10) -> list:
        """Get top-performing chunks for a given regime."""
        results = []
        for name, stats in self.history["chunk_stats"].items():
            regime_data = stats.get("regime_breakdown", {}).get(regime)
            if regime_data and regime_data["trades"] >= 3:
                win_rate = regime_data["wins"] / regime_data["trades"]
                avg_pnl = regime_data["pnl"] / regime_data["trades"]
                results.append({
                    "setup_name": name,
                    "win_rate": win_rate,
                    "avg_pnl": avg_pnl,
                    "trades": regime_data["trades"]
                })
        results.sort(key=lambda x: x["avg_pnl"], reverse=True)
        return results[:top_k]
    
    def get_regime_summary(self) -> dict:
        """Get overall performance by regime."""
        regime_totals = {}
        for trade in self.history["trades"]:
            r = trade["regime"]
            if r not in regime_totals:
                regime_totals[r] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
            regime_totals[r]["trades"] += 1
            if trade["is_win"]:
                regime_totals[r]["wins"] += 1
            regime_totals[r]["total_pnl"] += trade["pnl_pct"]
        
        summary = {}
        for r, data in regime_totals.items():
            summary[r] = {
                "win_rate": data["wins"] / data["trades"] if data["trades"] > 0 else 0,
                "avg_pnl": data["total_pnl"] / data["trades"] if data["trades"] > 0 else 0,
                "total_trades": data["trades"]
            }
        return summary

    def update_chunk_scores_from_outcomes(self, collection=None) -> dict:
        """
        Read outcome_history.json, compute win rates per (regime, setup_name) pair,
        and update ChromaDB collection metadata for matching chunks.

        This pushes live outcome data back into the vector store so future queries
        can leverage historical performance directly from chunk metadata.

        Args:
            collection: ChromaDB collection object. If None, uses _get_collection().

        Returns:
            dict with counts of updated, skipped, and errored chunks.
        """
        if collection is None:
            collection = _get_collection()

        stats = {"updated": 0, "skipped": 0, "errors": 0, "details": []}

        # Build a map of (regime, setup_name) → aggregated win-rate info
        regime_setup_rates: Dict[Tuple[str, str], dict] = {}
        for trade in self.history.get("trades", []):
            regime = trade.get("regime", "")
            for setup_name in trade.get("setup_names", []):
                key = (regime, setup_name)
                if key not in regime_setup_rates:
                    regime_setup_rates[key] = {"trades": 0, "wins": 0, "total_pnl": 0.0, "total_r": 0.0}
                regime_setup_rates[key]["trades"] += 1
                if trade.get("is_win"):
                    regime_setup_rates[key]["wins"] += 1
                regime_setup_rates[key]["total_pnl"] += trade.get("pnl_pct", 0.0)
                regime_setup_rates[key]["total_r"] += trade.get("r_multiple", 0.0)

        # Also aggregate per setup_name (across all regimes)
        setup_global_rates: Dict[str, dict] = {}
        for (regime, setup_name), data in regime_setup_rates.items():
            if setup_name not in setup_global_rates:
                setup_global_rates[setup_name] = {"trades": 0, "wins": 0, "total_pnl": 0.0, "total_r": 0.0}
            setup_global_rates[setup_name]["trades"] += data["trades"]
            setup_global_rates[setup_name]["wins"] += data["wins"]
            setup_global_rates[setup_name]["total_pnl"] += data["total_pnl"]
            setup_global_rates[setup_name]["total_r"] += data["total_r"]

        # Pull all chunk IDs and their current metadata from the collection
        all_chunks = collection.get(include=["metadatas"])
        chunk_ids = all_chunks["ids"]
        chunk_metas = all_chunks["metadatas"]

        for idx, chunk_id in enumerate(chunk_ids):
            meta = chunk_metas[idx]
            setup_name = meta.get("setup_name", "")
            if not setup_name:
                stats["skipped"] += 1
                continue

            # Skip if we have no outcome data for this setup_name
            if setup_name not in setup_global_rates:
                stats["skipped"] += 1
                continue

            try:
                global_data = setup_global_rates[setup_name]
                global_win_rate = global_data["wins"] / global_data["trades"] if global_data["trades"] > 0 else 0.5
                global_avg_pnl = global_data["total_pnl"] / global_data["trades"] if global_data["trades"] > 0 else 0.0
                global_avg_r = global_data["total_r"] / global_data["trades"] if global_data["trades"] > 0 else 0.0

                # Build per-regime win rates for this setup_name as a JSON string
                regime_wr = {}
                for (regime, sname), data in regime_setup_rates.items():
                    if sname == setup_name and data["trades"] > 0:
                        regime_wr[regime] = round(data["wins"] / data["trades"], 4)

                # Merge outcome metadata into existing metadata
                updated_meta = dict(meta)
                updated_meta["outcome_win_rate"] = round(global_win_rate, 4)
                updated_meta["outcome_avg_pnl_pct"] = round(global_avg_pnl, 4)
                updated_meta["outcome_avg_r_multiple"] = round(global_avg_r, 4)
                updated_meta["outcome_total_trades"] = global_data["trades"]
                updated_meta["outcome_regime_win_rates"] = json.dumps(regime_wr)

                collection.update(ids=[chunk_id], metadatas=[updated_meta])
                stats["updated"] += 1
                stats["details"].append({
                    "chunk_id": chunk_id,
                    "setup_name": setup_name,
                    "win_rate": round(global_win_rate, 4),
                    "trades": global_data["trades"]
                })
            except Exception as e:
                stats["errors"] += 1
                stats["details"].append({
                    "chunk_id": chunk_id,
                    "setup_name": setup_name,
                    "error": str(e)
                })

        return stats


class RegimeAwareQueryEngine:
    """
    Query ChromaDB adaptively based on detected market regime.
    Maps HMM regime → query templates → filtered retrieval → outcome-weighted ranking.
    """
    
    SETUP_TYPE_MAP = {
        "entry": "entry",
        "confirmation": "confirmation",
        "filter": "filter",
        "exit": "exit",
        "risk": "risk_management",
        "risk_management": "risk_management"
    }
    
    def __init__(self, collection=None, outcome_tracker: OutcomeTracker = None):
        self.collection = collection or _get_collection()
        self.outcome = outcome_tracker or OutcomeTracker()
    
    def query_by_regime(self, regime: str, n_results: int = 5,
                        setup_types: list = None) -> List[dict]:
        """
        Query ChromaDB with regime-appropriate queries.
        
        Args:
            regime: trending_up, trending_down, ranging, volatile
            n_results: Number of results per query
            setup_types: Filter by setup type (entry, confirmation, filter, exit, risk_management)
        
        Returns:
            List of strategy chunks sorted by combined score (cosine + outcome)
        """
        queries = REGIME_QUERIES.get(regime, DEFAULT_QUERIES)
        
        if setup_types is None:
            setup_types = ["entry", "confirmation", "filter", "exit", "risk_management"]
        
        all_results = []
        
        for stype in setup_types:
            # Map shorthand
            chroma_type = self.SETUP_TYPE_MAP.get(stype, stype)
            type_queries = queries.get(stype, queries.get(chroma_type, ["general trading strategy"]))
            
            for query in type_queries[:2]:  # Top 2 queries per type
                try:
                    chunks = self.collection.query(
                        query_texts=[query],
                        n_results=n_results,
                        where={"setup_type": chroma_type},
                        include=["documents", "metadatas", "distances"]
                    )
                except Exception as e:
                    print(f"Query error for '{query}' (type={chroma_type}): {e}")
                    continue
                
                if not chunks["ids"] or not chunks["ids"][0]:
                    continue
                
                for i in range(len(chunks["ids"][0])):
                    doc = chunks["documents"][0][i] if chunks["documents"] else ""
                    meta = chunks["metadatas"][0][i] if chunks["metadatas"] else {}
                    dist = chunks["distances"][0][i] if chunks["distances"] else 1.0
                    
                    # Outcome-weighted score
                    win_rate = self.outcome.get_win_rate(
                        setup_name=meta.get("setup_name", ""),
                        regime=regime
                    )
                    
                    # Combine cosine similarity with outcome history
                    cosine_score = 1 - dist
                    outcome_boost = (win_rate or 0.5) * 0.3  # 30% weight on outcomes
                    final_score = cosine_score + outcome_boost
                    
                    all_results.append({
                        "setup_name": meta.get("setup_name", ""),
                        "setup_type": meta.get("setup_type", ""),
                        "market_condition": meta.get("market_condition", ""),
                        "strategy_style": meta.get("strategy_style", ""),
                        "content": doc[:500],  # Truncated for display
                        "content_full": doc,
                        "keywords": meta.get("keywords", ""),
                        "cosine_score": round(cosine_score, 4),
                        "outcome_score": win_rate,
                        "final_score": round(final_score, 4),
                        "regime": regime,
                        "query": query
                    })
        
        # Sort by final score, deduplicate
        all_results.sort(key=lambda x: x["final_score"], reverse=True)
        seen = set()
        deduped = []
        for r in all_results:
            if r["setup_name"] not in seen:
                seen.add(r["setup_name"])
                deduped.append(r)
        
        return deduped[:20]  # Top 20 strategy chunks
    
    def get_regime_strategy_context(self, regime: str, top_k: int = 10) -> str:
        """
        Get a formatted string of top strategy chunks for a regime.
        This can be passed directly to TradingAgents LLM as context.
        """
        chunks = self.query_by_regime(regime, n_results=top_k)
        
        context = f"# Market Regime: {regime.upper()}\n\n"
        context += "## Recommended Strategies (by outcome-weighted score)\n\n"
        
        for i, chunk in enumerate(chunks[:top_k], 1):
            context += f"### {i}. {chunk['setup_name']} [{chunk['setup_type']}]\n"
            context += f"   Score: {chunk['final_score']:.3f} "
            context += f"(cosine: {chunk['cosine_score']:.3f}"
            if chunk.get("outcome_score") is not None:
                context += f", outcome WR: {chunk['outcome_score']:.1%}"
            context += ")\n"
            context += f"   Market: {chunk['market_condition']} | Style: {chunk['strategy_style']}\n"
            context += f"   {chunk['content'][:300]}...\n\n"
        
        return context

    def get_adaptive_strategy_context(self, regime: str, top_k: int = 8,
                                       outcome_weight: float = 0.3) -> str:
        """
        Combine cosine similarity with outcome-weighted scores to produce
        an adaptive strategy context string for the LLM.

        This method:
        1. Queries ChromaDB for regime-appropriate chunks (cosine similarity).
        2. For each chunk, retrieves the outcome win rate for (regime, setup_name).
        3. Computes an adaptive score = (1 - outcome_weight) * cosine + outcome_weight * outcome_factor.
        4. Re-ranks by adaptive score and returns a formatted context string.

        Args:
            regime: Market regime label (trending_up, trending_down, ranging, volatile).
            top_k: Number of strategy chunks to return.
            outcome_weight: Weight for outcome factor vs cosine similarity (0.0-1.0).
                           0.0 = pure cosine similarity, 1.0 = pure outcome history.

        Returns:
            Formatted context string for LLM injection.
        """
        # Step 1: Get chunks via cosine similarity using the existing query method
        raw_chunks = self.query_by_regime(regime, n_results=max(top_k * 3, 20))

        # Step 2: Re-score each chunk using adaptive formula
        scored_chunks = []
        for chunk in raw_chunks:
            cosine_score = chunk.get("cosine_score", 0.0)

            # Get outcome data for this setup_name in this regime
            setup_name = chunk.get("setup_name", "")
            regime_wr = self.outcome.get_win_rate(setup_name=setup_name, regime=regime)

            if regime_wr is not None:
                # Rescale win rate: 0.5 is neutral, >0.5 boosts, <0.5 penalizes
                # outcome_factor in [0, 1] range centered around 0.5
                outcome_factor = regime_wr
            else:
                # No outcome history — use neutral 0.5 (no boost, no penalty)
                outcome_factor = 0.5

            # Also check for globally-stored outcome metadata on the chunk
            # (written by update_chunk_scores_from_outcomes)
            # If present, blend it in
            global_wr = chunk.get("outcome_score")  # may be None from query_by_regime
            if global_wr is not None and regime_wr is None:
                outcome_factor = global_wr

            # Adaptive score: weighted combination
            # Normalize both scores to [0, 1] range
            # cosine_score is already 1 - distance ∈ [0, 1]
            # outcome_factor is already ∈ [0, 1]
            adaptive_score = ((1 - outcome_weight) * cosine_score) + (outcome_weight * outcome_factor)

            scored_chunks.append({
                **chunk,
                "adaptive_score": round(adaptive_score, 4),
                "outcome_factor": round(outcome_factor, 4),
                "outcome_weight": outcome_weight,
            })

        # Step 3: Sort by adaptive score and deduplicate
        scored_chunks.sort(key=lambda x: x["adaptive_score"], reverse=True)
        seen = set()
        deduped = []
        for c in scored_chunks:
            if c["setup_name"] not in seen:
                seen.add(c["setup_name"])
                deduped.append(c)

        top_chunks = deduped[:top_k]

        # Step 4: Build formatted context string
        context = f"# Market Regime: {regime.upper()}\n"
        context += f"# Adaptive Scoring: cosine_weight={1-outcome_weight:.1f}, outcome_weight={outcome_weight:.1f}\n\n"
        context += "## Top Strategies (adaptively ranked)\n\n"

        for i, chunk in enumerate(top_chunks, 1):
            context += f"### {i}. {chunk['setup_name']} [{chunk['setup_type']}]\n"
            context += f"   Adaptive Score: {chunk['adaptive_score']:.3f} "
            context += f"(cosine={chunk['cosine_score']:.3f}, outcome={chunk['outcome_factor']:.3f})\n"
            context += f"   Market: {chunk['market_condition']} | Style: {chunk['strategy_style']}\n"

            # Add outcome metadata if available
            if chunk.get("outcome_score") is not None:
                context += f"   Historical WR: {chunk['outcome_score']:.1%}\n"

            context += f"   {chunk['content'][:300]}...\n\n"

        # Step 5: Append regime-level outcome summary if available
        regime_summary = self.outcome.get_regime_summary()
        if regime in regime_summary:
            rdata = regime_summary[regime]
            context += f"---\n"
            context += f"### Regime Performance Summary: {regime}\n"
            context += f"Win Rate: {rdata['win_rate']:.1%} | "
            context += f"Avg P&L: {rdata['avg_pnl']:+.2f}% | "
            context += f"Total Trades: {rdata['total_trades']}\n"

        return context


class RegimeDetector:
    """
    Detect current market regime from OHLCV data.
    Uses rule-based thresholds (can be upgraded to HMM).
    """
    
    @staticmethod
    def detect(dataframe, lookback: int = 20) -> Tuple[str, dict]:
        """
        Detect market regime from recent price action.
        
        Returns:
            (regime_label, metrics_dict)
        """
        import ta  # technical analysis library
        
        close = dataframe["close"]
        high = dataframe["high"]
        low = dataframe["low"]
        volume = dataframe["volume"]
        
        # Calculate metrics
        returns = close.pct_change().rolling(lookback).mean()
        volatility = close.pct_change().rolling(lookback).std()
        atr_pct = (ta.atr(high, low, close, lookback) / close).rolling(lookback).mean()
        
        # ADX for trend strength
        try:
            adx = ta.adx(high, low, close, length=14)
        except:
            adx = dataframe.get("adx", [20] * len(dataframe))
        
        current_return = returns.iloc[-1] if len(returns) > 0 and not returns.isna().iloc[-1] else 0
        current_vol = volatility.iloc[-1] if len(volatility) > 0 and not volatility.isna().iloc[-1] else 0.015
        current_atr = atr_pct.iloc[-1] if len(atr_pct) > 0 and not atr_pct.isna().iloc[-1] else 0.02
        current_adx = adx.iloc[-1] if hasattr(adx, 'iloc') and not adx.isna().iloc[-1] else 20
        
        # Regime classification
        if current_atr > 0.04:  # 4%+ volatility
            regime = "volatile"
        elif current_return > 0.002 and current_adx > 25:
            regime = "trending_up"
        elif current_return < -0.002 and current_adx > 25:
            regime = "trending_down"
        elif current_adx < 20:
            regime = "ranging"
        else:
            # Weak trend
            regime = "ranging"
        
        metrics = {
            "regime": regime,
            "return_20": round(current_return, 6),
            "volatility_20": round(current_vol, 6),
            "atr_pct": round(current_atr, 6),
            "adx": round(current_adx, 2)
        }
        
        return regime, metrics


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Regime-Conditioned ChromaDB Query Engine")
    parser.add_argument("regime", choices=["trending_up", "trending_down", "ranging", "volatile"],
                        help="Market regime to query for")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results per type")
    parser.add_argument("--setup-types", nargs="+", 
                        choices=["entry", "confirmation", "filter", "exit", "risk_management"],
                        default=["entry", "confirmation", "filter", "exit", "risk_management"],
                        help="Setup types to query")
    parser.add_argument("--context-only", action="store_true", help="Print formatted context for LLM")
    parser.add_argument("--outcome-summary", action="store_true", help="Show outcome tracker summary")
    parser.add_argument("--sync-outcomes", action="store_true", help="Sync outcome history to ChromaDB chunk metadata")
    parser.add_argument("--adaptive-context", action="store_true", help="Use adaptive outcome-weighted scoring")
    parser.add_argument("--outcome-weight", type=float, default=0.3, help="Weight for outcome history vs cosine (default: 0.3)")
    
    args = parser.parse_args()
    
    engine = RegimeAwareQueryEngine()
    
    if args.outcome_summary:
        summary = engine.outcome.get_regime_summary()
        if not summary:
            print("No outcome history yet. Start trading to build feedback data.")
        else:
            print("=== REGIME OUTCOME SUMMARY ===")
            for regime, data in summary.items():
                print(f"  {regime}: WR={data['win_rate']:.1%}, avg_pnl={data['avg_pnl']:+.2f}%, trades={data['total_trades']}")
        exit(0)
    
    if args.sync_outcomes:
        print("Syncing outcome history to ChromaDB chunk metadata...")
        result = engine.outcome.update_chunk_scores_from_outcomes(collection=engine.collection)
        print(f"  Updated: {result['updated']} chunks")
        print(f"  Skipped: {result['skipped']} chunks (no match or no outcome data)")
        print(f"  Errors: {result['errors']}")
        for detail in result["details"][:10]:
            if "error" in detail:
                print(f"  ERROR: {detail['setup_name']} - {detail['error']}")
            else:
                print(f"  OK: {detail['setup_name']} (WR={detail['win_rate']:.2%}, trades={detail['trades']})")
        exit(0)
    
    if args.context_only:
        if args.adaptive_context:
            context = engine.get_adaptive_strategy_context(args.regime, top_k=args.top_k,
                                                           outcome_weight=args.outcome_weight)
        else:
            context = engine.get_regime_strategy_context(args.regime, top_k=args.top_k)
        print(context)
    else:
        results = engine.query_by_regime(args.regime, n_results=args.top_k, 
                                          setup_types=args.setup_types)
        
        print(f"\n=== REGIME: {args.regime.upper()} ===")
        print(f"Found {len(results)} strategy chunks\n")
        
        for i, r in enumerate(results, 1):
            print(f"{i:2d}. [{r['setup_type']:18s}] {r['setup_name']}")
            outcome_str = 'N/A' if r['outcome_score'] is None else f"{r['outcome_score']:.1%}"
            print(f"    Score: {r['final_score']:.3f} (cosine={r['cosine_score']:.3f}, outcome={outcome_str})")
            print(f"    Market: {r['market_condition']} | Style: {r['strategy_style']}")
            print(f"    Content: {r['content'][:120]}...")
            print()