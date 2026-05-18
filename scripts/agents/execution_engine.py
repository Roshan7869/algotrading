from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from .journal import AgentJournal
from .schemas import TradeDecision


class ExecutionEngine:
    def __init__(self, config: dict[str, Any], journal: AgentJournal):
        self.config = config
        self.journal = journal

    def execute(self, mode: str, decision: TradeDecision, risk_passed: bool, failures: list[str]) -> dict[str, Any]:
        if not risk_passed:
            result = {"status": "blocked", "failures": failures}
            self.journal.record_execution(decision.pair, mode, "blocked", result)
            return result

        if mode == "observe":
            result = {"status": "observed", "decision": decision.to_dict()}
        elif mode == "telegram_confirm":
            result = {
                "status": "awaiting_manual_confirmation",
                "message": self._telegram_message(decision),
            }
        elif mode == "paper_execute":
            if not self.config.get("dry_run", True):
                result = {"status": "blocked", "failures": ["paper_execute_requires_dry_run"]}
            else:
                result = self._force_enter(decision)
        elif mode == "live_execute":
            result = {"status": "blocked", "failures": ["live_execute_disabled_by_design"]}
        else:
            result = {"status": "blocked", "failures": [f"unknown_mode:{mode}"]}

        self.journal.record_execution(decision.pair, mode, result.get("status", "unknown"), result)
        return result

    def _telegram_message(self, decision: TradeDecision) -> str:
        return (
            f"AGENT {decision.decision.upper()} {decision.side.upper()} {decision.pair}\n"
            f"Confidence: {decision.confidence:.2f}\n"
            f"Stake: {decision.stake_pct:.1%}\n"
            f"Max leverage: {decision.max_leverage}x\n"
            "Reply manually in Freqtrade/Telegram after review."
        )

    def _force_enter(self, decision: TradeDecision) -> dict[str, Any]:
        api = self.config.get("api_server", {})
        host = api.get("listen_ip_address", "127.0.0.1")
        if host == "0.0.0.0":
            host = "127.0.0.1"
        port = api.get("listen_port", 8080)
        username = api.get("username", "")
        password = api.get("password", "")
        payload = {
            "pair": decision.pair,
            "side": decision.side,
            "ordertype": "limit",
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://{host}:{port}/api/v1/forceenter",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if username and password and not str(username).startswith("${"):
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            req.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return {
                    "status": "submitted",
                    "response": json.loads(response.read().decode("utf-8")),
                }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"status": "failed", "error": str(exc)}

