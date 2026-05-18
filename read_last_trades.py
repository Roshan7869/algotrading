import zipfile
import json
import glob
import os
import sys

# Windows path handling
base_dir = "c:\\Users\\USER\\Desktop\\Algotrading\\user_data\\backtest_results"
search_pattern = os.path.join(base_dir, "backtest-result-*.zip")

files = glob.glob(search_pattern)
if not files:
    print("No backtest files found")
    sys.exit(1)

latest_file = max(files, key=os.path.getctime)
print(f"Reading: {latest_file}")

with zipfile.ZipFile(latest_file, "r") as z:
    # There is usually one json file inside with similar name
    json_filename = [f for f in z.namelist() if f.endswith(".json")][0]
    with z.open(json_filename) as f:
        data = json.load(f)

print("\n" + "=" * 80)
print(
    f"{'PAIR':<15} | {'ENTRY (UTC)':<20} | {'PRICE':<10} | {'EXIT':<20} | {'P&L %':<8} | {'REASON'}"
)
print("=" * 80)

trades_found = False
for strategy in data["strategy"]:
    trades = data["strategy"][strategy]["trades"]
    for trade in trades:
        trades_found = True
        pair = trade["pair"]
        entry_time = trade["open_date"].replace("T", " ")
        entry_price = round(trade["open_rate"], 5)
        exit_time = trade["close_date"].replace("T", " ")
        exit_price = round(trade["close_rate"], 5)
        pnl = trade["profit_ratio"]
        reason = trade["exit_reason"]

        color = ""  # No color in pure text, but format helps
        pnl_str = f"{pnl:.2%}"

        print(
            f"{pair:<15} | {entry_time:<20} | {entry_price:<10} | {exit_time:<20} | {pnl_str:<8} | {reason}"
        )

if (
    non_trades := data.get("strategy", {})
    .get(list(data["strategy"].keys())[0], {})
    .get("total_trades", 0)
    == 0
):
    print("No trades found in the latest backtest.")
