# Phase 0 report — supervised risk enforcement + secret gate (items 0.3, 0.4)

Executed 2026-11-19. Repo: `D:\dev\algotrading` @ `7977650755f7178924b4fbcd18dee2b8e75ea426`
(`git rev-parse HEAD`, read-only). Interpreter: `.venv/Scripts/python.exe` (CPython 3.13.18,
freqtrade 2026.5-dev-797765075). No git write operations, no live config, no installs.

| item | state after this task |
|---|---|
| **0.3** supervised risk enforcement | **DONE** — `scripts/supervise.py` (normal / preflight / offline mock), 22/22 tests, mock drawdown demo proves `-4% → PAUSED → stop()` inside one poll. Start-script wiring is a one-line call (see §5). |
| **0.4** secret gate with allowlist | **DONE** — `scripts/secrets_scan.py` + `.githooks/pre-commit` + `.githooks/pre-push` + README; 16/16 tests; `${ENV}` placeholders pass; planted tokens blocked. Full-tree scan: **1 finding**, classified (§4). |
| **0.5** delete dead trade DBs | **NOT DONE — out of write scope.** See §6: requires `git rm --cached` (forbidden here) and deletion of three root files outside the allowed paths. Measured evidence recorded. |

## 1. What was built

### `scripts/supervise.py` (new, 766 lines)

One process, three modes, no daemon:

* **normal** — `supervise.py --config user_data/config_dryrun.json [--check-interval 300]`
  launches `freqtrade trade -c <config>` (the repo's `.venv/Scripts/freqtrade.exe` when present,
  else `freqtrade` on PATH, else `python -m freqtrade`), then polls
  `scripts/circuit_breaker.py --check` every interval. On `PAUSED`/`UNKNOWN` — or any state outside
  `{OK, HEALTHY, WARNING, CAUTION, RESTRICTED}` — it stops the bot and exits **3**.
  Stop order: freqtrade REST `POST /api/v1/stop` (Basic auth, credentials resolved from *this*
  config's `api_server`, with `${ENV_VAR}` expansion, then `~/.config/freqtrade/api_password`) →
  `SIGTERM` → `SIGKILL`. Exits with the bot when the bot exits on its own.
* **preflight** — `supervise.py --preflight [--config ...]` runs one check, prints JSON, exits
  **0** (OK) / **1** (PAUSED/UNKNOWN/failure). This is the hook every start script should call.
* **mock** — `supervise.py --mock-balance '1000,-4%,-8%'` feeds synthetic balances through the
  **same** `poll_once → decide → stop` path with a mock controller. No freqtrade, no REST, no
  network, no `shared_config/` writes; state goes to `reports/phase0/supervise_mock_state.json`.
  Percent entries are drawdowns from the first absolute balance (`-4%` of 1000 = 960).
  `none|null|?` injects an unreadable balance to exercise UNKNOWN.

Two decisions worth stating:

1. **Pause cap = 4 % (default, `--max-drawdown`).** `scripts/circuit_breaker.py` keeps its
   last-resort tiers (25 % warning / 40 % critical). The supervisor is deliberately *tighter* and
   matches the vocabulary already in `shared_config/circuit_breaker.json`
   (`"Weekly drawdown -8.17% > 4.0%"` → `PAUSED`). The supervisor never *relaxes* the breaker: a
   breaker PAUSED/CRITICAL always stops the bot; a 4 % supervisor drawdown stops it earlier.
2. **Fail closed on unknown state.** Any state string not in the continue-set stops the bot, so a
   typo or a future upstream state can never read as healthy.

Also fixed while building: `circuit_breaker._load_api_server_config()` only knows
`config.json` / `config_live_real.json` / `config_api.json`, so the supervisor exports
`FREQTRADE_CONFIG=<config>` into the breaker subprocess — otherwise a dry-run session would always
report UNKNOWN and the bot could never start.

### `scripts/secrets_scan.py` (new, 565 lines) + `.githooks/`

Modes: staged diff (default, `git diff --cached -U0`, **added lines only**), `--all [ROOT]`,
`--files`, `--diff-file`, `--stdin-diff`, `--json`, `--init-ignore`, `--include-nested`.
Exit 0 clean / 1 findings / 2 usage. Output is always masked:
`path:line: pattern=<name> [key=<name>] match=<first4>...(len=N)`.

Patterns (as specified): bare 64-char `[A-Za-z0-9]`; bare 40–64 hex;
`(api[_-]?key|secret|token|password|jwt)\s*[:=]\s*["'][^"']{8,}["']`.

Allowlist: `${ENV}` / `${VAR:-default}`; `<your-key>`, `CHANGEME`, `xxxx`, `****`, `redacted`,
`dummy`, `example`; Python template fields `{var}` / `{token(24)}`; inline `secrets:allow` and
`pragma: allowlist secret`; `.secretsignore` globs; built-in defaults (`.venv/`, `attic/`,
`reports/`, `node_modules/`, `user_data/data/`, lockfiles, `*.asc`, binary data); nested checkouts
with their own `.git` are skipped by default. Bare-token context exemptions (checksum/`run_id`/
`HEAD`/`commit` markers, `uses: action@<sha>` pins, ids inside a URL, `<hash>.jpg`, all-digit ids)
exist **only for bare tokens** — an assignment match is never context-exempted (§3).

`.githooks/pre-commit` (staged) and `.githooks/pre-push` (`--all`) are thin bash wrappers:
repo-root discovery, venv interpreter selection, then the scanner. Both **chain** to
`.git/hooks/pre-commit` / `pre-push` when present (guarded by `SECRETS_SCAN_CHAINED=1`), so the
existing `.pre-commit-config.yaml` hooks keep running. `.githooks/README.md` documents
`git config core.hooksPath .githooks` — **not run here**, as instructed.

## 2. Commands and measured results

```bash
.venv/Scripts/python.exe tests/test_supervise.py        # rc=0
.venv/Scripts/python.exe tests/test_secrets_scan.py     # rc=0
.venv/Scripts/python.exe scripts/secrets_scan.py --all  # rc=1 (1 classified finding)
```

| run | result | log |
|---|---|---|
| `tests/test_supervise.py` | **22/22 passed, 0 failed** (rc 0) | `reports/phase0/supervise_test.log` |
| `tests/test_secrets_scan.py` | **16/16 passed, 0 failed** (rc 0) | `reports/phase0/secrets_selftest.log` |
| `secrets_scan.py --all` | **1 finding, 1571 files scanned, 12 skipped**, 13.0 s wall | `reports/phase0/secrets_full_scan.log` |
| hook wrappers (stub `git`) | pre-commit clean → rc 0; planted secret → rc 1 + block message; pre-push → rc 1 (same 1 finding) | `reports/phase0/hooks_test.log` |
| mock demo (CLI) | `-4%` → PAUSED, stop, exit **3** | `reports/phase0/supervise_mock_demo.log` |
| preflight, no API server | `state=UNKNOWN`, exit **1** (fail-closed) | `reports/phase0/supervise_preflight_no_api.log` |

pytest is **not installed** in `.venv` (`No module named pytest`), so both suites are plain-assert
runners that print `PASS/FAIL` per case and exit non-zero on failure.

## 3. Breaker mock-drawdown evidence (0.3 acceptance)

`supervise.py --mock-balance '1000,-4%,-8%'`, real log lines:

```
mock sequence 1000,-4%,-8% -> [1000.0, 960.0, 920.0]
mock bot started (freqtrade NOT launched)
supervising mock-bot (no process) interval=0s pause_cap=4.00%
poll=1 source=mock breaker=OK drawdown=0.00% state=OK action=continue
poll=2 source=mock breaker=OK drawdown=4.00% state=PAUSED action=stop_bot reasons=drawdown 4.00% >= pause threshold 4.00%
mock bot stop() called state=PAUSED reason=drawdown 4.00% >= pause threshold 4.00%
STOP state=PAUSED via=mock:stop after 2 poll(s); supervisor exiting 3
```

Asserted by `mock_drawdown_demo` (tests/test_supervise.py):

* `polls == 2` — the stop happens in the poll that observed −4 %, not the next one;
* `values_consumed == 2` — the third value (−8 %) is **never read**, proving the stop is inside
  that poll rather than a later iteration;
* state file: `state=PAUSED`, `action=stop_bot`, `drawdown=0.04`, `drawdown_pct=4.0`,
  `pause_threshold_pct=4.0`, `balance=960.0`, `peak_balance=1000.0`;
* `stop()` was called with state `PAUSED`; exit code `3`.

Other cases proven offline: unreadable balance → `UNKNOWN` → stop on poll 2; healthy sequence
(`1000,1010,1000`) → 3 polls, no stop, exit 0; mock mode with `FreqtradeController` **and**
`subprocess.Popen` patched to raise still completes (no freqtrade launch); REST stop preferred over
signals; SIGTERM when REST is unavailable; SIGKILL when SIGTERM is ignored; `api_server.enabled=false`
skips REST; `${FREQTRADE_API_PASSWORD}`-style config placeholders resolve from env; breaker output
that is not JSON → `UNKNOWN`; `--help` renders.

## 4. Secret-gate allowlist cases proven (0.4 acceptance)

Blocked (all fixtures generated at runtime — no key-shaped literal exists in the repo):

* bare 64-char alnum token → `alnum_token_64`, masked as `AbCd...(len=64)`, full token never printed;
* bare 40- and 64-char hex → `hex_40_64` (single finding, not double-counted as alnum);
* `api_key|secret|token|password|jwt` `=`/`:` `"<value>"` → `secret_assignment`, one finding each;
* added line in a unified diff → caught at the post-image line number (`app/config.py:11`);
  a **deleted** secret line is ignored; new-file (`--- /dev/null`) diffs parse;
* CLI exit 1 on a dirty file, 0 on a clean file; `--json` masks the value.

Passed:

* `"${FREQTRADE_API_PASSWORD}"`, `"${FREQTRADE_JWT_SECRET}"`, `"${BINANCE_API_KEY}"`,
  `"${BINANCE_SECRET:-unset}"` — 0 findings;
* all three canonical configs (`user_data/config_backtest.json`, `config_dryrun.json`,
  `config_spot.json`) → rc 0 when scanned explicitly (ignores bypassed);
* `"<your-key>"`, `"CHANGEME"`, `"xxxxxxxx"`, values shorter than 8 chars, `{var}` / `{token(24)}`
  template fields, `secrets:allow`, `pragma: allowlist secret`;
* identifier contexts: `git rev-parse HEAD` SHAs, `uses: actions/checkout@<sha>`, ids inside URLs,
  `<hash>.jpg`, `"run_id": "<sha>"`, `sha256 checksum:` lines, all-digit ids;
* `.secretsignore` globs (`legacy/`, `*.generated.json`) and the built-in dirs
  (`.venv/`, `attic/`, `user_data/data/`, `node_modules/`, `reports/`);
* nested checkout (`vendor/.git`) skipped by default, scanned with `--include-nested`;
* the gate does not flag its own sources — `scripts/secrets_scan.py`, `scripts/supervise.py`,
  both test files → 0 findings.

**Full-tree scan result: 1 finding** — `tests/rpc/test_rpc_apiserver.py:55`,
`hex_40_64`, 62 hex chars: `_JWT_SECRET_KEY = "…"` in upstream freqtrade's API test suite
(vendored `freqtrade/` tree, not a fork-authored file). It signs **test** JWTs only; the same
constant ships in public upstream freqtrade. It is left untouched (out of write scope).

Consequence: `pre-push` currently **blocks** (rc 1) until that line is allowlisted. The one-line,
reviewable remediation (owner decision, not applied here because root files were outside this
task's write scope):

```bash
python scripts/secrets_scan.py --init-ignore   # writes .secretsignore
printf 'tests/rpc/test_rpc_apiserver.py\n' >> .secretsignore
```

or add `# secrets:allow` to that upstream line. Everything else in the tree is clean, and the
pre-commit gate only looks at added lines, so it does not block normal work today.

## 5. Wiring left to the owner (no files touched outside scope)

Start scripts (`start_local.sh`, `start_trading.sh`, `scripts/*` launchers) are outside this
task's allowed paths, so the preflight call was **not** inserted. Each start path needs exactly:

```bash
.venv/Scripts/python.exe scripts/supervise.py --preflight --config user_data/config_dryrun.json \
  || { echo "circuit breaker not OK — refusing to start"; exit 1; }
```

and the supervised launch itself replaces a bare `freqtrade trade -c …` with:

```bash
.venv/Scripts/python.exe scripts/supervise.py --config user_data/config_dryrun.json --check-interval 300
```

Hooks need one opt-in per clone: `git config core.hooksPath .githooks`.

## 6. Item 0.5 — measured, not executed

```
tradesv3.dryrun.sqlite        81920 B   tables: KeyValueStore=0, trades=0, pairlocks=0,
tradesv3.dryrun.sqlite-shm    32768 B            trade_custom_data=0, orders=0
tradesv3.dryrun.sqlite-wal   127752 B
```

Confirmed empty, still tracked and on disk. Deletion requires `git rm --cached` plus removing three
root-level files — both outside this task's hard constraints (no git writes; only the listed paths
may be touched). Left for the owner / the agent that owns 0.5.

## 7. Residual risks

1. **Pre-push is red until the upstream test constant is allowlisted** (§4). Fail-closed by design;
   the fix is one reviewable line.
2. **Preflight inherits the breaker's write.** `--preflight` runs `circuit_breaker.py --check`,
   which writes `shared_config/circuit_breaker.json` (the breaker is the writer). The evidence run
   overwrote the stale `PAUSED/VectorStrategy` payload; it was **restored byte-for-byte** afterwards.
   Any future preflight will rewrite that file — expected, documented in the script docstring.
3. **REST stop is unit-tested with stubs, never against a live API.** No freqtrade process was
   running (port 8080 closed, no `user_data/.freqtrade.pid`), and launching one was not part of this
   task. The fallback path (SIGTERM/SIGKILL) is fully tested; the REST path is tested for
   ordering, credential resolution and `enabled=false` handling only.
4. **Windows `terminate()` is `TerminateProcess`**, not a graceful shutdown: on SIGTERM the child
   does not get to cancel open orders. Acceptable for dry-run; a live deployment would need the REST
   stop to be reachable (it is tried first).
5. **Bare-token context exemptions are heuristics.** A credential on a line that also says `hash`,
   `run_id`, `HEAD` or contains a URL could evade the *bare-token* rules — but any `secret = "…"` /
   `api_key = "…"` assignment on that same line is still caught. Assignments are never
   context-exempted; only placeholders exempt them.
6. **`*.log` and lockfiles are in the built-in ignores.** A secret pasted into a committed `.log`
   or `Cargo.lock` would not be reported by `--all`; the pre-commit hook never sees ignored paths
   either. Deliberate trade-off for a usable signal-to-noise ratio.
7. **Repo is being modified concurrently** (other Phase-0/1 agents). Scan counts are a snapshot:
   `1571` files scanned / `12` skipped at 17:43 local; an earlier run of the same command saw
   `1890`/`1681` as files moved. The single finding was stable across all runs.
8. **`--mock-balance` percentages are relative to the first absolute value**, not the running peak.
   Documented in the docstring; the supervisor's live path uses the breaker's own peak logic.

## 8. Files

Created: `scripts/supervise.py`, `scripts/secrets_scan.py`, `.githooks/pre-commit`,
`.githooks/pre-push`, `.githooks/README.md`, `tests/test_supervise.py`,
`tests/test_secrets_scan.py`, `reports/phase0/{supervise_test.log, secrets_selftest.log,
secrets_full_scan.log, hooks_test.log, supervise_mock_demo.log, supervise_mock_state.json,
supervise_preflight_no_api.log, PHASE0_REPORT.md}`.

Modified: `shared_config/circuit_breaker.json` (overwritten by the breaker during the preflight
evidence run, then **restored** to its exact pre-run content). No other file was touched;
`scripts/circuit_breaker.py` needed no edit.
