from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "scripts.agents"

from .aggregator import DecisionAggregator
from .execution_engine import ExecutionEngine
from .journal import AgentJournal
from .market_data_bus import load_config, load_latest_snapshot
from .research_agents import (
    MarketRegimeAgent,
    PairScannerAgent,
    RiskAgent,
    SentimentAgent,
    StrategyValidatorAgent,
)
from .risk_gate import RiskGate


async def analyze_pair(
    pair: str,
    config: dict[str, Any],
    mode: str,
    use_ollama: bool,
    quick_model: str,
    deep_model: str,
) -> dict[str, Any]:
    journal = AgentJournal()
    snapshot = load_latest_snapshot(config, pair)
    context = {
        "open_trades": 0,
        "max_open_trades": config.get("max_open_trades", 3),
        "min_confidence": 0.70,
        "max_stake_pct": 0.10,
        "max_daily_drawdown_pct": 5.0,
        "max_total_drawdown_pct": 15.0,
        "spread_bps": snapshot.spread_bps or 0.0,
    }
    journal.record_snapshot(pair, snapshot.to_dict())

    agents = [
        MarketRegimeAgent(model=quick_model, use_ollama=use_ollama),
        PairScannerAgent(model=quick_model, use_ollama=use_ollama),
        StrategyValidatorAgent(model=quick_model, use_ollama=use_ollama),
        RiskAgent(model=deep_model, use_ollama=use_ollama),
        SentimentAgent(model=quick_model, use_ollama=use_ollama),
    ]
    results = await asyncio.gather(*(agent.run(snapshot, context) for agent in agents))
    for result in results:
        journal.record_agent_output(pair, result.agent, result.to_dict())

    decision = DecisionAggregator().combine(pair, results)
    risk_passed, failures = RiskGate(config).evaluate(decision, context)
    journal.record_decision(pair, decision.decision, {**decision.to_dict(), "risk_passed": risk_passed, "failures": failures})
    execution = ExecutionEngine(config, journal).execute(mode, decision, risk_passed, failures)
    return {
        "pair": pair,
        "snapshot": snapshot.to_dict(),
        "decision": decision.to_dict(),
        "risk_passed": risk_passed,
        "failures": failures,
        "execution": execution,
    }


async def main_async(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pairs = args.pairs.split(",") if args.pairs else config.get("exchange", {}).get("pair_whitelist", [])
    pairs = [pair.strip() for pair in pairs if pair.strip()]
    if not pairs:
        raise SystemExit("No pairs provided or configured.")

    outputs = await asyncio.gather(
        *(
            analyze_pair(pair, config, args.mode, args.use_ollama, args.quick_model, args.deep_model)
            for pair in pairs[: args.max_pairs]
        )
    )
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel Ollama/Freqtrade market agent runner")
    parser.add_argument("--config", default="user_data/config_market_ready.json")
    parser.add_argument("--mode", choices=["observe", "telegram_confirm", "paper_execute", "live_execute"], default="observe")
    parser.add_argument("--pairs", default="")
    parser.add_argument("--max-pairs", type=int, default=3)
    parser.add_argument("--use-ollama", action="store_true")
    parser.add_argument("--quick-model", default="qwen3:latest")
    parser.add_argument("--deep-model", default="gpt-oss:latest")
    return parser.parse_args()


def main() -> int:
    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
