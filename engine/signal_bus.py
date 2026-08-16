"""
Redis Signal Bus — pub/sub for trade signals, risk events, PnL, commands.

JSON backward-compat: every published message is also written to shared_config.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import redis

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", Path(__file__).parent.parent / "shared_config"))

CHANNELS = {
    "signals": "signals",
    "risk": "risk",
    "pnl": "pnl",
    "commands": "commands",
}


class RedisSignalBus:
    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0):
        self._client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self._pubsub = self._client.pubsub()
        self._subscribed = False

    @property
    def client(self):
        return self._client

    def publish(self, channel: str, message: dict) -> bool:
        if channel not in CHANNELS:
            raise ValueError(f"Unknown channel: {channel}. Valid: {list(CHANNELS)}")
        msg = {
            "type": channel,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": message,
        }
        payload = json.dumps(msg, default=str)
        self._write_json_backup(channel, msg)
        try:
            self._client.publish(channel, payload)
        except redis.RedisError:
            pass
        return True

    def subscribe(self, channel: str):
        if channel not in CHANNELS:
            raise ValueError(f"Unknown channel: {channel}. Valid: {list(CHANNELS)}")
        self._pubsub.subscribe(channel)
        self._subscribed = True

    def subscribe_all(self):
        for ch in CHANNELS:
            self._pubsub.subscribe(ch)
        self._subscribed = True

    def listen(self, timeout: Optional[float] = None):
        if not self._subscribed:
            return
        deadline = time.time() + timeout if timeout else None
        while True:
            msg = self._pubsub.get_message(timeout=1.0)
            if msg is None:
                if deadline and time.time() >= deadline:
                    break
                continue
            if msg.get("type") != "message":
                continue
            try:
                yield json.loads(msg["data"])
            except (json.JSONDecodeError, KeyError):
                continue
            if deadline and time.time() >= deadline:
                break

    def unsubscribe(self, channel: str):
        self._pubsub.unsubscribe(channel)

    def unsubscribe_all(self):
        for ch in CHANNELS:
            self._pubsub.unsubscribe(ch)
        self._subscribed = False

    def publish_signal(self, pair: str, side: str, price: float,
                       amount: float, strategy: str = "", signal_id: str = ""):
        return self.publish("signals", {
            "pair": pair,
            "side": side,
            "price": price,
            "amount": amount,
            "strategy": strategy,
            "signal_id": signal_id or f"sig_{int(time.time())}_{pair.replace('/', '_')}",
        })

    def publish_risk_event(self, event_type: str, message: str, details: dict = None):
        return self.publish("risk", {
            "event": event_type,
            "message": message,
            "details": details or {},
        })

    def publish_pnl(self, pair: str, pnl: float, trade_id: str = ""):
        return self.publish("pnl", {
            "pair": pair,
            "pnl": pnl,
            "trade_id": trade_id or f"trade_{int(time.time())}",
        })

    def close(self):
        self.unsubscribe_all()
        self._client.close()

    def _write_json_backup(self, channel: str, msg: dict):
        path = SHARED_DIR / f"signal_bus_{channel}.json"
        try:
            existing = []
            if path.exists():
                existing = json.loads(path.read_text())
            if not isinstance(existing, list):
                existing = []
            existing.append(msg)
            if len(existing) > 1000:
                existing = existing[-500:]
            path.write_text(json.dumps(existing, indent=2, default=str))
        except (OSError, json.JSONDecodeError):
            pass
