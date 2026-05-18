import zipfile
import json
import glob
import os
import collections

# Find latest backtest result
list_of_files = glob.glob("user_data/backtest_results/backtest-result-*.zip")
if not list_of_files:
    print("No backtest results found.")
    exit()

latest_file = max(list_of_files, key=os.path.getctime)

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
    strategies = data.get("strategy", {})
    if not strategies:
        print("No strategy data found.")
        exit()

    output_lines = []

    for strategy_name, strategy_data in strategies.items():
        output_lines.append(f"# Trade Performance Analysis: {strategy_name}")
        trades = strategy_data.get("trades", [])

        if not trades:
            output_lines.append("No trades found.")
            continue

        # --- Statistics Calculation ---
        total_trades = len(trades)
        wins = 0
        losses = 0
        total_profit_abs = 0.0
        exit_reasons = collections.defaultdict(int)

        for trade in trades:
            profit_abs = trade["profit_abs"]
            total_profit_abs += profit_abs
            if profit_abs > 0:
                wins += 1
            else:
                losses += 1

            exit_reasons[trade["exit_reason"]] += 1

        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        avg_profit = (total_profit_abs / total_trades) if total_trades > 0 else 0

        # --- Table 1: Performance Matrix ---
        output_lines.append("\n## Performance Matrix")
        output_lines.append("| Metric | Value |")
        output_lines.append("| :--- | :--- |")
        output_lines.append(f"| Total Trades | {total_trades} |")
        output_lines.append(
            f"| Win Rate | {win_rate:.2f}% ({wins} Wins / {losses} Losses) |"
        )
        output_lines.append(f"| Total Profit | {total_profit_abs:.2f} USDT |")
        output_lines.append(f"| Avg Profit per Trade | {avg_profit:.2f} USDT |")

        # --- Table 2: Exit Reason Breakdown ---
        output_lines.append("\n## Exit Reasons Breakdown")
        output_lines.append("| Exit Reason | Count | Percentage |")
        output_lines.append("| :--- | :--- | :--- |")

        for reason, count in sorted(
            exit_reasons.items(), key=lambda x: x[1], reverse=True
        ):
            percentage = (count / total_trades) * 100
            readable_reason = reason.replace("_", " ").capitalize()
            output_lines.append(f"| {readable_reason} | {count} | {percentage:.2f}% |")

        # --- Table 3: Detailed Trade List ---
        output_lines.append("\n## Detailed Trade List")
        output_lines.append(
            "| Pair | Open Time | Close Time | Profit % | Profit USDT | Exit Reason |"
        )
        output_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

        for trade in trades:
            pair = trade["pair"]
            open_time = trade["open_date"].split(".")[
                0
            ]  # Remove milliseconds if present
            close_time = trade["close_date"].split(".")[0]
            profit_ratio = trade["profit_ratio"]
            profit_abs = trade["profit_abs"]
            exit_reason = trade["exit_reason"]

            output_lines.append(
                f"| {pair} | {open_time} | {close_time} | {profit_ratio * 100:.2f}% | {profit_abs:.2f} | {exit_reason} |"
            )

    # Write to file
    with open("trade_analysis_report.md", "w") as f:
        f.write("\n".join(output_lines))

    print("Analysis written to trade_analysis_report.md")

except Exception as e:
    print(f"Error analyzing trades: {e}")
