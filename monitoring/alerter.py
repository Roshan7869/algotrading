"""
Alerter — webhook/console alerts for risk events, PnL, and circuit breaker.

Monitors shared_config JSON files for state changes and publishes alerts
to configured webhooks (Slack, generic) and the signal bus.

Usage:
  python3 monitoring/alerter.py --watch   # continuous monitoring
  python3 monitoring/alerter.py --once    # single check + alert
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

PROJECT_ROOT = Path(__file__).parent.parent
SHARED_DIR = PROJECT_ROOT / "shared_config"

CHECK_INTERVAL = 60
BREAKER_PATH = SHARED_DIR / "circuit_breaker.json"
PNL_BUS_PATH = SHARED_DIR / "signal_bus_pnl.json"
SIGNAL_BUS_PATH = SHARED_DIR / "signal_bus_signals.json"
AGENT_HEALTH_PATH = SHARED_DIR / "agent_health.json"

DEFAULT_CONFIG = {
    "slack_webhook_url": "",
    "generic_webhook_url": "",
    "min_pnl_alert": 50.0,
    "max_signal_age": 300,
    "alert_on_critical_breaker": True,
    "alert_on_warning_breaker": True,
    "alert_on_large_pnl": True,
    "alert_on_stale_signals": True,
}


def load_config() -> dict:
    config_path = SHARED_DIR / "alerter_config.json"
    if config_path.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(config_path.read_text())}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_CONFIG)


def send_webhook(url: str, payload: dict) -> bool:
    if not url:
        return False
    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        urlopen(req, timeout=5)
        return True
    except (URLError, OSError):
        return False


def send_slack(cfg: dict, message: str, color: str = "#ff4444"):
    webhook = cfg.get("slack_webhook_url", "")
    if not webhook:
        return
    send_webhook(webhook, {
        "attachments": [{
            "color": color,
            "text": message,
            "ts": datetime.now(timezone.utc).timestamp(),
        }]
    })


def send_generic(cfg: dict, event: str, severity: str, message: str):
    url = cfg.get("generic_webhook_url", "")
    if not url:
        return
    send_webhook(url, {
        "event": event,
        "severity": severity,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def read_json_safe(path: Path) -> Optional[dict]:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return None


def read_json_list(path: Path) -> list:
    try:
        if path.exists():
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


class Alerter:
    def __init__(self, config: Optional[dict] = None):
        self.cfg = config or load_config()
        self._last_breaker_state = None
        self._last_pnl_count = 0
        self._last_signal_count = 0
        self._alert_count = 0

    def check_breaker(self) -> list:
        alerts = []
        data = read_json_safe(BREAKER_PATH)
        if not data:
            return alerts

        state = data.get("state", "UNKNOWN")
        drawdown = abs(data.get("drawdown_pct", 0))
        monthly = data.get("monthly_pnl_pct", 0)

        if self._last_breaker_state is not None and state != self._last_breaker_state:
            color = "#00ff00" if state == "NORMAL" else ("#ffaa00" if state in ("CAUTION", "RESTRICTED") else "#ff4444")
            msg = f"Circuit Breaker: {self._last_breaker_state} → {state} (drawdown: {drawdown:.1f}%, monthly: {monthly:+.1f}%)"
            if state in ("HALT", "LIQUIDATE") and self.cfg.get("alert_on_critical_breaker"):
                send_slack(self.cfg, msg, color)
                send_generic(self.cfg, "circuit_breaker", "critical", msg)
                alerts.append({"type": "breaker", "severity": "critical", "message": msg})
            elif state in ("CAUTION", "RESTRICTED") and self.cfg.get("alert_on_warning_breaker"):
                send_slack(self.cfg, msg, color)
                alerts.append({"type": "breaker", "severity": "warning", "message": msg})

        self._last_breaker_state = state
        return alerts

    def check_pnl(self) -> list:
        alerts = []
        if not self.cfg.get("alert_on_large_pnl"):
            return alerts

        events = read_json_list(PNL_BUS_PATH)
        count = len(events)

        if count > self._last_pnl_count:
            threshold = self.cfg.get("min_pnl_alert", 50.0)
            for evt in events[self._last_pnl_count:]:
                pnl = abs(evt.get("data", {}).get("pnl", 0))
                if pnl >= threshold:
                    pair = evt.get("data", {}).get("pair", "unknown")
                    ts = evt.get("timestamp", "")
                    direction = "PROFIT" if evt.get("data", {}).get("pnl", 0) > 0 else "LOSS"
                    msg = f"Large PnL ({direction}): {pair} ${pnl:.2f} at {ts}"
                    send_slack(self.cfg, msg, "#00ff00" if direction == "PROFIT" else "#ff4444")
                    alerts.append({"type": "pnl", "severity": "info" if direction == "PROFIT" else "warning", "message": msg})

        self._last_pnl_count = count
        return alerts

    def check_signal_freshness(self) -> list:
        alerts = []
        if not self.cfg.get("alert_on_stale_signals"):
            return alerts

        events = read_json_list(SIGNAL_BUS_PATH)
        if events:
            last = events[-1]
            ts_str = last.get("timestamp", "")
            try:
                last_ts = datetime.fromisoformat(ts_str).timestamp()
                age = time.time() - last_ts
                max_age = self.cfg.get("max_signal_age", 300)
                if age > max_age:
                    msg = f"Signals stale: {int(age)}s since last signal (threshold: {max_age}s)"
                    send_slack(self.cfg, msg, "#ffaa00")
                    alerts.append({"type": "freshness", "severity": "warning", "message": msg})
            except (ValueError, TypeError):
                pass

        return alerts

    def check_all(self) -> list:
        alerts = []
        alerts.extend(self.check_breaker())
        alerts.extend(self.check_pnl())
        alerts.extend(self.check_signal_freshness())
        self._alert_count += len(alerts)
        return alerts

    def get_stats(self) -> dict:
        return {
            "total_alerts_fired": self._alert_count,
            "last_breaker_state": self._last_breaker_state,
            "config": {k: v for k, v in self.cfg.items() if "webhook" not in k},
        }


def write_state(state: dict):
    path = SHARED_DIR / "alerter_state.json"
    try:
        path.write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def load_state() -> dict:
    path = SHARED_DIR / "alerter_state.json"
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Alerter — webhook alerts for trading events")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring")
    parser.add_argument("--once", action="store_true", help="Single check")
    parser.add_argument("--config", type=str, help="Path to config JSON")
    args = parser.parse_args()

    cfg = load_config()
    if args.config:
        custom_path = Path(args.config)
        if custom_path.exists():
            cfg.update(json.loads(custom_path.read_text()))

    alerter = Alerter(cfg)

    if args.watch:
        print(f"[alerter] Watching every {CHECK_INTERVAL}s  (Ctrl+C to stop)")
        while True:
            alerts = alerter.check_all()
            if alerts:
                for a in alerts:
                    print(f"[{a['severity']}] {a['message']}")
            time.sleep(CHECK_INTERVAL)
    elif args.once:
        alerts = alerter.check_all()
        for a in alerts:
            print(f"[{a['severity']}] {a['message']}")
        if not alerts:
            print("[alerter] All clear — no alerts")
    else:
        alerts = alerter.check_all()
        print(f"[alerter] Checked: {len(alerts)} alerts")
        for a in alerts:
            print(f"  [{a['severity']}] {a['message']}")
        if not alerts:
            print("  (none — all clear)")


if __name__ == "__main__":
    main()
