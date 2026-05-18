import json
import zipfile
import pandas as pd
from datetime import datetime
import glob
import os


def load_backtest_data():
    # Find the specific backtest file based on timestamp provided in context
    # user_data/backtest_results/backtest-result-2026-02-03_10-37-12.zip

    file_path = "user_data/backtest_results/backtest-result-2026-02-03_10-37-12.zip"

    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return None

    with zipfile.ZipFile(file_path, "r") as z:
        # Usually there's a file named similar to the zip but .json
        # or just extract the first json file found
        json_files = [f for f in z.namelist() if f.endswith(".json")]
        if not json_files:
            print("No JSON found in zip")
            return None

        with z.open(json_files[0]) as f:
            data = json.load(f)
            return data


def analyze_trades(data):
    if not data or "strategy" not in data:
        print("Invalid data format")
        return

    # Use the first strategy found (usually only one)
    strat_name = list(data["strategy"].keys())[0]
    results = data["strategy"][strat_name]
    trades = results["trades"]

    df = pd.DataFrame(trades)

    if df.empty:
        print("No trades found")
        return

    # Metrics
    total_trades = len(df)
    total_profit_abs = df["profit_abs"].sum()
    total_profit_pct = (df["profit_ratio"] * 100).sum()  # Sum of percentages
    avg_profit_pct = (df["profit_ratio"] * 100).mean()
    win_rate = len(df[df["profit_ratio"] > 0]) / total_trades * 100

    max_drawdown_abs = results.get("max_drawdown_abs", 0)
    max_drawdown_pct = results.get("max_drawdown", 0) * 100

    print(f"=== Performance Summary ===")
    print(f"Strategy: {strat_name}")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Total Profit: {total_profit_abs:.2f} USDT")
    print(f"Avg Profit per Trade: {avg_profit_pct:.2f}%")
    print(f"Max Drawdown: {max_drawdown_pct:.2f}%")
    print(f"\n")

    print(f"=== Best Trades ===")
    best = df.nlargest(5, "profit_ratio")
    for _, row in best.iterrows():
        print(
            f"{row['pair']} | Profit: {row['profit_ratio'] * 100:.2f}% | Abs: {row['profit_abs']:.2f}"
        )

    print(f"\n=== Worst Trades ===")
    worst = df.nsmallest(5, "profit_ratio")
    for _, row in worst.iterrows():
        print(
            f"{row['pair']} | Profit: {row['profit_ratio'] * 100:.2f}% | Abs: {row['profit_abs']:.2f}"
        )

    print(f"\n=== Pair Performance ===")
    pair_stats = (
        df.groupby("pair")
        .agg({"profit_abs": "sum", "profit_ratio": "mean", "pair": "count"})
        .rename(columns={"pair": "count"})
        .sort_values("profit_abs", ascending=False)
    )

    # Convert mean profit ratio to percentage for display
    pair_stats["avg_profit_pct"] = pair_stats["profit_ratio"] * 100
    print(pair_stats[["count", "profit_abs", "avg_profit_pct"]].head(10))


if __name__ == "__main__":
    data = load_backtest_data()
    analyze_trades(data)
