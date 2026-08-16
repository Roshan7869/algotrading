"""
Data Manager — single source of truth for ALL shared state.

Centralized read/write layer over JSON files, SQLite, and ChromaDB.
Provides:
  - File-locked reads/writes (fcntl) for concurrent safety
  - TTL-based cache (5s hot, 5min cold)
  - Event publishing on state mutations

Backward compatible: still reads the same JSON files on disk, but adds
caching, locking, and event-driven notifications on top.
"""

import fcntl
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.event_bus import EventBus, EventTypes, get_event_bus

logger = logging.getLogger(__name__)

SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR",
                             Path(__file__).parent.parent / "shared_config"))

BREAKER_PATH = SHARED_DIR / "circuit_breaker.json"
REGIME_PATH = SHARED_DIR / "market_regime.json"
SIGNAL_LOG_PATH = SHARED_DIR / "signal_bus_signals.json"
PNL_PATH = SHARED_DIR / "signal_bus_pnl.json"
HEDGE_PATH = SHARED_DIR / "hedge_state.json"
ORCHESTRATOR_PATH = SHARED_DIR / "orchestrator_signal.json"
ACTIVE_STRATEGY_PATH = SHARED_DIR / "active_strategy.json"
AGENT_HEALTH_PATH = SHARED_DIR / "agent_health.json"

HOT_TTL = 5.0
COLD_TTL = 300.0


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float):
        self.value = value
        self.expires_at = time.monotonic() + ttl

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at


class DataError(Exception):
    pass


class FileNotFoundError(DataError):
    pass


class ParseError(DataError):
    pass


class _LockedJson:
    """File-locked JSON read/write using fcntl."""

    @staticmethod
    def read(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        fd = None
        try:
            fd = os.open(str(path), os.O_RDONLY)
            fcntl.flock(fd, fcntl.LOCK_SH)
            raw = os.read(fd, 1_048_576)
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ParseError(f"Invalid JSON in {path}")
        except OSError as e:
            logger.debug("LockedJson read error for %s: %s", path, e)
            return None
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                except OSError:
                    pass

    @staticmethod
    def write(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = None
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX)
            payload = json.dumps(data, indent=2, default=str).encode()
            os.write(fd, payload)
            os.fsync(fd)
        except OSError as e:
            raise DataError(f"Failed to write {path}: {e}")
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                except OSError:
                    pass


class DataManager:
    """
    Singleton data manager — centralized access to all shared state.

    All reads go through a cached layer. Writes update the file on disk
    and publish an event via the EventBus.
    """

    _instance: Optional["DataManager"] = None
    _init_lock = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, event_bus: Optional[EventBus] = None):
        if self._initialized:
            return
        self._cache: dict[str, _CacheEntry] = {}
        self._json = _LockedJson()
        self._bus = event_bus or get_event_bus()
        self._initialized = True

    # ── Regime ────────────────────────────────────────────────────────

    def get_regime(self) -> Optional[dict]:
        return self._read_cached(REGIME_PATH, HOT_TTL, "regime")

    def set_regime(self, regime: str, extra: Optional[dict] = None) -> dict:
        current = self.get_regime() or {}
        old_regime = current.get("regime", "unknown")
        merged = {**current, "regime": regime,
                  "_timestamp": datetime.now(timezone.utc).isoformat(),
                  "_written_by": "data_manager"}
        if extra:
            merged.update(extra)
        self._json.write(REGIME_PATH, merged)
        self._invalidate(REGIME_PATH)
        if old_regime != regime:
            self._bus.publish(EventTypes.REGIME_CHANGE, {
                "old_regime": old_regime,
                "new_regime": regime,
                **merged,
            }, source="data_manager")
        return merged

    # ── Circuit Breaker ────────────────────────────────────────────────

    def get_circuit_breaker(self) -> Optional[dict]:
        return self._read_cached(BREAKER_PATH, HOT_TTL, "circuit_breaker")

    def set_circuit_breaker(self, state: str, extra: Optional[dict] = None) -> dict:
        current = self.get_circuit_breaker() or {}
        old_state = current.get("state", "UNKNOWN")
        merged = {**current, "state": state,
                  "_timestamp": datetime.now(timezone.utc).isoformat(),
                  "_written_by": "data_manager"}
        if extra:
            merged.update(extra)
        self._json.write(BREAKER_PATH, merged)
        self._invalidate(BREAKER_PATH)
        if old_state != state:
            self._bus.publish(EventTypes.CIRCUIT_BREAKER_CHANGE, {
                "old_state": old_state,
                "new_state": state,
                **merged,
            }, source="data_manager")
        return merged

    # ── PnL ────────────────────────────────────────────────────────────

    def get_pnl(self) -> Optional[list]:
        data = self._read_cached(PNL_PATH, COLD_TTL, "pnl")
        if data is None:
            return None
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return None

    # ── Positions ──────────────────────────────────────────────────────

    def get_positions(self) -> list:
        try:
            db_path = Path(__file__).parent.parent / "user_data" / "tradesv3.sqlite"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM trades WHERE is_open = 1 ORDER BY open_date DESC"
                )
                rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
                return rows
        except Exception as e:
            logger.debug("Failed to read positions from SQLite: %s", e)
        return self._read_cached(SHARED_DIR / "positions.json",
                                  COLD_TTL, "positions") or []

    # ── Signals ────────────────────────────────────────────────────────

    def get_signals(self, limit: int = 50) -> Optional[list]:
        data = self._read_cached(SIGNAL_LOG_PATH, HOT_TTL, "signals")
        if data is None:
            return None
        if isinstance(data, list):
            return data[-limit:]
        return [data]

    # ── Risk Tier / Hedge ──────────────────────────────────────────────

    def get_risk_tier(self) -> Optional[str]:
        breaker = self.get_circuit_breaker()
        if breaker is None:
            return None
        from core import RiskTier
        tier_map = {
            "NORMAL": "NORMAL", "CAUTION": "CAUTION",
            "RESTRICTED": "RESTRICTED", "HALT": "HALT",
            "PAUSED": "HALT", "LIQUIDATE": "LIQUIDATE",
        }
        return tier_map.get(breaker.get("state", "").upper())

    def get_hedge_state(self) -> Optional[dict]:
        return self._read_cached(HEDGE_PATH, HOT_TTL, "hedge_state")

    # ── Active Strategy ────────────────────────────────────────────────

    def get_active_strategy(self) -> Optional[dict]:
        return self._read_cached(ACTIVE_STRATEGY_PATH, HOT_TTL, "active_strategy")

    def set_active_strategy(self, strategy_name: str,
                            extra: Optional[dict] = None) -> dict:
        current = self.get_active_strategy() or {}
        old_strategy = current.get("strategy", current.get("name", ""))
        merged = {**current, "strategy": strategy_name,
                  "name": strategy_name,
                  "_timestamp": datetime.now(timezone.utc).isoformat(),
                  "_written_by": "data_manager"}
        if extra:
            merged.update(extra)
        self._json.write(ACTIVE_STRATEGY_PATH, merged)
        self._invalidate(ACTIVE_STRATEGY_PATH)
        if old_strategy != strategy_name:
            self._bus.publish(EventTypes.STRATEGY_SWITCH, {
                "old_strategy": old_strategy,
                "new_strategy": strategy_name,
                **merged,
            }, source="data_manager")
        return merged

    # ── Orchestrator Signal ─────────────────────────────────────────────

    def get_orchestrator_signal(self) -> Optional[dict]:
        return self._read_cached(ORCHESTRATOR_PATH, HOT_TTL, "orchestrator_signal")

    # ── Agent Health ────────────────────────────────────────────────────

    def get_agent_health(self) -> Optional[dict]:
        return self._read_cached(AGENT_HEALTH_PATH, COLD_TTL, "agent_health")

    # ── Generic read/write ──────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        path = SHARED_DIR / f"{key}.json"
        return self._read_cached(path, HOT_TTL, key)

    def set(self, key: str, data: dict) -> None:
        path = SHARED_DIR / f"{key}.json"
        self._json.write(path, data)
        self._invalidate(path)

    # ── Cache Management ────────────────────────────────────────────────

    def invalidate_all(self) -> None:
        self._cache.clear()

    def invalidate(self, key: str) -> None:
        path = SHARED_DIR / f"{key}.json"
        self._invalidate(path)

    # ── Internal ────────────────────────────────────────────────────────

    def _read_cached(self, path: Path, ttl: float,
                     cache_key: str) -> Optional[Any]:
        entry = self._cache.get(cache_key)
        if entry is not None and entry.is_valid():
            return entry.value
        try:
            data = self._json.read(path)
        except (DataError, FileNotFoundError):
            return None
        if data is None:
            return None
        self._cache[cache_key] = _CacheEntry(data, ttl)
        return data

    def _invalidate(self, path: Path) -> None:
        stem = path.stem
        self._cache.pop(stem, None)


import threading