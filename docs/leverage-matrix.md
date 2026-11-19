# Leverage matrix — where leverage actually comes from

**Owner:** Phase 1.2 (`EXECUTION_PLAN.md`). **Repo state:** `git rev-parse HEAD` = `7977650755f7178924b4fbcd18dee2b8e75ea426`
(freqtrade `2026.5-dev-797765075`, editable install of the in-repo `freqtrade/` tree).
**Method:** every row below was read from the strategy source, not grepped from configs. Line numbers are
from the tree at the SHA above.

## TL;DR

- **No freqtrade code path reads a `leverage` key from the config.** It is not even a property of
  `CONF_SCHEMA` (`freqtrade/config_schema/config_schema.py`); configs only carry it as an ignored extra key.
- The operative value is `strategy.leverage(...)`, clamped to `[1.0, exchange.get_max_leverage(pair, stake)]`.
- Six of the eight surviving strategies return a **hard-coded 3.0**; two Aroon strategies read a signal
  file with a **5.0 hard cap**, and on this host (no `SHARED_CONFIG_DIR`, no `/freqtrade/shared_config`)
  they always fall back to **2.0**.
- Effective leverage range in the repo after consolidation: **2.0 – 5.0**, not the 3→18 previously implied
  by the config pile.

## Per-strategy table

| # | Strategy | Leverage source (file:line) | Returns | Notes |
|---|---|---|---|---|
| 1 | `AroonMomentumEngine_Hybrid` | `user_data/strategies/AroonMomentumEngine_Hybrid.py:152` (def), `:168` (signal path), `:172` (default 2.0), `:179` (return) | `min(signal, 5.0, max_leverage)`; signal file holds **3.0**, but the read path resolves to a non-existent directory on this host → **2.0** | Only strategy with a literal `# Hard cap at 5x` comment. Reads `SHARED_CONFIG_DIR` (default `/freqtrade/shared_config`), env unset → `Path('/freqtrade/shared_config/leverage_signal.json')` → does not exist → `except`/else branch → 2.0. |
| 2 | `AroonMomentumEngine_V2` | `user_data/strategies/AroonMomentumEngine_V2.py:147` (def), `:160` (signal path), `:164` (default 2.0), `:169` (return) | same as #1 → **2.0** on this host, 5.0 ceiling | Identical signal-file pattern. Telegram banner claims "Dynamic (2-5x)" — accurate only if the signal path resolves. |
| 3 | `BollingerMeanReversion` | `user_data/strategies/BollingerMeanReversion.py:69` (def), `:70` (return) | `min(3.0, max_leverage)` → **3.0** | Constant. |
| 4 | `DmiAdxStrategy` | `user_data/strategies/DmiAdxStrategy.py:71` (def), `:72` (return) | `min(3.0, max_leverage)` → **3.0** | Constant. |
| 5 | `EmaTrendFollowing` | `user_data/strategies/EmaTrendFollowing.py:71` (def), `:72` (return) | `min(3.0, max_leverage)` → **3.0** | Constant. |
| 6 | `EnsembleStrategy` (`ensemble_strategy.py`) | `user_data/strategies/ensemble_strategy.py:131` (def), `:132` (return) | `min(3.0, max_leverage)` → **3.0** | Constant; the class also carries a `signal_leverage` dataframe column (`:251`, `:264`) that **never reaches** the callback — the return is hard-coded. |
| 7 | `MacdRsiStrategy` | `user_data/strategies/MacdRsiStrategy.py:72` (def), `:73` (return) | `min(3.0, max_leverage)` → **3.0** | Constant. |
| 8 | `SupertrendEmaStrategy` | `user_data/strategies/SupertrendEmaStrategy.py:67` (def), `:68` (return) | `min(3.0, max_leverage)` → **3.0** | Constant. |

`max_leverage` in every row is `exchange.get_max_leverage(pair, stake_amount)` — 1.0 in spot mode, and the
pair's leverage-tier cap in futures (`freqtrade/exchange/exchange.py:3674`).

## Where freqtrade reads leverage

Exhaustive: these are the only two call sites of `strategy.leverage` in the tree.

1. **Dry-run / live order path** — `freqtrade/freqtradebot.py:1142-1157`:
   ```
   1142  if self.trading_mode != TradingMode.SPOT and trade is None:
   1143      max_leverage = self.exchange.get_max_leverage(pair, stake_amount)
   1144      if leverage_:                      # entry-signal leverage, else:
   1147          leverage = strategy_safe_wrapper(self.strategy.leverage, default_retval=1.0)(...)
   1156      # Cap leverage between 1.0 and max_leverage.
   1157      leverage = min(max(leverage, 1.0), max_leverage)
   ```
2. **Backtesting** — `freqtrade/optimize/backtesting.py:1021-1036`: same shape, and at `:1032-1033`
   `if self.trading_mode != TradingMode.SPOT ... else 1.0` — **spot is forced to 1.0**.
3. **Default callback** — `freqtrade/strategy/interface.py:828-851`: `return 1.0`, i.e. a strategy without
   an override trades at 1x, and the docstring says the return must be "between 1.0 and max_leverage".

Verification of the negative: `grep -rn 'config.*leverage\|leverage.*config' freqtrade/configuration/*.py
freqtrade/resolvers/*.py freqtrade/strategy/interface.py` → **0 hits**; `grep -n '"leverage"' freqtrade/config_schema/config_schema.py` → **0 hits**.
The `leverage` key in a freqtrade config is therefore **inert**; it survives schema validation only because
the root schema sets no `additionalProperties: false`.

## What the config `leverage` key is still for

Repo-side scripts read it as an advisory number (never as an order-path cap):

| Consumer | Line | Use |
|---|---|---|
| `scripts/agents/risk_gate.py` | `:50` | `self.config.get("leverage", 1)` — risk sizing input; risk_gate still has **no order-path call site** (plan R2) |
| `scripts/live_trading/preflight_check.py` | `:175` | preflight display/threshold check |
| `scripts/orchestrate.py` | `:140` | orchestration display |
| `scripts/config_loader.py` | `:81` | prints "Leverage: …" |
| `scripts/validation/test_configs.py` | `:128` | asserts `== 10` for a **moved** legacy config family (now in `attic/configs/`) |

Because those readers exist, the canonical configs keep the key (removing it would flip
`config.get("leverage", 1)` to 1 silently). It is documented in each config's `_comment` as advisory.

## The nine former "leverage sources" → what actually remains

| Former source | Status after Phase 1.2 | Real effect |
|---|---|---|
| `config.json` = 6, `config_backtest*_6x/9x/_10x/_12x` = 6/9/9/10/12, `config_live_trading_6x` = **18**, `*_p3*.json` = `{"3": 3}` (a **dict**, not a number) | moved to `attic/configs/` | none — freqtrade never read them |
| Canonical `config_backtest.json` = 6, `config_dryrun.json` = 3, `config_spot.json` = 1 | kept, annotated `_comment` | advisory for repo scripts only; spot is 1.0 by construction |
| `shared_config/leverage_signal.json` = 3.0 (`_written_by: signal_bus`, `_timestamp` 2026-05-14) | kept (runtime signal, not a config) | **inert on Windows native runs** — only read if `SHARED_CONFIG_DIR` points at `shared_config/`; the strategies' default is the Docker path `/freqtrade/shared_config` |
| `user_data/strategies/leverage_config.py` (`DEFAULT_LEVERAGE = 3.0`, `get_leverage()`) | left in place (a `.py` module, not a config) | **zero callers** — `grep -rn 'get_leverage('` outside its own definition → 0 hits; referenced only inside two prose strings (`AroonMomentumEngine_Hybrid.py:78`, `scripts/backtesting/Run-7Day-Backtest-{6,18}x.ps1:10`) |
| 8 `leverage()` callbacks | unchanged (strategy files are out of scope for 1.2) | **the only operative source** |

## Interaction with stoploss (why this table matters)

freqtrade divides the stoploss by leverage when sizing the exit: a `-0.05` stoploss at 3x is a **-1.67% price
move**, at 5x it is **-1.0%**. The canonical configs now carry `stoploss: -0.05` **explicitly**, and a
config-level stoploss **overrides** the strategy attribute (`freqtrade/resolvers/strategy_resolver.py:106-114`,
prevalence "Configuration > Strategy > default"). Every strategy also declares its own stoploss
(`-0.04` BollingerMeanReversion, `-0.06` AroonMomentumEngine_Hybrid and EmaTrendFollowing, `-0.05` the other
five), so the single config value **is a deliberate ceiling**: five strategies match it exactly, Bollinger
is loosened 4%→5%, the two 6% strategies are tightened 6%→5%.

## Residual risks

1. **Signal-file leverage is unreachable on this host.** `AroonMomentumEngine_*` will trade 2.0x, not the
   3.0 stored in `shared_config/leverage_signal.json`, unless `SHARED_CONFIG_DIR` is exported. Fix belongs to
   whoever wires the dry-run launcher (Phase 0.3 / 2.3) — do **not** patch strategy files from this phase.
2. **`leverage_config.py` is dead code** with a plausible-looking API. It is a candidate for the same attic
   treatment once the two `.ps1` banners that mention it are retired.
3. **Any future "config leverage cap" idea is a no-op** unless it is implemented as a strategy-side clamp or a
   strategy wrapper; adding a key to JSON will never be honored.
