# =============================================================================
# Algotrading Makefile
# =============================================================================

SHELL := /bin/bash
.PHONY: run stop dashboard test lint clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Core ────────────────────────────────────────────────────────────────────

run: ## Start core trading stack (dry-run by default)
	docker compose --profile core up -d

stop: ## Stop all containers
	docker compose down

restart: stop run ## Restart core stack

logs: ## Tail logs from freqtrade container
	docker compose logs -f freqtrade

# ─── Profiles ────────────────────────────────────────────────────────────────

full: ## Start full stack (core + AI agents)
	docker compose --profile full up -d

dev: ## Start dev stack (core + AI + Jupyter)
	docker compose --profile dev up -d

# ─── Testing ─────────────────────────────────────────────────────────────────

test: ## Run all tests
	python -m pytest tests/ -x -v --timeout=120 2>&1 | tail -20

test-fast: ## Run tests excluding integration/redis-dependent
	python -m pytest tests/ -x -v --timeout=120 \
		--ignore=tests/test_integration_pipeline.py \
		--ignore=tests/test_signal_bus.py \
		--ignore=tests/test_hedge_coordinator.py \
		2>&1 | tail -20

test-file: ## Run a specific test file: make test-file f=tests/test_foo.py
	python -m pytest $(f) -x -v --timeout=120

# ─── Linting ─────────────────────────────────────────────────────────────────

lint: ## Run ruff linter
	ruff check . --ignore F821,E402

lint-fix: ## Auto-fix lint issues
	ruff check . --ignore F821,E402 --fix

typecheck: ## Run mypy type checker
	mypy config/paths.py 2>&1 | tail -5

# ─── Cleanup ─────────────────────────────────────────────────────────────────

clean: ## Clean cache, pyc, and temp files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf user_data/backtest_results* 2>/dev/null || true
	echo "Cleaned."

# ─── Maintenance ─────────────────────────────────────────────────────────────

reset-db: ## Reset SQLite trade database (backup first)
	cp user_data/tradesv3.sqlite user_data/tradesv3.sqlite.bak 2>/dev/null || true
	rm -f user_data/tradesv3.sqlite
	@echo "Database reset (backup saved as .bak)"

backup: ## Quick backup of key state files
	mkdir -p .backups
	cp user_data/tradesv3.sqlite .backups/tradesv3.sqlite.$$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
	cp shared_config/*.json .backups/ 2>/dev/null || true
	@echo "Backup saved to .backups/"

# ─── Strategy Knowledge Base ─────────────────────────────────────────────────

strategy-ingest: ## Re-index trading strategies into ChromaDB
	python3 strategy_db/ingest.py

strategy-query: ## Query strategy KB: make strategy-query q="liquidity trap"
	python3 strategy_db/gcode_bridge.py query "$(q)"

strategy-stats: ## Show KB stats
	python3 strategy_db/gcode_bridge.py list-types
