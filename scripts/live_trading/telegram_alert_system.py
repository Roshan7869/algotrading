"""
Telegram Alert System for Live Trading
Sends real-time entry/exit alerts to Telegram bot.
"""

import os
import sys
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

try:
    import telegram
    from telegram import Bot
except ImportError:
    print("⚠️ python-telegram-bot not installed. Run: pip install python-telegram-bot")
    sys.exit(1)


class TradingAlertBot:
    """
    Telegram bot for sending trading alerts.

    Usage:
        bot = TradingAlertBot()  # Reads TELEGRAM_TOKEN and TELEGRAM_CHAT_ID from .env
        bot.send_entry_alert("RENDER/USDT:USDT", "short", 2.45, "Aroon+MACD bearish cross")
    """

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        token = token or os.getenv("TELEGRAM_TOKEN")
        chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise ValueError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        """
        Initialize Telegram bot.

        Args:
            token: Telegram bot token from @BotFather
            chat_id: Your Telegram chat ID
        """
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    def send_entry_alert(
        self,
        pair: str,
        side: str,
        price: float,
        reason: str,
        additional_info: Optional[dict] = None,
    ):
        """
        Send entry signal alert.

        Args:
            pair: Trading pair (e.g., "RENDER/USDT:USDT")
            side: "long" or "short"
            price: Entry price
            reason: Entry reason/tag
            additional_info: Optional dict with extra data (aroon, macd, etc.)
        """
        emoji = "🟢" if side.lower() == "long" else "🔴"
        side_upper = side.upper()

        message = f"""
{emoji} **{side_upper} ENTRY SIGNAL**

**Pair:** {pair}
**Side:** {side_upper}
**Entry Price:** ${price:.4f}
**Reason:** {reason}
**Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        if additional_info:
            message += "\n**Indicators:**\n"
            for key, value in additional_info.items():
                message += f"- {key}: {value}\n"

        message += f"\n📊 Execute: `/force{side} {pair}`"

        try:
            self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode="Markdown"
            )
            print(f"✅ Entry alert sent for {pair} {side}")
        except Exception as e:
            print(f"❌ Failed to send entry alert: {e}")

    def send_exit_alert(
        self,
        pair: str,
        exit_price: float,
        pnl_pct: float,
        reason: str,
        entry_price: Optional[float] = None,
    ):
        """
        Send exit signal alert.

        Args:
            pair: Trading pair
            exit_price: Exit price
            pnl_pct: Profit/loss percentage
            reason: Exit reason
            entry_price: Optional entry price for reference
        """
        emoji = "🟢" if pnl_pct > 0 else "🔴"

        message = f"""
{emoji} **EXIT SIGNAL**

**Pair:** {pair}
**Exit Price:** ${exit_price:.4f}
**P&L:** {pnl_pct:+.2f}%
**Reason:** {reason}
**Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        if entry_price:
            message += f"\n**Entry Price:** ${entry_price:.4f}"

        try:
            self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode="Markdown"
            )
            print(f"✅ Exit alert sent for {pair}")
        except Exception as e:
            print(f"❌ Failed to send exit alert: {e}")

    def send_portfolio_update(
        self, balance: float, open_trades: int, daily_pnl: float, total_pnl_pct: float
    ):
        """
        Send daily portfolio summary.

        Args:
            balance: Current balance
            open_trades: Number of open trades
            daily_pnl: Daily P&L in USDT
            total_pnl_pct: Total P&L percentage
        """
        emoji = "📈" if daily_pnl > 0 else "📉"

        message = f"""
{emoji} **DAILY PORTFOLIO UPDATE**

**Balance:** ${balance:.2f} USDT
**Open Trades:** {open_trades}
**Daily P&L:** ${daily_pnl:+.2f} USDT
**Total P&L:** {total_pnl_pct:+.2f}%
**Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        try:
            self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode="Markdown"
            )
            print("✅ Portfolio update sent")
        except Exception as e:
            print(f"❌ Failed to send portfolio update: {e}")

    def send_emergency_alert(self, message: str):
        """
        Send emergency alert (drawdown, errors, etc.).

        Args:
            message: Emergency message
        """
        alert = f"""
🚨 **EMERGENCY ALERT** 🚨

{message}

**Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        try:
            self.bot.send_message(
                chat_id=self.chat_id, text=alert, parse_mode="Markdown"
            )
            print("🚨 Emergency alert sent")
        except Exception as e:
            print(f"❌ Failed to send emergency alert: {e}")

    def test_connection(self):
        """Test bot connection."""
        try:
            bot_info = self.bot.get_me()
            message = f"""
✅ **Telegram Bot Connected**

**Bot Name:** {bot_info.first_name}
**Username:** @{bot_info.username}
**Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

🚀 Live trading alerts are now active!
"""
            self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode="Markdown"
            )
            print(f"✅ Bot connected: @{bot_info.username}")
            return True
        except Exception as e:
            print(f"❌ Bot connection failed: {e}")
            return False


def main():
    """Test the Telegram alert system."""
    import argparse

    parser = argparse.ArgumentParser(description="Telegram Alert System Test")
    parser.add_argument(
        "--token", help="Telegram bot token", default=os.getenv("TELEGRAM_TOKEN")
    )
    parser.add_argument(
        "--chat-id", help="Telegram chat ID", default=os.getenv("TELEGRAM_CHAT_ID")
    )
    parser.add_argument("--test", action="store_true", help="Send test messages")

    args = parser.parse_args()

    if not args.token or not args.chat_id:
        print("❌ Error: Telegram token and chat_id required")
        print(
            "Usage: python telegram_alert_system.py --token YOUR_TOKEN --chat-id YOUR_CHAT_ID --test"
        )
        sys.exit(1)

    # Initialize bot
    bot = TradingAlertBot(token=args.token, chat_id=args.chat_id)

    # Test connection
    if not bot.test_connection():
        sys.exit(1)

    if args.test:
        print("\n📤 Sending test alerts...")

        # Test entry alert
        bot.send_entry_alert(
            pair="RENDER/USDT:USDT",
            side="short",
            price=2.45,
            reason="Aroon+MACD bearish cross + 4H trend down",
            additional_info={
                "Aroon Down": "85.7",
                "MACD": "-0.0234",
                "ATR Expanding": "✅",
                "BTC Safe": "✅",
            },
        )

        # Test exit alert
        bot.send_exit_alert(
            pair="DOGE/USDT:USDT",
            exit_price=0.1234,
            pnl_pct=12.5,
            reason="short_profit_rr_3.0",
            entry_price=0.1095,
        )

        # Test portfolio update
        bot.send_portfolio_update(
            balance=1250.00, open_trades=3, daily_pnl=45.50, total_pnl_pct=25.0
        )

        print("\n✅ Test alerts sent successfully!")


if __name__ == "__main__":
    main()
