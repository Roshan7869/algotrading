"""
Trade Event Bridge — connects Rust execution signals → NEXUS outcome history.

Reads from Redis `signals:*` streams, maintains paper positions, and records
trade outcomes to strategy_db/outcome_history.json for NEXUS learning.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OUTCOME_PATH = Path(__file__).resolve().parent.parent / "strategy_db" / "outcome_history.json"


class TradeEventBridge:
    def __init__(self, redis_host: str = "127.0.0.1", redis_port: int = 6379):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self._running = False
        self._position: Optional[dict] = None
        self._last_ids: dict[str, Optional[str]] = {}
        self._r = None

    def _connect_redis(self):
        import redis as redis_lib
        self._r = redis_lib.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
        self._r.ping()
        logger.info("TradeEventBridge connected to Redis")

    def _load_outcomes(self) -> dict:
        if OUTCOME_PATH.exists():
            with open(OUTCOME_PATH) as f:
                return json.load(f)
        return {"trades": [], "chunk_stats": {}}

    def _save_outcomes(self, data: dict):
        OUTCOME_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTCOME_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def _record_trade(self, signal: dict, exit_price: float, pnl: float):
        outcomes = self._load_outcomes()
        trade = {
            "trade_id": f"T{len(outcomes['trades']) + 1:04d}",
            "pair": signal.get("pair", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "regime": "auto",
            "setup_names": [signal.get("reason", "auto")],
            "direction": "long" if signal.get("signal_type") == "Buy" else "short",
            "entry_price": self._position.get("entry_price", 0),
            "exit_price": exit_price,
            "pnl": round(pnl, 4),
            "r_multiple": round(pnl / (self._position.get("entry_price", 1) * 0.01), 2),
            "confidence": signal.get("confidence", 0.5),
        }
        outcomes["trades"].append(trade)

        for name in trade["setup_names"]:
            if name not in outcomes["chunk_stats"]:
                outcomes["chunk_stats"][name] = {
                    "total_trades": 0, "wins": 0, "losses": 0,
                    "total_pnl": 0.0, "total_r_multiple": 0.0,
                    "regime_breakdown": {},
                }
            s = outcomes["chunk_stats"][name]
            s["total_trades"] += 1
            if pnl > 0:
                s["wins"] += 1
            else:
                s["losses"] += 1
            s["total_pnl"] += trade["pnl"]
            s["total_r_multiple"] += trade["r_multiple"]

        self._save_outcomes(outcomes)
        logger.info(f"Recorded trade {trade['trade_id']}: {trade['direction']} {trade['pnl']:.2f}")

    def _process_signal(self, signal: dict):
        stype = signal.get("signal_type")
        price = signal.get("price", 0)
        now = time.time()

        if stype == "Buy":
            if self._position is None:
                self._position = {
                    "side": "long",
                    "entry_price": price,
                    "entry_time": now,
                    "signal": signal,
                }
                logger.info(f"Opened LONG at {price}")
            elif self._position["side"] == "short":
                pnl = self._position["entry_price"] - price
                self._record_trade(self._position["signal"], price, pnl)
                self._position = {
                    "side": "long",
                    "entry_price": price,
                    "entry_time": now,
                    "signal": signal,
                }
                logger.info(f"Closed SHORT at {price} (PnL: {pnl:.2f}), opened LONG")

        elif stype == "Sell":
            if self._position is None:
                self._position = {
                    "side": "short",
                    "entry_price": price,
                    "entry_time": now,
                    "signal": signal,
                }
                logger.info(f"Opened SHORT at {price}")
            elif self._position["side"] == "long":
                pnl = price - self._position["entry_price"]
                self._record_trade(self._position["signal"], price, pnl)
                self._position = {
                    "side": "short",
                    "entry_price": price,
                    "entry_time": now,
                    "signal": signal,
                }
                logger.info(f"Closed LONG at {price} (PnL: {pnl:.2f}), opened SHORT")

        elif stype == "CloseLong" and self._position and self._position["side"] == "long":
            pnl = price - self._position["entry_price"]
            self._record_trade(self._position["signal"], price, pnl)
            self._position = None
            logger.info(f"Closed LONG at {price} (PnL: {pnl:.2f})")

        elif stype == "CloseShort" and self._position and self._position["side"] == "short":
            pnl = self._position["entry_price"] - price
            self._record_trade(self._position["signal"], price, pnl)
            self._position = None
            logger.info(f"Closed SHORT at {price} (PnL: {pnl:.2f})")

    def run(self, streams: Optional[list[str]] = None):
        if streams is None:
            streams = ["signals:BTCUSDT:1h"]

        import redis as redis_lib
        self._connect_redis()
        self._running = True

        logger.info(f"TradeEventBridge watching streams: {streams}")

        while self._running:
            try:
                for stream in streams:
                    last_id = self._last_ids.get(stream, "$")
                    result = self._r.xread({stream: last_id}, block=1000, count=10)
                    if not result:
                        continue
                    for sname, messages in result:
                        for msg_id, msg_data in messages:
                            self._last_ids[sname] = msg_id
                            raw = msg_data.get("data", "{}")
                            signal = json.loads(raw)
                            self._process_signal(signal)
            except redis_lib.ConnectionError:
                logger.warning("Redis connection lost, reconnecting...")
                time.sleep(1)
                try:
                    self._connect_redis()
                except Exception:
                    pass
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"TradeEventBridge error: {e}")
                time.sleep(1)

    def stop(self):
        self._running = False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = TradeEventBridge()
    try:
        bridge.run()
    except KeyboardInterrupt:
        bridge.stop()
        logger.info("TradeEventBridge stopped")
