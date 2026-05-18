#!/usr/bin/env python3
"""Seed news_sentiment ChromaDB with realistic crypto news articles."""

import sys
import chromadb
from datetime import datetime, timedelta
from pathlib import Path

DB_DIR = Path(__file__).parent / "chroma_db"

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from strategy_db.news_pipeline import FinBERTNewsEmbedder

SEED_ARTICLES = [
    {"headline": "Bitcoin surges past 104K as institutional adoption accelerates", "source": "CoinDesk", "sentiment": "positive", "score": 0.7},
    {"headline": "Ethereum ETF approval boosts market confidence", "source": "Reuters", "sentiment": "positive", "score": 0.65},
    {"headline": "Solana ecosystem growth drives renewed investor interest", "source": "CoinTelegraph", "sentiment": "positive", "score": 0.55},
    {"headline": "SEC postpones decision on altcoin ETF applications", "source": "Bloomberg", "sentiment": "negative", "score": -0.3},
    {"headline": "Crypto market faces short-term correction after rally", "source": "CoinDesk", "sentiment": "neutral", "score": 0.0},
    {"headline": "DeFi total value locked reaches new yearly high", "source": "DeFi Pulse", "sentiment": "positive", "score": 0.6},
    {"headline": "Bitcoin mining difficulty hits all-time high", "source": "Blockware", "sentiment": "neutral", "score": 0.1},
    {"headline": "Major exchange reports record trading volume", "source": "Binance", "sentiment": "positive", "score": 0.5},
    {"headline": "Regulatory uncertainty weighs on crypto sentiment", "source": "Reuters", "sentiment": "negative", "score": -0.4},
    {"headline": "Layer 2 scaling solutions gain traction on Ethereum", "source": "CoinDesk", "sentiment": "positive", "score": 0.55},
    {"headline": "Bitcoin whale accumulation signals bullish trend", "source": "Glassnode", "sentiment": "positive", "score": 0.65},
    {"headline": "Federal Reserve holds rates steady, markets react", "source": "Bloomberg", "sentiment": "neutral", "score": 0.0},
    {"headline": "Altcoin season indicators flash as money rotates to mid-caps", "source": "CoinTelegraph", "sentiment": "positive", "score": 0.45},
    {"headline": "Stablecoin inflows to exchanges surge signaling buying pressure", "source": "CryptoQuant", "sentiment": "positive", "score": 0.7},
    {"headline": "Liquidation cascade wipes out overleveraged long positions", "source": "Coinglass", "sentiment": "negative", "score": -0.5},
    {"headline": "OP token governance vote sparks community debate", "source": "Optimism", "sentiment": "neutral", "score": -0.1},
    {"headline": "SUI network TVL grows 40% month over month", "source": "DeFi Llama", "sentiment": "positive", "score": 0.6},
    {"headline": "ARB ecosystem upgrades attract new developers", "source": "Arbitrum", "sentiment": "positive", "score": 0.45},
    {"headline": "Kaspa hash rate reaches new milestone", "source": "Kaspa", "sentiment": "positive", "score": 0.4},
    {"headline": "Crypto fear and greed index drops to fear territory", "source": "Alternative.me", "sentiment": "negative", "score": -0.35},
]

def main():
    print("Seeding news_sentiment ChromaDB...")
    client = chromadb.PersistentClient(path=str(DB_DIR))
    embedder = FinBERTNewsEmbedder(client=client)
    
    count = 0
    for i, article in enumerate(SEED_ARTICLES):
        timestamp = (datetime.utcnow() - timedelta(hours=i*2)).isoformat()
        try:
            result = embedder.embed_and_store(
                headline=article["headline"],
                source=article["source"],
                timestamp=timestamp,
                content=article["headline"],
                assets=["BTC", "ETH", "SOL"],
                categories=["crypto"]
            )
            count += 1
            print(f"  [{count}] {article['headline'][:60]}... ({article['sentiment']})")
        except Exception as e:
            print(f"  [ERR] {article['headline'][:40]}... {e}")
    
    collection = client.get_collection(name="news_sentiment")
    print(f"\nNews sentiment collection: {collection.count()} vectors")
    print("SUCCESS: News sentiment ChromaDB populated!")

if __name__ == "__main__":
    main()