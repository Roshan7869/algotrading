#!/usr/bin/env python3
"""
Queue-Based Backtest System with Telegram Reporting
1. Download data for single token
2. Run backtest
3. Parse and Notify via Telegram
4. Delete data
5. Repeat
"""

import subprocess
import json
import os
import sys
import re
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

# Configuration
CONFIG_FILE = "user_data/config_backtest_300day_STANDARD.json"
KEYS_FILE = "user_data/config_live_analysis.json"
STRATEGY = "AroonMomentumEngine"
DAYS = 300
TIMEFRAMES = ["1h", "4h"]
DATA_DIR = "user_data/data/binance"
RESULTS_DIR = "user_data/backtest_results"

# Docker command template - Use existing container
DOCKER_CMD = "docker exec freqtrade freqtrade"


def get_telegram_creds():
    """Load Telegram creds from live config"""
    with open(KEYS_FILE, "r") as f:
        config = json.load(f)
    return config["telegram"]["token"], config["telegram"]["chat_id"]


def send_telegram(message):
    """Send message to Telegram via urllib"""
    try:
        token, chat_id = get_telegram_creds()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

        # Encode data
        data_encoded = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url, data=data_encoded, headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req) as response:
            pass  # Success

        print(f"📤 Sent Telegram Notification")
    except Exception as e:
        print(f"⚠️ Telegram Send Failed: {e}")


def load_token_list():
    """Load token whitelist from config"""
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    return config["exchange"]["pair_whitelist"]


def clear_data():
    """Remove all downloaded data"""
    print(f"🗑️  Clearing data directory: {DATA_DIR}")
    subprocess.run(f"rm -rf {DATA_DIR}/*", shell=True, check=False)


def download_data(token):
    """Download data for single token"""
    print(f"\n📥 Downloading {DAYS} days of data for {token}...")

    # Create single-token config
    temp_config = {
        "exchange": {"name": "binance", "pair_whitelist": [token]},
        "timeframe": "1h",
        "trading_mode": "futures",
        "margin_mode": "isolated",
    }

    temp_config_path = "user_data/temp_download_config.json"
    with open(temp_config_path, "w") as f:
        json.dump(temp_config, f, indent=2)

    timeframes_str = " ".join([f"-t {tf}" for tf in TIMEFRAMES])
    cmd = f"{DOCKER_CMD} download-data --config {temp_config_path} --days {DAYS} {timeframes_str} --trading-mode futures"

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    try:
        os.remove(temp_config_path)
    except FileNotFoundError:
        pass

    if result.returncode != 0:
        print(f"❌ Download failed for {token}")
        return False

    print(f"✅ Downloaded {token}")
    return True


def parse_results(output):
    """Extract metrics from output"""
    try:
        # Regex for Total Profit % (e.g., | 12.34% |)
        profit_match = re.search(r"Total profit %\s+\|\s+([\d\.\-]+)%", output)
        trades_match = re.search(r"Total trades\s+\|\s+(\d+)", output)

        profit = profit_match.group(1) if profit_match else "N/A"
        trades = trades_match.group(1) if trades_match else "0"
        return profit, trades
    except:
        return "N/A", "0"


def run_backtest(token):
    """Run backtest for single token"""
    print(f"\n🔬 Running backtest for {token}...")

    # Create single-token backtest config
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)

    config["exchange"]["pair_whitelist"] = [token]

    temp_config_path = "user_data/temp_backtest_config.json"
    with open(temp_config_path, "w") as f:
        json.dump(config, f, indent=2)

    # Calculate proper timerange
    end_date = datetime.now()
    start_date = end_date - timedelta(days=DAYS)
    timerange = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"

    cmd = f"{DOCKER_CMD} backtesting --config /freqtrade/{temp_config_path} --strategy {STRATEGY} --timeframe 1h --timerange {timerange}"

    print(f"🔍 DEBUG: Running command: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    # Preserve temp config for debugging
    # try:
    #     os.remove(temp_config_path)
    # except FileNotFoundError:
    #     pass

    if result.returncode != 0:
        print(f"❌ Backtest failed for {token}")
        print(result.stderr)
        return None

    print(f"✅ Backtest completed for {token}")
    return result.stdout


def save_results(token, output):
    """Save backtest results to file"""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{RESULTS_DIR}/{token.replace('/', '_')}_{timestamp}.txt"
    with open(filename, "w") as f:
        f.write(output)
    print(f"💾 Results saved: {filename}")
    return filename


def main():
    print("=" * 80)
    print("🚀 Queue-Based Backtest System v2.0")
    print("=" * 80)

    send_telegram(
        "🚀 **Starting Queue Backtest**\nStrategy: Hybrid Assistant\nRange: 300 Days\nCapital: 100 USDT"
    )

    tokens = load_token_list()
    total = len(tokens)
    summary_data = []

    # PHASE 1: Download all data first
    print(f"\n📥 PHASE 1: Downloading data for all {total} tokens...")
    print(f"⏳ Downloading {DAYS} days for {', '.join(TIMEFRAMES)} timeframes...")

    timeframes_str = " ".join([f"-t {tf}" for tf in TIMEFRAMES])
    cmd = f"{DOCKER_CMD} download-data --config {CONFIG_FILE} --days {DAYS} {timeframes_str} --trading-mode futures"

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print("❌ Batch download failed!")
        print(result.stderr)
        send_telegram("❌ Batch data download failed. Aborting.")
        return

    print("✅ Downloaded all token data successfully!")
    send_telegram(f"✅ Downloaded {total} tokens\n📊 Starting backtests...")

    # PHASE 2: Run backtests sequentially
    print(f"\n🔬 PHASE 2: Running backtests for {total} tokens...")
    for idx, token in enumerate(tokens, 1):
        print(f"\nProcessing {idx}/{total}: {token}")

        output = run_backtest(token)
        if output:
            save_results(token, output)
            profit, trades = parse_results(output)

            msg = (
                f"✅ **Backtest Result: {token}**\n"
                f"Profit: **{profit}%**\n"
                f"Trades: {trades}\n"
                f"Progress: {idx}/{total}"
            )
            print(msg)
            send_telegram(msg)
            summary_data.append((token, profit, trades))
        else:
            send_telegram(f"❌ Backtest Failed: {token}")

    # PHASE 3: Cleanup
    clear_data()

    # Final Summary
    summary_msg = "📊 **Final Backtest Summary**\n\n"
    for t, p, tr in summary_data:
        summary_msg += f"- **{t}**: {p}% ({tr} trades)\n"

    print(summary_msg)
    send_telegram(summary_msg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        clear_data()
        sys.exit(1)
