#!/usr/bin/env python3
"""Refresh news sentiment signal via ChromaDB queries.

Queries the strategy KB news_sentiment collection and computes
an aggregate sentiment score. Writes to Signal Bus.
Meant to run every 30 minutes via cron.
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "strategy_db"))

from shared_config.signal_bus import get_bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [sentiment] %(message)s")
log = logging.getLogger(__name__)

KEYWORDS = ["bitcoin", "ethereum", "crypto", "BTC", "ETF", "regulation", "Fed"]


def compute_sentiment():
    """Compute aggregate sentiment from news_sentiment ChromaDB."""
    try:
        from strategy_db.news_pipeline import FinBERTNewsEmbedder
        import chromadb

        client = chromadb.PersistentClient(path=str(PROJECT_ROOT / "strategy_db" / "chroma_db"))
        collection = client.get_collection("news_sentiment")
        total = collection.count()

        if total == 0:
            log.warning("No news vectors in ChromaDB")
            return {"sentiment_score": 0.5, "article_count": 0, "dominant": "neutral"}

        # Query recent articles about crypto
        results = collection.query(
            query_texts=["crypto market bitcoin ethereum trading"],
            n_results=min(10, total),
        )

        scores = []
        for md in results["metadatas"][0]:
            raw = md.get("sentiment_score", "0.0")
            try:
                scores.append(float(raw))
            except (ValueError, TypeError):
                pass

        if not scores:
            # Rule-based from sentiment labels
            for md in results["metadatas"][0]:
                s = md.get("sentiment", "neutral")
                scores.append({"positive": 0.7, "negative": -0.3, "neutral": 0.0}.get(s, 0.0))

        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Map to 0-1 scale (raw scores are -1 to 1)
        normalized = round((avg_score + 1) / 2, 3)

        if avg_score > 0.1:
            dominant = "bullish"
        elif avg_score < -0.1:
            dominant = "bearish"
        else:
            dominant = "neutral"

        log.info(f"Sentiment: avg={avg_score:.3f}, normalized={normalized}, dominant={dominant}")

        return {
            "sentiment_score": normalized,
            "raw_score": round(avg_score, 4),
            "article_count": total,
            "dominant": dominant,
            "recent_articles": len(scores),
        }

    except Exception as e:
        log.error(f"Sentiment computation failed: {e}")
        return {"sentiment_score": 0.5, "article_count": 0, "dominant": "neutral", "error": str(e)}


def main():
    bus = get_bus()
    log.info("Refreshing news sentiment signal...")
    sentiment = compute_sentiment()
    bus.write("sentiment_signal.json", sentiment)
    log.info(f"Sentiment signal written: score={sentiment.get('sentiment_score')}, dominant={sentiment.get('dominant')}")


if __name__ == "__main__":
    main()