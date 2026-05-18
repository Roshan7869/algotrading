"""
News Sentiment Pipeline - FinBERT-powered news embedding and ChromaDB storage.
Adds real-time news intelligence to the trading system.
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ChromaDB
import chromadb

# Config
DB_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "news_sentiment"


class FinBERTNewsEmbedder:
    """
    Embed news articles with financial sentiment analysis.
    Stores in ChromaDB 'news_sentiment' collection.
    
    Pipeline: RSS/API → FinBERT classification → sentiment embedding → ChromaDB upsert
    Target latency: <30 seconds from news publication to tradeable signal.
    """
    
    def __init__(self, client=None, collection_name: str = "news_sentiment"):
        """Initialize with shared ChromaDB client to avoid singleton errors."""
        if client is not None:
            self.client = client
        else:
            self.client = chromadb.PersistentClient(path=str(DB_DIR))
        # Check if collection exists, get or create
        existing = [c.name for c in self.client.list_collections()]
        if collection_name in existing:
            self.collection = self.client.get_collection(name=collection_name)
        else:
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
    
    def _get_or_create_collection(self):
        """Get or create the news_sentiment ChromaDB collection."""
        client = chromadb.PersistentClient(path=str(DB_DIR))
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        return collection
    
    def _load_classifier(self):
        """Lazy-load FinBERT sentiment classifier."""
        if self.classifier is not None:
            return self.classifier
        
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch
            
            self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
            self.model.eval()
            self.classifier = "finbert"
            return "finbert"
        except ImportError:
            print("[WARNING] transformers not installed. Using rule-based sentiment fallback.")
            self.classifier = "rule_based"
            return "rule_based"
    
    def classify_sentiment(self, text: str) -> Dict:
        """
        Classify financial text sentiment.
        Uses FinBERT if available, rule-based fallback otherwise.
        """
        if self.classifier is None:
            self._load_classifier()
        
        if self.classifier == "finbert":
            return self._classify_finbert(text)
        else:
            return self._classify_rule_based(text)
    
    def _classify_finbert(self, text: str) -> Dict:
        """Classify using FinBERT model."""
        import torch
        
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
            "sentiment_score": round(sentiment_score, 4),
            "method": "finbert"
        }
    
    def _classify_rule_based(self, text: str) -> Dict:
        """Rule-based sentiment fallback when FinBERT is unavailable."""
        text_lower = text.lower()
        
        positive_words = ["bullish", "surge", "rally", "gain", "breakout", "up", "pump",
                         "adoption", "institutional", "approval", "etf", "buy", "moon",
                         " ATH", "all-time high", "recovery", "growth", "upgrade"]
        negative_words = ["bearish", "crash", "dump", "hack", "ban", "regulation", "sec",
                         "sell", "decline", "drop", "fear", "risk", "fraud", "rug pull",
                         "liquidation", "default", "downgrade", "loss", "warning"]
        
        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)
        
        if pos_count > neg_count + 1:
            sentiment = "positive"
            sentiment_score = min(0.8, 0.3 + pos_count * 0.1)
        elif neg_count > pos_count + 1:
            sentiment = "negative"
            sentiment_score = max(-0.8, -0.3 - neg_count * 0.1)
        else:
            sentiment = "neutral"
            sentiment_score = 0.0
        
        return {
            "sentiment": sentiment,
            "scores": {"positive": max(0, sentiment_score), "neutral": 1 - abs(sentiment_score), "negative": max(0, -sentiment_score)},
            "sentiment_score": round(sentiment_score, 4),
            "method": "rule_based"
        }
    
    def embed_and_store(self, headline: str, source: str, timestamp: str,
                         content: str = "", assets: List[str] = None,
                         categories: List[str] = None) -> Dict:
        """
        Process a news article: classify sentiment and store in ChromaDB.
        
        Args:
            headline: News headline
            source: News source (e.g., "CoinDesk", "Reuters", "CryptoPanic")
            timestamp: ISO format timestamp
            content: Full article text (optional)
            assets: List of related assets (e.g., ["BTC", "ETH"])
            categories: List of categories (e.g., ["regulation", "macro"])
        """
        # Sentiment analysis
        full_text = f"{headline}. {content}" if content else headline
        sentiment = self.classify_sentiment(full_text)
        
        # Create embedding text (what we search by)
        embedding_text = f"{headline}. {sentiment['sentiment']} sentiment. "
        if assets:
            embedding_text += f"Related assets: {', '.join(assets)}. "
        if categories:
            embedding_text += f"Categories: {', '.join(categories)}. "
        embedding_text += f"Source: {source}."
        
        # Unique ID (deterministic based on content)
        doc_id = f"news_{hashlib.md5(headline.encode()).hexdigest()[:12]}"
        
        # Decay factor: recent news is more relevant
        try:
            news_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            hours_old = max(0, (datetime.now(news_time.tzinfo) - news_time).total_seconds() / 3600)
        except:
            hours_old = 0
        relevance_decay = max(0.1, 1.0 / (1 + hours_old / 24))
        
        # Store in ChromaDB
        metadata = {
            "headline": headline[:500],  # ChromaDB metadata limit
            "source": source,
            "timestamp": timestamp,
            "sentiment_score": sentiment["sentiment_score"],
            "sentiment_label": sentiment["sentiment"],
            "method": sentiment.get("method", "unknown"),
            "impact_assets": ", ".join(assets) if assets else "",
            "categories": ", ".join(categories) if categories else "",
            "relevance_decay": round(relevance_decay, 4),
            "hours_old": round(hours_old, 2)
        }
        
        self.collection.upsert(
            ids=[doc_id],
            documents=[embedding_text],
            metadatas=[metadata]
        )
        
        return {
            "doc_id": doc_id,
            "sentiment": sentiment,
            "relevance_decay": round(relevance_decay, 4),
            "stored": True
        }
    
    def query_relevant_news(self, query: str, pair: str = None,
                             sentiment_filter: str = None, top_k: int = 5) -> List[Dict]:
        """
        Retrieve relevant news from ChromaDB.
        
        Args:
            query: Search query
            pair: Filter by trading pair (e.g., "BTC")
            sentiment_filter: Filter by sentiment ("positive", "negative", "neutral")
            top_k: Number of results
        """
        where_filter = {}
        if pair:
            where_filter["impact_assets"] = {"$contains": pair}
        if sentiment_filter:
            where_filter["sentiment_label"] = sentiment_filter
        
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter if where_filter else None,
            include=["documents", "metadatas", "distances"]
        )
        
        output = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                output.append({
                    "doc_id": results["ids"][0][i],
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 1.0
                })
        
        return output
    
    def get_sentiment_summary(self, pair: str = None, hours: int = 24) -> Dict:
        """
        Get aggregated sentiment for a pair over recent hours.
        
        Returns:
            Dict with sentiment scores, article counts, and trending topics
        """
        all_docs = self.collection.get(include=["metadatas"])
        
        now = datetime.utcnow()
        recent_articles = []
        
        for meta in all_docs["metadatas"]:
            try:
                ts = datetime.fromisoformat(meta.get("timestamp", "").replace("Z", ""))
                hours_diff = (now - ts).total_seconds() / 3600
                if hours_diff <= hours:
                    if pair and pair.lower() not in meta.get("impact_assets", "").lower():
                        continue
                    recent_articles.append(meta)
            except:
                continue
        
        if not recent_articles:
            return {"pair": pair, "hours": hours, "articles": 0, "avg_sentiment": 0, 
                    "sentiment_label": "neutral"}
        
        avg_sentiment = sum(a.get("sentiment_score", 0) for a in recent_articles) / len(recent_articles)
        pos = sum(1 for a in recent_articles if a.get("sentiment_label") == "positive")
        neg = sum(1 for a in recent_articles if a.get("sentiment_label") == "negative")
        neu = sum(1 for a in recent_articles if a.get("sentiment_label") == "neutral")
        
        return {
            "pair": pair,
            "hours": hours,
            "articles": len(recent_articles),
            "avg_sentiment": round(avg_sentiment, 4),
            "sentiment_label": "positive" if avg_sentiment > 0.1 else ("negative" if avg_sentiment < -0.1 else "neutral"),
            "positive_count": pos,
            "negative_count": neg,
            "neutral_count": neu,
            "positive_pct": round(pos / len(recent_articles) * 100, 1) if recent_articles else 0,
            "negative_pct": round(neg / len(recent_articles) * 100, 1) if recent_articles else 0,
        }


class CryptoNewsFetcher:
    """
     Fetch crypto news from free RSS/API sources.
     Supported sources: CryptoPanic API (free tier), CoinDesk RSS, Reuters crypto.
    """
    
    CRYPTOPANIC_API = "https://cryptopanic.com/api/v1/posts/"
    COINDESK_RSS = "https://www.coindesk.com/arc/outboundfeeds/rss/"
    
    def __init__(self, cryptopanic_api_key: str = None):
        self.api_key = cryptopanic_api_key
    
    def fetch_cryptopanic(self, currencies: str = "BTC,ETH,SOL", 
                           filter_type: str = "rising",
                           limit: int = 20) -> List[Dict]:
        """
        Fetch news from CryptoPanic API.
        Free tier allows 5 requests/minute.
        """
        import urllib.request
        import urllib.parse
        
        if not self.api_key:
            # Use free public endpoint (limited)
            url = f"{self.CRYPTOPANIC_API}?auth_token=free&currencies={currencies}&filter={filter_type}&public=true&limit={limit}"
        else:
            url = f"{self.CRYPTOPANIC_API}?auth_token={self.api_key}&currencies={currencies}&filter={filter_type}&limit={limit}"
        
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            
            articles = []
            for post in data.get("results", []):
                articles.append({
                    "headline": post.get("title", ""),
                    "source": post.get("domain", "cryptopanic"),
                    "timestamp": post.get("created_at", ""),
                    "content": post.get("body", ""),
                    "url": post.get("url", ""),
                    "currencies": post.get("currencies", []),
                    "categories": [post.get("filter", "")]
                })
            return articles
            
        except Exception as e:
            print(f"[ERROR] CryptoPanic fetch failed: {e}")
            return []
    
    def fetch_and_embed(self, embedder: FinBERTNewsEmbedder,
                         currencies: str = "BTC,ETH,SOL",
                         limit: int = 20) -> List[Dict]:
        """Fetch news and embed into ChromaDB."""
        articles = self.fetch_cryptopanic(currencies=currencies, limit=limit)
        
        results = []
        for article in articles:
            result = embedder.embed_and_store(
                headline=article["headline"],
                source=article["source"],
                timestamp=article["timestamp"],
                content=article.get("content", ""),
                assets=article.get("currencies", []),
                categories=article.get("categories", [])
            )
            results.append(result)
        
        return results


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="News Sentiment Pipeline")
    parser.add_argument("--regime", type=str, help="Query news for regime context")
    parser.add_argument("--pair", type=str, help="Filter by trading pair (e.g., BTC)")
    parser.add_argument("--fetch", action="store_true", help="Fetch and embed news from CryptoPanic")
    parser.add_argument("--summary", action="store_true", help="Get sentiment summary")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results")
    args = parser.parse_args()
    
    embedder = FinBERTNewsEmbedder()
    fetcher = CryptoNewsFetcher()
    
    if args.fetch:
        print("Fetching news from CryptoPanic...")
        results = fetcher.fetch_and_embed(embedder, limit=10)
        print(f"Embedded {len(results)} articles")
        for r in results:
            print(f"  {r['doc_id']}: {r['sentiment']['sentiment']} ({r['sentiment']['sentiment_score']:+.3f})")
    
    elif args.summary:
        summary = embedder.get_sentiment_summary(pair=args.pair, hours=24)
        print(f"\n=== SENTIMENT SUMMARY ({args.pair or 'all'}) ===")
        print(f"Articles (24h): {summary['articles']}")
        print(f"Avg Sentiment: {summary['avg_sentiment']:+.4f} ({summary['sentiment_label']})")
        print(f"Positive: {summary.get('positive_count', 0)} ({summary.get('positive_pct', 0)}%)")
        print(f"Negative: {summary.get('negative_count', 0)} ({summary.get('negative_pct', 0)}%)")
        print(f"Neutral: {summary.get('neutral_count', 0)}")
    
    elif args.regime or args.pair:
        query = f"{args.regime} market crypto {args.pair or ''} impact trading"
        results = embedder.query_relevant_news(query, pair=args.pair, top_k=args.top_k)
        
        print(f"\n=== NEWS FOR: {args.regime or 'general'} | {args.pair or 'all pairs'} ===\n")
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            print(f"{i}. [{meta.get('sentiment_label', '?'):8s}] {meta.get('headline', '?')[:80]}")
            print(f"   Score: {meta.get('sentiment_score', 0):+.3f} | Source: {meta.get('source', '?')} | Age: {meta.get('hours_old', '?')}h")
            print()
    
    else:
        # Default: show collection stats
        count = embedder.collection.count()
        print(f"News sentiment collection: {count} articles")
        if count == 0:
            print("No articles yet. Run with --fetch to import news.")