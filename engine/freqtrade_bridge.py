"""
Freqtrade Bridge — wires Freqtrade IStrategy signals to Redis signal bus.

Runs alongside Freqtrade, intercepting entry/exit signals and publishing
to the Redis bus after passing through the circuit breaker gate.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from engine.signal_bus import RedisSignalBus
from agents.risk_managers.circuit_breaker import EnforcedRiskGate, read_breaker_state, classify_tier
from core import RiskTier


class FreqtradeBridge:
    def __init__(self, redis_host: str = "127.0.0.1", redis_port: int = 6379,
                 enable_learning: bool = True, account_size: float = 1000.0):
        self.bus = RedisSignalBus(host=redis_host, port=redis_port)
        self.gate = EnforcedRiskGate()
        self.account_size = account_size
        self._running = False
        self._learning = None
        if enable_learning:
            try:
                from knowledge.learning_loop import LearningLoop
                self._learning = LearningLoop()
                self._learning._lazy_init()
            except Exception:
                self._learning = None

    def validate_signal(self, pair: str, side: str, price: float, amount: float) -> Tuple[bool, str]:
        if not isinstance(pair, str) or not pair.strip():
            return False, "pair must be a non-empty string"
        if side.lower() not in ("buy", "sell"):
            return False, "side must be 'buy' or 'sell'"
        if not isinstance(amount, (int, float)) or amount <= 0:
            return False, "amount must be numeric and > 0"
        if not isinstance(price, (int, float)) or price <= 0:
            return False, "price must be numeric and > 0"
        return True, ""

    def process_signal(self, pair: str, side: str, price: float,
                       amount: float, strategy: str = "", signal_id: str = "") -> dict:
        is_valid, reason = self.validate_signal(pair, side, price, amount)
        if not is_valid:
            logging.error("Signal validation failed: %s", reason)
            return {"approved": False, "reason": reason, "gate": "validation"}

        if self._learning is not None:
            learning_check = self._learning.pre_trade_check(
                pair=pair, side=side, strategy=strategy,
            )
            if not learning_check["approved"]:
                self.bus.publish_risk_event("learning_blocked", learning_check["block_reason"], {
                    "pair": pair, "side": side, "strategy": strategy,
                    "win_rate": learning_check["win_rate"],
                })
                return {"approved": False, "reason": learning_check["block_reason"],
                        "gate": "learning"}

        decision = self.gate.gate(pair, side, amount, strategy)
        if not decision.approved:
            self.bus.publish_risk_event("signal_blocked", decision.reason, {
                "pair": pair, "side": side, "strategy": strategy
            })
            return {"approved": False, "reason": decision.reason, "gate": "circuit_breaker"}

        scaled_amount = amount * decision.size_multiplier
        self.bus.publish_signal(pair, side, price, scaled_amount, strategy, signal_id)
        self.bus.publish("commands", {
            "action": "entry" if side.lower() in ("long", "buy") else "exit",
            "pair": pair,
            "side": side,
            "amount": scaled_amount,
            "price": price,
            "strategy": strategy,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {"approved": True, "size_multiplier": decision.size_multiplier}

    def process_pnl(self, pair: str, pnl: float, trade_id: str = ""):
        self.bus.publish_pnl(pair, pnl, trade_id)
        breaker = read_breaker_state()
        monthly = breaker.get("monthly_pnl_pct", 0)
        new_monthly = monthly + (pnl / self.account_size * 100)
        if new_monthly < -25:
            self.bus.publish_risk_event("drawdown_breach",
                                        f"Monthly PnL {new_monthly:.2f}% exceeds -25% threshold")

    def subscribe_commands(self, callback):
        self.bus.subscribe("commands")
        for msg in self.bus.listen():
            callback(msg)

    def start_command_loop(self):
        self._running = True
        self.bus.subscribe("commands")
        while self._running:
            for msg in self.bus.listen(timeout=1.0):
                if not self._running:
                    break

    def stop(self):
        self._running = False
        self.bus.close()
