import os
import sys
import asyncio
import telegram
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("❌ Error: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not found in .env file")
    print("Please update your .env file with the new credentials")
    sys.exit(1)


async def test_telegram():
    print(f"Testing Telegram Bot...")
    print(f"Token: {TOKEN[:5]}...{TOKEN[-5:]}")
    print(f"Chat ID: {CHAT_ID}")

    try:
        bot = telegram.Bot(token=TOKEN)
        me = await bot.get_me()
        print(f"✅ Bot Connected: {me.username} (ID: {me.id})")

        print("Sending test message...")
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🔔 **Test Notification** from Algotrading Bot Verification Script",
        )
        print("✅ Message sent successfully!")

    except telegram.error.InvalidToken:
        print("❌ Error: Invalid Token")
    except telegram.error.Unauthorized:
        print(
            "❌ Error: Unauthorized (User might have blocked bot or hasn't started it)"
        )
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_telegram())
