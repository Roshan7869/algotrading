# .githooks — Phase 0.4 secret gate

Two git hooks, both thin wrappers around `scripts/secrets_scan.py`:

| hook | command it runs | scope |
|---|---|---|
| `pre-commit` | `python scripts/secrets_scan.py` | **added lines only** (`git diff --cached -U0`) — fast, blocks the commit that introduces a secret |
| `pre-push` | `python scripts/secrets_scan.py --all` | whole working tree — catches secrets that arrived through merge, rebase, or `--no-verify` |

## Install (not done automatically — it is a per-clone setting)

```bash
git config core.hooksPath .githooks
```

Verify with `git config --get core.hooksPath` (should print `.githooks`) and
`git config --unset core.hooksPath` to disable. The hooks are ordinary files, so
they are versioned with the repo; every clone opts in once.

## Coexistence with `.pre-commit-config.yaml`

`core.hooksPath=.githooks` makes git ignore `.git/hooks/pre-commit`, which is
where the `pre-commit` framework installs itself. Both wrappers therefore
**chain** to `.git/hooks/pre-commit` / `.git/hooks/pre-push` when that file is
executable (guarded by `SECRETS_SCAN_CHAINED=1` against recursion), so the
existing mypy/ruff/codespell/zizmor hooks keep running.

If you would rather keep the framework in charge, drop the hooks and add a local
entry to `.pre-commit-config.yaml` instead (not modified by this task):

```yaml
  - repo: local
    hooks:
      - id: secrets-scan
        name: secrets-scan
        entry: python scripts/secrets_scan.py
        language: system
        pass_filenames: false
```

## What it flags

1. a bare 64-character `[A-Za-z0-9]` token (Binance key shape),
2. a bare 40–64 character hex string (Binance secret / HMAC shape),
3. an assignment: `api_key|api-key|secret|token|password|jwt` `:`/`=` `"<8+ chars>"`.

## What it lets through

* `${ENV_VAR}` and `${VAR:-default}` placeholders — the repo's config convention
  (`user_data/config_dryrun.json` uses `${FREQTRADE_API_PASSWORD}`).
* documented placeholders: `<your-key>`, `CHANGEME`, `xxxxxxxx`, `****`, `redacted`, `dummy`, `example`.
* the inline pragma `secrets:allow` (or detect-secrets' `pragma: allowlist secret`) on the line.
* identifier context for *bare* tokens only: checksum/integrity/hash/commit/`run_id`/`HEAD`
  markers on the line, `uses: action@<sha>` pins, ids inside a URL, `<hash>.jpg`, all-digit ids,
  lockfiles (`*.lock`, `package-lock.json`, …), public key blobs (`*.asc`, `*.gpg`, `*.pub`).
  Assignment matches are **not** context-exempted — only placeholder-exempted.
* paths in `.secretsignore` (globs, one per line, `#` comments). Built-in defaults
  cover `.venv/`, `attic/`, `reports/`, `node_modules/`, `user_data/data/` and binary data.
  A nested checkout with its own `.git` (a vendored clone) is skipped unless
  `--include-nested` is passed.

`python scripts/secrets_scan.py --init-ignore` writes a starter `.secretsignore`.

## Manual use

```bash
python scripts/secrets_scan.py                      # staged changes
python scripts/secrets_scan.py --all                # repo tree
python scripts/secrets_scan.py --all --json         # machine-readable
python scripts/secrets_scan.py --files a.py b.json  # explicit files
python scripts/secrets_scan.py --diff-file d.patch  # offline diff (tests/CI)
```

Exit codes: `0` clean, `1` findings, `2` usage/IO error. Output is
`path:line: pattern=<name> [key=<name>] match=<first4>...(len=N)` — the full
match is never printed, so the gate's own output cannot leak the secret.

## Bypass

`git commit --no-verify` skips the hook; `pre-push` still runs a full-tree scan,
which is why both are installed. If a finding is a genuine false positive, prefer
`secrets:allow` on the line or a `.secretsignore` entry — both are reviewable in
the diff, unlike `--no-verify`.
