# Phase 2.1 — lookahead audit: SupertrendEmaStrategy, BollingerMeanReversion

**Scope.** The two Phase 2.1 candidates, file-by-file, against the project lookahead checklist
(`EXECUTION_PLAN.md` Phase 2.1 / `trading-platform-ops` skill).
**Tree audited:** `git rev-parse HEAD` = `9fd8eca2b2793bd7d79452ab92c8376671673746`, freqtrade
`2026.5-dev-9fd8eca2b` (editable install of the in-repo `freqtrade/` tree).
**Line numbers** refer to the working tree *after* the Phase 2.1 stop edit in
`BollingerMeanReversion.py` (+5 lines vs HEAD; the audited indicator blocks are unchanged,
only shifted).

## Verdicts

| Strategy | Verdict | Evidence |
|---|---|---|
| `SupertrendEmaStrategy` | **SUSPECT — do not ship; quarantine decision is the orchestrator's** | 4h informative frame merged on the raw candle stamp and forward-filled (`SupertrendEmaStrategy.py:124-132`). A 4h candle stamped D closes at D+4h, so 75% of 1h rows consume a close that happens in their future. |
| `BollingerMeanReversion` | **CLEAN** | Only informative merge is a **1h → 1h** BTC merge (`:101-110`), which needs no shift (freqtrade's own `merge_informative_pair` skips the shift when timeframes are equal, `strategy_helper.py:45-47`). All indicators are backward-looking TA-Lib/rolling. `_load_signals()` is a constant stub. |

No file was edited on the basis of a suspect verdict: `SupertrendEmaStrategy.py` was left
untouched after this audit (see §1.6) and no stop-logic work was done on it.

---

## 1. `SupertrendEmaStrategy.py`

### 1.1 Centred rolling windows — PASS

`grep -n "center\s*="` → no hits; no `resample`, no `bfill`, no `shift(-n)` in the file.

```
120|        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
```
pandas default `center=False` → backward window.

### 1.2 `shift(-n)` / future indexing — PASS

Every shift is positive (backward):

```
105|        dataframe["supertrend_turn_up"] = (direction == 1) & (pd.Series(direction).shift(1) == -1)
106|        dataframe["supertrend_turn_down"] = (direction == -1) & (pd.Series(direction).shift(1) == 1)
115|        dataframe["ema_slope"] = dataframe["ema_fast"] - dataframe["ema_fast"].shift(5)
```

`iloc[-1]` appears only inside `custom_stoploss` (`:215`, `:223`) and `custom_exit` (`:246`,
`:249`). In backtesting `get_analyzed_dataframe()` returns
`df.iloc[max(0, max_index - MAX_DATAFRAME_CANDLES) : max_index]` — an **exclusive** end, i.e. the
last *closed* candle (`freqtrade/data/dataprovider.py:408-414`). Not future data.

### 1.3 Swing windows (± half bar) — N/A

The Supertrend recursion has no pivot/swing window; it only walks the band forward:

```
79|        for i in range(period, len(dataframe)):
80|            prev_upper = upper_band.iloc[i - 1]
81|            prev_lower = lower_band.iloc[i - 1]
```
`i-1` only → backward.

### 1.4 `resample().last()` of the current period — N/A

No `resample` call. The 4h frame comes from the data provider (§1.5).

### 1.5 Informative-pair alignment — **FAIL (lookahead)**

`informative_pairs()` requests a 4h frame per pair (`:61-65`), and `populate_indicators`
merges it on the raw 4h candle stamp:

```
122|        if self.dp:
123|            inf_tf = "4h"
124|            informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe=inf_tf)
126|                informative = self.supertrend(informative, self.supertrend_period.value, self.supertrend_multiplier.value)
128|                informative = informative[["date", "supertrend_direction", "ema_fast_4h"]].copy()
130|                dataframe = pd.merge(dataframe, informative, on="date", how="left")
131|                dataframe["st_direction_4h"] = dataframe["st_direction_4h"].ffill()
132|                dataframe["ema_fast_4h"] = dataframe["ema_fast_4h"].ffill()
```

Why this is lookahead:

- freqtrade stamps candles by **open** time, so the 4h row stamped `D` contains the high/low/close
  of `[D, D+4h)`. Its close exists only at `D+4h`.
- `pd.merge(..., on="date")` puts that row on the 1h candle stamped `D`, and `.ffill()` carries it
  to `D+1h`, `D+2h`, `D+3h`. Three of every four 1h rows therefore consume a 4h value that is
  known only later; only the `D+3h` row is clean (its own close *is* `D+4h`).
- freqtrade ships the fix and the strategy **imports it and never calls it**:
  `:19  from freqtrade.strategy import merge_informative_pair`. Its docstring is the exact
  statement of this bug — `strategy_helper.py:17-25`: *"Since dates are candle open dates, merging
  a 15m candle that starts at 15:00 and a 1h candle that starts at 15:00 will result in all
  candles to know the close at 16:00 which they should not know. Moves the date of the
  informative pair by 1 time interval forward."*
- Backtesting does not save the strategy here: `DataProvider.get_pair_dataframe()` trims to the
  current candle only when `__slice_date` is set, and that happens inside the trade loop
  (`freqtrade/optimize/backtesting.py:1654`), while `populate_indicators` runs once for the whole
  timerange **before** the loop (`backtesting.py:1769`, `advise_all_indicators`). During
  indicator computation `__slice_date` is `None` (`dataprovider.py:53`), so the full 4h series is
  returned and merged.

**Measured impact** (`probe_lookahead_4h.py` / `.log`, BTC/USDT:USDT futures, 2026-01-01 → 2026-02-01):

| Measurement | Result |
|---|---|
| `4h.close[D]` vs `1h.close[D+3h]` | identical for **186/186** buckets — the 4h row provably contains the future |
| 1h rows whose 4h value is known only after they close | **558/744 = 75.0%** |
| 4h direction vs the last *closed* 4h candle | differs on **4/740 rows (0.5%)** |
| `mtf_ok` (`st_direction_4h == 1`, `:169`) true only because of the leak | **0 rows** |
| …false only because of the leak | **4 rows** |

**Honest reading:** the defect is structural and unambiguous, but its effect on this window is
tiny and *adverse* — the leak never opened a gate that was closed, it closed 4. It is not the
explanation for the −0.637 %/trade. That does **not** make the file safe: the number cannot be
called out-of-sample while 75 % of its rows read the future, and the file is one `merge_informative_pair`
call away from being clean (out of scope for this lane — quarantine is an orchestrator decision).

### 1.6 Live `shared_config` JSON reads inside `populate_*` — PASS (inert)

```
160|        signals = self._load_signals()
161|        dataframe["signal_ta"] = 1 if signals["ta_rating"] in ("Buy", "Overweight") else (-1 if ...)
```

`_load_signals()` is a **constant stub**, not a file read:

```
signal_bus_mixin.py:22|    def _load_signals(self) -> dict:
signal_bus_mixin.py:23|        """Return default signal values for backtesting (no external bus available)."""
signal_bus_mixin.py:24|        return {"ta_rating": "Hold", "sentiment_score": 0.0, "breaker_state": "HEALTHY"}
```

and the columns it writes (`signal_ta`, `signal_sentiment`, `signal_healthy`) are **never read**
by the entry conditions (`:167-191`) — dead columns. No leakage path.

### 1.7 Same-timeframe BTC merge — PASS

```
137|        if self.dp and metadata["pair"] != "BTC/USDT:USDT":
139|                btc_data = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1h")
145|                    dataframe = pd.merge(dataframe, btc_data, on="date", how="left")
146|                    dataframe["btc_st_direction"] = dataframe["btc_st_direction"].ffill().fillna(1)
```
1h → 1h. `merge_informative_pair` needs no shift when `minutes == minutes_inf`
(`strategy_helper.py:45-47`), so this merge is aligned by construction: the 1h candle's close is
known when the signal is evaluated at that candle's close, and freqtrade enters on the next open.

**Verdict — SUSPECT** (`SupertrendEmaStrategy.py:130`, context `:122-132`).

---

## 2. `BollingerMeanReversion.py`

### 2.1 Centred rolling windows — PASS

```
96|        dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
```
`qtpylib.bollinger_bands` (used at `:77-80`) resolves to
`series.rolling(window=window, min_periods=min_periods).mean()/.std()`
(`freqtrade/vendor/qtpylib/indicators.py:256-277`) — no `center`, no future window.

### 2.2 `shift(-n)` / future indexing — PASS

`grep -n "shift(-\|resample\|center\s*=\|\.last()\|bfill"` → **0 hits** in the file.
`iloc[-1]` appears only at `:197` and `:231` (entry-candle lookup in `custom_stoploss` /
`custom_exit`), always filtered by `date <= trade_date` → historical, and the analysed dataframe is
end-exclusive as in §1.2.

### 2.3 Swing windows — N/A. No pivot detection.

### 2.4 `resample().last()` — N/A. No resample.

### 2.5 Informative-pair alignment — PASS

```
101|                btc_data = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1h")
107|                    dataframe = pd.merge(dataframe, btc_data, on="date", how="left")
108|                    dataframe["btc_ema_50"] = dataframe["btc_ema_50"].ffill()
```
Both frames are 1h and `informative_pairs()` only requests 4h (`:66-71`) for pairs it never uses —
the merge itself is same-timeframe, which freqtrade's own helper says needs no shift
(`strategy_helper.py:45-47`). The `ema_50`/`ema_200` values are EMA of the *same* candle close,
consumed at that close.

### 2.6 Live `shared_config` reads — PASS (inert)

```
122|        signals = self._load_signals()
```
Constant stub (see §1.6), and `signal_*` columns are not referenced by `long_conditions` /
`short_conditions` (`:141-156`).

**Verdict — CLEAN.**

Residual note (not lookahead, but it breaks the "out-of-sample" claim): this strategy is loaded
with a hyperopt parameter file, `user_data/strategies/BollingerMeanReversion.json`
(`export_time: 2026-05-14 10:41:11`, `ft_stratparam_v: 1`), which overrides the class defaults
(`atr_multiplier=1.3`, `risk_reward=2.6`, `bb_period=16`, `rsi_oversold=40`, …). An export dated
2026-05-14 cannot be fitted only on data ending before the validation window opens on 2026-01-01;
the fit window overlaps the validation window by ~4.5 months. Recorded here, expanded in
`PHASE2_1_REPORT.md` §4.4 — no file edit was made for it.

---

## 3. Checklist summary

| Checklist item | SupertrendEma | BollingerMR |
|---|---|---|
| centred rolling windows | PASS (`:120`) | PASS (`:96`, qtpylib `:256-277`) |
| `shift(-n)` | PASS (only `shift(1)`, `shift(5)`) | PASS (none) |
| ± half-bar swing windows | N/A | N/A |
| `resample().last()` of current period | N/A (4h comes from dp) | N/A |
| live `shared_config` JSON in `populate_*` | PASS — constant stub, unused | PASS — constant stub, unused |
| informative-pair alignment | **FAIL — `:130` (4h merged on raw stamp, `:122-132`)** | PASS — 1h→1h (`:107`) |

**Action taken:** `BollingerMeanReversion.py` was edited (stop logic only, §`STOP_FIXES.md`).
`SupertrendEmaStrategy.py` was **not** edited; its validation number is reported in
`PHASE2_1_REPORT.md` as "unchanged, lookahead-suspect", not as a fixed result.
