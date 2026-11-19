# Phase 2.1 — candidate audit, stop fixes, honest re-measurement

**Verdict in one line: neither candidate merits a walkforward.** BollingerMeanReversion's
validation expectancy was already −0.271 %/trade with a stop mechanism that never ran; once its
coded ATR stop is enabled (the only behaviour-changing fix available) the same window returns
−0.928 %/trade. SupertrendEmaStrategy was left untouched because it is lookahead-SUSPECT, and its
−0.637 %/trade stands as a defective measurement, not a candidate.

## 1. Reproducibility header

| Field | Value |
|---|---|
| git SHA | `9fd8eca2b2793bd7d79452ab92c8376671673746` |
| freqtrade | `2026.5-dev-9fd8eca2b` (editable install of the in-repo `freqtrade/` tree) |
| config | `user_data/config_backtest.json` |
| config sha256 | `26e14c8c2f8c419eca3266f0fefd3be92a3c2f77b8599fa6fde8c5dc9a532b2a` (identical to the Phase 1.4 scoreboard's) |
| fee model | `--fee 0.001` charged on entry **and** exit = 10 bps all-in per side-equivalent (exchange fee + slippage proxy; the backtester has no native slippage model) |
| timerange | `20260101-20260701` (validation stage, END exclusive — `SCOREBOARD.md` boundary convention) |
| universe | canonical 20-pair futures universe (`reports/scoreboard-20261119-1229/UNIVERSE.json`, no substitutions) |
| strategy files sha256 | Bollinger `5814a87f…b1508b08` (post-fix), Supertrend `5f78dbf1…2303ba` (unmodified) |
| generated (UTC) | 2026-11-19T13:06Z |

Command (identical flags to `scripts/scoreboard.py:build_command`, one strategy per process):

```
.venv/Scripts/freqtrade.exe backtesting --strategy <Class> -c user_data/config_backtest.json \
  --userdir user_data --timerange 20260101-20260701 --fee 0.001 --cache none --export trades \
  --backtest-directory reports/phase2/2.1/raw/<label> --timeframe 1h -p <20 pairs>
```

Wrapper: `reports/phase2/2.1/run_validation.py` (reuses `scoreboard.extract_metrics` so BEFORE and
AFTER numbers are computed by the same code). Raw stdout: `backtest_<strategy>.log`.

## 2. Lookahead audit — verdicts

| Strategy | Verdict | Anchor |
|---|---|---|
| `SupertrendEmaStrategy` | **SUSPECT** | `SupertrendEmaStrategy.py:130` (context `:122-132`): the 4h informative frame is merged on the raw 4h candle stamp and forward-filled, so 75 % of 1h rows consume a close that happens in their future. `merge_informative_pair` is imported (`:19`) and never called. |
| `BollingerMeanReversion` | **CLEAN** | only informative merge is 1h→1h (`:107`), which freqtrade's own helper says needs no shift (`strategy_helper.py:45-47`); all indicators backward-looking; `_load_signals()` is a constant stub. |

Full per-checklist evidence with quoted lines: `LOOKAHEAD_AUDIT.md`.
Per the task rule, `SupertrendEmaStrategy.py` was **not edited** after its verdict — quarantine
is an orchestrator decision. Quantified impact of its defect on the probe month: 4h direction
differs from the last *closed* 4h candle on 4/740 rows (0.5 %), and the leak never opened the MTF
gate (0 rows true only because of the leak, 4 rows false). It is a real defect with a small,
mildly *adverse* effect on this window — not the source of the losses, and not citable as an
out-of-sample number either.

## 3. Fixes applied — 3, all in `BollingerMeanReversion.py`

| # | file:line | What | Why |
|---|---|---|---|
| 1 | `BollingerMeanReversion.py:37-40` | `use_custom_stoploss = True` | `interface.py:85` defaults it to `False` and `:1551` is the only call site, so `custom_stoploss()` **never ran** in either strategy. The ATR stop was dead code; every stop in the Phase 1.4 scoreboard was the raw config stoploss. |
| 2 | `:208-222` | convert the ATR stop price with `stoploss_from_absolute(stop, current_rate, is_short, leverage=trade.leverage)` instead of returning `-(current − stop)/current` | freqtrade divides every stoploss ratio by leverage (`trade_model.py:833-837`); the old expression was already a price fraction, so at 3x the stop sat at **one third** of the intended ATR distance. |
| 3 | `:184-188` (rationale), code at `:208-222` | removed `max(stop_loss_pct, self.stoploss)` | both values are negative, so `max()` kept the *tighter* one and silently replaced a wider ATR stop with the fixed config stop. Tightening is already enforced by freqtrade's own ratchet (`trade_model.py:856-876`, "stop losses only walk up, never down!"). |

Leverage values untouched (`:73-74`, still `min(3.0, max_leverage)`). Before/after diffs and the
full mechanism inventory: `STOP_FIXES.md`. Regression tests: `tests/phase2/test_strategy_stops.py`
(5/5 pass, including the assertion that the stop lands on `open ∓ 1.3 ATR` *in price terms*, which
the pre-fix code failed by 3x).

Verified indirectly that no stop can loosen: **0 of 74** post-fix trades ended with
`stop_loss_abs` below `initial_stop_loss_abs` (48 tightened, 26 unchanged).

## 4. Before / after — validation window only

BEFORE is reproduced at this SHA before any edit; it matches `SCOREBOARD.md` at 4 dp
(9 trades / −0.636832 % vs −0.637 %; 72 trades / −0.271230 % vs −0.271 %), so the harness and the
baseline are consistent.

| Strategy | run | Trades | Profit % | Win % | **Exp/trade %** | MaxDD % | PF | Sharpe |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SupertrendEmaStrategy | before (= scoreboard) | 9 | −1.443 | 55.6 | **−0.637** | 2.75 | 0.737 | −0.136 |
| SupertrendEmaStrategy | after | — | — | — | **−0.637 (unchanged, not edited)** | — | — | — |
| BollingerMeanReversion | before (= scoreboard) | 72 | −5.662 | 51.4 | **−0.271** | 22.64 | 0.873 | −0.481 |
| BollingerMeanReversion | after | 74 | −16.437 | 40.5 | **−0.928** | 26.26 | 0.641 | −1.591 |

Both runs long-only (9/0 and 74/0 long/short: `can_short = False`), 16 pairs traded, 4 open-trade
slots, 10 000 USDT start. The post-fix run was repeated in a second process
(`metrics_after2_*`): all seven headline metrics identical at 4 dp.

### 4.1 Attribution — the flag is the whole story

A fourth run isolates fix #1: `use_custom_stoploss` set back to `False` while the price-terms code
stays in place (`metrics_after_flagoff_*`, `raw/after_flagoff_BollingerMeanReversion/`) returns
**exactly the baseline at full precision** — 72 trades, −5.662399 %, exp −0.271230 %, DD
22.638169 %, PF 0.87317. So the eleven-line stop-math fix is inert until the flag switches the
method on, and the Phase 1.4 scoreboard was indeed measured with `custom_stoploss()` never
executing. The flag was restored to `True` immediately (file sha256 back to `5814a87f…b1508b08`,
tests re-run green).

### 4.2 What actually changed — exit mix

| Exit | before (n, mean price move) | after (n, mean price move) |
|---|---|---|
| `stop_loss` (hard stop hit) | 32 @ **−1.644 %** | 19 @ **−1.645 %** |
| `trailing_stop_loss` | 11 @ **+1.767 %** | 32 @ **−0.281 %** |
| `roi` | 18 @ +1.871 % | 16 @ +1.744 % |
| exit signal | 11 @ +0.672 % | 7 @ +0.604 % |

The hard stop is the same price in both runs (1.667 % at 3x) — the ATR stop is *wider* than it on
this sample (1.3 × ATR(1h) ≈ 2.0–2.4 % of price on the sampled entries, ETH 1.2 %), so the seeded
config stop remains the binding floor and the ATR stop can only tighten inside it. On the final
stops, 48 of 74 trades ended tighter than the seeded 1.667 % stop (ATR stop and trailing stop
together; 0 ever ended looser). The material change is on the
trailing side: 21 more trades now reach the +1.67 % price level that arms the trailing stop, and
with a **0.5 % price** trail at 3x (`trailing_stop_positive = 0.015` ÷ 3) the spike is given back
and the exit lands at a small loss. 24 of the 32 trailing exits closed negative (−0.06 % to
−1.62 % price); 8 closed positive (+1.39 % to +2.29 %); the group mean is −0.281 %.

### 4.3 Caveat that inflates the post-fix loss (stated, not hidden)

8 of the 32 trailing exits closed **inside the entry candle** (`trade_duration = 0`). For those,
freqtrade switches fill rule when `use_custom_stoploss` is True: `backtesting.py:566-590` takes the
"worst case: price ticks a tiny bit above open and dives down" branch and fills at
`max(candle_low, open × (1 − |stoploss_pct/leverage|))` — i.e. **at the candle low**, whereas the
flag-off branch assumes the trade first reached the trailing offset and fills at
`open × (1 + offset − positive/leverage)` = +4.5 % (equally crude, in the generous direction).
Re-pricing those 8 fills at their stop price instead of the candle low moves mean profit/trade
from **−0.928 % to −0.168 %**. That is a sensitivity estimate, not a rerun, and it is the honest
uncertainty band on the headline: the correct claim is "**no better than before, plausibly
between −0.17 % and −0.93 % per trade**". Neither end is positive.

### 4.4 Selection-integrity caveat (found during the audit, no file change)

`BollingerMeanReversion` does **not** run on its class defaults: freqtrade loads
`user_data/strategies/BollingerMeanReversion.json` (hyperopt export, `export_time
2026-05-14 10:41:11`, `ft_stratparam_v: 1`) with `atr_multiplier=1.3`, `risk_reward=2.6`,
`bb_period=16`, `rsi_oversold=40`, `ema_trend_period=148`. An export dated 2026-05-14 cannot have
been fitted on data ending before the validation window opens (2026-01-01); the fit window
overlaps validation by roughly 4.5 months. So the −0.271 %/trade that made this strategy the
"second-best by validation expectancy" is **partially in-sample** — it is not an out-of-sample
estimate at all. This is independent of the stop bugs and would need the hyperopt run record to
resolve precisely; the export timestamp is enough to disqualify it as Phase 2 evidence.

## 5. What would have to change for this strategy to be worth another look

Only one lever is left inside the strategy, and it is a design decision rather than a bug fix: the
trailing stop's two numbers are in **different units**. `trailing_stop_positive_offset = 0.05` is
compared with `current_profit` (equity, × leverage → arms at +1.67 % price) while
`trailing_stop_positive = 0.015` is divided by leverage (→ 0.5 % price trail). A 0.5 % trail on a
1h candle is noise-level; it converts spikes into small losses. Expressing both in price terms
(e.g. arm at +5 % price, trail 1.5 % price) is a *different strategy*, not a unit correction, so
it was not applied — it would also invalidate the comparison with the Phase 1.4 scoreboard. If the
orchestrator wants one more attempt on this file, that is the change to test, together with
retiring the hyperopt parameter file and re-deriving parameters only on the train window.

## 6. Conclusion

The honest result is negative on every axis. BollingerMeanReversion's stop wiring was broken in
three independent ways and **none of them was the reason it lost money**: with the dead ATR stop
disabled the strategy lost −0.27 %/trade, and with it enabled — price-terms, tight-only,
leverage-correct — it lost between −0.17 % and −0.93 %/trade on the same window, depending on how
the backtester prices eight same-candle trailing exits. Fixing correctness did not reveal a hidden
edge; it revealed that the strategy's own risk design (a 1.3-ATR stop seeded under a 1.667 %-price
config ceiling, plus a 0.5 %-price trailing stop at 3x) is a scalp that pays the 10 bps round trip
and loses the spread on noise: 72 trades in six months at profit factor 0.87 and a 22.6 % drawdown before the
fix; 74 trades at profit factor 0.64 and 26.3 % after. SupertrendEmaStrategy is worse off still: it
is lookahead-SUSPECT at `:130`, it traded 9 times in six months (−0.637 %/trade on a sample far too
small to estimate anything from), and its own ATR stop is equally dead behind the missing
`use_custom_stoploss` flag. Neither file is a
candidate for a 6-month rolling walkforward: a walkforward would spend a month of wall-clock
proving that a net-negative, partially in-sample scalp with a broken exit design stays negative.
The correct Phase 2 outcome here is the written **no-edge memo** (`EXECUTION_PLAN.md` §5 fail
case), quarantine review for SupertrendEmaStrategy, and — if the user wants a third attempt —
either a re-derived candidate from the scoreboard's next tier with the same audit applied, or a
deliberate redesign of the trailing/stop units in this one, validated on train only.

## 7. Artifacts

| File | Contents |
|---|---|
| `backtest_SupertrendEmaStrategy.log`, `backtest_BollingerMeanReversion.log` | raw freqtrade stdout/stderr, validation window |
| `backtest_before_*.log`, `backtest_after_*.log` | the same runs, labelled by phase |
| `metrics_*.json` | parsed metrics (scoreboard's own `extract_metrics`, 6 dp) |
| `raw/<label>/*.zip` | freqtrade result archives the metrics were parsed from |
| `run_validation.py`, `analyze_trades.py` | reproducible runners (scoreboard-identical flags; exit-reason diagnostics) |
| `probe_lookahead_4h.py` / `.log` | 4h merge lookahead proof and impact measurement |
| `probe_runtime_attrs.py` / `.log` | resolved runtime attributes (config override, `use_custom_stoploss`, leverage) |
| `LOOKAHEAD_AUDIT.md`, `STOP_FIXES.md` | per-item audit with quoted lines; fix diffs and rationale |
| `tests/phase2/test_strategy_stops.py` | 5 unittest regressions on the stop math and the enabling flag |
