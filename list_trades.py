import zipfile
import json
import glob
import os
import datetime

# Find latest backtest result
list_of_files = glob.glob("user_data/backtest_results/backtest-result-*.zip")
if not list_of_files:
    print("No backtest results found.")
    exit()

latest_file = max(list_of_files, key=os.path.getctime)
print(f"Reading results from: {latest_file}")

try:
    with zipfile.ZipFile(latest_file, "r") as z:
        # Find the json file inside
        json_files = [
            f
            for f in z.namelist()
            if f.endswith(".json") and not f.endswith("meta.json")
        ]
        if not json_files:
            print("No JSON result file found in zip.")
            exit()

        with z.open(json_files[0]) as f:
            data = json.load(f)

    # Extract trades
    # Structure: data['strategy'][strategy_name]['trades']
    strategies = data.get("strategy", {})
    if not strategies:
        print("No strategy data found.")
        exit()

    with open("trades_list_72h.txt", "w") as out_f:
        for strategy_name, strategy_data in strategies.items():
            out_f.write(f"\nStrategy: {strategy_name}\n")
            trades = strategy_data.get("trades", [])

            if not trades:
                out_f.write("No trades found.\n")
                continue

            out_f.write(
                f"{'Pair':<15} {'Open Time':<20} {'Close Time':<20} {'Profit %':<10} {'Profit USDT':<12} {'Exit Reason':<15}\n"
            )
            out_f.write("-" * 95 + "\n")

            for trade in trades:
                pair = trade["pair"]
                open_time = trade["open_date"]
                close_time = trade["close_date"]
                profit_ratio = trade["profit_ratio"]
                profit_abs = trade["profit_abs"]
                exit_reason = trade["exit_reason"]

                out_f.write(
                    f"{pair:<15} {open_time:<20} {close_time:<20} {profit_ratio * 100:>8.2f}% {profit_abs:>11.2f} {exit_reason:<15}\n"
                )

    print("Trades written to trades_list_72h.txt")

except Exception as e:
    print(f"Error reading backtest results: {e}")
