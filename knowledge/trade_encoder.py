"""
Trade Encoder — encodes trade context into ChromaDB query strings.

Converts (pair, side, market_conditions, signal_type) → semantic search query
for finding similar historical setups in ChromaDB.
"""

from datetime import datetime, timezone


SIDE_TO_BIAS = {
    "long": "bullish long upward trend",
    "buy": "bullish long upward trend",
    "short": "bearish short downward trend",
    "sell": "bearish short downward trend",
}

CONDITION_MAP = {
    "trending": "strong trend momentum trending market",
    "ranging": "ranging sideways consolidation market",
    "volatile": "high volatility volatile market",
    "reversal": "reversal exhaustion bounce market",
    "breakout": "breakout expansion volatility market",
}


def encode_trade_query(
    pair: str = "",
    side: str = "long",
    market_condition: str = "",
    signal_type: str = "",
    strategy: str = "",
    indicators: dict = None,
) -> str:
    parts = []
    base = pair.split("/")[0] if pair else "crypto"
    parts.append(f"{base}")

    bias = SIDE_TO_BIAS.get(side.lower(), "")
    if bias:
        parts.append(bias)

    if market_condition:
        cond = CONDITION_MAP.get(market_condition.lower(), market_condition)
        parts.append(cond)

    if signal_type:
        parts.append(signal_type)

    if strategy:
        strategy_clean = strategy.replace("_", " ").replace("-", " ")
        parts.append(strategy_clean)

    if indicators:
        for key, val in indicators.items():
            if isinstance(val, (int, float)):
                parts.append(f"{key} {val}")

    return " ".join(parts)


def encode_trade_outcome(
    pair: str,
    side: str,
    pnl: float,
    r_multiple: float,
    setup_name: str = "",
    market_condition: str = "",
    strategy: str = "",
) -> dict:
    return {
        "pair": pair,
        "side": side,
        "pnl": round(pnl, 2),
        "r_multiple": round(r_multiple, 2),
        "setup_name": setup_name,
        "market_condition": market_condition or "",
        "strategy": strategy,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
