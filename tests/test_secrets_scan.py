#!/usr/bin/env python3
"""Plain-python tests for scripts/secrets_scan.py (EXECUTION_PLAN 0.4).

pytest is not installed in .venv, so this file is a self-contained runner:

    .venv/Scripts/python.exe tests/test_secrets_scan.py

Every secret-shaped fixture is generated at runtime — no key-shaped literal is
ever written into this repository.
"""

from __future__ import annotations

import io
import json
import random
import shutil
import string
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import secrets_scan as ss  # noqa: E402

CASES = []
RNG = random.Random(20261119)


def case(fn):
    CASES.append(fn)
    return fn


def check(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def token(length: int = 64, alphabet: str | None = None) -> str:
    """Runtime-generated fake credential (never a literal in this file)."""
    alphabet = alphabet or (string.ascii_letters + string.digits)
    return "".join(RNG.choice(alphabet) for _ in range(length))


def hex_token(length: int = 40) -> str:
    return token(length, "0123456789abcdef")


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = ss.main(argv)
    return code, buffer.getvalue()


# ------------------------------------------------------------------ core rules


@case
def planted_64_char_token_is_blocked():
    planted = token(64)
    findings = ss.scan_text(f"payload {planted} suffix", path="planted.txt")
    check(len(findings) == 1, f"expected 1 finding, got {len(findings)}")
    finding = findings[0]
    check(finding.pattern == "alnum_token_64", f"pattern={finding.pattern}")
    check(planted[:4] in str(finding), "masked output lost the first 4 chars")
    check(planted not in str(finding), "FULL TOKEN LEAKED IN OUTPUT")
    check(finding.masked.endswith("(len=64)"), f"masked={finding.masked}")
    return f"caught {finding.masked} at planted.txt:1 without printing the token"


@case
def env_placeholder_passes():
    text = (
        '  "password": "${FREQTRADE_API_PASSWORD}",\n'
        '  "jwt_secret": "${FREQTRADE_JWT_SECRET}"\n'
        'api_key = "${BINANCE_API_KEY}"\n'
        'secret: "${BINANCE_SECRET:-unset}"\n'
    )
    findings = ss.scan_text(text, path="user_data/config_dryrun.json")
    check(findings == [], f"placeholders flagged: {[str(f) for f in findings]}")
    return "4 placeholder forms passed"


@case
def assignment_with_real_value_is_blocked():
    value = token(32)
    findings = ss.scan_text(f'api_key = "{value}"', path="config.py")
    check(len(findings) == 1, f"expected 1 finding, got {len(findings)}")
    check(findings[0].pattern == "secret_assignment", f"pattern={findings[0].pattern}")
    check(findings[0].key == "api_key", f"key={findings[0].key}")
    check(value not in str(findings[0]), "value leaked in output")

    for name in ("secret", "token", "password", "jwt"):
        hits = ss.scan_text(f'{name}: "{token(20)}"', path="config.json")
        check(len(hits) == 1, f"{name} not flagged")
    return "api_key/secret/token/password/jwt assignment shapes all caught"


@case
def short_values_and_docs_placeholders_pass():
    check(ss.scan_text('password: "short"', path="a.py") == [], "7-char value flagged")
    check(ss.scan_text('api_key: "<your-key>"', path="a.py") == [], "<your-key> flagged")
    check(ss.scan_text('token: "CHANGEME"', path="a.py") == [], "CHANGEME flagged")
    check(ss.scan_text('password: "xxxxxxxx"', path="a.py") == [], "xxx placeholder flagged")
    return "short values and documented placeholders pass"


@case
def hex_shapes_are_blocked():
    secret = hex_token(64)
    findings = ss.scan_text(f"value {secret}", path="x.env")
    check(len(findings) == 1, f"expected 1 finding, got {len(findings)}")
    check(findings[0].pattern == "hex_40_64", f"pattern={findings[0].pattern}")
    short = hex_token(40)
    check(len(ss.scan_text(f"value {short}", path="x.env")) == 1, "40-hex not flagged")
    return "40-hex and 64-hex bare tokens caught"


@case
def identifier_context_is_exempt():
    sha = hex_token(40)
    cases = [
        f"**Repo state:** `git rev-parse HEAD` = `{sha}`",
        f"uses: actions/checkout@{sha}",
        f"see https://github.com/x/y/blob/{sha}/a.py",
        f"see https://preview.redd.it/{sha}.jpg",
        f'"run_id": "{sha}",',
        f"sha256 checksum: {sha}",
        f"id {token(64, '0123456789')}",
    ]
    for text in cases:
        findings = ss.scan_text(text, path="doc.md")
        check(findings == [], f"identifier context flagged: {text[:50]} -> {[str(f) for f in findings]}")
    return f"{len(cases)} identifier/checksum/URL contexts exempt"


@case
def assignment_on_hash_line_is_still_blocked():
    value = token(32)
    findings = ss.scan_text(f'checksum_note = 1; api_key = "{value}"', path="a.py")
    check(len(findings) == 1, f"assignment on a 'checksum' line was missed: {findings}")
    return "context exemption never hides an assignment match"


@case
def inline_pragma_passes():
    planted = token(64)
    text = f"PLANTED = \"{planted}\"  # secrets:allow — documented test fixture"
    check(ss.scan_text(text, path="test_x.py") == [], "secrets:allow pragma ignored")
    text2 = f"PLANTED = \"{planted}\"  # pragma: allowlist secret"
    check(ss.scan_text(text2, path="test_x.py") == [], "detect-secrets pragma ignored")
    return "secrets:allow and 'pragma: allowlist secret' both honoured"


# ------------------------------------------------------------------------ diff


@case
def diff_scans_added_lines_only():
    planted = token(64)
    removed = token(64)
    diff = (
        "diff --git a/app/config.py b/app/config.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/app/config.py\n"
        "+++ b/app/config.py\n"
        "@@ -10,0 +11,2 @@\n"
        f'+api_key = "{planted}"\n'
        '+password = "${FREQTRADE_API_PASSWORD}"\n'
        "@@ -20 +22,0 @@\n"
        f'-api_key = "{removed}"\n'
    )
    result = ss.scan_diff_text(diff)
    check(len(result.findings) == 1, f"expected 1 finding, got {[str(f) for f in result.findings]}")
    finding = result.findings[0]
    check(finding.path == "app/config.py", f"path={finding.path}")
    check(finding.line == 11, f"line={finding.line} (must be the post-image line)")
    check(removed not in str(finding), "a deleted line was reported")
    check(result.files_scanned == 1, f"files_scanned={result.files_scanned}")
    return f"added line caught at {finding.path}:{finding.line}; deleted line ignored"


@case
def diff_handles_new_file_and_dev_null():
    planted = token(64)
    diff = (
        "diff --git a/new.env b/new.env\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/new.env\n"
        "@@ -0,0 +1,1 @@\n"
        f"+SECRET_VALUE={planted}\n"
    )
    result = ss.scan_diff_text(diff)
    check(len(result.findings) == 1, f"new-file diff missed: {result.findings}")
    check(result.findings[0].path == "new.env", f"path={result.findings[0].path}")
    return "new-file diff parsed (post-image line 1)"


# ------------------------------------------------------------------- file modes


@case
def cli_exit_codes_and_masking():
    tmp = Path(tempfile.mkdtemp(prefix="secrets_cli_"))
    planted = token(64)
    dirty = tmp / "dirty.py"
    dirty.write_text(f'api_key = "{planted}"\n', encoding="utf-8")
    clean = tmp / "clean.py"
    clean.write_text('api_key = "${BINANCE_API_KEY}"\n', encoding="utf-8")

    code, output = run_cli(["--files", str(dirty)])
    check(code == ss.EXIT_FINDINGS, f"dirty file exit={code}")
    check(planted not in output, "scanner printed the full secret")
    check(planted[:4] in output, "scanner did not print the 4-char prefix")

    code, output = run_cli(["--files", str(clean)])
    check(code == ss.EXIT_CLEAN, f"clean file exit={code}")

    code, output = run_cli(["--files", str(dirty), "--json"])
    payload = json.loads(output)
    check(code == ss.EXIT_FINDINGS and payload["count"] == 1, f"json payload={payload}")
    check(payload["findings"][0]["masked"].endswith("(len=64)"),
          f"masked={payload['findings'][0]['masked']}")
    shutil.rmtree(tmp, ignore_errors=True)
    return "exit 1 on finding / 0 clean; JSON mode masks the value"


@case
def ignored_directories_are_skipped():
    tmp = Path(tempfile.mkdtemp(prefix="secrets_tree_"))
    planted = token(64)
    for rel in (".venv/lib/x.py", "attic/old.py", "user_data/data/y.json",
                "node_modules/z.js", "reports/log.txt"):
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'secret = "{planted}"\n', encoding="utf-8")
    (tmp / "kept.py").write_text('api_key = "${BINANCE_API_KEY}"\n', encoding="utf-8")
    result = ss.scan_tree(tmp)
    check(result.findings == [], f"skipped dirs still flagged: {[str(f) for f in result.findings]}")
    check(result.files_scanned >= 1, f"files_scanned={result.files_scanned}")
    shutil.rmtree(tmp, ignore_errors=True)
    return f"0 findings, {result.files_scanned} file(s) scanned, skipped dirs honoured"


@case
def secretsignore_globs_are_honoured():
    tmp = Path(tempfile.mkdtemp(prefix="secrets_ignore_"))
    (tmp / ".secretsignore").write_text("# test\nlegacy/\n*.generated.json\n", encoding="utf-8")
    planted = token(64)
    (tmp / "legacy").mkdir()
    (tmp / "legacy" / "app.py").write_text(f'secret = "{planted}"\n', encoding="utf-8")
    (tmp / "conf.generated.json").write_text(f'{{"token": "{planted}"}}\n', encoding="utf-8")
    (tmp / "live.py").write_text(f'api_key = "{token(24)}"\n', encoding="utf-8")

    result = ss.scan_tree(tmp)
    paths = {finding.path for finding in result.findings}
    check(paths == {"live.py"}, f"paths={paths} (expected only live.py)")
    # without the ignore file the same tree is dirty
    direct = ss.scan_paths([tmp / "legacy" / "app.py"], root=tmp,
                           patterns=list(ss.DEFAULT_IGNORES))
    check(len(direct.findings) == 1, "scan_paths should still catch the ignored file directly")
    shutil.rmtree(tmp, ignore_errors=True)
    return "legacy/ and *.generated.json ignored; live.py still caught"


@case
def nested_checkout_is_skipped_by_default():
    tmp = Path(tempfile.mkdtemp(prefix="secrets_nested_"))
    planted = token(64)
    vendor = tmp / "vendor"
    (vendor / ".git").mkdir(parents=True)
    (vendor / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (vendor / "leak.py").write_text(f'api_key = "{planted}"\n', encoding="utf-8")
    (tmp / "ours.py").write_text('api_key = "${BINANCE_API_KEY}"\n', encoding="utf-8")

    default = ss.scan_tree(tmp)
    check(default.findings == [], f"nested checkout scanned: {[str(f) for f in default.findings]}")
    strict = ss.scan_tree(tmp, include_nested=True)
    check(len(strict.findings) == 1, f"--include-nested found {len(strict.findings)}")
    shutil.rmtree(tmp, ignore_errors=True)
    return "nested repo skipped by default, scanned with --include-nested"


# ------------------------------------------------------------------ self-scan


@case
def gate_does_not_flag_its_own_sources():
    paths = [SCRIPTS / "secrets_scan.py", SCRIPTS / "supervise.py",
             REPO_ROOT / "tests" / "test_secrets_scan.py",
             REPO_ROOT / "tests" / "test_supervise.py"]
    result = ss.scan_paths(paths)
    check(result.findings == [], f"gate flags itself: {[str(f) for f in result.findings]}")
    return f"{len(paths)} phase-0 source files scanned, 0 findings"


@case
def real_config_placeholders_pass():
    config = REPO_ROOT / "user_data" / "config_dryrun.json"
    result = ss.scan_paths([config])
    check(result.findings == [], f"config_dryrun.json flagged: {[str(f) for f in result.findings]}")
    payload = json.loads(config.read_text(encoding="utf-8"))
    api = payload["api_server"]
    check(api["password"].startswith("${"), "test is validating the wrong file")
    return f"{config.name} (password={api['password']}) passes"


def main() -> int:
    print(f"test_secrets_scan: {len(CASES)} cases, python {sys.version.split()[0]}")
    failures = 0
    for fn in CASES:
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
        else:
            print(f"PASS {fn.__name__}" + (f" — {detail}" if detail else ""))
    total = len(CASES)
    print(f"\n{total - failures}/{total} passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
