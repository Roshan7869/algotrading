#!/usr/bin/env python3
"""
Dynamic Leverage Controller

Rules:
1. Base leverage = 2x
2. Increase to 3x if: profit > 2% + trend_confirmed + volume_ok
3. Increase to 5x if: profit > 5% + strong_momentum + sentiment_positive
4. Decrease to 1x if: drawdown > 3% OR market_regime == "ranging"
5. Emergency: close if drawdown > 6%

Called by strategy before each trade.
Karpathy: single file, pure Python, zero dependencies beyond stdlib.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Default path inside Docker; override via env for local dev
SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", "/freqtrade/shared_config"))
SIGNAL_PATH = SHARED_DIR / "leverage_signal.json"


@dataclass(frozen=True)
class LeverageSignal:
    leverage: float
    reason: str
    confidence: float
    timestamp: str


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_market_regime() -> str:
    try:
        data = json.loads((SHARED_DIR / "market_regime.json").read_text())
        return data.get("regime", "ranging")
    except Exception:
        return "ranging"


def load_sentiment() -> float:
    try:
        data = json.loads((SHARED_DIR / "sentiment_signal.json").read_text())
        return float(data.get("sentiment_score", 0.0))
    except Exception:
        return 0.0


def calculate_leverage(
    current_profit_pct: float,
    drawdown_pct: float,
    trend_score: float,
    volume_ratio: float,
) -> LeverageSignal:
    sentiment = load_sentiment()
    regime = load_market_regime()

    # Emergency exit
    if drawdown_pct > 6.0:
        return LeverageSignal(0.0, "emergency_close_drawdown_6pct", 1.0, now())

    # Risk-off
    if drawdown_pct > 3.0 or regime == "ranging":
        return LeverageSignal(1.0, f"drawdown_or_{regime}", 0.9, now())

    # Base
    leverage = 2.0
    reasons = ["base_2x"]
    confidence = 0.5

    # Increase 1: small profit + trend + volume
    if current_profit_pct > 2.0 and trend_score > 0.3 and volume_ratio > 1.2:
        leverage = 3.0
        reasons.append("profit_2pct_trend_confirmed")
        confidence = 0.7

    # Increase 2: strong profit + momentum + sentiment
    if current_profit_pct > 5.0 and trend_score > 0.6 and sentiment > 0.5:
        leverage = 5.0
        reasons.append("profit_5pct_momentum_sentiment")
        confidence = 0.85

    return LeverageSignal(leverage, " | ".join(reasons), confidence, now())


def write_signal(signal: LeverageSignal):
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.write_text(json.dumps({
        "timestamp": signal.timestamp,
        "leverage": signal.leverage,
        "reason": signal.reason,
        "confidence": signal.confidence,
    }, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Dynamic Leverage Calculator")
    parser.add_argument("--profit", type=float, default=0.0, help="Current profit %")
    parser.add_argument("--drawdown", type=float, default=0.0, help="Current drawdown %")
    parser.add_argument("--trend", type=float, default=0.0, help="Trend score -1 to 1")
    parser.add_argument("--volume", type=float, default=1.0, help="Volume ratio")
    args = parser.parse_args()

    sig = calculate_leverage(args.profit, args.drawdown, args.trend, args.volume)
    write_signal(sig)
    print(f"Leverage: {sig.leverage}x | {sig.reason} | confidence: {sig.confidence}")
