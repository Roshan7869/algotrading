"""
Portfolio Monitor - Risk Management System
Monitors drawdown, position sizes, and triggers emergency stops.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from scripts.live_trading.telegram_alert_system import TradingAlertBot
except ImportError:
    print("❌ Error: telegram_alert_system.py not found")
    sys.exit(1)


# Risk Management Configuration
MAX_DRAWDOWN = 0.40  # 40% max drawdown (kill switch)
MAX_OPEN_TRADES = 5
MAX_ALLOCATION_PER_PAIR = 0.30  # 30% max per pair
WARNING_DRAWDOWN = 0.25  # 25% warning threshold


class PortfolioMonitor:
    """
    Monitor portfolio health and enforce risk limits.
    """

    def __init__(
        self, initial_balance: float, telegram_bot: Optional[TradingAlertBot] = None
    ):
        """
        Initialize portfolio monitor.

        Args:
            initial_balance: Starting balance in USDT
            telegram_bot: Optional TradingAlertBot for alerts
        """
        self.initial_balance = initial_balance
        self.peak_balance = initial_balance
        self.telegram_bot = telegram_bot
        self.emergency_stop_triggered = False

    def check_portfolio_health(
        self, current_balance: float, open_trades: List[Dict]
    ) -> Dict[str, any]:
        """
        Check portfolio health and return status.

        Args:
            current_balance: Current balance in USDT
            open_trades: List of open trade dicts

        Returns:
            dict with health status and metrics
        """
        # Update peak balance
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance

        # Calculate drawdown
        current_dd = (self.peak_balance - current_balance) / self.peak_balance

        # Calculate total P&L
        total_pnl_pct = (
            (current_balance - self.initial_balance) / self.initial_balance
        ) * 100

        # Check position concentration
        position_sizes = {}
        for trade in open_trades:
            pair = trade.get("pair", "UNKNOWN")
            stake = trade.get("stake_amount", 0)
            position_sizes[pair] = position_sizes.get(pair, 0) + stake

        max_position_pct = max(
            [(size / current_balance) for size in position_sizes.values()], default=0
        )

        # Determine health status
        health_status = "HEALTHY"
        warnings = []

        if current_dd >= MAX_DRAWDOWN:
            health_status = "EMERGENCY"
            warnings.append(f"🚨 DRAWDOWN LIMIT BREACHED: {current_dd * 100:.1f}%")
            self._trigger_emergency_stop(current_dd)

        elif current_dd >= WARNING_DRAWDOWN:
            health_status = "WARNING"
            warnings.append(f"⚠️ High drawdown: {current_dd * 100:.1f}%")

        if len(open_trades) > MAX_OPEN_TRADES:
            health_status = "WARNING"
            warnings.append(f"⚠️ Too many open trades: {len(open_trades)}")

        if max_position_pct > MAX_ALLOCATION_PER_PAIR:
            health_status = "WARNING"
            warnings.append(
                f"⚠️ Position too concentrated: {max_position_pct * 100:.1f}%"
            )

        # Send alerts if needed
        if warnings and self.telegram_bot:
            self.telegram_bot.send_emergency_alert("\\n".join(warnings))

        return {
            "status": health_status,
            "current_balance": current_balance,
            "peak_balance": self.peak_balance,
            "drawdown_pct": current_dd * 100,
            "total_pnl_pct": total_pnl_pct,
            "open_trades": len(open_trades),
            "max_position_pct": max_position_pct * 100,
            "warnings": warnings,
            "emergency_stop": self.emergency_stop_triggered,
        }

    def _trigger_emergency_stop(self, drawdown: float):
        """
        Trigger emergency stop.

        Args:
            drawdown: Current drawdown percentage
        """
        if self.emergency_stop_triggered:
            return

        self.emergency_stop_triggered = True

        message = f"""
🚨 **EMERGENCY STOP TRIGGERED** 🚨

**Drawdown:** {drawdown * 100:.1f}%
**Limit:** {MAX_DRAWDOWN * 100:.1f}%

**Action Required:**
1. All positions will be closed
2. Trading will be halted
3. Manual review required before restart

**Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        print(message)

        if self.telegram_bot:
            self.telegram_bot.send_emergency_alert(message)

        # In production, this would call close_all_positions()
        print("⚠️ In production: Would close all positions now")

    def validate_position_size(
        self,
        pair: str,
        proposed_stake: float,
        current_balance: float,
        existing_positions: Dict[str, float],
    ) -> float:
        """
        Validate and adjust position size if needed.

        Args:
            pair: Trading pair
            proposed_stake: Proposed stake amount
            current_balance: Current balance
            existing_positions: Dict of pair -> stake amount

        Returns:
            Adjusted stake amount
        """
        # Check if emergency stop is active
        if self.emergency_stop_triggered:
            print(f"❌ Emergency stop active - blocking new position for {pair}")
            return 0

        # Calculate total exposure for this pair
        current_exposure = existing_positions.get(pair, 0)
        total_exposure = current_exposure + proposed_stake

        # Check concentration limit
        max_allowed = current_balance * MAX_ALLOCATION_PER_PAIR

        if total_exposure > max_allowed:
            adjusted_stake = max(0, max_allowed - current_exposure)
            print(
                f"⚠️ Position size reduced for {pair}: ${proposed_stake:.2f} -> ${adjusted_stake:.2f}"
            )
            return adjusted_stake

        return proposed_stake


def simulate_drawdown_test():
    """Test emergency stop with simulated drawdown."""
    print("\n🧪 Testing Emergency Stop System\n")

    monitor = PortfolioMonitor(initial_balance=1000.0)

    # Simulate declining balance
    test_scenarios = [
        (1000, "Initial balance"),
        (900, "10% drawdown"),
        (750, "25% drawdown - WARNING"),
        (600, "40% drawdown - EMERGENCY"),
        (550, "45% drawdown - Already stopped"),
    ]

    for balance, description in test_scenarios:
        print(f"\n📊 Scenario: {description}")
        health = monitor.check_portfolio_health(current_balance=balance, open_trades=[])

        print(f"Status: {health['status']}")
        print(f"Drawdown: {health['drawdown_pct']:.1f}%")
        print(f"Emergency Stop: {health['emergency_stop']}")

        if health["warnings"]:
            for warning in health["warnings"]:
                print(warning)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Portfolio Monitor")
    parser.add_argument("--simulate-dd", type=float, help="Simulate drawdown (0.0-1.0)")
    parser.add_argument("--test", action="store_true", help="Run test scenarios")

    args = parser.parse_args()

    if args.test:
        simulate_drawdown_test()
    elif args.simulate_dd is not None:
        monitor = PortfolioMonitor(initial_balance=1000.0)
        simulated_balance = 1000.0 * (1 - args.simulate_dd)

        health = monitor.check_portfolio_health(
            current_balance=simulated_balance, open_trades=[]
        )

        print(f"\n📊 Simulated Drawdown: {args.simulate_dd * 100:.1f}%")
        print(f"Status: {health['status']}")
        print(f"Emergency Stop: {health['emergency_stop']}")
    else:
        print("Usage: python portfolio_monitor.py --test")
        print("   or: python portfolio_monitor.py --simulate-dd 0.45")


if __name__ == "__main__":
    main()
