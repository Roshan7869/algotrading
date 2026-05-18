"""Lightweight scheduler that runs TradingAgents every N minutes.

Replaces external cron for containerized environments.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add TradingAgents to path
TA_ROOT = Path(__file__).parent.parent / "TradingAgents"
sys.path.insert(0, str(TA_ROOT))


def run_tradingagents(ticker: str, trade_date: str) -> dict:
    """Run TradingAgents graph and return structured signal."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(config={})
    final_state, rating = graph.propagate(ticker, trade_date)

    # Extract typed reports if available
    analyst_reports = []
    for key in [
        "market_report_typed",
        "sentiment_report_typed",
        "news_report_typed",
        "fundamentals_report_typed",
    ]:
        report = final_state.get(key)
        if report is not None:
            from tradingagents.agents.schemas import _serialize_dataclass

            analyst_reports.append(_serialize_dataclass(report))

    debate_conclusion = None
    if "debate_conclusion" in final_state:
        from tradingagents.agents.schemas import _serialize_dataclass

        debate_conclusion = _serialize_dataclass(final_state["debate_conclusion"])

    risk_assessment = None
    if "risk_assessment" in final_state:
        from tradingagents.agents.schemas import _serialize_dataclass

        risk_assessment = _serialize_dataclass(final_state["risk_assessment"])

    return {
        "ticker": ticker,
        "date": trade_date,
        "rating": rating,
        "analyst_reports": analyst_reports,
        "debate_conclusion": debate_conclusion,
        "risk_assessment": risk_assessment,
        "final_trade_decision": final_state.get("final_trade_decision", ""),
        "timestamp": datetime.utcnow().isoformat(),
    }


def save_signal(signal: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(signal, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="BTC/USDT")
    parser.add_argument(
        "--interval", type=int, default=300, help="Seconds between runs"
    )
    parser.add_argument(
        "--output",
        default="shared_config/tradingagents_signal.json",
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--mock", action="store_true", help="Write mock signal")
    args = parser.parse_args()

    while True:
        date_str = datetime.now().strftime("%Y-%m-%d")
        try:
            if args.mock:
                signal = {
                    "ticker": args.ticker,
                    "date": date_str,
                    "rating": "Buy",
                    "analyst_reports": [],
                    "debate_conclusion": {
                        "winner": "bullish",
                        "confidence": 0.75,
                    },
                    "risk_assessment": {
                        "risk_level": "medium",
                        "approval": True,
                    },
                    "final_trade_decision": "**Rating**: Buy\n**Executive Summary**: Strong momentum.",
                    "timestamp": datetime.utcnow().isoformat(),
                    "mock": True,
                }
            else:
                signal = run_tradingagents(args.ticker, date_str)

            save_signal(signal, args.output)
            print(
                f"[{datetime.now().isoformat()}] Signal updated: {signal['rating']}"
            )
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error: {e}")

        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
