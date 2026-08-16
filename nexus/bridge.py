"""
NEXUS ↔ Trading Engine Bridge

Bidirectional bridge connecting NEXUS orchestration to the Algotrading engine:
  NEXUS → Trading: trade_status, execute_backtest, adjust_config
  Trading → NEXUS: feed_outcome_to_nexus, coach.record_outcome
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent / "shared_config"))


class NexusBridge:
    def __init__(self):
        self._last_breach = 0.0

    @property
    def enabled(self) -> bool:
        """True when NEXUS_THOMPSON_ROUTING is set to 'true'."""
        return os.getenv("NEXUS_THOMPSON_ROUTING", "false").lower() == "true"

    def _thompson_score(self, skill_name: str) -> float:
        from nexus.thompson_local import thompson_score
        return thompson_score(skill_name)

    # ── NEXUS → Trading: 4 MCP tools ──────────────────────────────

    def query_strategies(self, query: str, top_k: int = 5,
                         setup_type: str | None = None,
                         market_condition: str | None = None,
                         keyword: str | None = None) -> list[dict]:
        from strategy_db.search import search
        results = search(
            query=query,
            top_k=top_k * 3,
            setup_type=setup_type,
            market_condition=market_condition,
            keyword=keyword,
        )

        if self.enabled and results:
            from nexus.thompson_local import thompson_rank
            results = thompson_rank(results)[:top_k]

        return results[:top_k]

    def trade_status(self) -> dict:
        """Return current positions, PnL, and risk state."""
        from agents.risk_managers.circuit_breaker import read_breaker_state, classify_tier
        from agents.risk_managers.hedge_coordinator import HEdgeCoordinator

        breaker = read_breaker_state()
        tier = classify_tier(breaker)
        hedge = HEdgeCoordinator()
        risk = hedge.assess()

        hedge_state = self._read_json(SHARED_DIR / "hedge_state.json")
        agent_health = self._read_json(SHARED_DIR / "agent_health.json")

        return {
            "status": "online",
            "circuit_breaker": {
                "tier": int(tier),
                "tier_name": tier.name if hasattr(tier, "name") else str(tier),
                "state": breaker.get("state", "unknown"),
                "monthly_drawdown": breaker.get("monthly_drawdown_pct", 0.0),
            },
            "risk": {
                "composite_score": (hedge_state or {}).get("composite_score", None) or (risk.composite_score if risk else None),
                "max_drawdown_pct": breaker.get("max_drawdown_pct", 20.0),
                "drawdown_breached": (hedge_state or {}).get("drawdown_breached", False),
            },
            "agent_health": agent_health.get("agents", {}) if agent_health else {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def execute_backtest(self, strategy: str, pair: str = "BTC/USDT",
                         timerange: str = "20240101-20240601") -> dict:
        """Run a walkforward backtest for the given strategy."""
        from engine.walkforward import generate_windows, run_backtest_window, compute_report

        windows = generate_windows(
            total_start=timerange.split("-")[0],
            total_end=timerange.split("-")[1],
            window_size_days=60,
            test_size_days=20,
            step_days=20,
        )

        for w in windows:
            w.train_results = run_backtest_window(strategy, w.train_start, w.train_end)
            w.test_results = run_backtest_window(strategy, w.test_start, w.test_end)
            w.sharpe = w.test_results.get("sharpe", 0.0)
            w.max_drawdown = w.test_results.get("max_drawdown", 0.0)
            w.total_pnl = w.test_results.get("profit_total_pct", 0.0)
            w.win_rate = w.test_results.get("winrate", 0.0)
            w.num_trades = w.test_results.get("total_trades", 0)

        report = compute_report(strategy, windows)
        return {
            "strategy": strategy,
            "pair": pair,
            "timerange": timerange,
            "windows": len(windows),
            "avg_test_sharpe": report.avg_test_sharpe,
            "avg_test_dd": report.avg_test_dd,
            "total_trades": report.total_trades,
            "combined_win_rate": report.combined_win_rate,
            "is_robust": report.is_robust,
        }

    VALID_TIERS = {"NORMAL", "CAUTION", "RESTRICTED", "HALT", "LIQUIDATE"}

    def adjust_config(self, key: str, value: Any) -> dict:
        """Adjust a runtime configuration parameter."""
        breaker_path = SHARED_DIR / "circuit_breaker.json"
        if not breaker_path.exists():
            return {"success": False, "error": "circuit_breaker.json not found"}

        if key in ("max_drawdown_pct", "max_trades_per_day", "max_leverage"):
            breaker = self._read_json(breaker_path) or {}
            try:
                if key == "max_drawdown_pct":
                    val = float(value)
                    if val < 1 or val > 100:
                        return {"success": False, "error": f"max_drawdown_pct must be 1-100, got {value}"}
                    breaker["max_drawdown_pct"] = val
                elif key == "max_trades_per_day":
                    val = int(value)
                    if val < 0 or val > 100:
                        return {"success": False, "error": f"max_trades_per_day must be 0-100, got {value}"}
                    breaker["max_trades_per_day"] = val
                elif key == "max_leverage":
                    val = float(value)
                    if val < 1 or val > 100:
                        return {"success": False, "error": f"max_leverage must be 1-100, got {value}"}
                    breaker["max_leverage"] = val
            except (ValueError, TypeError):
                return {"success": False, "error": f"Invalid numeric value for {key}: {value}"}
            self._write_json(breaker_path, breaker)
            return {"success": True, "key": key, "value": value}

        if key == "risk_tier":
            tier = str(value).upper()
            if tier not in self.VALID_TIERS:
                return {"success": False, "error": f"Invalid risk_tier: {tier}. Valid: {sorted(self.VALID_TIERS)}"}
            old = self._read_json(breaker_path) or {}
            old["state"] = tier
            self._write_json(breaker_path, old)
            return {"success": True, "key": "state", "value": tier}

        return {"success": False, "error": f"Unknown config key: {key}"}

    # ── Trading → NEXUS: 2 feedback paths ─────────────────────────

    def feed_outcome_to_nexus(self, trade_data: dict) -> dict:
        """
        Feed trade outcome to NEXUS Thompson Sampling learning.

        Trade data format:
            { "pair": "BTC/USDT", "side": "buy", "pnl_pct": 2.1,
              "win": true, "strategy": "my_strat" }
        """
        try:
            from nexus.event_bridge import record_outcome

            win = trade_data.get("win", trade_data.get("pnl_pct", 0) > 0)
            record_outcome(
                skill_name=trade_data.get("strategy", "unknown"),
                outcome="correct" if win else "wrong",
                task_summary=f"trade on {trade_data.get('pair', 'unknown')} "
                             f"({trade_data.get('pnl_pct', 0):.2f}%)",
            )
            return {"success": True, "fed_to": "nexus_thompson", "win": win}
        except ImportError:
            logger.warning("feed_outcome_to_nexus: nexus.event_bridge not available")
        except Exception as e:
            logger.warning(f"feed_outcome_to_nexus failed: {e}")
            return {"success": False, "error": str(e)}

        return {"success": False, "error": "nexus/event_bridge not available"}

    def record_coach_outcome(self, trade_data: dict) -> dict:
        """Record trade outcome for coach practice scores via NEXUS feedback."""
        try:
            from nexus.event_bridge import record_outcome

            win = trade_data.get("win", trade_data.get("pnl_pct", 0) > 0)
            record_outcome(
                skill_name=f"coach:{trade_data.get('strategy', 'unknown')}",
                outcome="correct" if win else "wrong",
                task_summary=f"coach trade {trade_data.get('trade_id', '')} "
                             f"on {trade_data.get('pair', 'unknown')} "
                             f"({trade_data.get('pnl_pct', 0):.2f}%)",
            )
            return {"success": True, "fed_to": "coach"}
        except ImportError:
            logger.warning("record_coach_outcome: nexus.event_bridge not available")
        except Exception as e:
            logger.warning(f"record_coach_outcome failed: {e}")
            return {"success": False, "error": str(e)}

        return {"success": False, "error": "nexus event_bridge not available"}

    # ── Internals ─────────────────────────────────────────────────

    def _read_json(self, path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write_json(self, path: Path, data: dict) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, default=str))
            return True
        except OSError:
            return False


import threading

_bridge: Optional[NexusBridge] = None
_bridge_lock = threading.Lock()


def get_bridge() -> NexusBridge:
    global _bridge
    if _bridge is not None:
        return _bridge
    with _bridge_lock:
        if _bridge is None:
            _bridge = NexusBridge()
    return _bridge
