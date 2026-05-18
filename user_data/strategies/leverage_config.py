"""
Centralized Leverage Configuration
"""

# Default global leverage
DEFAULT_LEVERAGE = 3.0

# Pair-specific leverage overrides
# Format: "PAIR": leverage_value
CUSTOM_LEVERAGE = {
    # Example:
    # "BTC/USDT:USDT": 5.0,
}


def get_leverage(pair: str) -> float:
    """
    Retrieve the leverage for a given pair.
    Returns the pair-specific leverage if defined, otherwise the default leverage.
    """
    return CUSTOM_LEVERAGE.get(pair, DEFAULT_LEVERAGE)
