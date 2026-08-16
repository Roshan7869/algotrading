#!/usr/bin/env python3
"""
hmm_regime.py — Hidden Markov Model regime detector.

Detects market regime (trending_up, trending_down, ranging, volatile)
using HMM on log returns + volatility.

Output: writes market_regime.json for consumption by regime_router.py
and strategies.

Usage:
  python3 scripts/regime/hmm_regime.py --pair BTC/USDT:USDT --candles 500
  python3 scripts/regime/hmm_regime.py --from-file candles.csv
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "shared_config"
REGIME_PATH = SHARED_DIR / "market_regime.json"


def fetch_ohlcv(pair: str, timeframe: str = "1h", limit: int = 500) -> np.ndarray:
    """Fetch OHLCV data via CCXT (read-only)."""
    import ccxt
    exchange = ccxt.binance({"options": {"defaultType": "future"}})
    ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
    closes = np.array([c[4] for c in ohlcv], dtype=float)
    return closes


def detect_regime(prices: np.ndarray, n_states: int = 4) -> str:
    """
    Fit HMM on log returns + volatility to detect market regime.

    Returns: trending_up, trending_down, ranging, volatile
    """
    try:
        from hmmlearn import hmm
    except ImportError:
        print("[hmm_regime] hmmlearn not installed. Install: pip install hmmlearn")
        return "unknown"

    returns = np.diff(np.log(prices)).reshape(-1, 1)
    vol = np.array([
        np.std(returns[max(0, i - 14):i + 1])
        for i in range(len(returns))
    ]).reshape(-1, 1)
    X = np.hstack([returns, vol])

    if len(X) < n_states * 10:
        return "unknown"

    model = hmm.GaussianHMM(
        n_components=n_states,
        covariance_type="diag",
        n_iter=100,
        random_state=42,
    )
    model.fit(X)
    hidden_states = model.predict(X)
    last_state = hidden_states[-1]

    means = model.means_[last_state]
    mean_return = means[0]
    mean_vol = means[1]

    vol_threshold = np.median(vol)

    if mean_vol > vol_threshold * 1.5:
        return "volatile"
    elif mean_return > 0.0001:
        return "trending_up"
    elif mean_return < -0.0001:
        return "trending_down"
    else:
        return "ranging"


def write_regime(regime: str, pair: str):
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "regime": regime,
        "pair": pair,
        "timestamp": str(np.datetime64("now")),
    }
    REGIME_PATH.write_text(json.dumps(data, indent=2))
    print(f"[hmm_regime] Wrote regime='{regime}' for {pair} → {REGIME_PATH}")


def main():
    parser = argparse.ArgumentParser(description="HMM market regime detector")
    parser.add_argument("--pair", default="BTC/USDT:USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1h", help="Timeframe")
    parser.add_argument("--candles", type=int, default=500, help="Number of candles")
    parser.add_argument("--from-file", help="Load prices from CSV file instead of API")
    args = parser.parse_args()

    if args.from_file:
        prices = np.loadtxt(args.from_file, delimiter=",", usecols=4)
    else:
        prices = fetch_ohlcv(args.pair, args.timeframe, args.candles)

    regime = detect_regime(prices)
    print(f"[hmm_regime] Regime: {regime}")
    write_regime(regime, args.pair)


if __name__ == "__main__":
    main()
