# ATTIC — decision quarantine (Phase 1.1)

Nothing in here is evidence. Files moved here on 2026-11-19 per EXECUTION_PLAN.md v0.2 §1.1.
The directory is **gitignored**: moved files leave the tracked tree (their blobs remain in git
history until the scheduled P1.5 object purge — backup bundle required first).

| Entry | Size | Reason moved |
|---|---|---|
| `results/` | 256 KB | Unvalidated backtest/result artifacts: batch_results*, godmode_* (incl. the +3.6M% compounding artifact), eden_*, generated_results_*, all_results_8y*, analysis_8y_spot, omni_results_*, kronos_results_*, strategy_rankings, UTF-16 backtest txts. Their headline rows belong to quarantined lookahead strategies or deleted strategy files — see `D:/nexus-data/audits/algotrading/run_artifacts_audit.md`. |
| `Algo @ 2/` | 356 MB | Duplicate legacy subtree (an older copy of the repo). Pure mass. |
| `claude-boilerplate/` | 2.8 MB | `.claude/` — 217 vendored boilerplate files with no consumer. |
| `docs-upstream/` | 8.4 MB | Upstream freqtrade documentation (GPL-3, unmodified, retained here per license). Runtime does not read it. |
| `notebooks/` | 16 KB | Stock freqtrade notebook templates. |
| `research/` | 276 KB | Fabio Valentino chunk dump + a 222 KB conversation transcript — inputs to old experiments, not results. |
| `misc/` | 57 KB | Old config artifact with `/home/roshan` paths (`ga.json`), stale `available_pairs.json`, stray txt outputs. |
| `configs/` | — | Populated by Phase 1.2 config consolidation (inventory in `configs/MOVED.md`). |

Also deleted (not attic): `user_data/tradesv3.dryrun.sqlite`(+shm/wal) — 0 rows, corrupt WAL,
never a paper record (Phase 0.5); `.git-rewrite/` filter-repo leftovers.

Reproducibility contract reminder: a number is only used in a decision if it carries git SHA +
data manifest + config path + cost model. Nothing in this attic qualifies.
