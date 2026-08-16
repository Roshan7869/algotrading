"""
In-Process Event Bus — pub/sub for state change notifications.

Replaces scattered JSON file IPC with structured event-driven communication.
When regime changes -> publish(REGIME_CHANGE) -> dashboard + strategy selector
re-render. When a trade closes -> publish(TRADE_CLOSE) -> risk gate updates.

Thread-safe, zero external dependencies (no Redis required).
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional, Union

logger = logging.getLogger(__name__)


class EventTypes(Enum):
    REGIME_CHANGE = "regime_change"
    SIGNAL_NEW = "signal_new"
    RISK_ALERT = "risk_alert"
    TRADE_OPEN = "trade_open"
    TRADE_CLOSE = "trade_close"
    STRATEGY_SWITCH = "strategy_switch"
    CIRCUIT_BREAKER_CHANGE = "circuit_breaker_change"
    POSITION_UPDATE = "position_update"
    PNL_UPDATE = "pnl_update"


@dataclass
class Event:
    event_type: EventTypes
    data: dict
    timestamp: str = ""
    source: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


SyncCallback = Callable[[Event], None]
AsyncCallback = Callable[[Event], Coroutine]


class _Subscription:
    __slots__ = ("callback", "is_async", "filter_fn")

    def __init__(self, callback: Union[SyncCallback, AsyncCallback],
                 is_async: bool, filter_fn: Optional[Callable[[Event], bool]] = None):
        self.callback = callback
        self.is_async = is_async
        self.filter_fn = filter_fn


class EventBus:
    """
    In-process thread-safe event bus.

    Supports both sync and async callbacks. Sync callbacks execute immediately
    in the publishing thread. Async callbacks are scheduled on the running
    event loop if available, otherwise executed synchronously as fallback.
    """

    def __init__(self):
        self._subscriptions: dict[EventTypes, list[_Subscription]] = defaultdict(list)
        self._lock = threading.Lock()
        self._history: list[Event] = []
        self._history_max = 200
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def subscribe(self, event_type: EventTypes,
                  callback: Union[SyncCallback, AsyncCallback],
                  filter_fn: Optional[Callable[[Event], bool]] = None) -> None:
        is_async = asyncio.iscoroutinefunction(callback)
        sub = _Subscription(callback=callback, is_async=is_async, filter_fn=filter_fn)
        with self._lock:
            self._subscriptions[event_type].append(sub)

    def unsubscribe(self, event_type: EventTypes,
                    callback: Union[SyncCallback, AsyncCallback]) -> None:
        with self._lock:
            subs = self._subscriptions.get(event_type, [])
            self._subscriptions[event_type] = [
                s for s in subs if s.callback != callback
            ]

    def publish(self, event_type: EventTypes, data: dict,
                source: str = "") -> Event:
        event = Event(event_type=event_type, data=data, source=source)
        self._record_history(event)
        subs = self._get_subscriptions(event_type)
        for sub in subs:
            if sub.filter_fn and not sub.filter_fn(event):
                continue
            try:
                if sub.is_async:
                    self._dispatch_async(sub.callback, event)
                else:
                    sub.callback(event)
            except Exception:
                logger.exception(
                    "EventBus callback error for %s on %s",
                    sub.callback, event_type.value,
                )
        return event

    def publish_sync(self, event_type: EventTypes, data: dict,
                     source: str = "") -> Event:
        return self.publish(event_type, data, source)

    async def publish_async(self, event_type: EventTypes, data: dict,
                            source: str = "") -> Event:
        event = Event(event_type=event_type, data=data, source=source)
        self._record_history(event)
        subs = self._get_subscriptions(event_type)
        for sub in subs:
            if sub.filter_fn and not sub.filter_fn(event):
                continue
            try:
                if sub.is_async:
                    await sub.callback(event)
                else:
                    sub.callback(event)
            except Exception:
                logger.exception(
                    "EventBus async callback error for %s on %s",
                    sub.callback, event_type.value,
                )
        return event

    def get_history(self, event_type: Optional[EventTypes] = None,
                    limit: int = 50) -> list[Event]:
        with self._lock:
            events = list(self._history)
        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    def subscription_count(self) -> dict[str, int]:
        with self._lock:
            return {et.value: len(subs) for et, subs in self._subscriptions.items() if subs}

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _get_subscriptions(self, event_type: EventTypes) -> list[_Subscription]:
        with self._lock:
            return list(self._subscriptions.get(event_type, []))

    def _dispatch_async(self, callback: AsyncCallback, event: Event) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(callback(event), self._loop)
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(callback(event))
            except RuntimeError:
                try:
                    asyncio.run(callback(event))
                except Exception:
                    logger.exception("EventBus: failed to dispatch async callback")

    def _record_history(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max:]


_event_bus_instance: Optional[EventBus] = None
_event_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _event_bus_instance
    if _event_bus_instance is None:
        with _event_bus_lock:
            if _event_bus_instance is None:
                _event_bus_instance = EventBus()
    return _event_bus_instance


def reset_event_bus() -> None:
    global _event_bus_instance
    with _event_bus_lock:
        if _event_bus_instance is not None:
            _event_bus_instance.clear_history()
        _event_bus_instance = None