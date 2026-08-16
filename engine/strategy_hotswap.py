"""
Strategy Hot-Swap — watches for strategy change events and applies them.

Subscribes to STRATEGY_SWITCH events from EventBus and:
  1. Sends Freqtrade RPC to reload config
  2. Falls back to container restart if RPC fails
  3. Logs all switches with timestamps and reasons
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.data_manager import DataManager
from core.event_bus import Event, EventTypes, get_event_bus

logger = logging.getLogger(__name__)

FREQTRADE_API_BASE = "http://localhost:8080/api/v1"
STRATEGIES_DIR = Path(__file__).parent.parent / "user_data" / "strategies"


class StrategyHotSwap:
    """
    Watches for strategy switch events and applies them to Freqtrade.

    Uses EventBus subscription for real-time notifications and Freqtrade
    REST API for config reload. Falls back to container restart.
    """

    def __init__(self, data_manager: Optional[DataManager] = None):
        self._dm = data_manager or DataManager()
        self._bus = get_event_bus()
        self._switch_log: list[dict] = []
        self._current_strategy: Optional[str] = None
        self._initialized = False

    def start(self) -> None:
        """Subscribe to STRATEGY_SWITCH events and load current state."""
        self._bus.subscribe(EventTypes.STRATEGY_SWITCH, self._on_strategy_switch)
        current = self._dm.get_active_strategy()
        if current:
            self._current_strategy = current.get("strategy",
                                       current.get("name", ""))
        self._initialized = True
        logger.info("StrategyHotSwap started, current strategy: %s",
                     self._current_strategy)

    def stop(self) -> None:
        """Unsubscribe from events."""
        self._bus.unsubscribe(EventTypes.STRATEGY_SWITCH,
                               self._on_strategy_switch)
        self._initialized = False

    @property
    def current_strategy(self) -> str:
        if self._current_strategy is None:
            current = self._dm.get_active_strategy()
            if current:
                self._current_strategy = current.get("strategy",
                                           current.get("name", ""))
        return self._current_strategy or ""

    def switch_to(self, strategy_name: str,
                  reason: str = "manual_hotswap") -> dict:
        """
        Explicitly switch to a strategy. Updates active_strategy.json,
        publishes STRATEGY_SWITCH event, and applies to Freqtrade.
        """
        from engine.regime_selector import RegimeSelector
        selector = RegimeSelector(data_manager=self._dm)
        result = selector.hotswap_strategy(strategy_name, reason=reason)
        self._apply_to_freqtrade(strategy_name)
        return result

    def get_switch_log(self, limit: int = 50) -> list[dict]:
        return list(self._switch_log[-limit:])

    # ── Internal ───────────────────────────────────────────────────────

    def _on_strategy_switch(self, event: Event) -> None:
        """
        EventBus callback — triggered when STRATEGY_SWITCH is published.
        """
        new_strategy = event.data.get("new_strategy", "")
        old_strategy = event.data.get("old_strategy", "")
        reason = event.data.get("switch_reason", "event_driven")

        if not new_strategy:
            logger.warning("STRATEGY_SWITCH event with empty strategy name")
            return

        if new_strategy == self._current_strategy:
            logger.debug("Strategy %s already active, skipping", new_strategy)
            return

        logger.info("Strategy switch event: %s -> %s (reason: %s)",
                     old_strategy, new_strategy, reason)

        self._apply_to_freqtrade(new_strategy)
        self._current_strategy = new_strategy

    def _apply_to_freqtrade(self, strategy_name: str) -> dict:
        """
        Apply strategy change to Freqtrade via RPC.
        POST /api/v1/reload_config to reload with new strategy.
        """
        result = {
            "strategy": strategy_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rpc_reload": False,
            "restart_attempted": False,
            "errors": [],
        }

        try:
            import urllib.request
            import urllib.error

            url = f"{FREQTRADE_API_BASE}/reload_config"
            req = urllib.request.Request(url, method="POST")
            req.add_header("Content-Type", "application/json")

            payload = json.dumps({"strategy": strategy_name}).encode()
            req.data = payload

            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                result["rpc_reload"] = True
                logger.info("Freqtrade reload_config OK: %s", body[:200])

        except ImportError:
            result["errors"].append("urllib not available")
        except urllib.error.URLError as e:
            logger.warning("Freqtrade RPC failed: %s", e)
            result["errors"].append(f"RPC URLError: {e.reason}")
            result["restart_attempted"] = self._restart_freqtrade(strategy_name)
        except Exception as e:
            logger.warning("Freqtrade RPC error: %s", e)
            result["errors"].append(f"RPC error: {e}")
            result["restart_attempted"] = self._restart_freqtrade(strategy_name)

        log_entry = {
            **result,
            "old_strategy": self._current_strategy,
        }
        self._switch_log.append(log_entry)
        return result

    def _restart_freqtrade(self, strategy_name: str) -> bool:
        """
        Attempt to restart Freqtrade container via docker/subprocess.
        Only used as fallback when RPC is unavailable.
        """
        try:
            import subprocess
            env_strategy = f"FREQTRADE_STRATEGY={strategy_name}"
            result = subprocess.run(
                ["docker", "restart", "freqtrade"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                logger.info("Freqtrade container restarted for strategy %s",
                            strategy_name)
                return True
            logger.warning("Docker restart failed: %s", result.stderr[:200])
        except FileNotFoundError:
            logger.info("Docker not available, skipping container restart")
        except subprocess.TimeoutExpired:
            logger.warning("Docker restart timed out")
        except Exception as e:
            logger.warning("Container restart error: %s", e)

        return False