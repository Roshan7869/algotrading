#!/usr/bin/env python3
"""Supervised dry-run launcher with circuit-breaker polling (EXECUTION_PLAN 0.3).

The supervisor owns one freqtrade process and one job: make it stop when the
risk picture turns bad.

Modes
-----
normal      ``supervise.py --config user_data/config_dryrun.json``
            Launches ``freqtrade trade -c <config>`` as a child process, then
            polls ``scripts/circuit_breaker.py --check`` every ``--check-interval``
            seconds. On PAUSED/UNKNOWN (or any state outside the continue set)
            it stops the bot — freqtrade REST ``/api/v1/stop`` first when the
            API answers, otherwise SIGTERM/SIGKILL on the child — and exits 3.
            The script exits when the bot exits; it never daemonizes.

preflight   ``supervise.py --preflight [--config ...]``
            Runs exactly one check (no bot launch) and exits 0 when the state
            is OK, 1 when it is PAUSED/UNKNOWN/failed. For start scripts.
            Note: the check is ``circuit_breaker.py --check``, and the breaker
            is the writer of ``shared_config/circuit_breaker.json`` — preflight
            reads its verdict back, it does not write risk state itself.

mock        ``supervise.py --mock-balance '1000,-4%,-8%'``
            Feeds a synthetic balance sequence through the *same* poll/decide/
            stop path with a mock controller. Never launches freqtrade, never
            calls the REST API, never writes shared_config/. Fully offline.
            Percent entries are drawdowns measured from the first (absolute)
            balance, e.g. ``-4%`` on ``1000`` is 960.0.

Why a 4% pause cap?
-------------------
``scripts/circuit_breaker.py`` keeps the last-resort tiers (25% warning,
40% critical). The supervisor is deliberately tighter: the workspace's own
risk layer already calls a 4% drawdown PAUSED
(``shared_config/circuit_breaker.json``: "Weekly drawdown -8.17% > 4.0%").
A paper month that loses 4% is not a paper month worth continuing, so the
default ``--max-drawdown`` is 4%; raise it explicitly for longer sessions.
The supervisor is a strict superset of the breaker: a breaker PAUSED/CRITICAL
always stops the bot, and a supervisor drawdown breach stops it earlier.

Usage
-----
  python scripts/supervise.py --preflight --config user_data/config_dryrun.json
  python scripts/supervise.py --config user_data/config_dryrun.json --check-interval 300
  python scripts/supervise.py --mock-balance '1000,-4%,-8%'
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BREAKER_SCRIPT = REPO_ROOT / "scripts" / "circuit_breaker.py"
DEFAULT_STATE_FILE = REPO_ROOT / "shared_config" / "supervise_state.json"
MOCK_STATE_FILE = REPO_ROOT / "reports" / "phase0" / "supervise_mock_state.json"
SIGNAL_FILE = Path(os.getenv("SHARED_CONFIG_DIR") or (REPO_ROOT / "shared_config")) / "circuit_breaker.json"
API_PASSWORD_FILE = Path.home() / ".config" / "freqtrade" / "api_password"
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

EXIT_OK = 0
EXIT_PREFLIGHT_FAIL = 1
EXIT_LAUNCH_FAILED = 2
EXIT_STOPPED = 3

# States that mean "keep the bot running". Everything else stops the bot —
# fail closed, so a typo or a new upstream state never reads as healthy.
CONTINUE_STATES = frozenset({"OK", "HEALTHY", "WARNING", "CAUTION", "RESTRICTED"})
STOP_STATES = frozenset({"PAUSED", "HALT", "LIQUIDATE", "CRITICAL", "UNKNOWN", "ERROR", "FAILED"})

DEFAULT_PAUSE_DRAWDOWN = 0.04
DEFAULT_WARN_DRAWDOWN = 0.02


# --------------------------------------------------------------------------- utils


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_line(message: str) -> None:
    print(f"[{now()}] supervise: {message}", flush=True)


def _finite(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_drawdown(value) -> float | None:
    """Return a drawdown as a *fraction*.

    Producers in this repo disagree: ``scripts/circuit_breaker.py`` stores a
    fraction (0.04), while the agents' risk layer stores true percent (8.17).
    Values above 1.0 can only be percent, so they are divided by 100.
    """
    number = _finite(value)
    if number is None:
        return None
    number = abs(number)
    if number > 1.0:
        number = number / 100.0
    return number


def parse_ratio(text: str | float) -> float:
    """Parse ``0.04``, ``4%`` or ``4`` into a fraction."""
    if isinstance(text, (int, float)):
        value = float(text)
        return value / 100.0 if value > 1.0 else value
    raw = str(text).strip()
    if raw.endswith("%"):
        return float(raw[:-1]) / 100.0
    value = float(raw)
    return value / 100.0 if value > 1.0 else value


def extract_json_object(text: str | None) -> dict | None:
    """Last JSON object in a blob of text (logs may precede the payload)."""
    if not text:
        return None
    stripped = text.strip()
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def parse_mock_balance(spec: str) -> list[float | None]:
    """``'1000,-4%,-8%'`` -> ``[1000.0, 960.0, 920.0]``.

    Percent entries are relative to the first absolute balance (the peak), and
    the literal tokens ``none``/``null``/``?`` inject an unreadable balance so
    the UNKNOWN path can be exercised.
    """
    parts = [part.strip() for part in str(spec).split(",") if part.strip()]
    if not parts:
        raise ValueError("empty --mock-balance sequence")
    values: list[float | None] = []
    initial: float | None = None
    for part in parts:
        lowered = part.lower()
        if lowered in {"none", "null", "?", "unknown"}:
            values.append(None)
            continue
        if part.endswith("%"):
            if initial is None:
                raise ValueError("the first --mock-balance entry must be an absolute balance")
            values.append(initial * (1.0 + float(part[:-1]) / 100.0))
            continue
        balance = float(part)
        if initial is None:
            initial = balance
        values.append(balance)
    return values


# ----------------------------------------------------------------------- decisions


@dataclass
class Observation:
    """One risk observation, however it was produced."""

    state: str | None
    drawdown: float | None
    balance: float | None = None
    peak: float | None = None
    source: str = "unknown"
    detail: str = ""


@dataclass
class Policy:
    pause_drawdown: float = DEFAULT_PAUSE_DRAWDOWN
    warn_drawdown: float = DEFAULT_WARN_DRAWDOWN


@dataclass
class Decision:
    state: str
    should_stop: bool
    reasons: list[str] = field(default_factory=list)
    observation: Observation | None = None

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "no reason recorded"


def decide(observation: Observation, policy: Policy) -> Decision:
    """Map an observation to OK / PAUSED / UNKNOWN. Never upgrades to OK."""
    reasons: list[str] = []
    breaker_state = (observation.state or "").strip().upper()
    state = "OK"

    if not breaker_state:
        state = "UNKNOWN"
        reasons.append("breaker reported no state (fail-closed)")
    elif breaker_state == "UNKNOWN":
        state = "UNKNOWN"
        reasons.append("breaker_state=UNKNOWN (balance unreadable, fail-closed)")
    elif breaker_state not in CONTINUE_STATES:
        state = "PAUSED" if breaker_state in STOP_STATES else "UNKNOWN"
        reasons.append(f"breaker_state={breaker_state} is not in {sorted(CONTINUE_STATES)}")
    elif breaker_state in {"WARNING", "CAUTION", "RESTRICTED"}:
        reasons.append(f"breaker_state={breaker_state} (size reduction, not a stop)")

    drawdown = observation.drawdown
    if drawdown is None:
        if state == "OK":
            state = "UNKNOWN"
        reasons.append("drawdown unavailable (fail-closed)")
    elif drawdown >= policy.pause_drawdown:
        state = "PAUSED"
        reasons.append(
            f"drawdown {drawdown:.2%} >= pause threshold {policy.pause_drawdown:.2%}"
        )
    elif drawdown >= policy.warn_drawdown:
        reasons.append(f"drawdown {drawdown:.2%} >= warn threshold {policy.warn_drawdown:.2%}")

    return Decision(state=state, should_stop=state in {"PAUSED", "UNKNOWN"}, reasons=reasons,
                    observation=observation)


# ------------------------------------------------------------------------- probes


class BreakerProbe:
    """Runs ``scripts/circuit_breaker.py --check`` and parses its JSON."""

    def __init__(self, breaker: Path = BREAKER_SCRIPT, config: Path | None = None,
                 timeout: float = 90.0, python: str | None = None):
        self.breaker = Path(breaker)
        self.config = Path(config) if config else None
        self.timeout = timeout
        self.python = python or sys.executable

    def __call__(self) -> Observation:
        env = dict(os.environ)
        if self.config is not None:
            # The breaker resolves api_server from FREQTRADE_CONFIG; without it
            # it only knows config.json/config_live_real.json and would report
            # UNKNOWN for a dry-run session.
            env["FREQTRADE_CONFIG"] = str(self.config)
        try:
            proc = subprocess.run(
                [self.python, str(self.breaker), "--check"],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed on any launch error
            return Observation(state="UNKNOWN", drawdown=None, source="breaker_cli",
                               detail=f"breaker check failed to run: {exc}")

        payload = extract_json_object(proc.stdout)
        if not isinstance(payload, dict):
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            return Observation(state="UNKNOWN", drawdown=None, source="breaker_cli",
                               detail=f"unparseable breaker output rc={proc.returncode}: "
                                      f"{detail[-1] if detail else '<empty>'}")

        state = str(payload.get("state") or "UNKNOWN").strip().upper()
        drawdown = normalize_drawdown(payload.get("drawdown_pct"))
        balance = _finite(payload.get("current_balance"))
        peak = _finite(payload.get("peak_balance"))
        if balance is None or peak is None:
            balance, peak = self._signal_balances()
        return Observation(state=state, drawdown=drawdown, balance=balance, peak=peak,
                           source="breaker_cli", detail=f"rc={proc.returncode}")

    @staticmethod
    def _signal_balances() -> tuple[float | None, float | None]:
        try:
            payload = json.loads(SIGNAL_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None, None
        return _finite(payload.get("current_balance")), _finite(payload.get("peak_balance"))


class JsonProbe:
    """Offline probe: reads a canned breaker payload from a JSON file."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def __call__(self) -> Observation:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return Observation(state="UNKNOWN", drawdown=None, source="probe_json",
                               detail=f"cannot read {self.path}: {exc}")
        if not isinstance(payload, dict):
            return Observation(state="UNKNOWN", drawdown=None, source="probe_json",
                               detail=f"{self.path} is not a JSON object")
        return Observation(
            state=str(payload.get("state") or "UNKNOWN").strip().upper(),
            drawdown=normalize_drawdown(payload.get("drawdown_pct")),
            balance=_finite(payload.get("current_balance")),
            peak=_finite(payload.get("peak_balance")),
            source="probe_json",
            detail=str(self.path),
        )


class MockProbe:
    """Synthetic balance sequence; drawdown is computed with the breaker's math."""

    def __init__(self, balances: list[float | None]):
        if not balances:
            raise ValueError("mock sequence is empty")
        self.balances = list(balances)
        self.index = 0
        self.peak: float | None = None

    @property
    def consumed(self) -> int:
        return self.index

    def __call__(self) -> Observation:
        if self.index >= len(self.balances):
            raise RuntimeError("mock balance sequence exhausted")
        balance = self.balances[self.index]
        self.index += 1
        if balance is None:
            return Observation(state="UNKNOWN", drawdown=None, source="mock",
                               detail=f"mock balance #{self.index} unreadable")
        if self.peak is None or balance > self.peak:
            self.peak = balance
        drawdown = max(0.0, (self.peak - balance) / self.peak)
        return Observation(state="OK", drawdown=drawdown, balance=balance, peak=self.peak,
                           source="mock", detail=f"mock balance #{self.index}")


# --------------------------------------------------------------------- controllers


class MockBot:
    """Stand-in controller: records that stop() was called and when."""

    def __init__(self, log=log_line):
        self.log = log
        self.started = False
        self.stopped = False
        self.stop_state: str | None = None
        self.stop_reason: str | None = None
        self.stop_method: str | None = None

    def describe(self) -> str:
        return "mock-bot (no process)"

    def start(self) -> None:
        self.started = True
        self.log("mock bot started (freqtrade NOT launched)")

    def poll(self) -> int | None:
        return None  # always alive until stop() is called

    def stop(self, state: str, reason: str) -> str:
        self.stopped = True
        self.stop_state = state
        self.stop_reason = reason
        self.stop_method = "mock:stop"
        self.log(f"mock bot stop() called state={state} reason={reason}")
        return self.stop_method


class FreqtradeController:
    """Real controller: one ``freqtrade trade -c <config>`` child process."""

    def __init__(self, config: Path, log=log_line, stop_timeout: float = 45.0,
                 rest_timeout: float = 5.0, freqtrade_cmd: list[str] | None = None):
        self.config = Path(config)
        self.log = log
        self.stop_timeout = stop_timeout
        self.rest_timeout = rest_timeout
        self.cmd = list(freqtrade_cmd) if freqtrade_cmd else self._default_cmd()
        self.child: subprocess.Popen | None = None

    def _default_cmd(self) -> list[str]:
        local = REPO_ROOT / ".venv" / "Scripts" / "freqtrade.exe"
        if local.exists():
            return [str(local)]
        found = shutil.which("freqtrade")
        if found:
            return [found]
        return [sys.executable, "-m", "freqtrade"]

    def describe(self) -> str:
        return f"{' '.join(self.cmd)} trade -c {self.config}"

    def start(self) -> None:
        if not self.config.exists():
            raise FileNotFoundError(f"config not found: {self.config}")
        env = dict(os.environ)
        env["FREQTRADE_CONFIG"] = str(self.config)
        self.cmd_line = self.cmd + ["trade", "-c", str(self.config)]
        self.log(f"launching: {' '.join(self.cmd_line)}")
        self.child = subprocess.Popen(self.cmd_line, cwd=str(REPO_ROOT), env=env)

    def poll(self) -> int | None:
        return None if self.child is None else self.child.poll()

    def stop(self, state: str, reason: str) -> str:
        self.log(f"stopping bot state={state} reason={reason}")
        method = self._rest_stop()
        if method is None:
            return self._terminate()
        if self._wait_for_exit(self.stop_timeout):
            return method
        return f"{method}+{self._terminate()}"

    def _rest_stop(self) -> str | None:
        """POST /api/v1/stop. Returns 'rest_api' on success, None otherwise."""
        credentials = self._api_credentials()
        if credentials is None:
            self.log("REST stop unavailable (no API password configured)")
            return None
        username, password, port = credentials
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        request = urllib.request.Request(
            f"http://127.0.0.1:{int(port)}/api/v1/stop",
            data=b"",
            method="POST",
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.rest_timeout) as response:
                self.log(f"REST stop accepted (HTTP {response.status})")
            return "rest_api"
        except Exception as exc:  # noqa: BLE001
            self.log(f"REST stop failed ({exc}); falling back to process signal")
            return None

    def _api_credentials(self) -> tuple[str, str, int] | None:
        """Resolve (username, password, port) for *this* config's api_server.

        Mirrors scripts/circuit_breaker.py: explicit env vars win, then the
        ${ENV_VAR} placeholder is expanded from the environment, then the
        0600 password file. Returns None when no password can be resolved.
        """
        try:
            config = json.loads(self.config.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.log(f"cannot read config for REST stop: {exc}")
            return None
        api = config.get("api_server") if isinstance(config, dict) else None
        if not isinstance(api, dict) or api.get("enabled") is False:
            return None
        try:
            port = int(os.getenv("FREQTRADE_API_PORT") or api.get("listen_port") or 8080)
        except (TypeError, ValueError):
            port = 8080
        username = os.getenv("FREQTRADE_API_USERNAME") or api.get("username") or "freqtrader"

        password = os.getenv("FREQTRADE_API_PASSWORD") or ""
        if not password:
            raw = str(api.get("password") or "")
            placeholder = PLACEHOLDER_RE.fullmatch(raw)
            password = os.getenv(placeholder.group(1), "") if placeholder else raw
        if not password:
            try:
                password = API_PASSWORD_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                password = ""
        if not password:
            return None
        return username, password, port

    def _wait_for_exit(self, timeout: float) -> bool:
        if self.child is None:
            return True
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if self.child.poll() is not None:
                return True
            time.sleep(0.5)
        return self.child.poll() is not None

    def _terminate(self) -> str:
        if self.child is None:
            return "no_child"
        if self.child.poll() is not None:
            return "already_exited"
        self.log("sending SIGTERM to freqtrade child")
        try:
            self.child.terminate()
        except Exception as exc:  # noqa: BLE001
            self.log(f"SIGTERM failed: {exc}")
        if self._wait_for_exit(min(self.stop_timeout, 30.0)):
            return "sigterm"
        self.log("child still alive after SIGTERM; sending SIGKILL")
        try:
            self.child.kill()
        except Exception as exc:  # noqa: BLE001
            self.log(f"SIGKILL failed: {exc}")
        self._wait_for_exit(10.0)
        return "sigkill"


# ----------------------------------------------------------------------- supervisor


class Supervisor:
    def __init__(self, probe, policy: Policy | None = None,
                 state_path: Path = DEFAULT_STATE_FILE, log=log_line,
                 interval: float = 300.0, mode: str = "live"):
        self.probe = probe
        self.policy = policy or Policy()
        self.state_path = Path(state_path)
        self.log = log
        self.interval = interval
        self.mode = mode
        self.polls = 0
        self.history: list[dict] = []
        self.last_decision: Decision | None = None

    # -- state file (atomic write; readers never see a half-written file)

    def write_state(self, state: str, action: str, decision: Decision | None = None,
                    extra: dict | None = None) -> dict:
        observation = decision.observation if decision else None
        drawdown = observation.drawdown if observation else None
        payload = {
            "timestamp": now(),
            "state": state,
            "action": action,
            "mode": self.mode,
            "polls": self.polls,
            "drawdown": round(drawdown, 6) if drawdown is not None else None,
            "drawdown_pct": round(drawdown * 100.0, 2) if drawdown is not None else None,
            "pause_threshold_pct": round(self.policy.pause_drawdown * 100.0, 2),
            "balance": observation.balance if observation else None,
            "peak_balance": observation.peak if observation else None,
            "breaker_state": observation.state if observation else None,
            "source": observation.source if observation else None,
            "reasons": decision.reasons if decision else [],
        }
        if extra:
            payload.update(extra)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)
        return payload

    # -- one poll

    def poll_once(self) -> Decision:
        observation = self.probe()
        decision = decide(observation, self.policy)
        self.polls += 1
        self.last_decision = decision
        drawdown_text = "unknown" if observation.drawdown is None else f"{observation.drawdown:.2%}"
        self.log(
            f"poll={self.polls} source={observation.source} breaker={observation.state} "
            f"drawdown={drawdown_text} state={decision.state} "
            f"action={'stop_bot' if decision.should_stop else 'continue'}"
            + (f" reasons={decision.reason}" if decision.reasons else "")
        )
        self.write_state(decision.state,
                         "stop_bot" if decision.should_stop else "continue", decision)
        self.history.append({"poll": self.polls, "state": decision.state,
                             "drawdown": observation.drawdown,
                             "breaker_state": observation.state})
        return decision

    # -- main loop

    def run(self, controller, max_polls: int | None = None, startup_grace: float = 0.0,
            sleep: bool = True) -> int:
        controller.start()
        self.log(f"supervising {controller.describe()} interval={self.interval:g}s "
                 f"pause_cap={self.policy.pause_drawdown:.2%}")
        if startup_grace > 0 and sleep:
            self._grace(controller, startup_grace)

        while True:
            exit_code = controller.poll()
            if exit_code is not None:
                self.log(f"bot exited on its own rc={exit_code}; supervisor exiting")
                self.write_state("STOPPED", "bot_exited", self.last_decision,
                                 {"exit_code": exit_code})
                return EXIT_OK if exit_code == 0 else int(exit_code)

            decision = self.poll_once()
            if decision.should_stop:
                method = controller.stop(decision.state, decision.reason)
                self.write_state(decision.state, "stop_bot", decision,
                                 {"stop_method": method})
                self.log(f"STOP state={decision.state} via={method} after {self.polls} poll(s); "
                         f"supervisor exiting {EXIT_STOPPED}")
                return EXIT_STOPPED

            if max_polls is not None and self.polls >= max_polls:
                self.log(f"sequence exhausted after {self.polls} poll(s) without a stop condition")
                if isinstance(controller, MockBot):
                    self.write_state(decision.state, "sequence_exhausted", decision)
                return EXIT_OK

            if sleep and self.interval > 0:
                time.sleep(self.interval)

    def _grace(self, controller, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if controller.poll() is not None:
                return
            time.sleep(1.0)


# ----------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Supervise a freqtrade dry-run session with circuit-breaker polling.",
    )
    parser.add_argument("--config", help="freqtrade config (dry-run only)")
    parser.add_argument("--check-interval", type=float, default=300.0,
                        help="seconds between breaker checks (default 300)")
    parser.add_argument("--max-drawdown", default=f"{DEFAULT_PAUSE_DRAWDOWN:.0%}",
                        help="supervisor pause cap; '0.04' or '4 percent' or '4%%' "
                             "(default: 4 percent)")
    parser.add_argument("--warn-drawdown", default=f"{DEFAULT_WARN_DRAWDOWN:.0%}",
                        help="log-only warning level (default: 2 percent)")
    parser.add_argument("--state-file", help="where to write supervise state JSON")
    parser.add_argument("--preflight", action="store_true",
                        help="run one check and exit 0 (OK) / 1 (PAUSED/UNKNOWN)")
    parser.add_argument("--mock-balance", metavar="SEQ",
                        help="offline sequence, e.g. '1000,-4%%,-8%%' (no freqtrade launched)")
    parser.add_argument("--probe-json", help="read the breaker payload from this JSON file "
                                             "instead of calling the API (offline)")
    parser.add_argument("--startup-grace", type=float, default=20.0,
                        help="seconds to wait for the bot to come up before the first poll")
    parser.add_argument("--log-file", help="also append log lines to this file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.log_file:
        path = Path(args.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)

        def _log(message: str) -> None:
            line = f"[{now()}] supervise: {message}"
            print(line, flush=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        logger = _log
    else:
        logger = log_line

    policy = Policy(pause_drawdown=parse_ratio(args.max_drawdown),
                    warn_drawdown=parse_ratio(args.warn_drawdown))
    config = Path(args.config).resolve() if args.config else None

    # ---- offline mock mode -------------------------------------------------
    if args.mock_balance:
        balances = parse_mock_balance(args.mock_balance)
        state_path = Path(args.state_file) if args.state_file else MOCK_STATE_FILE
        supervisor = Supervisor(MockProbe(balances), policy, state_path, logger, interval=0.0,
                                mode="mock")
        bot = MockBot(logger)
        logger(f"mock sequence {args.mock_balance} -> {balances}")
        exit_code = supervisor.run(bot, max_polls=len(balances), sleep=False)
        summary = {
            "event": "supervise_mock",
            "exit_code": exit_code,
            "polls": supervisor.polls,
            "values_consumed": supervisor.probe.consumed,
            "stop_called": bot.stopped,
            "stop_state": bot.stop_state,
            "state_file": str(state_path),
            "final_state": supervisor.last_decision.state if supervisor.last_decision else None,
        }
        print(json.dumps(summary, indent=2), flush=True)
        return exit_code

    probe = JsonProbe(Path(args.probe_json)) if args.probe_json else BreakerProbe(config=config)

    # ---- preflight ---------------------------------------------------------
    if args.preflight:
        decision = decide(probe(), policy)
        payload = {
            "event": "preflight",
            "state": decision.state,
            "should_stop": decision.should_stop,
            "reasons": decision.reasons,
            "observation": {
                "source": decision.observation.source,
                "breaker_state": decision.observation.state,
                "drawdown": decision.observation.drawdown,
                "detail": decision.observation.detail,
            },
        }
        print(json.dumps(payload, indent=2), flush=True)
        code = EXIT_OK if not decision.should_stop else EXIT_PREFLIGHT_FAIL
        logger(f"preflight state={decision.state} -> exit {code}")
        return code

    # ---- normal supervised launch -----------------------------------------
    if config is None:
        logger("error: --config is required (or use --preflight / --mock-balance)")
        return EXIT_LAUNCH_FAILED
    if not config.exists():
        logger(f"error: config not found: {config}")
        return EXIT_LAUNCH_FAILED
    if args.check_interval <= 0:
        logger("error: --check-interval must be > 0 in supervised mode")
        return EXIT_LAUNCH_FAILED

    state_path = Path(args.state_file) if args.state_file else DEFAULT_STATE_FILE
    controller = FreqtradeController(config, logger)
    supervisor = Supervisor(probe, policy, state_path, logger,
                            interval=args.check_interval, mode="live")
    try:
        return supervisor.run(controller, startup_grace=args.startup_grace)
    except OSError as exc:
        logger(f"error: cannot launch freqtrade: {exc}")
        return EXIT_LAUNCH_FAILED
    except KeyboardInterrupt:
        logger("interrupted; stopping bot")
        controller.stop("UNKNOWN", "supervisor interrupted (operator)")
        return 130


if __name__ == "__main__":
    sys.exit(main())
