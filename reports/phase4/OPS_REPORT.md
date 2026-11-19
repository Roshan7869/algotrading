# Phase 4 operations report — weekly gate + KB coverage (items 4.2, 4.3)

Executed 2026-11-19. Repo `D:\dev\algotrading` @ `aa505d8fdc1cd40b2b621895c4e95c7d0a5dd5a6`
(read-only `git rev-parse HEAD`). Interpreter `.venv/Scripts/python.exe` (CPython 3.13.18,
freqtrade 2026.5-dev). No git writes, no bot started, no live config touched, no installs.

| item | state |
|---|---|
| **4.3** `make check` gate | **DONE** — `scripts/make_check.py`, 4/4 steps PASS, 25.68 s total (cold 42.60 s), exit 0 |
| **4.2** executable KB coverage | **DONE** — `scripts/kb_coverage.py`; baseline **10.1307 %** (62/612), 3x target **30.3922 %** (186/612) |
| **0.3** start-script wiring | **DONE** — `start_local.sh` prepended with the `# SUPERVISE-PREFLIGHT` guard; idempotent; `bash -n` clean |

## 1. `make check` (4.3) — measured

Command: `python scripts/make_check.py --json` (log: `reports/phase4/make_check_run.log`).
Final run `2026-11-19T13:34Z`, overall **PASS**, `total_seconds=25.68`, `sla_ok=true`.

| step | what it runs | rc | seconds | verdict |
|---|---|---|---|---|
| strategies | `freqtrade list-strategies --userdir user_data` → parse table | 0 | 3.60 | PASS — exactly 7 loadable; 19-file quarantine list, none loadable |
| configs | `python scripts/validate_configs.py` | 0 | 0.16 | PASS — 43 checks, 0 warn, 0 fail |
| secrets | `python scripts/secrets_scan.py --all` | 0 | 13.21 | PASS — 0 findings, 1513 files scanned, 12 skipped |
| smoke | `scoreboard.py --stage validation --limit 1 --strategies BollingerMeanReversion --timerange 20260601-20260701 --outdir <temp>` | 0 | 8.70 | PASS — `results.json` present with the requested entry, temp dir deleted |

Timing: **25.68 s** warm (repeated runs 25.3–25.9 s; first cold run 42.60 s including the cold
ONNX/interpreter path); the 5-minute timebox is met with margin (`sla_ok: true`). `--skip smoke`
run: 21.31 s, 3/3 executed steps PASS, smoke reported SKIP.

What the strategy step actually asserts, not just counts:

* exactly `EXPECTED_STRATEGIES = 7` rows with status `OK` (any other status is listed by name);
* no strategy whose name matches a `.py` stem in
  `user_data/strategies/_archived/lookahead_20261119/` (19 files) is loadable;
* no row whose location contains `_archived`;
* the raw output contains no `Failed to load`.

Fail-path evidence without touching the repo: `python scripts/make_check.py --self-test` exercises
the parser and the fail logic on crafted tables — 7/7 cases PASS (clean 7-row table; 8 rows;
quarantined name loadable; `LOAD FAILED` row; `_archived` location; rc≠0; ANSI noise + "Failed to
load"). Exit codes: 0 all executed steps pass, 1 any FAIL, 2 usage error.

`make check` as a literal make target is **not** wired: a root `Makefile` already exists (docker
compose / pytest targets) and is outside this task's allowed paths, so it was not modified. Run
`python scripts/make_check.py`; adding `check:` to that Makefile is a two-line owner edit.

## 2. KB coverage (4.2) — measured baseline vs 3x target

Command: `python scripts/kb_coverage.py` → `reports/phase4/kb_coverage.md`.
Source: chromadb `strategy_db/chroma_db`, collection `trading_strategies`, all 612 chunks batch-read
(`collection.count()` = 612, fetched 612).

| metric | value |
|---|---|
| total chunks | 612 |
| chunks mentioning futures keywords | 62 |
| **baseline (measured fraction)** | **10.1307 %** (62/612) |
| **target (3 × baseline)** | **30.3922 %** (186/612) |
| gap to target | 124 chunks |

Per keyword (a chunk counts once): `futures` 15, `perpetual` 0, `funding` 2, `open interest` 1,
`leverage` 23, `liquidation` 9, `1h` 14, `4h` 11. Matched via title alone: 12. Matched without the
`1h`/`4h` timeframe keywords: 43 (= 7.0261 %, reported for auditability; the official baseline keeps
them because the plan's keyword list includes them).

Metadata coverage (keys present on the sampled record, so both are measured, not assumed):
`setup_id` 612/612 = 100 % (609 distinct); `tf_norm` distribution `multi` 256, `1d` 130, `1h` 118,
`1m` 45, `intraday` 40, `5m` 8, `4h` 8, `15m` 4, `30m` 2, `unknown` 1.

Method is fixed in the script: case-insensitive regexes over `video_title`+`setup_name` and the
document text; `open interest` tolerates space/hyphen/underscore; `1h`/`4h` carry a left word
boundary so `24h` does not count as `4h` (raw substring matching would over-count by 1 chunk).
`--fail-under-target` exits 1 today (measured), so the target is a gate, not a comment.

## 3. `start_local.sh` breaker preflight (Phase 0.3 wiring)

* **Edited: yes — prepend only.** The `# SUPERVISE-PREFLIGHT` block sits immediately after
  `set -euo pipefail`; nothing else in the file changed, LF line endings preserved (0 CRLF bytes).
* Command is the one documented in `reports/phase0/PHASE0_REPORT.md` §5:
  `"$py" scripts/supervise.py --preflight --config user_data/config_dryrun.json`.
* **Idempotent:** guarded by `grep '# SUPERVISE-PREFLIGHT'`; a second wiring run printed
  `already wired — no change`, marker count stays 1.
* Only `start`/`restart` are gated; `stop`/`status`/`help` still work (verified `help` prints usage)
  so services can always be inspected or shut down.
* `bash -n start_local.sh` clean. Measured behaviour: `./start_local.sh start` →
  `circuit breaker not OK — refusing to start`, **rc=1**, no service started.

## 4. How to run

```bash
# weekly gate (4.3), ~26 s
.venv/Scripts/python.exe scripts/make_check.py            # add --json for a machine-readable summary
.venv/Scripts/python.exe scripts/make_check.py --skip smoke   # fast path, ~21 s
.venv/Scripts/python.exe scripts/make_check.py --self-test    # test the gate's own logic

# KB coverage (4.2) — after every strategy ingest/normalize
.venv/Scripts/python.exe scripts/kb_coverage.py
.venv/Scripts/python.exe scripts/kb_coverage.py --fail-under-target   # gate mode (exit 1 until 3x)
```

Weekly cron example (Windows Task Scheduler or git-bash cron):
`cd /d/dev/algotrading && .venv/Scripts/python.exe scripts/make_check.py --json >> reports/phase4/make_check_cron.log 2>&1`

## 5. Findings and residual risks

1. **The breaker preflight is UNKNOWN on this machine right now** — the balance is unreadable, so
   `start_local.sh start` refuses (fail-closed by design, rc=1, verified). Starting local services
   therefore needs a readable balance source for `scripts/circuit_breaker.py`, not a bypass.
2. **The scoreboard smoke is an execution check, not a signal check.** It passed with
   `status=no_trades`, `trades=0` on `BTC/USDT:USDT` for 2026-06-01→2026-07-01. The gate proves the
   backtest path runs and writes a manifest; it cannot prove an entry fires. Combined with the known
   0-trade strategies (DmiAdx, AroonMomentumEngine_Hybrid), a month of BTC-only data is too thin to
   assert anything about the strategy — the gate deliberately does not gate on trade count.
3. `secrets_scan --all` file counts drift between runs (1513–1577) because untracked scratch/
   `__pycache__` churn is included; the finding count is stably 0, and the allowlist unchanged.
4. The 4.2 "target" is 3× a 10.13 % baseline, i.e. 186 chunks. Roughly 124 futures-specific chunks
   must be added or re-ingested to meet it; the measure reports the gap, it does not claim progress.
5. `reports/phase4/` also holds `docs/INVENTORY.md` from the parallel 4.1 lane; this task only added
   the files below.

## 6. Files

| path | change |
|---|---|
| `scripts/make_check.py` | **new** — 4-step gate, `--skip`, `--json`, `--self-test`, temp-dir smoke |
| `scripts/kb_coverage.py` | **new** — chromadb batch measure + markdown table |
| `start_local.sh` | prepend-only: `# SUPERVISE-PREFLIGHT` guard after `set -euo pipefail` |
| `reports/phase4/kb_coverage.md` | **new** — measured table (baseline vs 3x) |
| `reports/phase4/make_check_run.log` | **new** — full run transcript + JSON summary |
| `reports/phase4/OPS_REPORT.md` | **new** — this report |
