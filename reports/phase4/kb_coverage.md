# KB coverage — futures-related chunks (Phase 4.2)

Measured 2026-11-19T19:09:50+05:30 · repo `aa505d8fdc1cd40b2b621895c4e95c7d0a5dd5a6` · collection `trading_strategies` · db `D:\dev\algotrading\strategy_db\chroma_db`

| metric | value |
|---|---|
| total chunks | 612 |
| chunks mentioning futures keywords | 62 |
| **baseline (measured fraction)** | **10.1307%** (62/612) |
| target (3x baseline) | 30.3922% (186/612 chunks) |
| gap to target | 124 chunks |

| keyword | chunks matched |
|---|---|
| futures | 15 |
| perpetual | 0 |
| funding | 2 |
| open interest | 1 |
| leverage | 23 |
| liquidation | 9 |
| 1h | 14 |
| 4h | 11 |

| supplementary | value |
|---|---|
| matched via title alone | 12 |
| matched without the 1h/4h timeframe keywords | 43 |
| `setup_id` coverage | 100.0000% (612/612, 609 distinct) |
| `tf_norm` distribution | `multi` 256, `1d` 130, `1h` 118, `1m` 45, `intraday` 40, `5m` 8, `4h` 8, `15m` 4, `30m` 2, `unknown` 1 |

Method: a chunk counts once when any of `futures`, `perpetual`, `funding`, `open interest`, `leverage`, `liquidation`, `1h`, `4h` matches its `video_title`/`setup_name` or document text (case-insensitive; `1h`/`4h` use a left word boundary so `24h` does not match `4h`). Baseline is the measured value above, not a target; the target is 3x that number and is only met when a re-run reports it.

Reproduce: `python scripts/kb_coverage.py`
