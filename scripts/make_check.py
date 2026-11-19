#!/usr/bin/env python3
"""Phase 4.3 — the weekly gate runner (`make check`).

Runs, in order:

  1. ``freqtrade list-strategies --userdir user_data`` — parse the table, assert
     exactly 7 loadable strategies, and assert that no quarantined strategy file
     (``user_data/strategies/_archived/lookahead_20261119/*.py``) is loadable.
  2. ``python scripts/validate_configs.py`` — canonical configs parse + policy.
  3. ``python scripts/secrets_scan.py --all`` — full-tree secret scan (allowlist
     respected by the scanner itself).
  4. scoreboard smoke — one strategy, one pair, one month into a throwaway temp
     dir under ``reports/``; assert rc == 0 and that ``results.json`` carries the
     requested strategy, then delete the temp dir.

Every step prints PASS/FAIL + rc + seconds; a summary table ends the run and the
process exits 0 only when every executed step passed.

No live trading, no config writes, no git writes: read-only inspection plus one
temporary report directory that is removed in a ``finally`` block.

Usage:
    python scripts/make_check.py                # full gate (~30 s measured)
    python scripts/make_check.py --skip smoke   # skip the backtest smoke
    python scripts/make_check.py --json         # also print a JSON summary
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
QUARANTINE_DIR = REPO_ROOT / "user_data" / "strategies" / "_archived" / "lookahead_20261119"

EXPECTED_STRATEGIES = 7
SMOKE_STRATEGY = "BollingerMeanReversion"
SMOKE_TIMERANGE = "20260601-20260701"
SMOKE_STAGE = "validation"
SMOKE_PAIRS_LIMIT = 1

STEP_ORDER = ("strategies", "configs", "secrets", "smoke")
STEP_ALIASES = {
    "strategy": "strategies",
    "list-strategies": "strategies",
    "config": "configs",
    "validate-configs": "configs",
    "secret": "secrets",
    "secrets-scan": "secrets",
    "scoreboard": "smoke",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# --------------------------------------------------------------------------- io


def run_step(cmd: list[str], timeout: float) -> tuple[int, str, float]:
    """Run *cmd* from the repo root, merging stdout+stderr. Returns (rc, text, secs)."""
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
        return 124, f"TIMEOUT after {timeout:.0f}s\n{out}", time.perf_counter() - started
    except FileNotFoundError as exc:
        return 127, f"command not found: {exc}", time.perf_counter() - started
    return rc, ANSI_RE.sub("", out), time.perf_counter() - started


@dataclass
class StepResult:
    name: str
    status: str = "SKIP"
    rc: int | None = None
    seconds: float = 0.0
    detail: str = ""
    output: str = field(default="", repr=False)

    @property
    def passed(self) -> bool:
        return self.status in {"PASS", "SKIP"}

    def as_dict(self) -> dict:
        return {
            "step": self.name,
            "status": self.status,
            "rc": self.rc,
            "seconds": round(self.seconds, 2),
            "detail": self.detail,
        }


# ---------------------------------------------------------------- step 1: list


def _table_rows(text: str) -> list[tuple[str, str, str]]:
    """Return (name, location, status) from a freqtrade list-strategies table."""
    rows: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if "\u2502" not in line:  # │ box-drawing column separator
            continue
        cells = [c.strip() for c in line.split("\u2502")]
        if len(cells) < 5:
            continue
        name, location, status = cells[1], cells[2], cells[3]
        if not name or name.lower() == "strategy name":
            continue
        if not re.fullmatch(r"[A-Za-z_][\w.]*", name):
            continue
        rows.append((name, location, status))
    return rows


def quarantined_stems() -> list[str]:
    if not QUARANTINE_DIR.is_dir():
        return []
    return sorted(p.stem for p in QUARANTINE_DIR.glob("*.py"))


def evaluate_strategy_table(
    rows: list[tuple[str, str, str]], rc: int, quarantined: list[str], output: str = ""
) -> tuple[list[str], list[str]]:
    """Return (problems, loaded names) for one parsed list-strategies table."""
    loaded = [name for name, _loc, status in rows if status.upper() == "OK"]
    broken = [(name, status) for name, _loc, status in rows if status.upper() != "OK"]

    problems: list[str] = []
    if rc != 0:
        problems.append(f"list-strategies rc={rc}")
    if not rows:
        problems.append("could not parse any strategy row from the table")
    if len(loaded) != EXPECTED_STRATEGIES:
        problems.append(f"loadable strategies = {len(loaded)}, expected {EXPECTED_STRATEGIES}")
    if broken:
        problems.append("non-OK rows: " + ", ".join(f"{n}({s})" for n, s in broken))
    if "failed to load" in output.lower():
        problems.append("output contains 'Failed to load'")

    loaded_lower = {n.lower() for n in loaded}
    leaked = [q for q in quarantined if q.lower() in loaded_lower]
    if leaked:
        problems.append("quarantined strategy loadable: " + ", ".join(leaked))
    archived_locations = [n for n, loc, _s in rows if "_archived" in loc.lower()]
    if archived_locations:
        problems.append("strategy loaded from _archived: " + ", ".join(archived_locations))
    return problems, loaded


def step_strategies(timeout: float) -> StepResult:
    res = StepResult("strategies")
    rc, out, secs = run_step(
        [sys.executable, "-m", "freqtrade", "list-strategies", "--userdir", "user_data"],
        timeout,
    )
    res.rc, res.seconds, res.output = rc, secs, out
    quarantined = quarantined_stems()
    problems, loaded = evaluate_strategy_table(_table_rows(out), rc, quarantined, out)

    if problems:
        res.status, res.detail = "FAIL", "; ".join(problems)
    else:
        res.status = "PASS"
        res.detail = f"{len(loaded)} loadable: " + ", ".join(sorted(loaded))
        if quarantined:
            res.detail += f" | quarantine list: {len(quarantined)} files, none loadable"
    return res


# --------------------------------------------------------------- step 2 and 3


def step_configs(timeout: float) -> StepResult:
    res = StepResult("configs")
    res.rc, res.output, res.seconds = run_step(
        [sys.executable, "scripts/validate_configs.py"], timeout
    )
    tail = [ln for ln in res.output.splitlines() if ln.strip()]
    if res.rc == 0:
        res.status = "PASS"
        res.detail = tail[-1].strip() if tail else "rc=0"
    else:
        res.status = "FAIL"
        res.detail = (tail[-1].strip() if tail else "no output") + f" (rc={res.rc})"
    return res


def step_secrets(timeout: float) -> StepResult:
    res = StepResult("secrets")
    res.rc, res.output, res.seconds = run_step(
        [sys.executable, "scripts/secrets_scan.py", "--all"], timeout
    )
    tail = [ln for ln in res.output.splitlines() if ln.strip()]
    if res.rc == 0:
        res.status = "PASS"
        res.detail = tail[-1].strip() if tail else "rc=0"
    else:
        res.status = "FAIL"
        res.detail = (tail[-1].strip() if tail else "no output") + f" (rc={res.rc})"
    return res


# ------------------------------------------------------------------ step 4


def step_smoke(timeout: float) -> StepResult:
    res = StepResult("smoke")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_root = Path(tempfile.mkdtemp(prefix="makecheck-", dir=str(REPORTS_DIR)))
    outdir = tmp_root / "scoreboard"
    try:
        rc, out, secs = run_step(
            [
                sys.executable,
                "scripts/scoreboard.py",
                "--stage",
                SMOKE_STAGE,
                "--limit",
                str(SMOKE_PAIRS_LIMIT),
                "--strategies",
                SMOKE_STRATEGY,
                "--timerange",
                SMOKE_TIMERANGE,
                "--outdir",
                str(outdir),
            ],
            timeout,
        )
        res.rc, res.seconds, res.output = rc, secs, out
        results_file = outdir / "results.json"
        problems: list[str] = []
        if rc != 0:
            problems.append(f"scoreboard rc={rc}")
        if not outdir.is_dir():
            problems.append(f"no output dir at {outdir}")
        elif not results_file.is_file():
            problems.append("results.json missing")
        else:
            try:
                data = json.loads(results_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                data = None
                problems.append(f"results.json unreadable: {exc}")
            if isinstance(data, dict):
                entries = data.get("results") or data.get("entries") or []
                names = {str(e.get("strategy")) for e in entries if isinstance(e, dict)}
                if not entries:
                    problems.append("results.json has no result entries")
                elif SMOKE_STRATEGY not in names:
                    problems.append(f"results.json lacks {SMOKE_STRATEGY}")
                else:
                    metrics = (entries[0] or {}).get("metrics") or {}
                    res.detail = (
                        f"{SMOKE_STRATEGY} {SMOKE_TIMERANGE} pairs<={SMOKE_PAIRS_LIMIT} "
                        f"trades={metrics.get('trades')} status={entries[0].get('status')}"
                    )
            elif results_file.is_file():
                problems.append("results.json is not a JSON object")
        if problems:
            res.status = "FAIL"
            res.detail = "; ".join(problems)
        else:
            res.status = "PASS"
            res.detail = res.detail or "results.json written"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        if tmp_root.exists():
            res.status = "FAIL"
            res.detail = (res.detail + "; " if res.detail else "") + f"temp dir not removed: {tmp_root}"
    return res


# ------------------------------------------------------------------- runner


def parse_skips(values: list[str]) -> set[str]:
    skipped: set[str] = set()
    for raw in values:
        for token in re.split(r"[,\s]+", raw.strip().lower()):
            if not token:
                continue
            name = STEP_ALIASES.get(token, token)
            if name not in STEP_ORDER:
                raise SystemExit(
                    f"make_check: unknown step '{token}' (choose from: {', '.join(STEP_ORDER)})"
                )
            skipped.add(name)
    return skipped


def print_summary(results: list[StepResult], total: float) -> None:
    width = max(len(r.name) for r in results) + 2
    print()
    print("=" * 74)
    print("make check — summary")
    print("=" * 74)
    print(f"{'step':<{width}}{'result':<9}{'rc':>5}{'seconds':>10}  detail")
    print("-" * 74)
    for r in results:
        rc = "-" if r.rc is None else str(r.rc)
        print(f"{r.name:<{width}}{r.status:<9}{rc:>5}{r.seconds:>10.2f}  {r.detail}")
    print("-" * 74)
    failed = [r for r in results if r.status == "FAIL"]
    executed = [r for r in results if r.status != "SKIP"]
    overall = "PASS" if not failed else "FAIL"
    skipped = len(results) - len(executed)
    print(
        f"total {total:.2f}s | {len(executed) - len(failed)}/{len(executed)} executed steps passed"
        + (f" | {skipped} skipped" if skipped else "")
        + f" | {overall}"
    )
    print("=" * 74)


def self_test() -> int:
    """Exercise the parser + fail logic with crafted tables (no repo mutation)."""
    header = (
        "\u250c\u2500\u2500\u2510\n"
        "\u2502              Strategy name \u2502                      Location \u2502 Status \u2502\n"
    )
    row_fmt = "\u2502 {name:>25} \u2502 {loc:>29} \u2502 {status:>6} \u2502\n"

    def table(names: list[tuple[str, str, str]]) -> str:
        body = "".join(
            row_fmt.format(name=n, loc=loc, status=st) for n, loc, st in names
        )
        return header + body

    seven = [(f"Strat{i}", f"Strat{i}.py", "OK") for i in range(7)]
    cases: list[tuple[str, str, int, list[str], str, list[str]]] = [
        ("clean 7-row table", table(seven), 0, [], "", []),
        (
            "8 loadable rows",
            table(seven + [("Extra", "Extra.py", "OK")]),
            0,
            [],
            "",
            ["expected 7"],
        ),
        (
            "quarantined strategy loadable",
            table(seven[:-1] + [("SupertrendEmaStrategy", "SupertrendEmaStrategy.py", "OK")]),
            0,
            ["SupertrendEmaStrategy"],
            "",
            ["quarantined strategy loadable"],
        ),
        (
            "load failed row",
            table(seven[:-1] + [("Broken", "Broken.py", "LOAD FAILED")]),
            0,
            [],
            "",
            ["non-OK rows"],
        ),
        (
            "loaded from _archived",
            table(seven[:-1] + [("Old", "_archived/Old.py", "OK")]),
            0,
            [],
            "",
            ["_archived"],
        ),
        ("nonzero rc", table(seven), 1, [], "", ["rc=1"]),
        (
            "ansi + unparsable output",
            "\x1b[32mFailed to load strategy\x1b[0m\n" + table(seven),
            0,
            [],
            "Failed to load strategy",
            ["Failed to load"],
        ),
    ]

    failures = 0
    for label, text_, rc_, quarantine_, output_, expected in cases:
        rows = _table_rows(ANSI_RE.sub("", text_))
        problems, _loaded = evaluate_strategy_table(rows, rc_, quarantine_, output_)
        ok = all(any(needle in p for p in problems) for needle in expected) if expected else not problems
        status = "PASS" if ok else "FAIL"
        failures += 0 if ok else 1
        print(f"  self-test {status}: {label}" + ("" if ok else f" -> problems={problems}"))
    print(f"  self-test: {len(cases) - failures}/{len(cases)} cases passed")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Phase 4.3 weekly gate: strategies, configs, secrets, scoreboard smoke."
    )
    ap.add_argument(
        "--skip",
        nargs="+",
        default=[],
        metavar="STEP",
        help=f"skip steps for speed (any of: {', '.join(STEP_ORDER)})",
    )
    ap.add_argument("--timeout", type=float, default=600.0, help="per-step timeout seconds (default 600)")
    ap.add_argument("--json", action="store_true", help="print a JSON summary after the table")
    ap.add_argument("--show-output", action="store_true", help="stream every step's captured output")
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="test the strategy-table parser and fail logic, then exit",
    )
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    skipped = parse_skips(args.skip)
    runners = {
        "strategies": step_strategies,
        "configs": step_configs,
        "secrets": step_secrets,
        "smoke": step_smoke,
    }

    started = time.perf_counter()
    print(f"make check — repo {REPO_ROOT}")
    print(f"python {sys.executable}")
    if skipped:
        print(f"skipping: {', '.join(sorted(skipped))}")
    print()

    results: list[StepResult] = []
    for name in STEP_ORDER:
        if name in skipped:
            res = StepResult(name, status="SKIP", detail="skipped via --skip")
            print(f"[4.{STEP_ORDER.index(name) + 2}] {name:<10} SKIP")
            results.append(res)
            continue
        print(f"[4.{STEP_ORDER.index(name) + 2}] {name:<10} running ...", end="", flush=True)
        res = runners[name](args.timeout)
        results.append(res)
        print(f"\r[4.{STEP_ORDER.index(name) + 2}] {name:<10} {res.status:<4} "
              f"rc={'-' if res.rc is None else res.rc} {res.seconds:.2f}s  {res.detail}")
        if args.show_output and res.output:
            print("-" * 74)
            print(res.output.rstrip())
            print("-" * 74)
        elif res.status == "FAIL" and res.output:
            tail = res.output.rstrip().splitlines()[-25:]
            print("    --- last output ---")
            for line in tail:
                print(f"    {line}")
            print("    ------------------")

    total = time.perf_counter() - started
    print_summary(results, total)

    if args.json:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "repo": str(REPO_ROOT),
            "total_seconds": round(total, 2),
            "status": "PASS" if all(r.passed for r in results) else "FAIL",
            "steps": [r.as_dict() for r in results],
            "sla_seconds": 300,
            "sla_ok": total < 300,
        }
        print(json.dumps(payload, indent=2))

    if total >= 300:
        print(f"NOTE: full run took {total:.1f}s, over the 5-minute timebox.")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
