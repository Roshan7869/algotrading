# Real-Time Financial Intelligence System Architecture

> How ChromaDB becomes an adaptive intelligence layer for trading agents  
> Date: 2026-05-16 | Version: 1.0

---

## 1. THE CORE INSIGHT

Your ChromaDB has 474 strategy chunks across 10 types. Right now it's a **static knowledge base** — you query it once, pick strategies, and they don't change. The transformation is to make it a **living intelligence system** where:

1. Market regime is detected in real-time
2. ChromaDB is queried adaptively based on regime
3. Trade outcomes feed BACK into ChromaDB as outcome tags
4. Strategy selection improves over time via walk-forward feedback
5. News/sentiment is embedded alongside strategy concepts

This turns ChromaDB from a "dictionary" into an "advisor that gets smarter."

---

## 2. CURRENT STATE ANALYSIS

### What We Have

| Component | Status | Location |
|-----------|--------|----------|
| ChromaDB Strategy KB | 474 chunks, 472 unique setups, all-MiniLM-L6-v2 | `strategy_db/chroma_db/` |
| HMM Regime Detector | GaussianHMM on returns + volatility | `TradingAgents/` |
| Signal Bus | Filesystem IPC via JSON | `shared_config/` |
| TradingAgents (LangGraph) | 13 agents, 19 models | `TradingAgents/` |
| Freqtrade | Execution engine (v2026.5-dev) | `.venv/bin/freqtrade` |
| Market Regime JSON | trending_up/down, ranging, volatile | `shared_config/market_regime.json` |
| VDBMixin | ChromaDB runtime query mixin | `user_data/strategies/vdb_mixin.py` |
| MCP Server | 5 tools, stdio transport | `strategy_db/mcp_server.py` |

### Critical Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| Only 5 exit chunks vs 101 entry chunks | System knows when to enter but not when to leave | **CRITICAL** |
| No outcome feedback loop | ChromaDB never learns which chunks worked | **CRITICAL** |
| No news/sentiment embeddings | Pure technical, no fundamental context | HIGH |
| No time-series embeddings | Can't encode OHLCV patterns as vectors | MEDIUM |
| HMM not connected to ChromaDB queries | Regime detected but not used for strategy selection | HIGH |
| VDBMixin not wired into strategies | DB queries never reach live trading | HIGH |

---

## 3. PROPOSED ARCHITECTURE

### 3.1 Five-Layer Intelligence Stack

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 5: EXECUTION (Freqtrade)                                 │
│  - Place trades, manage positions, track P&L                     │
│  - Write trade outcomes back to Outcome Tracker                  │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 4: DECISION SYNTHESIS (TradingAgents + LLM)               │
│  - Receives: technical signals + KB chunks + sentiment           │
│  - Debates: Market Analyst ← → Risk Analyst ← → News Analyst    │
│  - Outputs: BUY/SELL/HOLD with confidence + strategy_id           │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: ADAPTIVE RETRIEVAL (ChromaDB Intelligence)            │
│  - Regime → Query mapping (trending_up → momentum queries)      │
│  - Outcome-weighted ranking (chunks that worked get boosted)    │
│  - Gap detection (if regime has few chunks, flag for ingestion) │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: SIGNAL FUSION (Multi-Modal)                            │
│  - Technical: OHLCV indicators (FreqAI/TA-Lib)                  │
│  - Knowledge: ChromaDB strategy chunks (cosine similarity)      │
│  - Sentiment: FinBERT news embeddings + social signals            │
│  - Macro: FRED data + crypto on-chain metrics                    │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: DATA INGESTION (Streaming)                             │
│  - ccxt WebSockets for OHLCV + order book                       │
│  - RSS/API for news (Reuters, CoinDesk, CryptoPanic)            │
│  - FRED for macro indicators                                     │
│  - On-chain: Glassnode/Arkham for whale movements               │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow: Live Trading Cycle

```
Every candle close (1h):

1. OHLCV buffer updates
   └─→ HMM Regime Detector classifies: {trending_up, trending_down, ranging, volatile}

2. Technical indicators compute
   └─→ RSI, BB, EMA alignment, volume spikes, %b, ADX

3. ChromaDB ADAPTIVE query
   └─→ query = f"{regime} market {dominant_signal} entry confirmation"
   └─→ Filter by setup_type IN [entry, confirmation, filter]
   └─→ Weight by outcome_history (win_rate in this regime)
   └─→ Return top-5 strategy chunks as context

4. News/Sentiment (if available)
   └─→ FinBERT sentiment score: {-1.0 to +1.0}
   └─→ Recent headlines embedded and retrieved

5. TradingAgents synthesis
   └─→ Market Analyst uses technical data
   └─→ News Analyst uses sentiment
   └─→ Research Manager references ChromaDB chunks
   └─→ Risk Analyst evaluates position sizing
   └─→ Portfolio Manager makes final call

6. Freqtrade executes signal
   └─→ Writes trade outcome to Outcome Tracker

7. Outcome feedback (every N trades)
   └─→ Tag ChromaDB chunks used with: {regime, pnl, r_multiple, win/loss}
   └─→ Recalculate outcome-weighted rankings
   └─→ Re-ingest failed-regime patterns as new chunk candidates
```

---

## 4. DETAILED COMPONENT DESIGNS

### 4.1 Regime-Conditioned ChromaDB Query Engine

```python
# strategy_db/regime_query.py

REGIME_QUERIES = {
    "trending_up": {
        "entry": [
            "momentum breakout entry with volume confirmation",
            "EMA crossover alignment uptrend continuation",
            "higher high higher low structure entry"
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
        "risk": [
            "risk reward ratio trending market position sizing"
        ]
    },
    "trending_down": {
        "entry": [
            "short selling bearish market structure entry",
            "lower low continuation short setup",
            "bearish liquidity trap entry"
        ],
        "confirmation": [
            "volume confirmation bearish breakdown",
            "negative delta divergence distribution"
        ],
        "filter": [
            "avoid longs in downtrend filter",
            "kill zone short entry session"
        ],
        "exit": [
            "profit target support level short covering",
            "risk zero breakeven short trade"
        ],
        "risk": [
            "2% daily max loss in bear market",
            "smaller position size downtrend"
        ]
    },
    "ranging": {
        "entry": [
            "mean reversion support resistance level entry",
            "Bollinger Band squeeze breakout ranging market",
            "absorption pattern passive order detection range"
        ],
        "confirmation": [
            "CVD divergence range bound confirmation",
            "volume profile value area range"
        ],
        "filter": [
            "no trade zone consolidation filter",
            "range bound market session filter"
        ],
        "exit": [
            "scale out at resistance ranging market",
            "auction cap too expensive rejection"
        ],
        "risk": [
            "tight stop loss ranging market",
            "reduced position size chop"
        ]
    },
    "volatile": {
        "entry": [
            "confirmation before entry high volatility",
            "circuit breaker flash crash protection"
        ],
        "confirmation": [
            "full candle close confirmation volatile",
            "multiple timeframe confirmation volatility"
        ],
        "filter": [
            "low probability day filter post large expansion",
            "FOMC news event filter skip"
        ],
        "exit": [
            "adaptive stop loss volatile market",
            "risk to zero quickly high volatility"
        ],
        "risk": [
            "reduce leverage volatile regime",
            "circuit breaker drawdown protection"
        ]
    }
}


class RegimeAwareQueryEngine:
    def __init__(self, chroma_collection, hmm_model=None):
        self.collection = chroma_collection
        self.hmm = hmm_model
        self.outcome_tracker = OutcomeTracker()
    
    def detect_regime(self, returns, volatility):
        """Use HMM to classify current market regime."""
        if self.hmm:
            state = self.hmm.predict(returns, volatility)
            return ["trending_up", "trending_down", "ranging", "volatile"][state]
        # Fallback: rule-based regime detection
        if volatility > 0.03:
            return "volatile"
        elif returns > 0.01:
            return "trending_up"
        elif returns < -0.01:
            return "trending_down"
        else:
            return "ranging"
    
    def query_by_regime(self, regime: str, n_results: int = 5):
        """Query ChromaDB with regime-appropriate queries."""
        setup_types = ["entry", "confirmation", "filter", "exit", "risk_management"]
        queries = REGIME_QUERIES.get(regime, REGIME_QUERIES["ranging"])
        
        results = []
        for setup_type in setup_types:
            type_queries = queries.get(setup_type, ["general trading strategy"])
            for query in type_queries[:2]:  # Top 2 queries per type
                chunks = self.collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where={"setup_type": setup_type},
                    include=["documents", "metadatas", "distances"]
                )
                # Apply outcome weighting
                for i in range(len(chunks["ids"][0])):
                    doc = chunks["documents"][0][i]
                    meta = chunks["metadatas"][0][i]
                    dist = chunks["distances"][0][i]
                    
                    # Outcome-weighted score
                    win_rate = self.outcome_tracker.get_win_rate(
                        setup_name=meta.get("setup_name", ""),
                        regime=regime
                    )
                    # Combine cosine similarity with outcome history
                    outcome_boost = win_rate * 0.3 if win_rate else 0
                    final_score = (1 - dist) + outcome_boost
                    
                    results.append({
                        "setup_name": meta.get("setup_name", ""),
                        "setup_type": meta.get("setup_type", ""),
                        "content": doc,
                        "cosine_score": 1 - dist,
                        "outcome_score": win_rate,
                        "final_score": final_score,
                        "regime": regime
                    })
        
        # Sort by final score, deduplicate
        results.sort(key=lambda x: x["final_score"], reverse=True)
        seen = set()
        deduped = []
        for r in results:
            if r["setup_name"] not in seen:
                seen.add(r["setup_name"])
                deduped.append(r)
        
        return deduped[:20]  # Top 20 strategy chunks
```

### 4.2 Outcome Feedback Tracker

```python
# strategy_db/outcome_tracker.py

import json
from pathlib import Path
from datetime import datetime

OUTCOME_DB = Path("strategy_db/outcome_history.json")

class OutcomeTracker:
    """
    Track trade outcomes mapped to ChromaDB strategy chunks.
    Each trade records which chunks informed the decision and whether it won/lost.
    This closes the feedback loop: ChromaDB → Strategy → Trade → Outcome → ChromaDB.
    """
    
    def __init__(self, db_path=OUTCOME_DB):
        self.db_path = db_path
        self.history = self._load()
    
    def _load(self):
        if self.db_path.exists():
            with open(self.db_path) as f:
                return json.load(f)
        return {"trades": [], "chunk_stats": {}}
    
    def _save(self):
        with open(self.db_path, "w") as f:
            json.dump(self.history, f, indent=2, default=str)
    
    def record_trade(self, trade_id, pair, regime, setup_names, pnl_pct, 
                     r_multiple, is_win, strategy_type, dominant_signal):
        """
        Record a completed trade with its ChromaDB strategy context.
        
        Args:
            trade_id: Unique trade identifier
            pair: Trading pair (e.g., "BTC/USDT")
            regime: Market regime at entry (trending_up/down/ranging/volatile)
            setup_names: List of ChromaDB chunk names that informed this trade
            pnl_pct: Trade P&L as percentage
            r_multiple: Reward-to-risk ratio achieved
            is_win: Whether trade was profitable
            strategy_type: "VectorStrategy" or other
            dominant_signal: Which indicator prompted entry (bb_squeeze, rsi, etc.)
        """
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
                    "avg_r_multiple": 0.0,
                    "regime_breakdown": {}
                }
            stats = self.history["chunk_stats"][name]
            stats["total_trades"] += 1
            stats["wins" if is_win else "losses"] += 1
            stats["total_pnl"] += pnl_pct
            
            # Track by regime
            if regime not in stats["regime_breakdown"]:
                stats["regime_breakdown"][regime] = {"trades": 0, "wins": 0, "pnl": 0.0}
            stats["regime_breakdown"][regime]["trades"] += 1
            if is_win:
                stats["regime_breakdown"][regime]["wins"] += 1
            stats["regime_breakdown"][regime]["pnl"] += pnl_pct
        
        self._save()
    
    def get_win_rate(self, setup_name: str, regime: str = None) -> float:
        """Get win rate for a strategy chunk, optionally filtered by regime."""
        stats = self.history["chunk_stats"].get(setup_name)
        if not stats or stats["total_trades"] < 3:
            return None  # Not enough data
        
        if regime and regime in stats.get("regime_breakdown", {}):
            r = stats["regime_breakdown"][regime]
            return r["wins"] / r["trades"] if r["trades"] > 0 else None
        
        return stats["wins"] / stats["total_trades"]
    
    def get_best_chunks_for_regime(self, regime: str, top_k: int = 10):
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
    
    def get_regime_summary(self):
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
                "win_rate": data["wins"] / data["trades"],
                "avg_pnl": data["total_pnl"] / data["trades"],
                "total_trades": data["trades"]
            }
        return summary
```

### 4.3 Multi-Collection ChromaDB Architecture

Currently you have one collection (`trading_strategies`). The intelligence system needs multiple:

```python
# strategy_db/collections.py

COLLECTIONS = {
    # EXISTING: Strategy concepts (currently 474 vectors)
    "strategies": {
        "description": "Trading strategy chunks from YouTube, books, research",
        "embedding": "all-MiniLM-L6-v2",
        "fields": ["setup_name", "setup_type", "market_condition", "strategy_style",
                    "keywords", "entry_condition", "confirmation_signal", "stop_loss_rule",
                    "target_exit_rule", "invalidation_condition", "risk_reward", 
                    "edge_description", "outcome_history"],
        "vector_count": 474
    },
    
    # NEW: Market regime embeddings
    "regimes": {
        "description": "Historical market regime embeddings with outcomes",
        "embedding": "all-MiniLM-L6-v2",
        "fields": ["regime_label", "start_date", "end_date", "avg_return",
                    "volatility", "trend_strength", "best_strategy_type",
                    "worst_strategy_type", "dominant_pairs"],
        "vector_count": 0  # To be built
    },
    
    # NEW: News/sentiment embeddings
    "news_sentiment": {
        "description": "Embedded news articles with FinBERT sentiment",
        "embedding": "ProsusAI/finbert",  # 768-dim financial BERT
        "fields": ["headline", "source", "timestamp", "sentiment_score",
                    "entities", "impact_assets", "relevance_decay"],
        "vector_count": 0  # To be built
    },
    
    # NEW: Trade outcome history
    "trade_outcomes": {
        "description": "Embedded trade contexts for pattern matching",
        "embedding": "all-MiniLM-L6-v2",
        "fields": ["regime_at_entry", "signals_triggered", "strategy_chunks_used",
                    "pnl_pct", "r_multiple", "is_win", "entry_date", "exit_date",
                    "pair", "timeframe"],
        "vector_count": 0  # Built incrementally from live trading
    },
    
    # NEW: Macro indicators
    "macro_indicators": {
        "description": "FRED data + crypto on-chain metrics embedded as state vectors",
        "embedding": "all-MiniLM-L6-v2",
        "fields": ["indicator_name", "value", "change_pct", "timestamp",
                    "regime_context", "historical_percentile"],
        "vector_count": 0
    }
}
```

### 4.4 FinBERT News Embedding Pipeline

```python
# strategy_db/news_pipeline.py

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from datetime import datetime, timedelta

class FinBERTNewsEmbedder:
    """
    Embed news articles with financial sentiment analysis.
    Stores in ChromaDB 'news_sentiment' collection.
    
    Pipeline: RSS/API → FinBERT classification → sentiment embedding → ChromaDB upsert
    Target latency: <30 seconds from news publication to tradeable signal.
    """
    
    def __init__(self, chroma_client, collection_name="news_sentiment"):
        self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        self.model.eval()
        self.collection = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    
    def classify_sentiment(self, text: str) -> dict:
        """Classify financial text sentiment using FinBERT."""
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)
        
        labels = ["negative", "neutral", "positive"]
        scores = {label: prob.item() for label, prob in zip(labels, probs[0])}
        sentiment_score = scores["positive"] - scores["negative"]  # Range: -1 to +1
        
        return {
            "sentiment": max(scores, key=scores.get),
            "scores": scores,
            "sentiment_score": sentiment_score
        }
    
    def embed_and_store(self, headline: str, source: str, timestamp: str,
                         content: str = "", assets: list = None):
        """Process a news article: classify sentiment and store in ChromaDB."""
        # Sentiment analysis
        sentiment = self.classify_sentiment(headline + " " + content)
        
        # Create embedding text (what we search by)
        embedding_text = f"{headline}. {sentiment['sentiment']} sentiment. "
        if assets:
            embedding_text += f"Related assets: {', '.join(assets)}. "
        embedding_text += f"Source: {source}."
        
        # Unique ID
        doc_id = f"news_{int(datetime.now().timestamp())}_{hash(headline) % 10000}"
        
        # Decay factor: recent news is more relevant
        # News loses 50% relevance every 24 hours
        hours_old = (datetime.now() - datetime.fromisoformat(timestamp)).total_seconds() / 3600
        relevance_decay = max(0.1, 1.0 / (1 + hours_old / 24))
        
        self.collection.upsert(
            ids=[doc_id],
            documents=[embedding_text],
            metadatas=[{
                "headline": headline[:200],
                "source": source,
                "timestamp": timestamp,
                "sentiment_score": sentiment["sentiment_score"],
                "sentiment_label": sentiment["sentiment"],
                "impact_assets": ", ".join(assets) if assets else "",
                "relevance_decay": relevance_decay
            }]
        )
        
        return {
            "doc_id": doc_id,
            "sentiment": sentiment,
            "relevance_decay": relevance_decay
        }
    
    def query_relevant_news(self, pair: str, regime: str, top_k: int = 5):
        """Retrieve recent news relevant to a trading pair and regime."""
        query = f"crypto {pair} {regime} market impact"
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"impact_assets": {"$contains": pair.split("/")[0]}},
            include=["documents", "metadatas", "distances"]
        )
        return results
```

### 4.5 Enhanced VectorStrategy with Outcome Feedback

```python
# user_data/strategies/VectorStrategyV2.py (key additions)

class VectorStrategyV2(IStrategy):
    """
    VectorStrategy with regime-aware ChromaDB queries and outcome feedback.
    
    Key improvements over V1:
    1. HMM regime detection before each trade decision
    2. ChromaDB query adapts to detected regime
    3. Outcome-weighted chunk ranking
    4. Trade outcome recording back to OutcomeTracker
    5. News/sentiment consideration (if available via SignalBus)
    """
    
    # HMM regime thresholds (rule-based fallback)
    REGIME_THRESHOLDS = {
        "volatile": {"atr_pct": 0.03},
        "trending_up": {"returns_pct": 0.01, "adx": 25},
        "trending_down": {"returns_pct": -0.01, "adx": 25},
        "ranging": {"default": True}
    }
    
    def detect_regime(self, dataframe, metadata):
        """Detect current market regime from recent price action."""
        close = dataframe["close"]
        returns = close.pct_change().rolling(20).mean()
        volatility = close.pct_change().rolling(20).std()
        adx = ta.ADX(dataframe, timeperiod=14) if "adx" not in dataframe else dataframe["adx"]
        
        current_return = returns.iloc[-1] if len(returns) > 0 else 0
        current_vol = volatility.iloc[-1] if len(volatility) > 0 else 0
        current_adx = adx.iloc[-1] if len(adx) > 0 else 20
        
        if current_vol > 0.03:
            return "volatile", current_vol, current_adx
        elif current_return > 0.01 and current_adx > 25:
            return "trending_up", current_vol, current_adx
        elif current_return < -0.01 and current_adx > 25:
            return "trending_down", current_vol, current_adx
        else:
            return "ranging", current_vol, current_adx
    
    def query_knowledge_base(self, regime, signal_type, top_k=5):
        """Query ChromaDB with regime-adaptive queries."""
        query_engine = RegimeAwareQueryEngine(self.chroma_collection)
        return query_engine.query_by_regime(regime, n_results=top_k)
    
    def populate_entry_trend(self, dataframe, metadata):
        """Enhanced entry logic with regime-aware KB queries."""
        # Step 1: Detect regime
        regime, vol, adx = self.detect_regime(dataframe, metadata)
        
        # Step 2: Query ChromaDB for regime-appropriate strategies
        kb_chunks = self.query_knowledge_base(regime, "entry")
        
        # Step 3: Adjust signal thresholds based on regime + KB
        if regime == "volatile":
            # KB says: require MORE confirmation in volatile markets
            bb_threshold = 0.06  # Wider BB squeeze
            volume_mult = 2.0    # Higher volume required
            rsi_lower = 30       # More extreme RSI
            rsi_upper = 70
        elif regime in ("trending_up", "trending_down"):
            # KB says: standard thresholds, but favor trend direction
            bb_threshold = 0.04
            volume_mult = 1.5
            rsi_lower = 35
            rsi_upper = 65
        else:  # ranging
            # KB says: favor mean reversion, tighter bands
            bb_threshold = 0.03
            volume_mult = 1.2
            rsi_lower = 40
            rsi_upper = 60
        
        # Step 4: Compute confluence (same as V1 but with regime-adjusted thresholds)
        conditions_long = 0
        conditions_short = 0
        
        # ... (same indicator logic as V1, using regime-adjusted thresholds)
        
        # Step 5: Return signals with KB context
        dataframe["regime"] = regime
        dataframe["kb_chunks"] = json.dumps([c["setup_name"] for c in kb_chunks[:5]])
        
        return dataframe
    
    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        """Enhanced exit with KB-sourced exit rules."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        regime = last_candle.get("regime", "ranging")
        
        # Query exit strategies for current regime
        exit_chunks = self.query_knowledge_base(regime, "exit", top_k=3)
        
        # Apply exit rules from KB
        # Example: "Auction Cap / Too Expensive Rejection" → exit when BB %b > 0.8
        # Example: "Risk to Zero ASAP" → move stop to breakeven at 1.5R profit
        
        if current_profit > 0.015:  # 1.5% profit → risk-to-zero
            return "risk_to_zero"
        
        # Standard BB %b exit
        if trade.is_short and last_candle.get("bb_lowerband") and current_rate < last_candle["bb_lowerband"]:
            return "bb_lower_exit"
        
        return None  # Let ROI/trailing handle it
```

### 4.6 Walk-Forward Feedback Loop

```
┌────────────────────────────────────────────────────────────┐
│  WALK-FORWARD WITH KNOWLEDGE GRAPH FEEDBACK                 │
│                                                              │
│  IS Window 1: [----TRAIN----] [TEST]                          │
│  IS Window 2:    [----TRAIN----] [TEST]                       │
│  IS Window 3:       [----TRAIN----] [TEST]                    │
│                    ───────────────────────→ TIME              │
│                                                              │
│  After each TEST window:                                     │
│    1. Record all trade outcomes                               │
│    2. Map outcomes → ChromaDB chunks used                     │
│    3. Tag chunks: {regime, pnl, r_multiple, win_rate}         │
│    4. Re-rank: chunks that worked get boosted                 │
│    5. Re-train HMM if regime shift detected                   │
│    6. Next IS: use outcome-weighted ChromaDB rankings          │
│                                                              │
│  This turns ChromaDB from "static dictionary"                │
│  into "adaptive advisor that gets smarter."                   │
└────────────────────────────────────────────────────────────┘
```

---

## 5. RESEARCH FOUNDATIONS

### 5.1 Key Papers & Systems

| Paper / System | Year | Key Innovation | Relevance |
|---|---|---|---|
| **TradingAgents** (arXiv:2412.20138) | 2024 | Multi-agent LLM debate via LangGraph | Already in your codebase |
| **QuantAgent** (arXiv:2509.09995) | 2025 | Price-driven multi-agent for HFT | Architecture for microstructure |
| **FinVision** (arXiv:2411.08899) | 2024 | Multi-agent + vision for chart patterns | Chart image augmentation |
| **TrustTrade** (arXiv:2603.22567) | 2026 | Trust-weighted agent consensus | Improvement to your debate mechanism |
| **Financial RAG** (arXiv:2603.26815) | 2026 | Hybrid document-routed retrieval for finance | Directly applicable to ChromaDB chunking |
| **FinGPT** (GitHub: 20.2k★) | 2023-25 | Open-source financial LLM, LoRA adapters | FinBERT embedder for news |
| **FinRL** (GitHub: 15.2k★) | 2020-25 | Deep RL for trading, walk-forward eval | FreqAI integration path |
| **Kronos** (AAAI 2026) | 2025 | Hierarchical OHLCV tokenization | Time-series embedding approach |
| **BloombergGPT** | 2023 | 50B financial LLM, domain pre-training | Architecture reference only |
| **DeepTrade** | 2024 | Multi-modal fusion (indicators + news) | Unified signal pipeline design |

### 5.2 Relevant Quant Journal Topics

- **Regime-Switching Models**: Hamilton (1989), Hidden Markov Models for bull/bear markets
- **Adaptive Filtering**: Kalman filters for time-varying parameter estimation
- **Kelly Criterion**: Thorp (2006), optimal position sizing with edge estimation
- **Walk-Forward Analysis**: Pardo (2008), out-of-sample validation methodology
- **Order Flow Imbalance**: Cont et al. (2014), relationship between order flow and price
- **Sentiment Alpha**: Tetlock (2007), Garcia (2013), news sentiment as return predictor
- **Knowledge Graphs in Finance**: Wu et al. (2023), graph neural networks for stock prediction

### 5.3 How Top Quant Funds Build Intelligence Layers

| Approach | Who | Description |
|----------|-----|-------------|
| Signal Factory | Renaissance (Medallion) | Thousands of alpha signals → statistical combination → portfolio |
| Sentiment Radar | Two Sigma | NLP pipeline ingesting 10K+ news sources/day → sentiment signals |
| Knowledge Graph | Point72 | Entity-relationship graphs linking companies, people, events |
| Alternative Data | Citadel | Satellite imagery, credit card transactions, web scraping |
| Regime Classifier | Bridgewater | Macro regime detection → asset allocation shifts |
| Continuous Research | Jane Street | 24/7 research cycle: hypothesis → test → deploy → feedback |

---

## 6. IMPLEMENTATION ROADMAP

### Phase 1: Connect Existing Pieces (1-2 days)

```
Priority: CRITICAL
Goal: Close the loop between existing components

Tasks:
1. Wire HMM regime detector → ChromaDB query parameters
2. Wire OutcomeTracker into VectorStrategy custom_exit()
3. Add regime column to Freqtrade trade exports
4. Fix VDBMixin import in VectorStrategy (currently disconnected)
5. Add ChromaDB chunk name tracking to trade records
```

### Phase 2: Exit & Gap Filling (2-3 days)

```
Priority: CRITICAL
Goal: Fill the exit/position_sizing gap in ChromaDB

Tasks:
1. Scrape and ingest exit strategy content (currently only 5 chunks vs 101 entry)
2. Ingest position sizing content (currently only 3 chunks)
3. Target: 50+ exit chunks, 30+ position sizing chunks
4. Re-embed with consistent all-MiniLM-L6-v2
5. Validate retrieval quality for exit/position queries
```

### Phase 3: News & Sentiment Pipeline (3-5 days)

```
Priority: HIGH
Goal: Add real-time news intelligence

Tasks:
1. Set up CryptoPanic/RSS news feed
2. FinBERT sentiment classification pipeline
3. Create news_sentiment ChromaDB collection
4. Implement news_pipeline.py (ingest → classify → embed → store)
5. Wire sentiment scores into SignalBus
6. Add sentiment filter to VectorStrategy V2
```

### Phase 4: Outcome Feedback Loop (2-3 days)

```
Priority: HIGH
Goal: Make ChromaDB learn from trade outcomes

Tasks:
1. Implement OutcomeTracker with regime-tagged statistics
2. Wire into VectorStrategy V2 (record every trade's KB chunks)
3. Every N trades: recalculate chunk win rates by regime
4. Boost high-performing chunks in retrieval rankings
5. Deprecate low-performing chunks (weight decay)
6. Monthly walk-forward: full re-optimization with KG-guided init
```

### Phase 5: Regime-Aware Adaptive Strategy (5-7 days)

```
Priority: MEDIUM
Goal: Full adaptive intelligence system

Tasks:
1. Build RegimeAwareQueryEngine with REGIME_QUERIES mapping
2. Train HMM on 365-day BTC data with 4 regime classes
3. Implement VectorStrategyV2 with regime-adjusted thresholds
4. Walk-forward validation: 70/30 split, rotate 4 times
5. Compare V1 (static) vs V2 (adaptive) out-of-sample
6. Add macro indicator collection (FRED + on-chain)
7. Build unified SignalBus v2 with all 5 layers
```

---

## 7. QUICK WINS (Do Today)

These are architecture-agnostic improvements that can be done in minutes:

```bash
# 1. Query ChromaDB for exit strategies (currently a critical gap)
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/gcode_bridge.py query "exit strategy profit target stop loss trailing" --setup-type exit

# 2. Query for the regime you're currently in
python3 strategy_db/gcode_bridge.py query "ranging market mean reversion Bollinger Band" --market-condition ranging

# 3. Get strategy statistics
python3 strategy_db/gcode_bridge.py stats

# 4. Run the deep-dive analysis
python3 strategy_db/chromadb_deep_analysis.py
python3 strategy_db/chromadb_content_sample.py
```

---

## 8. ARCHITECTURAL DECISIONS

### Why ChromaDB (not FAISS/pinecone/weaviate)?

| Feature | ChromaDB | FAISS | Pinecone | Weaviate |
|---------|---------|-------|----------|----------|
| Local-first | ✅ | ✅ | ❌ (cloud) | ❌ |
| Metadata filtering | ✅ | ❌ | ✅ | ✅ |
| Schema flexibility | ✅ | ❌ | ✅ | ✅ |
| MCP integration | ✅ (built) | Needs work | Needs work | Needs work |
| Embedding function | ✅ built-in | ❌ manual | ✅ | ✅ |
| Real-time updates | ✅ upsert | ❌ rebuild | ✅ | ✅ |
| Cost | Free | Free | Paid | Paid |

**Verdict:** Keep ChromaDB. Add a second collection for news/sentiment with FinBERT embeddings.

### Why all-MiniLM-L6-v2 (not FinBERT for strategies)?

- Strategy chunks are short (512-1986 chars) — MiniLM handles these well
- FinBERT is 768-dim, requires a separate collection (can't mix dimensions)
- Strategy concept retrieval works fine with general embeddings
- Use FinBERT specifically for the news_sentiment collection

### Why HMM (not LSTM/Transformer for regime)?

- HMM is interpretable — you can see the transition matrix
- HMM is fast — inference in <1ms per candle
- HMM works with limited data — our BTC history has only ~11K candles
- Transformer-based regime detection is overkill for 4 states

---

## 9. MONITORING & OBSERVABILITY

```python
# Key metrics to track per regime:

REGIME_METRICS = {
    "trending_up": {
        "win_rate": "target > 60%",
        "avg_pnl_per_trade": "target > 0%",
        "best_chunks": ["EMA alignment", "momentum breakout"],
        "worst_chunks": ["mean reversion in uptrend"]
    },
    "trending_down": {
        "win_rate": "target > 60%", 
        "avg_pnl_per_trade": "target > 0%",
        "best_chunks": ["short selling structure", "lower low continuation"],
        "worst_chunks": ["buying dips in downtrend"]
    },
    "ranging": {
        "win_rate": "target > 55%",
        "avg_pnl_per_trade": "target > 0%",
        "best_chunks": ["BB squeeze mean reversion", "absorption pattern"],
        "worst_chunks": ["breakout in range"]
    },
    "volatile": {
        "win_rate": "target > 50%",
        "avg_pnl_per_trade": "target > 0%",
        "best_chunks": ["risk to zero quickly", "avoid low probability"],
        "worst_chunks": ["trend following in volatility"]
    }
}
```

---

## 10. SUMMARY

The transformation from **static knowledge base** to **adaptive intelligence system** requires 5 key changes:

1. **Regime Detection → ChromaDB Query Mapping**: The HMM regime detector selects which query templates to send to ChromaDB. Trending markets query momentum strategies. Ranging markets query mean reversion. Volatile markets query risk management.

2. **Outcome Feedback Loop**: Every trade records which ChromaDB chunks informed it. Wins boost those chunks. Losses deprioritize them. Over time, the DB learns which concepts work in which regimes.

3. **Exit Strategy Gap Fill**: Go from 5 exit chunks to 50+. This is the single biggest quick win. A system that knows when to enter but not when to leave is a car with gas but no brakes.

4. **News/Sentiment Collection**: Add a second ChromaDB collection for FinBERT-embedded news. This adds fundamental context to pure technical decisions.

5. **Walk-Forward Validation**: Every 3 months, run a full walk-forward test. In-sample optimize → out-of-sample validate → feed outcomes back → adapt for next cycle.

The result: ChromaDB stops being a "dictionary you query" and becomes an "advisor that gets smarter with every trade."