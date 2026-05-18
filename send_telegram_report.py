import sys
import requests
import json
import os

CONFIG_PATH = "user_data/config_live_trading_6x.json"
REPORT_FILE = "last_trades_report.txt"


def main():
    if not os.path.exists(CONFIG_PATH):
        print(f"Config not found: {CONFIG_PATH}")
        return

    # Load config for credentials
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    token = config["telegram"]["token"]
    chat_id = config["telegram"]["chat_id"]

    if not os.path.exists(REPORT_FILE):
        report = "No report file generated."
    else:
        # Read report
        with open(REPORT_FILE, "r") as f:
            report = f.read()

    if not report.strip():
        report = "No trades found in the last 24 hours."

    # Send message
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram limit is 4096. If report is too long, truncate.
    if len(report) > 3000:
        report = report[:3000] + "\n... (truncated)"

    message_text = f"📊 **Backtest Report (Last 24h)**\n\n```\n{report}\n```"

    payload = {"chat_id": chat_id, "text": message_text, "parse_mode": "Markdown"}

    print(f"Sending report to Chat ID: {chat_id}...")
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        print("Success! Message sent.")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")
        # Try without markdown if it fails (sometimes special chars break it)
        try:
            payload["parse_mode"] = ""  # Plain text
            requests.post(url, json=payload)
            print("Sent as plain text fallback.")
        except:
            pass


if __name__ == "__main__":
    main()
