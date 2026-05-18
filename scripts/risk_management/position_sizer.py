"""
Dynamic Position Sizer
Implements inverse volatility weighting for optimal capital allocation.
"""

import numpy as np
import pandas as pd
from typing import Dict, List
from datetime import datetime, timedelta


class PositionSizer:
    """
    Calculate position sizes based on inverse volatility weighting.

    Concept: Allocate MORE capital to LOW volatility pairs (stable bleeders like RENDER)
             and LESS capital to HIGH volatility pairs (like PEPE).
    """

    def __init__(self, total_capital: float, max_positions: int = 5):
        """
        Initialize position sizer.

        Args:
            total_capital: Total available capital
            max_positions: Maximum number of open positions
        """
        self.total_capital = total_capital
        self.max_positions = max_positions
        self.volatility_cache = {}  # Cache ATR values

    def calculate_position_size(
        self,
        pair: str,
        atr_value: float,
        all_pair_atrs: Dict[str, float],
        base_stake: float,
    ) -> float:
        """
        Calculate position size using inverse volatility weighting.

        Args:
            pair: Trading pair
            atr_value: ATR value for this pair
            all_pair_atrs: Dict of all pairs and their ATR values
            base_stake: Base stake amount from config

        Returns:
            Adjusted stake amount
        """
        if atr_value <= 0 or not all_pair_atrs:
            return base_stake

        # Calculate inverse volatility
        inverse_vol = 1 / atr_value

        # Calculate normalization factor (sum of all inverse volatilities)
        total_inverse_vol = sum([1 / atr for atr in all_pair_atrs.values() if atr > 0])

        if total_inverse_vol == 0:
            return base_stake

        # Calculate weight for this pair
        weight = inverse_vol / total_inverse_vol

        # Calculate position size
        # Total capital divided by max positions, then weighted
        position_size = (
            (self.total_capital / self.max_positions) * weight * self.max_positions
        )

        return position_size

    def get_allocation_weights(self, pair_atrs: Dict[str, float]) -> Dict[str, float]:
        """
        Get allocation weights for all pairs.

        Args:
            pair_atrs: Dict of pair -> ATR value

        Returns:
            Dict of pair -> allocation percentage
        """
        if not pair_atrs:
            return {}

        # Calculate inverse volatilities
        inverse_vols = {pair: 1 / atr for pair, atr in pair_atrs.items() if atr > 0}

        total_inverse_vol = sum(inverse_vols.values())

        if total_inverse_vol == 0:
            # Equal weight if no valid ATR data
            equal_weight = 1.0 / len(pair_atrs)
            return {pair: equal_weight for pair in pair_atrs.keys()}

        # Calculate weights
        weights = {
            pair: inv_vol / total_inverse_vol for pair, inv_vol in inverse_vols.items()
        }

        return weights


def example_allocation():
    """
    Example: Show how allocation works for our watchlist.
    """
    print("\n📊 Dynamic Position Sizing Example\n")

    # Example ATR values (from recent data)
    # Lower ATR = more stable = higher allocation
    pair_atrs = {
        "RENDER/USDT:USDT": 0.05,  # Low volatility (stable bleeder)
        "DOGE/USDT:USDT": 0.08,  # Medium volatility
        "1000PEPE/USDT:USDT": 0.15,  # High volatility (meme coin)
        "XRP/USDT:USDT": 0.06,  # Low-medium volatility
        "ENA/USDT:USDT": 0.10,  # Medium volatility
        "TON/USDT:USDT": 0.07,  # Medium volatility
    }

    total_capital = 1000.0
    sizer = PositionSizer(total_capital=total_capital, max_positions=5)

    # Get allocation weights
    weights = sizer.get_allocation_weights(pair_atrs)

    print(f"Total Capital: ${total_capital:.2f}")
    print(f"Max Positions: {sizer.max_positions}\n")
    print("Allocation Breakdown:")
    print("-" * 60)

    # Sort by allocation (highest first)
    sorted_pairs = sorted(weights.items(), key=lambda x: x[1], reverse=True)

    for pair, weight in sorted_pairs:
        atr = pair_atrs[pair]
        allocation = total_capital * weight
        token = pair.split("/")[0]

        print(
            f"{token:12} | ATR: {atr:.3f} | Weight: {weight * 100:5.1f}% | Allocation: ${allocation:6.2f}"
        )

    print("-" * 60)
    print(
        f"{'TOTAL':12} |           | Weight: {sum(weights.values()) * 100:5.1f}% | Allocation: ${sum([total_capital * w for w in weights.values()]):6.2f}"
    )

    print("\n💡 Insight:")
    print("- RENDER gets highest allocation (lowest volatility)")
    print("- PEPE gets lowest allocation (highest volatility)")
    print("- This reduces risk while maintaining exposure")


def main():
    """Main entry point."""
    example_allocation()


if __name__ == "__main__":
    main()
