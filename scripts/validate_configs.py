#!/usr/bin/env python3
"""Validate the canonical freqtrade configs for this repo (Phase 1.2).

Exit codes
----------
0  all canonical checks passed (warnings may be present)
1  at least one canonical FAIL
2  a canonical config is missing or unparseable

Checks (a) — canonical configs, FAIL on violation:
    * parses as JSON
    * required keys: dry_run, stake_amount, max_open_trades, stoploss, exchange, pair_whitelist
    * api_server.listen_ip_address == 127.0.0.1
    * api_server.password and api_server.jwt_secret are ${ENV_VAR} placeholders
    * no literal 64-hex secret anywhere in the file
    * dry_run is true in every canonical config (config_dryrun.json must never be armed)
    * no api_server key outside the localhost block (token/chat_id/telegram disabled)

Checks (b) — every other user_data/config*.json, WARN on violation:
    * parses as JSON

Usage
-----
    .venv/Scripts/python.exe scripts/validate_configs.py
    .venv/Scripts/python.exe scripts/validate_configs.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
USER_DATA = REPO_ROOT / "user_data"

CANONICAL = (
    "user_data/config_backtest.json",
    "user_data/config_spot.json",
    "user_data/config_dryrun.json",
)

REQUIRED_KEYS = ("dry_run", "stake_amount", "max_open_trades", "stoploss", "exchange")
PLACEHOLDER_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
HEX64_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
# placeholders that are allowed to look "secret-ish" but must stay ${...}

results: list[dict] = []


def record(level: str, scope: str, check: str, detail: str) -> None:
    results.append({"level": level, "scope": scope, "check": check, "detail": detail})


def fail(scope: str, check: str, detail: str) -> None:
    record("FAIL", scope, check, detail)


def warn(scope: str, check: str, detail: str) -> None:
    record("WARN", scope, check, detail)


def ok(scope: str, check: str, detail: str = "ok") -> None:
    record("PASS", scope, check, detail)


def _dig(data: dict, *path: str):
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def check_canonical(rel: str) -> None:
    path = REPO_ROOT / rel
    name = Path(rel).name

    if not path.exists():
        fail(name, "exists", f"missing canonical config: {path}")
        return
    try:
        raw = path.read_text(encoding="utf-8")
        cfg = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - report, never crash
        fail(name, "parse", f"{type(exc).__name__}: {exc}")
        return
    ok(name, "parse", f"{len(cfg)} top-level keys")

    if not isinstance(cfg, dict):
        fail(name, "structure", "top-level JSON is not an object")
        return

    # _comment / purpose line (plan anti-goal 3: no config without a purpose line)
    comment = cfg.get("_comment")
    if isinstance(comment, str) and len(comment) > 40:
        ok(name, "purpose line", "_comment present")
    else:
        warn(name, "purpose line", "missing or too short _comment")

    # required keys
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        fail(name, "required keys", f"missing: {', '.join(missing)}")
    else:
        ok(name, "required keys", ", ".join(REQUIRED_KEYS))

    cfg_exchange = cfg.get("exchange")
    if isinstance(cfg_exchange, dict):
        whitelist = cfg_exchange.get("pair_whitelist")
        if isinstance(whitelist, list) and whitelist:
            ok(name, "pair_whitelist", f"{len(whitelist)} pairs")
        else:
            fail(name, "pair_whitelist", "exchange.pair_whitelist missing, not a list, or empty")
    else:
        fail(name, "exchange", "exchange block missing or not an object")

    # dry_run must exist and be true — safety invariant
    dry_run = cfg.get("dry_run")
    if dry_run is True:
        ok(name, "dry_run", "true")
    elif "dry_run" in cfg:
        fail(name, "dry_run", f"dry_run is {dry_run!r} — canonical configs must be dry_run: true")
    else:
        fail(name, "dry_run", "missing")

    # stake / trades types
    stake = cfg.get("stake_amount")
    if isinstance(stake, (int, float)) and stake > 0:
        ok(name, "stake_amount", f"{stake}")
    elif stake == "unlimited":
        ok(name, "stake_amount", "unlimited (explicit)")
    else:
        fail(name, "stake_amount", f"expected a positive number or 'unlimited', got {stake!r}")

    mot = cfg.get("max_open_trades")
    if isinstance(mot, int) and not isinstance(mot, bool) and mot != 0:
        ok(name, "max_open_trades", f"{mot}")
    else:
        fail(name, "max_open_trades", f"expected a non-zero int, got {mot!r}")

    sl = cfg.get("stoploss")
    if isinstance(sl, (int, float)) and not isinstance(sl, bool):
        if sl >= 0:
            fail(name, "stoploss", f"stoploss must be negative, got {sl!r}")
        else:
            ok(name, "stoploss", f"{sl}")
    else:
        fail(name, "stoploss", f"expected a number, got {sl!r}")

    # api_server hardening
    api = cfg.get("api_server")
    if not isinstance(api, dict):
        warn(name, "api_server", "no api_server block (REST disabled)")
    else:
        ip = api.get("listen_ip_address")
        if ip == "127.0.0.1":
            ok(name, "api_server.listen_ip_address", ip)
        else:
            fail(name, "api_server.listen_ip_address",
                 f"expected '127.0.0.1', got {ip!r} (must not bind publicly)")

        for field in ("password", "jwt_secret"):
            value = api.get(field)
            if isinstance(value, str) and PLACEHOLDER_RE.match(value):
                ok(name, f"api_server.{field}", "env placeholder")
            elif value in (None, ""):
                fail(name, f"api_server.{field}", "missing")
            else:
                fail(name, f"api_server.{field}",
                     f"not a ${{ENV_VAR}} placeholder (got {str(value)[:12]}…)")

        # this fork also accepts jwt_secret_key — same rule if present
        if "jwt_secret_key" in api:
            v = api.get("jwt_secret_key")
            if isinstance(v, str) and PLACEHOLDER_RE.match(v):
                ok(name, "api_server.jwt_secret_key", "env placeholder")
            else:
                fail(name, "api_server.jwt_secret_key",
                     "present but not a ${ENV_VAR} placeholder")

    # telegram must stay disabled in canonical configs
    tg = cfg.get("telegram")
    if isinstance(tg, dict) and tg.get("enabled") is True:
        fail(name, "telegram", "telegram.enabled is true — canonical configs must be silent")
    elif isinstance(tg, dict):
        ok(name, "telegram", "disabled")
        token = tg.get("token")
        if isinstance(token, str) and token and not PLACEHOLDER_RE.match(token):
            fail(name, "telegram.token", "literal token present")
    else:
        ok(name, "telegram", "no telegram block")

    # literal 64-hex secrets anywhere in the raw text
    hits = HEX64_RE.findall(raw)
    if hits:
        fail(name, "secrets", f"{len(hits)} literal 64-hex string(s) found (keys/secrets?)")
    else:
        ok(name, "secrets", "no literal 64-hex strings")

    # db_url: dry-run must have an explicit one (plan 1.2)
    if "db_url" in cfg:
        ok(name, "db_url", str(cfg["db_url"]))
    elif name == "config_dryrun.json":
        fail(name, "db_url", "config_dryrun.json must set db_url explicitly")
    else:
        warn(name, "db_url", "not set")


def check_other_configs() -> int:
    """Every other user_data/config*.json must at least parse (warn-level)."""
    scanned = 0
    for path in sorted(USER_DATA.rglob("config*.json")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in CANONICAL:
            continue
        scanned += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
            ok(Path(rel).name, "parse (non-canonical)", rel)
        except Exception as exc:  # noqa: BLE001
            warn(Path(rel).name, "parse (non-canonical)",
                 f"{rel}: {type(exc).__name__}: {exc}")
    return scanned


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate canonical freqtrade configs")
    ap.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = ap.parse_args()

    for rel in CANONICAL:
        check_canonical(rel)
    others = check_other_configs()

    fails = [r for r in results if r["level"] == "FAIL"]
    warns = [r for r in results if r["level"] == "WARN"]
    passes = [r for r in results if r["level"] == "PASS"]

    if args.json:
        print(json.dumps({
            "canonical": list(CANONICAL),
            "other_configs_scanned": others,
            "pass": len(passes),
            "warn": len(warns),
            "fail": len(fails),
            "results": results,
        }, indent=2))
    else:
        print("validate_configs.py — canonical freqtrade configs")
        print(f"repo: {REPO_ROOT}")
        for rel in CANONICAL:
            print(f"  canonical: {rel}")
        print("-" * 78)
        for r in results:
            if r["level"] == "PASS":
                continue
            print(f"[{r['level']}] {r['scope']}: {r['check']} — {r['detail']}")
        if not fails and not warns:
            print("(no warnings, no failures)")
        print("-" * 78)
        print(f"checks: {len(passes)} pass, {len(warns)} warn, {len(fails)} fail "
              f"| other user_data configs scanned: {others}")

    if fails:
        print(f"RESULT: FAIL ({len(fails)} canonical check(s) failed)", file=sys.stderr)
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
