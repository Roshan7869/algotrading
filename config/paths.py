"""Centralized path definitions for the Algotrading project.

All code should import paths from here rather than hardcoding relative paths.
"""

from pathlib import Path

# ── Project Root ─────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# ── Data / User Directories ──────────────────────────────────────────────────
USER_DATA_DIR: Path = PROJECT_ROOT / "user_data"
STRATEGIES_DIR: Path = USER_DATA_DIR / "strategies"
ARCHIVED_STRATEGIES_DIR: Path = STRATEGIES_DIR / "_archived"
DATA_DIR: Path = USER_DATA_DIR / "data"
CONFIG_DIR: Path = PROJECT_ROOT / "config"

# ── Shared Runtime Config ────────────────────────────────────────────────────
SHARED_DIR: Path = PROJECT_ROOT / "shared_config"

# ── Core Modules ─────────────────────────────────────────────────────────────
ENGINE_DIR: Path = PROJECT_ROOT / "engine"
AGENTS_DIR: Path = PROJECT_ROOT / "agents"
KNOWLEDGE_DIR: Path = PROJECT_ROOT / "knowledge"
SWARM_DIR: Path = PROJECT_ROOT / "swarm"
MCP_LAYER_DIR: Path = PROJECT_ROOT / "mcp_layer"
MONITORING_DIR: Path = PROJECT_ROOT / "monitoring"
CORE_DIR: Path = PROJECT_ROOT / "core"

# ── Strategy Knowledge Base ──────────────────────────────────────────────────
STRATEGY_DB_DIR: Path = PROJECT_ROOT / "strategy_db"
USER_KB_DIR: Path = PROJECT_ROOT / "user_kb"

# ── NEXUS ────────────────────────────────────────────────────────────────────
NEXUS_DIR: Path = PROJECT_ROOT / "nexus"

# ── Tests ────────────────────────────────────────────────────────────────────
TESTS_DIR: Path = PROJECT_ROOT / "tests"

# ── UI ───────────────────────────────────────────────────────────────────────
UI_DIR: Path = PROJECT_ROOT / "ui"

# ── Scripts ──────────────────────────────────────────────────────────────────
SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"

# ── Optimisation ─────────────────────────────────────────────────────────────
OPTIMISATION_DIR: Path = PROJECT_ROOT / "strat_optimisation"

# ── Convenience Shortcuts ────────────────────────────────────────────────────
CONFIG_JSON: Path = USER_DATA_DIR / "config.json"
ENV_FILE: Path = PROJECT_ROOT / ".env"
DOCKER_COMPOSE: Path = PROJECT_ROOT / "docker-compose.yml"
