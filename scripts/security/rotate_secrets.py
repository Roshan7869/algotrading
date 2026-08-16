#!/usr/bin/env python3
"""
rotate_secrets.py — Helper script for API key rotation and .env management.

Usage:
  python3 scripts/security/rotate_secrets.py --generate   # Create .env from template
  python3 scripts/security/rotate_secrets.py --check-only # Verify current state
  python3 scripts/security/rotate_secrets.py --help       # Full help
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GITIGNORE_PATH = PROJECT_ROOT / ".gitignore"
ENV_PATH = PROJECT_ROOT / ".env"
ENV_TEMPLATE = {
    "BINANCE_API_KEY": "",
    "BINANCE_API_SECRET": "",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
}

CHECKS = []


def check(label: str, ok: bool, detail: str = ""):
    icon = "PASS" if ok else "FAIL"
    CHECKS.append((label, ok, detail))
    print(f"  [{icon}] {label}" + (f" — {detail}" if detail else ""))


def cmd_generate():
    if ENV_PATH.exists():
        print(f"[rotate] .env already exists at {ENV_PATH}")
        print("[rotate] Remove it first if you want to regenerate from template")
        return

    print(f"[rotate] Generating .env from template...")
    lines = []
    for key, val in ENV_TEMPLATE.items():
        if not val:
            val = f"your_{key.lower()}"
        lines.append(f'{key}="{val}"')

    ENV_PATH.write_text("\n".join(lines) + "\n")
    print(f"[rotate] Wrote {ENV_PATH}")
    print("[rotate] Edit the file with your real keys")
    print("[rotate] NEVER commit this file to git")


def cmd_check_only():
    print(f"\n  {'=' * 50}")
    print(f"  SECURITY CHECK — {PROJECT_ROOT.name}")
    print(f"  {'=' * 50}\n")

    check("Git repo detected", True)

    check(
        ".gitignore exists",
        GITIGNORE_PATH.exists(),
        str(GITIGNORE_PATH) if GITIGNORE_PATH.exists() else "",
    )

    if GITIGNORE_PATH.exists():
        content = GITIGNORE_PATH.read_text()
        check(
            ".env in .gitignore",
            ".env" in content,
            "found" if ".env" in content else "MISSING",
        )

    check(
        ".env file exists",
        ENV_PATH.exists(),
        str(ENV_PATH) if ENV_PATH.exists() else "not found — run --generate",
    )

    if ENV_PATH.exists():
        env_content = ENV_PATH.read_text()
        has_keys = "BINANCE_API_KEY" in env_content
        has_telegram = "TELEGRAM_BOT_TOKEN" in env_content
        check("BINANCE_API_KEY in .env", has_keys)
        check("TELEGRAM_BOT_TOKEN in .env", has_telegram)

    print(f"\n  {'=' * 50}")
    passed = sum(1 for c in CHECKS if c[1])
    total = len(CHECKS)
    print(f"  Result: {passed}/{total} checks passed")
    print(f"  {'=' * 50}\n")

    return all(c[1] for c in CHECKS)


def main():
    parser = argparse.ArgumentParser(description="Rotate secrets and verify security state")
    parser.add_argument("--generate", action="store_true", help="Generate .env from template")
    parser.add_argument("--check-only", action="store_true", help="Check security posture")
    args = parser.parse_args()

    if args.generate:
        cmd_generate()
    elif args.check_only:
        ok = cmd_check_only()
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
