"""Assemble reports/phase1/data/DATA_REFRESH.md from measured artifacts.

Inputs (all produced by this lane):
  gap_scan.md          - per-pair gap table (gap_scan.py output)
  window_coverage.csv  - bars per scoreboard split, per pair
Narrative text is static; every number in it is copy-pasted from a tool output
captured in preflight.log / download.log / download_backfill.log / gap_scan.json.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

gap_raw = open(os.path.join(HERE, "gap_scan.md"), encoding="utf-8").read().strip()
_gap_lines = gap_raw.splitlines()
_cut = next((i for i, ln in enumerate(_gap_lines) if ln.startswith("coverage:")), len(_gap_lines))
gap = "\n".join(_gap_lines[:_cut]).rstrip() + "\n\n```\n" + "\n".join(_gap_lines[_cut:]) + "\n```"
cov = open(os.path.join(HERE, "window_coverage.csv"), encoding="utf-8").read().strip().splitlines()

cov_tbl = ["| " + " | ".join(cov[0].split(",")) + " |",
           "|" + "---|" * len(cov[0].split(","))]
for ln in cov[1:]:
    p = ln.split(",")
    cov_tbl.append(f"| {p[0]}/USDT:USDT | {int(p[1]):,} | {int(p[2]):,} | {int(p[3]):,} |")
cov_md = "\n".join(cov_tbl)

body = f"""# Phase 1.3 — Data refresh with connectivity preflight

Run date: **2026-11-19** (17:18-17:35 IST / 11:48-12:04 UTC). Lane: Phase 1, item 1.3.
Governing plan: `EXECUTION_PLAN.md` section 3 Phase 1.3 + section 6 risk "Exchange connectivity blocked".

## Reproducibility header

| Field | Value |
|---|---|
| Data manifest | `user_data/data/binance/futures/*-1h-futures.feather`, 20 files, **1,019,155 rows** |
| Manifest SHA-256 | `e8485279c2c625c93b9467d7d2324c019e81aa0917f6ce78bdccce4aff39b549` |
| Manifest definition | sha256 over `<file>|<rows>|<first_ts>|<last_ts>|<bytes>`, one line per pair, sorted by base, newline-joined |
| Listing dates source | `fapi/v1/exchangeInfo` snapshot saved as `fapi_exchangeInfo_20261119.json` (1,185,506 bytes, 953 symbols) |
| Timerange downloaded | 2026-05-16 to 2026-11-19 (append), 2017-01-01 to file start (prepend backfill), 2026-11-19 top-up |
| Config used | none - `download-data` CLI flags only; no API keys, no config, no trading endpoints |
| Fee model | n/a this phase (no backtest run) |
| Git SHA | **not recorded** - this lane runs under a NO-git rule (no git commands permitted) |
| Venue | binance (USDT-M perpetual futures), `--trading-mode futures` |

## 1. Connectivity preflight

Raw transcript: `preflight.log` (every command, exit code, headers, body). Probed in the
mandated order with `curl -sS --max-time 12`; host TZ = IST, no proxy configured
(`http_proxy` / `https_proxy` / `ALL_PROXY` all empty).

| # | Venue | URL | HTTP | Body (verbatim) | Verdict |
|---|---|---|---|---|---|
| 1 | Binance spot | `https://api.binance.com/api/v3/ping` | **200** | `{{}}` | **REACHABLE** |
| 2 | Binance USDT-M futures | `https://fapi.binance.com/fapi/v1/ping` | **200** | `{{}}` | **REACHABLE - selected venue** |
| 3 | Bybit | `https://api.bybit.com/v5/market/time` | **200** | `{{"retCode":0,"retMsg":"OK","result":{{"timeSecond":"1795088938",...}}}}` | REACHABLE (not needed) |
| 4 | OKX | `https://www.okx.com/api/v5/public/time` | **200** | `{{"code":"0","data":[{{"ts":"1795088939946"}}],"msg":""}}` | REACHABLE (not needed) |
| 5 | Gate.io | `https://api.gateio.ws/api/v4/spot/time` | **200** | `{{"server_time":1795088942274}}` | REACHABLE (not needed) |

**Geo-block finding: none.** All five venues answered 200 from this host in India. No 451, no
403, no Cloudflare/WAF challenge body. Binance served both spot and futures from the CloudFront
`DEL51` (Delhi) edge (`X-Amz-Cf-Pop: DEL51-P6` / `DEL51-P1`), i.e. the request terminated on an
Indian edge node, not a blocked path. The "Binance geo-blocks India" hypothesis is **not
reproduced on this machine today**. If it ever appears, the failure signature to look for is
HTTP 451/403 with a body like `{{"code":0,"msg":"Service unavailable from a restricted location..."}}`
(none was seen).

### 1b. Data-endpoint probe (a reachable ping is not a working feed)

The OHLCV endpoint was probed before committing to a 20-pair download:

| Probe | Result |
|---|---|
| `fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=3` | HTTP 200, 0.32 s, 3 candles, last open `1795086000000` = **2026-11-19 11:00 UTC** |
| `fapi/v1/klines?symbol=BTCUSDT&interval=1h&startTime=1794960000000` | HTTP 200, 0.35 s, historical candle returned correctly |
| `fapi/v1/exchangeInfo` | HTTP 200, 1,185,506 bytes, 953 symbols |
| spot `api/v3/klines?symbol=BTCUSDT&interval=1h&limit=2` | HTTP 200, current candles |

Conclusion: the futures REST feed is live, current, and returns history - the May-2026 data
cutoff in the repo was **a stale local dataset, not an exchange-side limit.**

## 2. What was downloaded

`download.log` (append + top-up) and `download_backfill.log` (prepend backfill) hold the full
per-pair transcripts. Three passes, all `exit_code=0`:

| Pass | Command | Pairs | Series | Rows fetched | Duration |
|---|---|---|---|---|---|
| 1. Append (mandated window) | `download-data --exchange binance --trading-mode futures -t 1h --pairs <20> --timerange 20260516-20261119 --datadir user_data/data/binance` | 20/20 | 60 (futures + mark + funding_rate) | 4,384-4,490 per pair (~88k) | **72 s** |
| 2. Prepend backfill | same + `--timerange 20170101-20261119 --prepend` | 20/20 | 60 | BNB 55,086 / ATOM 54,655 / SEI 3,573 | **621 s** |
| 3. Top-up | `--timerange 20261119-20261120` | 20/20 | 60 | 13-20 bars per pair | 19 s |

Per-pair outcome: **20/20 succeeded, 0 failures.** Every pair fetched all three series; no pair
required a retry.

### Why pass 2 existed (finding, not scope creep)

Pass 1 alone left the dataset unusable for the Phase 1.4 scoreboard. freqtrade appends from the
last existing candle and never backfills earlier holes, so pairs whose local files were
truncated at the start stayed truncated:

| Pair | Listing | Local first bar *before* backfill | History lost |
|---|---|---|---|
| SOL, DOGE, SUI | 2020-09-14 / 2020-07-10 / 2023-05-03 | 2025-02-01 | 1.5-5 y |
| AVAX, LINK, DOT, TRX, NEAR, ARB, OP | 2020-2023 | 2025-05-01 | 2-5.5 y |
| ATOM, APT | 2020-02-07 / 2022-10-18 | 2026-04-20 | 3-6 y |
| **BNB, INJ, SEI** | 2020-02-10 / 2022-08-16 / 2023-08-17 | *no file at all* | entire history |

Phase 1.4 splits train <= 2025-12-31 / validation 2026-H1 / holdout >= 2026-07-01. Under the
pre-backfill state BNB/INJ/SEI had **zero** train bars and 7 other pairs had ~8 months, so the
scoreboard would have compared pairs on wildly different histories without saying so.
`--prepend` backfills without erasing anything: no `--erase` was used anywhere and all 205
pre-existing feather files are still present (now 214, with the 9 new BNB/INJ/SEI series).

Local 1h futures coverage went from **40 pairs to 43 pairs** (the 40 pre-existing + BNB, INJ, SEI).
Universe check: all 20 canonical pairs report `status=TRADING`, `contractType=PERPETUAL` on
Binance futures - the 3 "missing" pairs were **absent locally, not absent from the exchange**.

## 3. Gap verification (per pair, 1h futures)

Script: `gap_scan.py` (re-runnable; reads `fapi_exchangeInfo_*.json` for listing dates).
Machine-readable output: `gap_scan.json`.

Denominators, per the plan wording "expected = candles between first and last bar for that
pair's listing window":

- **Gap % (listing)** - `expected = ((last_bar - listing_date) / 1h) + 1`, `missing = expected - rows`. Counts history absent from the local file entirely. This is the gate denominator.
- **Gap % (in-file)** - same over `first_bar -> last_bar`; isolates holes *between* bars.
- **Max gap (h)** - largest delta between consecutive timestamps. Perps trade 24/7, so anything above 1.0 h is a real hole.

Expected counts use the exchange `onboardDate`, which is not bar-aligned (bars open at :00/:07/:08/:12),
so `rows` can exceed `expected` by 1-2 and `missing` is clamped at 0. Differences of +/-2 rows are
arithmetic artefacts, not data.

{gap}

**Reading of the table.** No pair has an internal hole: `Max gap = 1.0 h` for all 20 pairs means
every consecutive bar pair is exactly one hour apart - zero missing bars between first and last.
`Gap % (in-file) = 0.00` for all 20. The listing-window residual is launch-day only: APT 19 bars
(onboard 2022-10-18, first bar 2022-10-19 02:00), SUI 16, INJ 19, ARB 8, OP 7 - a perp that
onboards on day D does not necessarily print a bar for every hour of day D. Worst listing-window
gap is **APT at 0.05%**, well inside the 1% gate.

Integrity checks across all 20 files: `duplicates = 0`, `monotonic = True`, columns
`['date','open','high','low','close','volume']`. `freqtrade list-data --trading-mode futures`
resolves all 20 pairs.

## 4. Fitness for the Phase 1.4 three-way split

Bar counts per split window:

{cov_md}

Every pair clears the split: minimum **20,807** train bars (SEI, ~2.4 y); validation is exactly
**4,344** bars (181 d) and holdout **3,419** bars (142 d) for all 20. The holdout is already
populated, so it must be *sealed by policy* in `scoreboard.py`, not by absence of data.

## 5. Findings for the orchestrator (outside this lane's ownership)

1. **BNB is blacklisted in `user_data/config_backtest.json`** - `"pair_blacklist": ["BNB/.*"]`. The canonical universe includes BNB/USDT:USDT and its data is now complete (59,380 bars). Phase 1.4 must either reconcile the config or drop BNB from the universe explicitly; leaving both produces a 19-pair scoreboard labelled as 20.
2. **The repo data was stale and truncated, not exchange-limited.** Nothing about the May-2026 cutoff was Binance's doing.
3. **`--prepend` is required for any future refresh of an existing pair file.** Plain `download-data` only extends the tail; it will not repair a truncated start.
4. **Data dir grew 205 -> 214 feather files** (156 MB, +9 series for BNB/INJ/SEI). No file was deleted or overwritten destructively; all writes were freqtrade merges.

## 6. Verdict

**Gap gate (plan section 3, item 1.3):** no pair exceeds 1% gaps (worst 0.05%) and 20/20 = **100%**
of the canonical universe is covered -> **PASS** on both halves.

**feeds usable for Phase 2 dry-run: YES - venue Binance (USDT-M perpetual futures, 1h), 20/20 pairs, 1,019,155 bars, last bar 2026-11-19 11:00 UTC.**

No venue migration is proposed. Bybit, OKX and Gate all answered 200 and remain viable fallbacks
if Binance ever starts refusing this host, but nothing observed today justifies moving the
scoreboard off binance-local data - that decision is not this lane's to make.
"""

out = os.path.join(HERE, "DATA_REFRESH.md")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(body)
print("written", out, len(body), "bytes")
