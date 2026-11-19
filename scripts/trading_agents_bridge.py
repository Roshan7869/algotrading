#!/usr/bin/env python3
"""TradingAgents -> NEXUS signal bridge.

Runs the Tauric Research TradingAgents framework (vendored at ../TradingAgents)
for a ticker list and writes the consensus decision to
shared_config/tradingagents_signal.json in the platform's signal schema —
replacing scripts/refresh_agents.py (the old placeholder that kept stale values).

Run with the TradingAgents venv python:
  TradingAgents\\.venv\\Scripts\\python.exe scripts\\trading_agents_bridge.py --check
  TradingAgents\\.venv\\Scripts\\python.exe scripts\\trading_agents_bridge.py --tickers NVDA,AAPL --date 2026-11-18

Requires an LLM API key in the environment (any of: OPENAI_API_KEY, GOOGLE_API_KEY,
ANTHROPIC_API_KEY, XAI_API_KEY, DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, ZHIPU_API_KEY,
MINIMAX_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, MOONSHOT_API_KEY).
No key => exit 3, and the existing signal file is left untouched.
Data comes free from Yahoo (yfinance); no data API key is needed.

Cost note: every ticker run is a full multi-agent LLM debate (multiple model calls).
Do NOT cron this every 15 minutes. Once or twice a day per ticker list is sane.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TA_DIR = ROOT / "TradingAgents"
SIGNAL_PATH = ROOT / "shared_config" / "tradingagents_signal.json"
LOG_PATH = ROOT / "user_data" / "logs" / "trading_agents_bridge.log"

KEY_ENVS = (
    "OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY",
    "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "ZHIPU_API_KEY", "MINIMAX_API_KEY",
    "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "MOONSHOT_API_KEY",
)


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} [ta-bridge] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def have_key() -> bool:
    return any(os.environ.get(k) for k in KEY_ENVS)


def verdict(decision: object) -> str:
    d = str(decision or "").upper()
    for tag, rating in (("SELL", "Sell"), ("BUY", "Buy"), ("HOLD", "Neutral")):
        if tag in d:
            return rating
    return "Neutral"


def main() -> int:
    ap = argparse.ArgumentParser(description="TradingAgents -> shared_config signal bridge")
    ap.add_argument("--tickers", default=os.environ.get("TRADINGAGENTS_TICKERS", "NVDA,AAPL,MSFT"))
    ap.add_argument("--date", default=(datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"))
    ap.add_argument("--check", action="store_true", help="print readiness diagnostics and exit")
    args = ap.parse_args()

    if not TA_DIR.is_dir():
        log(f"TradingAgents directory missing at {TA_DIR}")
        return 2

    sys.path.insert(0, str(TA_DIR))
    if args.check:
        print("TradingAgents dir:", TA_DIR.is_dir())
        try:
            import tradingagents  # noqa: PLC0415
            print("package version:", tradingagents.__version__)
        except Exception as e:  # noqa: BLE001
            print("import FAILED:", type(e).__name__, str(e)[:200])
            return 1
        print("LLM key present:", have_key(), f"(env vars checked: {len(KEY_ENVS)})")
        print("signal target:", SIGNAL_PATH)
        return 0

    if not have_key():
        log("no LLM API key in env -> refusing to run; set e.g. OPENROUTER_API_KEY or OPENAI_API_KEY. Existing signal untouched.")
        return 3

    from tradingagents.default_config import DEFAULT_CONFIG  # noqa: PLC0415
    from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: PLC0415

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        log("empty ticker list")
        return 2

    log(f"running {len(tickers)} ticker(s) for {args.date}: {', '.join(tickers)}")
    t0 = time.time()
    graph = TradingAgentsGraph(debug=False, config=DEFAULT_CONFIG.copy())
    per: dict[str, dict] = {}
    for t in tickers:
        try:
            _state, decision = graph.propagate(t, args.date)
            per[t] = {"rating": verdict(decision), "decision_excerpt": str(decision)[:500]}
            log(f"{t}: {per[t]['rating']}")
        except Exception as e:  # noqa: BLE001
            per[t] = {"rating": "Neutral", "error": f"{type(e).__name__}: {str(e)[:300]}"}
            log(f"{t}: ERROR {type(e).__name__}")

    counts = {"Buy": 0, "Sell": 0, "Neutral": 0}
    for v in per.values():
        counts[v["rating"]] += 1
    consensus = max(counts, key=counts.get) if counts["Buy"] != counts["Sell"] else "Neutral"
    errors = sum(1 for v in per.values() if "error" in v)

    payload = {
        "rating": consensus,
        "risk_assessment": {"approval": errors == 0},
        "details": per,
        "as_of": args.date,
        "consensus_counts": counts,
        "_timestamp": datetime.now(timezone.utc).isoformat(),
        "_written_by": f"trading_agents_bridge:{os.getpid()}",
        "_meta": {"framework": "TradingAgents v" + _ta_version(), "run_seconds": round(time.time() - t0, 1)},
    }
    tmp = SIGNAL_PATH.with_suffix(".json.tmp")
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, SIGNAL_PATH)
    log(f"signal written: {consensus} ({counts}) -> {SIGNAL_PATH}")
    return 0 if errors == 0 else 4


def _ta_version() -> str:
    try:
        import tradingagents  # noqa: PLC0415
        return getattr(tradingagents, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
