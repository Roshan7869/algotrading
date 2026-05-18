#!/usr/bin/env python3
"""
MiroFish Bridge — Crypto Market Sentiment Feed

Runs every 5 minutes via cron or scheduler.
Fetches market summary, sends to MiroFish, writes signal file.

Usage:
    python3 scripts/mirofish_bridge.py
    python3 scripts/mirofish_bridge.py --mock  # Skip API call, write neutral signal

Karpathy: single file, pure stdlib + requests (optional).
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Default paths
SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", "/freqtrade/shared_config"))
SIGNAL_PATH = SHARED_DIR / "sentiment_signal.json"
REGIME_PATH = SHARED_DIR / "market_regime.json"

MIROFISH_URL = os.getenv("MIROFISH_URL", "http://mirofish:5001/api/simulation/run")


def log(msg: str):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")


def fetch_market_summary() -> dict:
    """Fetch market summary. In production, use Coingecko or CCXT."""
    # Placeholder: return realistic mock data for now
    return {
        "btc_change_24h": 2.5,
        "eth_change_24h": 1.8,
        "sol_change_24h": 5.2,
        "top_gainer": "SOL",
        "top_gainer_pct": 12.0,
        "fear_greed_index": 65,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_mirofish_simulation(seed_data: dict) -> dict:
    """Call MiroFish API with market seed."""
    payload = {
        "type": "crypto_sentiment",
        "seed": seed_data,
        "max_rounds": 20,
        "platform": "twitter",
    }
    try:
        import requests
        r = requests.post(MIROFISH_URL, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()
    except ImportError:
        log("requests not installed — using mock response")
        return mock_response(seed_data)
    except Exception as e:
        log(f"MiroFish API error: {e}")
        return mock_response(seed_data)


def mock_response(seed: dict) -> dict:
    """Generate realistic mock sentiment based on seed data."""
    btc = seed.get("btc_change_24h", 0)
    greed = seed.get("fear_greed_index", 50)
    # Simple heuristic
    sentiment = (btc / 10) + ((greed - 50) / 50)
    sentiment = max(-1.0, min(1.0, sentiment))
    forecast = "bullish" if sentiment > 0.3 else "bearish" if sentiment < -0.3 else "neutral"
    return {
        "sentiment_score": round(sentiment, 2),
        "forecast": forecast,
        "confidence": 0.6,
        "source": "mock",
    }


def write_signals(result: dict, seed: dict):
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    signal = {
        "timestamp": ts,
        "sentiment_score": result.get("sentiment_score", 0.0),
        "forecast": result.get("forecast", "neutral"),
        "confidence": result.get("confidence", 0.5),
        "seed": seed,
        "raw": result,
    }
    SIGNAL_PATH.write_text(json.dumps(signal, indent=2))

    regime = (
        "bull" if signal["sentiment_score"] > 0.3
        else "bear" if signal["sentiment_score"] < -0.3
        else "ranging"
    )
    REGIME_PATH.write_text(json.dumps({"regime": regime, "timestamp": ts}, indent=2))
    log(f"Wrote sentiment={signal['sentiment_score']}, regime={regime}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MiroFish Bridge")
    parser.add_argument("--mock", action="store_true", help="Skip API, use mock")
    args = parser.parse_args()

    log("Fetching market summary...")
    summary = fetch_market_summary()

    if args.mock:
        result = mock_response(summary)
    else:
        result = run_mirofish_simulation(summary)

    write_signals(result, summary)
    log("Done")


if __name__ == "__main__":
    main()
