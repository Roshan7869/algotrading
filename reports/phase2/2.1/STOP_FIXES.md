# Phase 2.1 — stop-logic audit and fixes

**Files in scope:** `user_data/strategies/BollingerMeanReversion.py`,
`user_data/strategies/SupertrendEmaStrategy.py`.
**Tree:** `git rev-parse HEAD` = `9fd8eca2b2793bd7d79452ab92c8376671673746`, freqtrade
`2026.5-dev-9fd8eca2b`. **Config used for every measurement:** `user_data/config_backtest.json`
(`stoploss: -0.05`, futures, isolated). Leverage values were **not** changed
(`BollingerMeanReversion.py:73-74`, `SupertrendEmaStrategy.py:67-68` — both `min(3.0, max_leverage)`,
as documented in `docs/leverage-matrix.md`).

## 1. What the runtime actually does (not what the file suggests)

`freqtrade/resolvers/strategy_resolver.py:_override_attribute_helper` gives the **config**
precedence over the strategy class attribute. Resolved live (`probe_runtime_attrs.py` / `.log`):

| Attribute | SupertrendEma | BollingerMR | Effective meaning |
|---|---|---|---|
| `stoploss` | `-0.05` (config overrides class −0.05) | `-0.05` (config overrides class **−0.04**) | ratio; freqtrade divides by leverage → **1.6667 % price** stop at 3x |
| `use_custom_stoploss` | `False` | `False` → **`True`** (fix #1) | without the flag `custom_stoploss()` is never called |
| `trailing_stop` / `positive` / `offset` | `True` / `0.02` / `0.06` | `True` / `0.015` / `0.05` | see §3.2 |
| `leverage()` | `3.0` | `3.0` | unchanged |
| hyperopt params | defaults | `BollingerMeanReversion.json` (`export_time 2026-05-14`) | `atr_multiplier=1.3`, `risk_reward=2.6`, … |

The two facts that decide everything:

1. `freqtrade/strategy/interface.py:85` — `use_custom_stoploss: bool = False`, and `:1551`
   (`if self.use_custom_stoploss and dir_correct:`) is the **only** call site. Neither strategy
   declared the flag, so **`custom_stoploss()` never ran in either file**. The entire ATR stop
   was dead code; every stop in the Phase 1.4 scoreboard was the raw config stop.
2. `freqtrade/persistence/trade_model.py:833-837` —
   `new_loss = current_price * (1 - abs(stoploss / leverage))`. Every stoploss ratio is divided by
   leverage before it becomes a price. Anything already expressed as a price distance must be
   multiplied back by leverage (`stoploss_from_absolute`, `strategy_helper.py:156-185`).

## 2. Mechanism inventory

### 2.1 `BollingerMeanReversion.py`

| Mechanism | file:line | State before | State after |
|---|---|---|---|
| hard stop (`stoploss`) | `:36` (class) / config `:88` | −0.05 ratio → 1.667 % price at 3x; override by config | unchanged |
| trailing stop | `:41-44` | armed at +5 % **equity** (≈ +1.67 % price), then 0.015 ratio → **0.5 % price** trail | unchanged (see §4.2) |
| `custom_stoploss` (ATR) | `:175-222` | **never called** (`use_custom_stoploss` False); internally also divided the price distance by leverage and clamped it with `max()` | **enabled**, price-terms ATR stop, tight-only ratchet |
| `custom_exit` (ATR take-profit) | `:224-259` | called (no flag needed); long branch is price-terms and correct | unchanged |
| `minimal_roi` | `:29-34` | equity ROI → 15 / 8 / 4 / 2 % equity = 5.0 / 2.67 / 1.33 / 0.67 % price at 3x | unchanged |
| exchange stop | `order_types["stoploss_on_exchange"] = False` (`:54`) | modelled by the backtester | unchanged |

### 2.2 `SupertrendEmaStrategy.py`

| Mechanism | file:line | State |
|---|---|---|
| hard stop | `:36` / config | −0.05 → 1.667 % price at 3x |
| trailing stop | `:37-40` | armed at +6 % equity (≈ +2 % price), 0.02 ratio → **0.667 % price** trail |
| `custom_stoploss` (ATR + `-0.005` flatten-on-flip) | `:210-239` | **never called** — `use_custom_stoploss` is not declared (verified: `False`) |
| `custom_exit` (ATR TP + Supertrend reversal) | `:241-273` | called; long branch price-terms |
| unknown | — | file is lookahead-SUSPECT (`LOOKAHEAD_AUDIT.md` §1.5) → **not edited** |

## 3. Findings

### 3.1 Bug (a) — stops divided by leverage (both files, same expression)

`BollingerMeanReversion.py:186-192` and `SupertrendEmaStrategy.py:231-237` (pre-fix):

```python
stop_distance = atr_value * self.atr_multiplier.value
if trade.is_short:
    stop_price = trade.open_rate + stop_distance
    stop_loss_pct = -((stop_price - current_rate) / current_rate)
else:
    stop_price = trade.open_rate - stop_distance
    stop_loss_pct = -((current_rate - stop_price) / current_rate)
return max(stop_loss_pct, self.stoploss)
```

`stop_distance` is a **price** distance, and `stop_loss_pct` is that distance as a fraction of the
current rate — i.e. still a price fraction. freqtrade then divides it by leverage again
(`trade_model.py:837`), so at 3x the stop sat at **one third** of the intended ATR distance
(1.3 ATR → 0.43 ATR of price). `%-of-price` value fed into a `%-of-equity`-scaled field.

### 3.2 Bug (b) — `max(stop_loss_pct, self.stoploss)` tight-only clamp

Both values are negative, so `max()` returns the **tighter** one. Whenever `ATR × multiplier` was
wider than `stoploss/leverage`, the ATR stop was silently replaced by the fixed config stop, and
the ratchet could never give it back. Combined with `adjust_stop_loss(..., initial=True)`
(`interface.py:1540`), which seeds the trade at `stoploss/leverage` = 1.667 % price, the ATR stop
could only ever *tighten* from there — the opposite of what a 1.3–1.5 ATR stop is for.

Note the two units inside the trailing block are *also* mixed (`trailing_stop_positive_offset` is
compared to `current_profit`, which `calc_profit_ratio` multiplies by leverage
(`trade_model.py:1201-1208`), while `trailing_stop_positive` is divided by leverage) —
**documented, not changed** (§4.2).

### 3.3 Bug (c) — ATR multiplier direction

`stop_distance = atr_value * self.atr_multiplier.value` with `atr_multiplier ∈ [1.0, 2.5]` (1.3 in
the loaded parameter file): larger multiplier → wider stop → **direction is correct**, no fix.
What was wrong was its scale (bug a) and its clamp (bug b).

### 3.4 Dead-code finding (the one that mattered most)

`use_custom_stoploss` was missing in both files. Without it, neither the ATR stop nor the
Supertrend `-0.005` flatten existed at runtime. Evidence from the baseline run: **every** one of
the 32 `stop_loss` exits in BollingerMeanReversion closed at **−1.64 % price** (the config stop),
never at an ATR distance; `initial_stop_loss_ratio = -0.05` with `leverage = 3.0` on every trade.

## 4. Fixes applied — `BollingerMeanReversion.py` only (3 changes)

### 4.1 Fix #1 — enable the custom stoploss (`:37-40`)

```diff
     stoploss = -0.04
+    # Phase 2.1: without this flag freqtrade never calls custom_stoploss()
+    # (freqtrade/strategy/interface.py:85 default False, :1551 the only call site), so the
+    # ATR stop below was dead code and every trade ran on the raw config stoploss only.
+    use_custom_stoploss = True
     trailing_stop = True
```

**Why:** makes the coded ATR stop real. This is the only change that alters behaviour by itself —
measured: with the flag back to `False` and the price-terms code still in place, the validation run
is **identical to the baseline at full precision** (72 trades, −5.662399 %, exp −0.271230 %,
DD 22.638169 %), i.e. the math fix is inert until the method is called.

### 4.2 Fix #2 — price-terms conversion, no leverage division (`:208-222`)

```diff
-        stop_distance = atr_value * self.atr_multiplier.value
-        if trade.is_short:
-            stop_price = trade.open_rate + stop_distance
-            stop_loss_pct = -((stop_price - current_rate) / current_rate)
-        else:
-            stop_price = trade.open_rate - stop_distance
-            stop_loss_pct = -((current_rate - stop_price) / current_rate)
-
-        return max(stop_loss_pct, self.stoploss)
+        stop_distance = atr_value * self.atr_multiplier.value
+        if trade.is_short:
+            stop_price = trade.open_rate + stop_distance
+        else:
+            stop_price = trade.open_rate - stop_distance
+
+        return -stoploss_from_absolute(
+            stop_price,
+            current_rate,
+            is_short=trade.is_short,
+            leverage=trade.leverage or 1.0,
+        )
```

**Why:** `stoploss_from_absolute()` returns `max(1 - stop/current, 0) * leverage`
(`strategy_helper.py:179-185`) — the inverse of what `adjust_stop_loss` does — so the stop lands
exactly on `open_rate ∓ ATR × 1.3` in price terms. It returns `0` when the stop price is already
through the current rate; `0` is falsy and `interface.py:1563` then skips the custom stop for that
candle, leaving the previous stop in force (no runaway stop).
`trade.leverage` is the per-trade value (3.0 here); no leverage value was changed.

### 4.3 Fix #3 — remove the `max()` clamp (`:184-188` rationale, code at `:208-222`)

**Why:** tightening is already enforced by freqtrade's own ratchet —
`trade_model.py:856-876`: *"stop losses only walk up, never down!"* (`allow_refresh` is False for
this strategy, verified: `after_fill` is not in the `custom_stoploss` signature, so
`_ft_stop_uses_after_fill` stays False, `strategy_resolver.py:240-245`). The extra `max()` only
served to replace a wider ATR stop with the fixed stop. Verified empirically: **0 of 74** trades
in the post-fix run ended with a stop *below* `initial_stop_loss_abs`; 48 were tightened, 26 kept
the initial stop.

### 4.4 Regression tests — `tests/phase2/test_strategy_stops.py` (new)

`unittest` (the venv has no pytest and installing is out of scope). 5 tests, all pass:

```
test_custom_stoploss_is_enabled ......................... ok
test_long_stop_sits_at_atr_distance_in_price_terms ...... ok
test_short_stop_sits_at_atr_distance_in_price_terms ..... ok
test_stop_price_does_not_follow_the_rate_up ............. ok
test_flag_is_recorded (Supertrend still False) .......... ok
```

They assert the *price* the stop lands on after freqtrade's own conversion
(`price * (1 - abs(ratio/leverage))`), which is the exact bug that was fixed; the pre-fix code
fails test 2 by 3x.

## 5. What was deliberately NOT changed

| Item | Reason |
|---|---|
| `SupertrendEmaStrategy.py` (any line) | lookahead-SUSPECT at `:130`; task rule: stop editing and report. Its identical bug (a)/(b) pattern is documented above so the orchestrator can reuse the fix if the file is quarantined and re-wired. |
| leverage values / `leverage()` callbacks | out of scope by task rule and documented in `docs/leverage-matrix.md`. |
| config `stoploss: -0.05` | configs are not in this lane's ownership; it is documented as a deliberate ceiling (`docs/leverage-matrix.md:83-91`). It is also what caps the ATR stop: the trade is *seeded* at 1.667 % price, so the ATR stop can only tighten from there. |
| `stoploss = -0.04` class attribute | dead under this config (override) — changing it would be a no-op in backtest and would contradict the leverage matrix. |
| trailing parameters | units are genuinely ambiguous (offset is equity-relative, positive is price/leverage); changing them is a strategy redesign, not a unit fix. Measured effect of the current pair: arm at +1.67 % price, then a **0.5 % price** trail — extremely tight at 3x. Flagged for the next decision, see `PHASE2_1_REPORT.md` §5. |
| `minimal_roi` ladder | same unit issue (equity), but it is an exit target, not a stop. |
| short-side TP in `custom_exit` (`:249-256`) | mixes `current_profit` (equity) with a price ratio → fires `risk_reward`× early on shorts. **Dead path**: `can_short = False`, and both runs show 72/0 and 74/0 long/short. Documented only. |
| `exit_tag` collision (`:170-171`) | `exit_long` and `exit_short` write the same `exit_tag` column, so long exits on candles where the short condition also fires are labelled `bb_reversion_exit_short` (8 of 72 in the baseline). Cosmetic; does not change trades. |

## 6. Measured effect of the fixes (validation window, 20260101-20260701)

| Metric | before | after |
|---|---:|---:|
| trades | 72 | 74 |
| profit % | −5.662 | −16.437 |
| winrate % | 51.39 | 40.54 |
| expectancy %/trade | −0.271 | −0.928 |
| max DD % | 22.64 | 26.26 |
| profit factor | 0.873 | 0.641 |
| `stop_loss` exits | 32 @ −1.644 % price | 19 @ −1.645 % |
| `trailing_stop_loss` exits | 11 @ +1.767 % | 32 @ −0.281 % |
| stops loosened below initial | 0 | 0 |
| stops tightened above initial | 25 | 48 |

Full analysis, including the backtester fill-model caveat that inflates the post-fix loss, is in
`PHASE2_1_REPORT.md` §4-5. Short version: the coded ATR stop is real now, it is tighter than the
config stop on 48/74 trades, and on this window that makes the strategy materially worse — not
better.
