#!/usr/bin/env python3
"""
Generate Freqtrade strategy stubs from vector DB search results.

Usage:
  python3 strategy_db/to_config.py "mean reversion" --output user_data/strategies/
  python3 strategy_db/to_config.py "breakout" --top-k 1 --print
"""

import argparse
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search import search


STRATEGY_TEMPLATE = '''# Strategy generated from knowledge base: "{setup_name}"
# Source: {channel_name} — {video_title}
# Keywords: {keywords}

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
import pandas as pd


class AutoGenStrategy(IStrategy):
    """
    Auto-generated strategy stub based on: {setup_name}
    Type: {setup_type} | Condition: {market_condition} | Timeframe: {timeframe}

    {chunk_text_short}
    """

    timeframe = "{timeframe_clean}"

    minimal_roi = {{
        "0": 0.10,
        "30": 0.05,
        "60": 0.02,
        "120": 0,
    }}

    stoploss = -0.02

    trailing_stop = False

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[:, "exit_long"] = 0
        dataframe.loc[:, "exit_short"] = 0
        return dataframe
'''


def safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip().replace(" ", "_")


def main():
    parser = argparse.ArgumentParser(description="Generate Freqtrade strategy stubs from knowledge base")
    parser.add_argument("query", help="Natural language query for strategy ideas")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--setup-type")
    parser.add_argument("--keyword")
    parser.add_argument("--output", default="user_data/strategies", help="Output directory for .py files")
    parser.add_argument("--print", action="store_true", help="Print to stdout instead of writing files")
    args = parser.parse_args()

    results = search(
        query=args.query,
        top_k=args.top_k,
        setup_type=args.setup_type,
        keyword=args.keyword,
    )

    if not results:
        print("No strategies found for query.")
        return

    for r in results:
        tf = r.get("timeframe", "5m")
        if "intraday" in tf.lower():
            tf_clean = "5m"
        elif "daily" in tf.lower():
            tf_clean = "1d"
        else:
            tf_clean = "5m"

        content = STRATEGY_TEMPLATE.format(
            setup_name=r["setup_name"],
            channel_name=r.get("channel_name", "unknown"),
            video_title=r.get("video_title", "unknown"),
            keywords=r.get("keywords", ""),
            setup_type=r.get("setup_type", ""),
            market_condition=r.get("market_condition", ""),
            timeframe=r.get("timeframe", ""),
            timeframe_clean=tf_clean,
            chunk_text_short=r.get("chunk_text", "")[:300],
        )

        fname = f"strat_{safe_filename(r['setup_name'])[:40]}.py"

        if args.print:
            print(f"\n{'=' * 60}")
            print(f"File: {fname}")
            print(f"Score: {r['score']}")
            print(content)
        else:
            os.makedirs(args.output, exist_ok=True)
            fpath = os.path.join(args.output, fname)
            with open(fpath, "w") as f:
                f.write(content)
            print(f"Wrote {fpath}")


if __name__ == "__main__":
    main()
