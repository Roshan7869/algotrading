import json
import requests

# Load config
with open("user_data/config_live_trading_6x.json", "r") as f:
    config = json.load(f)

token = config["telegram"]["token"]
chat_id = config["telegram"]["chat_id"]

# Backtest results message
message = """
🎯 7-DAY BACKTEST RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 PERFORMANCE SUMMARY
• Total Trades: 36
• Win Rate: 94.4% (34 wins, 2 losses)
• Total Profit: +29.83% (+298.29 USDT)
• Avg Profit/Trade: 3.91%
• Avg Duration: 4h 43m

💰 CAPITAL GROWTH
• Starting Balance: 1,000 USDT
• Final Balance: 1,298.29 USDT
• Absolute Profit: +298.29 USDT
• Daily Avg Profit: 42.61 USDT

🏆 TOP PERFORMERS
• Best Trade: RENDER/USDT +13.44%
• Best Pair: RENDER/USDT +5.73%
• Best Day: +141.00 USDT

⚠️ RISK ANALYSIS
• Max Drawdown: 10.12% (103.49 USDT)
• Worst Trade: AVAX/USDT -25.63%
• Worst Pair: XMR/USDT -5.19%
• Worst Day: -80.81 USDT
• Stop Loss Hits: 2 trades

📈 ADVANCED METRICS
• Sharpe Ratio: 51.42 (Excellent)
• Sortino: 7279.13
• Profit Factor: 3.88
• SQN: 3.10 (Good)

⚡ EXIT BREAKDOWN
• Trailing Stop: 32 trades (100% win)
• Profit Target (3.5R): 1 trade (100% win)
• ROI Exit: 1 trade (100% win)
• Stop Loss: 2 trades (losses)

🎯 STRATEGY VALIDATION
The strategy demonstrated strong performance with 94.4% win rate. The 2 losses were controlled stop-loss exits, validating the risk management system. Trailing stops captured most profits effectively.

✅ System Status: LIVE & SCANNING 29 PAIRS
"""

# Send via Telegram API
url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = {"chat_id": chat_id, "text": message}

try:
    response = requests.post(url, json=payload)
    response.raise_for_status()
    print("Backtest results sent to Telegram successfully!")
except Exception as e:
    print(f"Error sending to Telegram: {e}")
