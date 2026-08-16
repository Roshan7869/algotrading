"""
SubAgentOverseer — monitors health of AI sub-agents.

Tracks heartbeats, staleness, and per-agent trade limits for:
  - TradingAgents
  - MiroFish / MiroShark
  - Scripts agent runtime (5 agents)
  - Learning Loop
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from engine.signal_bus import RedisSignalBus


SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent.parent / "shared_config"))

AGENT_HEARTBEAT_TTL = {
    "tradingagents": 300,
    "mirofish": 300,
    "learning_loop": 600,
    "scripts_agent_runner": 300,
    "market_regime": 300,
}


@dataclass
class AgentStatus:
    name: str
    status: str = "unknown"
    last_heartbeat: float = 0.0
    trades_today: int = 0
    max_trades_per_day: int = 10
    last_error: str = ""
    consecutive_failures: int = 0
    is_healthy: bool = True


class SubAgentOverseer:
    def __init__(self, redis_host: str = "127.0.0.1", redis_port: int = 6379):
        self._agents: dict[str, AgentStatus] = {}
        self._bus = RedisSignalBus(host=redis_host, port=redis_port)
        self._init_agents()

    def _init_agents(self):
        for name in AGENT_HEARTBEAT_TTL:
            self._agents[name] = AgentStatus(name=name)

    def register_agent(self, name: str, max_trades_per_day: int = 10):
        self._agents[name] = AgentStatus(
            name=name, max_trades_per_day=max_trades_per_day
        )

    def heartbeat(self, name: str, status: str = "running", error: str = ""):
        agent = self._agents.get(name)
        if agent is None:
            self.register_agent(name)
            agent = self._agents[name]
        agent.last_heartbeat = time.time()
        agent.status = status
        if error:
            agent.last_error = error
            agent.consecutive_failures += 1
        else:
            agent.consecutive_failures = 0
        agent.is_healthy = (
            agent.consecutive_failures < 3
            and agent.trades_today <= agent.max_trades_per_day
        )

    def record_trade(self, name: str):
        agent = self._agents.get(name)
        if agent:
            agent.trades_today += 1
            if agent.trades_today > agent.max_trades_per_day:
                self._bus.publish_risk_event("agent_trade_limit",
                    f"{name}: {agent.trades_today} trades > {agent.max_trades_per_day} limit")

    def reset_daily_counts(self):
        for agent in self._agents.values():
            agent.trades_today = 0

    def health_check(self) -> dict:
        now = time.time()
        total = len(self._agents)
        healthy = 0
        stale = 0
        results = {}

        for name, agent in self._agents.items():
            ttl = AGENT_HEARTBEAT_TTL.get(name, 300)
            age = now - agent.last_heartbeat if agent.last_heartbeat > 0 else float("inf")
            is_stale = age > ttl
            is_healthy = agent.is_healthy and not is_stale

            if is_healthy:
                healthy += 1
            if is_stale:
                stale += 1

            results[name] = {
                "status": "stale" if is_stale else agent.status,
                "age_seconds": int(age) if age != float("inf") else -1,
                "trades_today": agent.trades_today,
                "max_trades_per_day": agent.max_trades_per_day,
                "consecutive_failures": agent.consecutive_failures,
                "is_healthy": is_healthy,
            }

        health_score = healthy / total if total > 0 else 0.0

        return {
            "health_score": round(health_score, 2),
            "total_agents": total,
            "healthy_agents": healthy,
            "stale_agents": stale,
            "agents": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_agent(self, name: str) -> Optional[AgentStatus]:
        return self._agents.get(name)

    def publish_health(self):
        health = self.health_check()
        path = SHARED_DIR / "agent_health.json"
        try:
            path.write_text(json.dumps(health, indent=2))
        except OSError:
            pass
        return health
