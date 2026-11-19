#!/usr/bin/env python3
"""Plain-python tests for scripts/supervise.py (EXECUTION_PLAN 0.3).

pytest is not installed in .venv, so this file is a self-contained runner:

    .venv/Scripts/python.exe tests/test_supervise.py

Every case prints PASS/FAIL with the measured values; the runner exits non-zero
if anything fails. The centrepiece is ``mock_drawdown_demo``: it feeds
``1000, -4%, -8%`` through the real poll/decide/stop path (no freqtrade, no
network) and asserts that the -4% poll writes PAUSED and calls stop() inside
that same poll.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import supervise  # noqa: E402
import secrets_scan as ss  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_state(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class DummyChild:
    """Stands in for subprocess.Popen without spawning anything."""

    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9


# --------------------------------------------------------------------- parsing


@case
def parse_mock_balance_sequence():
    values = supervise.parse_mock_balance("1000,-4%,-8%")
    check(values == [1000.0, 960.0, 920.0], f"unexpected parse: {values}")
    check(supervise.parse_mock_balance("1000,None,-4%") == [1000.0, None, 960.0],
          "None token not parsed as unreadable balance")
    try:
        supervise.parse_mock_balance("-4%,1000")
    except ValueError:
        pass
    else:
        raise AssertionError("percent-first sequence should be rejected")
    return f"values={values}"


@case
def normalize_drawdown_units():
    check(supervise.normalize_drawdown(0.04) == 0.04, "fraction misread")
    check(abs(supervise.normalize_drawdown(4.0) - 0.04) < 1e-12, "percent not normalized")
    check(supervise.normalize_drawdown(None) is None, "None not preserved")
    check(supervise.parse_ratio("4%") == 0.04, "parse_ratio('4%')")
    check(supervise.parse_ratio("0.04") == 0.04, "parse_ratio('0.04')")
    return "0.04 / 4.0 / 4% all -> 0.04"


# ---------------------------------------------------------------- state machine


@case
def decide_ok_continues():
    decision = supervise.decide(supervise.Observation("OK", 0.0), supervise.Policy())
    check(decision.state == "OK", f"state={decision.state}")
    check(not decision.should_stop, "OK must not stop")


@case
def decide_paused_at_four_percent():
    decision = supervise.decide(supervise.Observation("OK", 0.04), supervise.Policy())
    check(decision.state == "PAUSED", f"state={decision.state}")
    check(decision.should_stop, "4% drawdown must stop")
    check("pause threshold" in decision.reason, f"reason={decision.reason}")


@case
def decide_unknown_when_drawdown_missing():
    decision = supervise.decide(supervise.Observation("OK", None), supervise.Policy())
    check(decision.state == "UNKNOWN", f"state={decision.state}")
    check(decision.should_stop, "unknown drawdown must stop (fail closed)")


@case
def breaker_state_vocabulary():
    policy = supervise.Policy()
    stop_states = ["PAUSED", "HALT", "LIQUIDATE", "CRITICAL", "UNKNOWN", "", "WAT"]
    for state in stop_states:
        decision = supervise.decide(supervise.Observation(state, 0.0), policy)
        check(decision.should_stop, f"state {state!r} should stop, got {decision.state}")
    for state in ["OK", "HEALTHY", "WARNING", "CAUTION", "RESTRICTED"]:
        decision = supervise.decide(supervise.Observation(state, 0.0), policy)
        check(not decision.should_stop, f"state {state!r} should not stop")
    # UNKNOWN keeps its own name instead of being relabelled PAUSED
    check(supervise.decide(supervise.Observation("UNKNOWN", None), policy).state == "UNKNOWN",
          "UNKNOWN was relabelled")
    return "7 stop states, 5 continue states verified"


# ------------------------------------------------------------- mock drawdown demo


@case
def mock_drawdown_demo():
    """The acceptance test: -4% -> PAUSED written, stop() called within one poll."""
    tmp = Path(tempfile.mkdtemp(prefix="supervise_demo_"))
    state_file = tmp / "supervise_state.json"
    lines: list[str] = []
    supervisor = supervise.Supervisor(
        supervise.MockProbe(supervise.parse_mock_balance("1000,-4%,-8%")),
        supervise.Policy(),
        state_file,
        lines.append,
        interval=0.0,
        mode="mock",
    )
    bot = supervise.MockBot(lines.append)
    exit_code = supervisor.run(bot, max_polls=3, sleep=False)
    transcript = "\n".join("    " + line for line in lines)

    check(exit_code == supervise.EXIT_STOPPED, f"exit_code={exit_code}")
    check(bot.stopped, "stop() was never called")
    check(bot.stop_state == "PAUSED", f"stop() state={bot.stop_state}")
    check(supervisor.polls == 2, f"expected stop on poll 2, got {supervisor.polls} polls")
    check(supervisor.probe.consumed == 2,
          f"third synthetic value was consumed ({supervisor.probe.consumed} values) — "
          "stop did not happen inside the poll that saw -4%")
    payload = read_state(state_file)
    check(payload["state"] == "PAUSED", f"state file state={payload['state']}")
    check(payload["action"] == "stop_bot", f"action={payload['action']}")
    check(abs(payload["drawdown"] - 0.04) < 1e-9, f"drawdown={payload['drawdown']}")
    check(payload["drawdown_pct"] == 4.0, f"drawdown_pct={payload['drawdown_pct']}")
    check(payload["polls"] == 2, f"state file polls={payload['polls']}")
    check(payload["balance"] == 960.0 and payload["peak_balance"] == 1000.0,
          f"balances={payload['balance']}/{payload['peak_balance']}")
    check(any("state=PAUSED action=stop_bot" in line for line in lines),
          "no explicit PAUSED/stop_bot log line")
    shutil.rmtree(tmp, ignore_errors=True)
    print("  demo transcript (real log lines):")
    print(transcript)
    print(f"  state file: {json.dumps(payload)}")
    return "poll 2 saw -4.00% -> PAUSED written, stop() called, 3rd value never read"


@case
def mock_drawdown_demo_via_cli():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_cli_"))
    state_file = tmp / "state.json"
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = supervise.main(["--mock-balance", "1000,-4%,-8%",
                                    "--state-file", str(state_file)])
    output = buffer.getvalue()
    check(exit_code == supervise.EXIT_STOPPED, f"exit_code={exit_code}")
    check("state=PAUSED" in output, "CLI output has no PAUSED line")
    check("stop() called" in output, "CLI output has no stop() line")
    summary = json.loads(output[output.rindex("{\n  \"event\""):])
    check(summary["stop_called"] is True and summary["polls"] == 2,
          f"summary={summary}")
    check(summary["values_consumed"] == 2, f"summary={summary}")
    shutil.rmtree(tmp, ignore_errors=True)
    return f"exit={exit_code} polls={summary['polls']} consumed={summary['values_consumed']}"


@case
def mock_unknown_balance_stops():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_unknown_"))
    lines: list[str] = []
    supervisor = supervise.Supervisor(
        supervise.MockProbe(supervise.parse_mock_balance("1000,None,-4%")),
        supervise.Policy(), tmp / "state.json", lines.append, interval=0.0, mode="mock")
    bot = supervise.MockBot(lines.append)
    exit_code = supervisor.run(bot, max_polls=3, sleep=False)
    payload = read_state(tmp / "state.json")
    check(exit_code == supervise.EXIT_STOPPED, f"exit_code={exit_code}")
    check(bot.stopped and bot.stop_state == "UNKNOWN", f"stop state={bot.stop_state}")
    check(payload["state"] == "UNKNOWN", f"state file={payload['state']}")
    check(supervisor.polls == 2, f"polls={supervisor.polls}")
    shutil.rmtree(tmp, ignore_errors=True)
    return "unreadable balance -> UNKNOWN -> stop on poll 2"


@case
def mock_clean_sequence_does_not_stop():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_clean_"))
    supervisor = supervise.Supervisor(
        supervise.MockProbe(supervise.parse_mock_balance("1000,1010,1000")),
        supervise.Policy(), tmp / "state.json", lambda _m: None, interval=0.0, mode="mock")
    bot = supervise.MockBot(lambda _m: None)
    exit_code = supervisor.run(bot, max_polls=3, sleep=False)
    payload = read_state(tmp / "state.json")
    check(exit_code == supervise.EXIT_OK, f"exit_code={exit_code}")
    check(not bot.stopped, "stop() called on a healthy sequence")
    check(supervisor.polls == 3, f"polls={supervisor.polls}")
    check(payload["action"] == "sequence_exhausted", f"action={payload['action']}")
    shutil.rmtree(tmp, ignore_errors=True)
    return "3 healthy polls, no stop, exit 0"


@case
def mock_mode_never_launches_freqtrade():
    original_controller = supervise.FreqtradeController
    original_popen = supervise.subprocess.Popen

    def explode(*_args, **_kwargs):
        raise AssertionError("mock mode must not construct a controller or spawn a process")

    supervise.FreqtradeController = explode
    supervise.subprocess.Popen = explode
    tmp = Path(tempfile.mkdtemp(prefix="supervise_offline_"))
    try:
        with redirect_stdout(io.StringIO()):
            exit_code = supervise.main(["--mock-balance", "1000,-4%,-8%",
                                        "--state-file", str(tmp / "state.json")])
    finally:
        supervise.FreqtradeController = original_controller
        supervise.subprocess.Popen = original_popen
        shutil.rmtree(tmp, ignore_errors=True)
    check(exit_code == supervise.EXIT_STOPPED, f"exit_code={exit_code}")
    return "FreqtradeController/Popen patched to raise; mock run still completed offline"


# ------------------------------------------------------------------- preflight


@case
def preflight_ok_exits_zero():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_pre_"))
    probe = tmp / "probe.json"
    probe.write_text(json.dumps({"state": "OK", "drawdown_pct": 0.012}), encoding="utf-8")
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = supervise.main(["--preflight", "--probe-json", str(probe)])
    payload = json.loads(buffer.getvalue()[:buffer.getvalue().rindex("}") + 1])
    check(exit_code == supervise.EXIT_OK, f"exit_code={exit_code}")
    check(payload["state"] == "OK", f"state={payload['state']}")
    shutil.rmtree(tmp, ignore_errors=True)
    return "state=OK -> exit 0"


@case
def preflight_paused_exits_one():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_pre_"))
    probe = tmp / "probe.json"
    probe.write_text(json.dumps({"state": "PAUSED", "drawdown_pct": 0.05}), encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        exit_code = supervise.main(["--preflight", "--probe-json", str(probe)])
    check(exit_code == supervise.EXIT_PREFLIGHT_FAIL, f"exit_code={exit_code}")
    shutil.rmtree(tmp, ignore_errors=True)
    return "state=PAUSED -> exit 1"


@case
def preflight_unreadable_probe_fails_closed():
    missing = Path(tempfile.mkdtemp(prefix="supervise_pre_")) / "nope.json"
    with redirect_stdout(io.StringIO()):
        exit_code = supervise.main(["--preflight", "--probe-json", str(missing)])
    check(exit_code == supervise.EXIT_PREFLIGHT_FAIL, f"exit_code={exit_code}")
    shutil.rmtree(missing.parent, ignore_errors=True)
    return "missing probe file -> UNKNOWN -> exit 1"


@case
def breaker_probe_handles_garbage():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_garbage_"))
    script = tmp / "broken_breaker.py"
    script.write_text("print('not json at all')\n", encoding="utf-8")
    observation = supervise.BreakerProbe(breaker=script, timeout=30)()
    check(observation.state == "UNKNOWN", f"state={observation.state}")
    check("unparseable" in observation.detail, f"detail={observation.detail}")
    shutil.rmtree(tmp, ignore_errors=True)
    return f"garbage output -> {observation.state}"


@case
def rest_credentials_resolve_env_placeholder():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_creds_"))
    config = tmp / "cfg.json"
    config.write_text(json.dumps({
        "api_server": {"enabled": True, "listen_port": 8099, "username": "api-user",
                       "password": "${SUPERVISE_TEST_API_PASSWORD}"},
    }), encoding="utf-8")
    password = "pw-" + "x" * 20
    os.environ["SUPERVISE_TEST_API_PASSWORD"] = password
    try:
        controller = supervise.FreqtradeController(config, log=lambda _m: None)
        credentials = controller._api_credentials()
    finally:
        os.environ.pop("SUPERVISE_TEST_API_PASSWORD", None)
    check(credentials == ("api-user", password, 8099), f"credentials={credentials!r}")
    shutil.rmtree(tmp, ignore_errors=True)
    return "config placeholder ${SUPERVISE_TEST_API_PASSWORD} expanded from env, port 8099"


@case
def rest_stop_disabled_when_api_server_off():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_creds_"))
    config = tmp / "cfg.json"
    config.write_text(json.dumps({"api_server": {"enabled": False}}), encoding="utf-8")
    controller = supervise.FreqtradeController(config, log=lambda _m: None)
    check(controller._api_credentials() is None, "credentials resolved for a disabled API")
    check(controller._rest_stop() is None, "REST stop attempted with the API disabled")
    shutil.rmtree(tmp, ignore_errors=True)
    return "api_server.enabled=false -> no REST attempt, falls back to the process signal"


# ------------------------------------------------------------------ stop paths


@case
def stop_prefers_rest_then_leaves_child_alone():
    controller = supervise.FreqtradeController(REPO_ROOT / "user_data/config_dryrun.json",
                                               log=lambda _m: None, stop_timeout=0.2)
    child = DummyChild()

    def fake_rest_stop():
        child.returncode = 0  # the API stop made the bot exit by itself
        return "rest_api"

    controller.child = child
    controller._rest_stop = fake_rest_stop
    method = controller.stop("PAUSED", "unit test")
    check(method == "rest_api", f"method={method}")
    check(not child.terminated, "child was signalled although the REST stop worked")
    return "REST stop used; process signal not needed"


@case
def stop_falls_back_to_sigterm_when_rest_unavailable():
    controller = supervise.FreqtradeController(REPO_ROOT / "user_data/config_dryrun.json",
                                               log=lambda _m: None, stop_timeout=2.0)
    child = DummyChild()
    controller.child = child
    controller._rest_stop = lambda: None
    method = controller.stop("PAUSED", "unit test")
    check(method == "sigterm", f"method={method}")
    check(child.terminated, "child was not terminated")
    check(not child.killed, "SIGKILL sent although SIGTERM worked")
    return "REST unavailable -> SIGTERM -> child exited"


@case
def stop_escalates_to_sigkill():
    controller = supervise.FreqtradeController(REPO_ROOT / "user_data/config_dryrun.json",
                                               log=lambda _m: None, stop_timeout=0.1)

    class StubbornChild(DummyChild):
        def terminate(self):
            self.terminated = True  # ignores SIGTERM

        def poll(self):
            return None

    child = StubbornChild()
    controller.child = child
    controller._rest_stop = lambda: None
    controller._wait_for_exit = lambda _timeout: False
    method = controller.stop("PAUSED", "unit test")
    check(method == "sigkill", f"method={method}")
    check(child.terminated and child.killed, "escalation did not happen")
    return "SIGTERM ignored -> SIGKILL"


# ------------------------------------------------------------------ subprocess


@case
def subprocess_entrypoint_is_not_a_daemon():
    tmp = Path(tempfile.mkdtemp(prefix="supervise_sub_"))
    state_file = tmp / "state.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "supervise.py"),
         "--mock-balance", "1000,-4%,-8%", "--state-file", str(state_file)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )
    check(proc.returncode == supervise.EXIT_STOPPED, f"returncode={proc.returncode}")
    check("state=PAUSED" in proc.stdout, "no PAUSED in stdout")
    check(read_state(state_file)["state"] == "PAUSED",
          f"state file={read_state(state_file)['state']}")
    shutil.rmtree(tmp, ignore_errors=True)
    return f"rc={proc.returncode}, exited (no daemon), PAUSED on disk"


@case
def help_text_renders():
    """argparse applies %-formatting to help strings — a stray % used to crash --help."""
    for module in (supervise, ss):
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                module.main(["--help"])
        except SystemExit as exc:
            check(exc.code == 0, f"{module.__name__} --help exited {exc.code}")
        else:
            raise AssertionError(f"{module.__name__} --help did not exit")
        check("usage:" in buffer.getvalue(), f"{module.__name__} --help printed no usage")
    return "supervise --help and secrets_scan --help both render"


def main() -> int:
    print(f"test_supervise: {len(CASES)} cases, python {sys.version.split()[0]}")
    failures = 0
    for fn in CASES:
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
            traceback.print_exc()
        else:
            print(f"PASS {fn.__name__}" + (f" — {detail}" if detail else ""))
    total = len(CASES)
    print(f"\n{total - failures}/{total} passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
