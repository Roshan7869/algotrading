"""
Unified Intelligence Layer - Fuses technical signals, ChromaDB knowledge, and news sentiment.
This is the main orchestration module that ties all intelligence layers together.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Local imports
import sys
sys.path.insert(0, str(Path(__file__).parent))

from regime_query import RegimeAwareQueryEngine, RegimeDetector, OutcomeTracker, _get_collection
from news_pipeline import FinBERTNewsEmbedder, CryptoNewsFetcher
from regime_detector_hmm import HMMRegimeDetector
import chromadb


class IntelligenceLayer:
    """
    Unified intelligence layer that fuses:
    1. Technical signals (from Freqtrade indicators)
    2. ChromaDB strategy knowledge (regime-conditioned queries)
    3. News/sentiment (FinBERT-embedded news articles)
    4. Outcome history (feedback loop from past trades)
    
    Outputs:
    - Combined signal with confidence score
    - Strategy context for TradingAgents LLM
    - Regime-appropriate parameter adjustments
    """
    
    def __init__(self, chroma_db_dir: str = None, outcome_db: str = None,
                 news_collection: str = "news_sentiment"):
        import chromadb
        
        # Strategy knowledge base (use same ChromaDB client to avoid singleton error)
        self.chroma_client = chromadb.PersistentClient(path=str(Path(__file__).parent / "chroma_db"))
        self.strategies_collection = self.chroma_client.get_collection("trading_strategies")
        self.query_engine = RegimeAwareQueryEngine(collection=self.strategies_collection)
        
        # Outcome feedback tracker
        self.outcome = OutcomeTracker(db_path=outcome_db)
        
        # Regime detector (HMM with rule-based fallback)
        self.hmm = None
        try:
            hmm_path = str(Path(__file__).parent / "regime_hmm.pkl")
            self.hmm = HMMRegimeDetector(model_path=hmm_path)
            self.hmm.load()
            self.regime_detector = None  # HMM takes priority
            print("[INFO] HMM regime detector loaded successfully")
        except (FileNotFoundError, Exception) as e:
            print(f"[WARN] HMM not available ({e}), falling back to rule-based detection")
            self.regime_detector = RegimeDetector()
            self.hmm = None
        
        # News sentiment (separate collection, same client)
        try:
            self.news_collection_name = news_collection
            self.news = FinBERTNewsEmbedder(client=self.chroma_client, collection_name=news_collection)
            self.news_available = True
        except Exception as e:
            print(f"[WARN] News sentiment unavailable: {e}")
            self.news_available = False
    
    def analyze(self, dataframe, pair: str = "BTC/USDT", 
                timeframe: str = "1h") -> Dict:
        """
        Full intelligence analysis for a trading decision.
        
        Args:
            dataframe: OHLCV DataFrame with indicators populated
            pair: Trading pair
            timeframe: Candle timeframe
        
        Returns:
            Complete intelligence report with regime, KB context, 
            sentiment, and recommended strategy parameters
        """
        # === LAYER 1: Regime Detection ===
        if dataframe is not None:
            if self.hmm is not None:
                # Use HMM for regime detection
                try:
                    regime, metrics = self.hmm.predict(dataframe)
                    # Add HMM-specific fields
                    metrics["detection_method"] = "hmm"
                except Exception as e:
                    print(f"[WARN] HMM prediction failed: {e}, falling back to rule-based")
                    regime, metrics = self.regime_detector.detect(dataframe) if self.regime_detector else ("ranging", {"return_20": 0, "volatility_20": 0.01, "atr_pct": 0.02, "adx": 20, "detection_method": "rule_fallback"})
                    metrics["detection_method"] = "rule_fallback"
            else:
                # Fallback to rule-based
                regime, metrics = self.regime_detector.detect(dataframe)
                metrics["detection_method"] = "rule_based"
        else:
            # CLI mode: no real data
            regime = "ranging"
            metrics = {"return_20": 0, "volatility_20": 0.01, "atr_pct": 0.02, "adx": 20, "detection_method": "default"}
        metrics["pair"] = pair
        metrics["timeframe"] = timeframe
        metrics["timestamp"] = datetime.utcnow().isoformat()
        
        # === LAYER 2: ChromaDB Knowledge Retrieval ===
        kb_context = self.query_engine.get_regime_strategy_context(regime, top_k=8)
        kb_chunks = self.query_engine.query_by_regime(regime, n_results=5)
        
        # === LAYER 3: News/Sentiment ===
        sentiment_summary = {}
        relevant_news = []
        if self.news_available:
            try:
                base_asset = pair.split("/")[0] if "/" in pair else pair
                sentiment_summary = self.news.get_sentiment_summary(
                    pair=base_asset, hours=24
                )
                relevant_news = self.news.query_relevant_news(
                    query=f"{regime} market {base_asset} crypto impact",
                    pair=base_asset,
                    top_k=5
                )
            except Exception as e:
                print(f"[WARN] News query failed: {e}")
        
        # === LAYER 4: Outcome-Weighted Rankings ===
        best_chunks = self.outcome.get_best_chunks_for_regime(regime, top_k=5)
        regime_summary = self.outcome.get_regime_summary()
        
        # === COMPUTE: Regime-Appropriate Parameters ===
        params = self._compute_regime_parameters(regime, metrics, kb_chunks, sentiment_summary)
        
        # === COMPUTE: Confidence & Risk ===
        confidence = self._compute_confidence(regime, kb_chunks, sentiment_summary)
        risk_score = self._compute_risk(regime, metrics, sentiment_summary)
        
        # Sentiment-adjusted confidence: if sentiment strongly contradicts regime, penalize
        if sentiment_summary and sentiment_summary.get("articles", 0) >= 3:
            sent_score = sentiment_summary.get("avg_sentiment", 0)
            # Down-trend regime + positive news = conflicting signals → lower confidence
            if regime == "trending_down" and sent_score > 0.3:
                confidence = round(confidence * 0.80, 3)
            # Up-trend regime + negative news = conflicting → lower confidence
            elif regime == "trending_up" and sent_score < -0.3:
                confidence = round(confidence * 0.80, 3)
            # Regime + sentiment aligned → slight boost
            elif (regime == "trending_up" and sent_score > 0.2) or \
                 (regime == "trending_down" and sent_score < -0.2):
                confidence = round(min(1.0, confidence * 1.05), 3)
        
        # Sentiment summary for report
        sentiment_label = "neutral"
        if sentiment_summary and sentiment_summary.get("articles", 0) > 0:
            sentiment_label = sentiment_summary.get("sentiment_label", "neutral")
        
        sentiment_adjustment = {
            "direction": "aligned" if (
                (regime in ("trending_up",) and sentiment_label == "positive") or
                (regime in ("trending_down",) and sentiment_label == "negative") or
                sentiment_label == "neutral"
            ) else "conflicting",
            "impact": "boost_confidence" if sentiment_label in ("positive",) and regime == "trending_up" else (
                "reduce_confidence" if sentiment_label == "negative" and regime == "trending_up" or
                sentiment_label == "positive" and regime == "trending_down" else "neutral"
            )
        }
        
        # === ASSEMBLE: Complete Report ===
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "pair": pair,
            "timeframe": timeframe,
            "regime": {
                "label": regime,
                "metrics": metrics
            },
            "knowledge_base": {
                "top_chunks": [
                    {
                        "name": c["setup_name"],
                        "type": c["setup_type"],
                        "score": c["final_score"],
                        "cosine": c["cosine_score"],
                        "outcome_wr": c.get("outcome_score"),
                        "market": c["market_condition"],
                        "style": c["strategy_style"]
                    }
                    for c in kb_chunks[:8]
                ],
                "llm_context": kb_context
            },
            "sentiment": sentiment_summary,
            "relevant_news": [
                {
                    "headline": n["metadata"].get("headline", ""),
                    "sentiment": n["metadata"].get("sentiment_label", "?"),
                    "score": n["metadata"].get("sentiment_score", 0),
                    "source": n["metadata"].get("source", "?"),
                    "hours_old": n["metadata"].get("hours_old", 0)
                }
                for n in relevant_news
            ],
            "outcome_feedback": {
                "best_chunks": best_chunks,
                "regime_summary": regime_summary
            },
            "recommended_params": params,
            "signal_confidence": confidence,
            "risk_score": risk_score,
            "sentiment_adjustment": sentiment_adjustment
        }
        
        return report
    
    def _compute_regime_parameters(self, regime: str, metrics: dict,
                                    kb_chunks: list, sentiment: dict) -> dict:
        """
        Compute regime-appropriate Freqtrade parameters.
        Based on ChromaDB knowledge + regime + sentiment.
        """
        # Default parameters (ranging market)
        params = {
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
            "leverage": 1
        }
        
        # Adjust based on regime
        if regime == "trending_up":
            params.update({
                "bb_squeeze_threshold": 0.04,
                "bb_pct_lower": 0.35,
                "bb_pct_upper": 0.65,
                "rsi_lower": 30,
                "rsi_upper": 70,
                "volume_multiplier": 1.5,
                "confluence_min": 2,
                "stoploss": -0.05,
                "trailing_stop": 0.03,
                "trailing_stop_offset": 0.05,
                "max_open_trades": 4,
                "leverage": 2
            })
        elif regime == "trending_down":
            params.update({
                "bb_squeeze_threshold": 0.04,
                "bb_pct_lower": 0.35,
                "bb_pct_upper": 0.65,
                "rsi_lower": 30,
                "rsi_upper": 70,
                "volume_multiplier": 1.5,
                "confluence_min": 2,
                "stoploss": -0.05,
                "trailing_stop": 0.03,
                "trailing_stop_offset": 0.05,
                "max_open_trades": 4,
                "leverage": 2
            })
        elif regime == "volatile":
            params.update({
                "bb_squeeze_threshold": 0.06,
                "bb_pct_lower": 0.3,
                "bb_pct_upper": 0.7,
                "rsi_lower": 25,
                "rsi_upper": 75,
                "volume_multiplier": 2.0,
                "confluence_min": 3,  # MORE confirmation needed
                "stoploss": -0.04,    # TIGHTER stop
                "trailing_stop": 0.02,
                "trailing_stop_offset": 0.03,
                "max_open_trades": 2,
                "leverage": 1         # LOWER leverage in volatility
            })
        # ranging uses defaults
        
        # Adjust based on sentiment (if available)
        if sentiment and sentiment.get("articles", 0) > 0:
            sentiment_score = sentiment.get("avg_sentiment", 0)
            if sentiment_score > 0.3:
                # Very bullish sentiment → can be more aggressive with longs
                params["rsi_lower"] = max(25, params["rsi_lower"] - 5)
                params["max_open_trades"] = min(5, params["max_open_trades"] + 1)
            elif sentiment_score < -0.3:
                # Very bearish sentiment → favor shorts, reduce longs
                params["rsi_upper"] = min(80, params["rsi_upper"] + 5)
                params["max_open_trades"] = max(1, params["max_open_trades"] - 1)
        
        return params
    
    def _compute_confidence(self, regime: str, kb_chunks: list, 
                             sentiment: dict) -> float:
        """
        Compute overall signal confidence (0-1).
        Factors: regime clarity, KB match quality, sentiment alignment.
        """
        # Regime confidence (ADX-based)
        regime_confidence = {
            "trending_up": 0.8,
            "trending_down": 0.8,
            "ranging": 0.5,     # Harder to trade
            "volatile": 0.3     # Very uncertain
        }.get(regime, 0.5)
        
        # KB match quality (average cosine similarity)
        kb_confidence = 0.5  # Default
        if kb_chunks:
            avg_cosine = sum(c.get("cosine_score", 0) for c in kb_chunks[:5]) / min(5, len(kb_chunks))
            kb_confidence = min(1.0, avg_cosine)
        
        # Sentiment alignment
        sentiment_confidence = 0.5  # Neutral
        if sentiment and sentiment.get("articles", 0) >= 3:
            sent_score = sentiment.get("avg_sentiment", 0)
            # Higher confidence when sentiment is extreme and aligned with regime
            sentiment_confidence = min(1.0, 0.5 + abs(sent_score) * 0.5)
        
        # Weighted combination
        confidence = (
            regime_confidence * 0.4 +    # 40% weight on regime
            kb_confidence * 0.35 +        # 35% weight on KB
            sentiment_confidence * 0.25    # 25% weight on sentiment
        )
        
        return round(min(1.0, max(0.0, confidence)), 3)
    
    def _compute_risk(self, regime: str, metrics: dict, sentiment: dict) -> dict:
        """
        Compute risk assessment based on regime, metrics, and sentiment.
        Returns a dict with overall risk level, sentiment risk contribution,
        and recommended risk adjustments.
        """
        # Base risk by regime
        regime_risk = {
            "trending_up": 0.3,
            "trending_down": 0.7,
            "ranging": 0.4,
            "volatile": 0.8
        }.get(regime, 0.5)
        
        # Volatility risk from metrics
        volatility = metrics.get("volatility_20", 0.02)
        atr_pct = metrics.get("atr_pct", 0.02)
        volatility_risk = min(1.0, (volatility + atr_pct) * 10)  # Scale to 0-1
        
        # Sentiment risk: extreme sentiment increases risk
        sentiment_risk = 0.5  # neutral default
        sentiment_direction = "neutral"
        if sentiment and sentiment.get("articles", 0) > 0:
            avg_sent = sentiment.get("avg_sentiment", 0)
            # Extreme sentiment (either direction) adds uncertainty/risk
            sentiment_risk = min(1.0, 0.3 + abs(avg_sent) * 0.7)
            if avg_sent > 0.1:
                sentiment_direction = "bullish"
            elif avg_sent < -0.1:
                sentiment_direction = "bearish"
            # Conflicting: positive sentiment in downtrend or negative in uptrend → higher risk
            if (regime == "trending_up" and avg_sent < -0.2) or \
               (regime == "trending_down" and avg_sent > 0.2):
                sentiment_risk = min(1.0, sentiment_risk + 0.2)
                sentiment_direction = "conflicting"
        
        # Composite risk score (0-1, higher = more risk)
        overall_risk = (
            regime_risk * 0.40 +
            volatility_risk * 0.30 +
            sentiment_risk * 0.30
        )
        overall_risk = round(min(1.0, max(0.0, overall_risk)), 3)
        
        # Risk level label
        if overall_risk < 0.3:
            risk_level = "low"
        elif overall_risk < 0.6:
            risk_level = "moderate"
        else:
            risk_level = "high"
        
        return {
            "overall_risk": overall_risk,
            "risk_level": risk_level,
            "regime_risk": round(regime_risk, 3),
            "volatility_risk": round(volatility_risk, 3),
            "sentiment_risk": round(sentiment_risk, 3),
            "sentiment_direction": sentiment_direction,
            "recommendation": "reduce_position" if overall_risk > 0.65 else (
                "increase_position" if overall_risk < 0.3 else "hold_position"
            )
        }
    
    def record_trade_outcome(self, trade_id: str, pair: str, regime: str,
                              setup_names: list, pnl_pct: float, 
                              r_multiple: float, is_win: bool,
                              strategy_type: str = "VectorStrategy",
                              dominant_signal: str = "") -> dict:
        """Record a trade outcome for the feedback loop."""
        return self.outcome.record_trade(
            trade_id=trade_id,
            pair=pair,
            regime=regime,
            setup_names=setup_names,
            pnl_pct=pnl_pct,
            r_multiple=r_multiple,
            is_win=is_win,
            strategy_type=strategy_type,
            dominant_signal=dominant_signal
        )


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Intelligence Layer CLI")
    parser.add_argument("--regime", type=str, 
                        choices=["trending_up", "trending_down", "ranging", "volatile"],
                        help="Analyze for a specific regime")
    parser.add_argument("--pair", type=str, default="BTC/USDT", help="Trading pair")
    parser.add_argument("--fetch-news", action="store_true", help="Fetch and embed news")
    parser.add_argument("--outcome-summary", action="store_true", help="Show outcome history")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    intel = IntelligenceLayer()
    
    if args.outcome_summary:
        summary = intel.outcome.get_regime_summary()
        if not summary:
            print("No outcome history yet. Start trading to build feedback data.")
        else:
            print("=== REGIME OUTCOME SUMMARY ===")
            for regime, data in summary.items():
                print(f"  {regime}: WR={data['win_rate']:.1%}, "
                      f"avg_pnl={data['avg_pnl']:+.2f}%, "
                      f"trades={data['total_trades']}")
        exit(0)
    
    if args.fetch_news:
        print("Fetching and embedding crypto news...")
        fetcher = CryptoNewsFetcher()
        results = fetcher.fetch_and_embed(intel.news, limit=10)
        print(f"Embedded {len(results)} articles")
        for r in results:
            print(f"  {r['doc_id']}: {r['sentiment']['sentiment']} "
                  f"({r['sentiment']['sentiment_score']:+.3f})")
        exit(0)
    
    if args.regime:
        # Get strategy context for a specific regime
        report = intel.analyze(None, pair=args.pair)
        # Override regime since we don't have real data
        report["regime"]["label"] = args.regime
        
        # Query KB for this regime
        kb_context = intel.query_engine.get_regime_strategy_context(args.regime, top_k=10)
        kb_chunks = intel.query_engine.query_by_regime(args.regime, n_results=5)
        
        report["knowledge_base"]["top_chunks"] = [
            {
                "name": c["setup_name"],
                "type": c["setup_type"],
                "score": c["final_score"],
                "cosine": c["cosine_score"],
                "outcome_wr": c.get("outcome_score"),
                "market": c["market_condition"],
                "style": c["strategy_style"]
            }
            for c in kb_chunks[:10]
        ]
        report["knowledge_base"]["llm_context"] = kb_context
        
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(f"\n{'='*70}")
            print(f"  INTELLIGENCE REPORT: {args.regime.upper()} | {args.pair}")
            print(f"{'='*70}")
            print(f"\n  Regime: {args.regime}")
            print(f"  Confidence: {report['signal_confidence']}")
            
            # Risk score display
            risk = report.get("risk_score", {})
            if risk:
                print(f"  Risk Score: {risk.get('overall_risk', '?')} ({risk.get('risk_level', '?')})")
                print(f"  Risk Recommendation: {risk.get('recommendation', 'N/A')}")
            
            # Sentiment adjustment display
            sent_adj = report.get("sentiment_adjustment", {})
            if sent_adj:
                print(f"  Sentiment Alignment: {sent_adj.get('direction', '?')}")
                print(f"  Sentiment Impact: {sent_adj.get('impact', '?')}")
            
            # Sentiment summary section
            sent = report.get("sentiment", {})
            if sent and sent.get("articles", 0) > 0:
                print(f"\n  --- News Sentiment ---")
                print(f"    Articles (24h):    {sent.get('articles', 0)}")
                print(f"    Avg Sentiment:     {sent.get('avg_sentiment', 0):+.4f} ({sent.get('sentiment_label', 'neutral')})")
                print(f"    Positive:          {sent.get('positive_count', 0)} ({sent.get('positive_pct', 0):.1f}%)")
                print(f"    Negative:          {sent.get('negative_count', 0)} ({sent.get('negative_pct', 0):.1f}%)")
                print(f"    Neutral:           {sent.get('neutral_count', 0)}")
            else:
                print(f"\n  --- News Sentiment ---")
                print(f"    No recent news data. Run with --fetch-news to populate.")
            
            # Relevant news headlines
            news_items = report.get("relevant_news", [])
            if news_items:
                print(f"\n  --- Top Relevant News ---")
                for i, item in enumerate(news_items[:5], 1):
                    print(f"    {i}. [{item.get('sentiment', '?'):8s}] {item.get('headline', '')[:70]}")
                    print(f"       Score: {item.get('score', 0):+.3f} | Source: {item.get('source', '?')} | Age: {item.get('hours_old', '?')}h")
            
            print(f"\n  Recommended Parameters:")
            params = report.get("recommended_params", {})
            for k, v in params.items():
                print(f"    {k:30s} = {v}")
            print(f"\n  Top Strategy Chunks:")
            for i, chunk in enumerate(report["knowledge_base"]["top_chunks"][:8], 1):
                print(f"    {i}. [{chunk['type']:18s}] {chunk['name'][:50]}")
                print(f"       Score: {chunk['score']:.3f} (cosine={chunk['cosine']:.3f})")
    else:
        print("Usage: intelligence_layer.py --regime <regime> [--pair BTC/USDT] [--fetch-news] [--outcome-summary] [--json]")