# CONFIG CONSOLIDATION — measured before/after

**Phase 1.2 of `EXECUTION_PLAN.md`.** Repo `D:\dev\algotrading`, HEAD `7977650755f7178924b4fbcd18dee2b8e75ea426`.
All numbers below were counted on this machine on 2026-11-19, not inherited from the plan.

## Counts

| Metric | Before | After | Command used |
|---|---|---|---|
| Tracked `user_data/config*.json` | **112** | **3** (working tree) / 112 (git index) | `git ls-files 'user_data/config*.json' \| wc -l`, `ls user_data/config*.json \| wc -l` |
| Tracked `user_data/config*.json`, non-archive | 52 | 3 | `git ls-files 'user_data/config*.json' \| grep -vc '^user_data/config_archive/'` |
| `user_data/config_archive/` files | 60 | 0 (dir gone) | `ls user_data/config_archive/*.json \| wc -l` |
| `config_examples/` files | 4 | 0 (dir gone) | `ls config_examples/*.json \| wc -l` |
| All on-disk `user_data/**` files whose name contains `config` and ends `.json` | 54 (52 `.json` + 2 `.DISABLED/.DANGEROUS`) | **3** | `find user_data -name '*config*.json'` |
| Path-matched `*config*.json` on disk (excl. `.venv`, `attic`, `TradingAgents`, `.git`) | 172 | **59** | python `rglob`, see note 1 |
| `attic/configs/` files | 0 | **117** (116 moved + `MOVED.md`) | `find attic/configs -type f \| wc -l` |
| Validator checks passing | 152 (with 112 configs present) | **43** (3 canonical × 14 checks, 0 others) | `scripts/validate_configs.py` |

Note 1 — the `git ls-files '*config*.json'` pathspec of 172 is **larger than the basename count** because
`*` matches across `/`, so every file under `shared_config/` matches on the directory name. The
apples-to-apples working-tree figure is 59; the drop is 113 tracked files (49 root + 60 archive +
4 examples), which matches the 112 → 3 tracked count plus the 4 example files.

**Why the index still says 112:** this lane is forbidden to run git write commands. The files are
gone from the working tree; `git rm --cached` + `.gitignore` + the commit are the orchestrator's step
(`EXECUTION_PLAN.md` principle 6). Until then every moved path shows as a deletion, not a rename.

## Canonical set (the only three configs a bot run may use)

| Config | Mode | dry_run | stake_amount | max_open_trades | stoploss | db_url | leverage key (advisory) | pairs |
|---|---|---|---|---|---|---|---|---|
| `user_data/config_backtest.json` | futures, isolated | true | `unlimited` | 4 | -0.05 | `sqlite:///tradesv3.backtest.sqlite` | 6 | 10 |
| `user_data/config_spot.json` | spot | true | 50 | 3 | -0.05 | `sqlite:///tradesv3.spot.sqlite` | 1 | 8 |
| `user_data/config_dryrun.json` | futures, isolated | true | `unlimited` | 3 | -0.05 | `sqlite:///tradesv3.dryrun.sqlite` | 3 | 5 |

MD5 at hand-off: `d83eb1c0b6a4a323cedd35b996da244e` (backtest), `b780c7f17b089c39e90fd027b3212e7a`
(spot), `8a2a9d59fe827103fee4bb85ef8f732b` (dryrun).

## Untouched by design

| Tree | Files | Reason |
|---|---|---|
| `HEdge/configs/` | 17 | separate HEdge experiment tree with its own `run_all_backtests.sh` |
| `strat_optimisation/configs/` (+ `archive/`) | 9 | separate optimisation tree, own runner |
| `shared_config/*.json` | 18 | live runtime state (signals, regime, health), not bot config |
| `tests/**/*config*.json` | 9 | freqtrade upstream test fixtures |
| `scripts/regime/regime_config.json` | 1 | regime-router config |

These are outside `user_data/`, are not freqtrade bot configs, and have their own consumers. If a
later phase wants the same treatment, it needs the same consumer sweep first.
