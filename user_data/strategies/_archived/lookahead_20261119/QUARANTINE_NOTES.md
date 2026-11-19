## 2026-11-19 — SupertrendEmaStrategy (Phase 2.1 audit)
Reason: 4h informative frame merged on the raw 4h candle stamp + forward-fill
(SupertrendEmaStrategy.py:130, context :122-132; merge_informative_pair imported but never used).
A 4h bar stamped D closes at D+4h, so 75% of 1h rows consumed a close from their future
(probe: 4h.close[D] == 1h.close[D+3h] for 186/186 buckets). Measured impact small (4/740 rows)
but results are not citable OOS. Stop-logic fixes were NOT applied (file quarantined unedited).
