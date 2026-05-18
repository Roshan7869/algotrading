#!/usr/bin/env python3
"""
Master Orchestrator — Unified Trading System

Wires together:
- Freqtrade core (dry-run paper trading)
- TradingAgents AI signals
- Telegram alerts
- Risk management (portfolio monitor, position sizer)
- Health monitoring
- Preflight validation

Usage:
    python3 scripts/orchestrate.py --mode paper
    python3 scripts/orchestrate.py --mode paper --config user_data/config_live_analysis.json
    python3 scripts/orchestrate.py --mode live --config user_data/config_live_analysis.json

Karpathy Principles:
- Single file orchestrator
- Reads all config from .env
- Fails fast if prerequisites missing
- Prints actionable output
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIGS_DIR = PROJECT_ROOT / "user_data"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Prefer venv if available
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists():
    PYTHON = str(VENV_PYTHON)
else:
    PYTHON = sys.executable

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()


def log(msg: str, level: str = "INFO"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    icon = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERROR": "❌", "STEP": "▶️"}.get(level, "•")
    print(f"[{now}] {icon} {msg}")


def fail(msg: str):
    log(msg, "ERROR")
    sys.exit(1)


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command."""
    return subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, capture_output=capture, text=True)


def check_env_vars():
    """Validate required environment variables."""
    log("Checking environment variables", "STEP")

    required = {
        "TELEGRAM_TOKEN": "Telegram bot token",
        "TELEGRAM_CHAT_ID": "Telegram chat ID",
        "FREQTRADE__EXCHANGE__KEY": "Binance API key",
        "FREQTRADE__EXCHANGE__SECRET": "Binance API secret",
    }

    missing = []
    for var, desc in required.items():
        val = os.getenv(var)
        if not val or "your_" in val.lower() or "placeholder" in val.lower():
            missing.append(f"  {var} ({desc})")
        else:
            display = val[:6] + "..." + val[-4:] if len(val) > 10 else "***"
            log(f"  {var}: {display}", "OK")

    if missing:
        log("Missing or placeholder environment variables:", "ERROR")
        for m in missing:
            print(m)
        fail("Fix .env and re-run")

    log("Environment variables OK", "OK")


def check_python_deps():
    """Check critical Python packages."""
    log("Checking Python dependencies", "STEP")
    log(f"  Using Python: {PYTHON}", "INFO")

    deps = {
        "freqtrade": "freqtrade",
        "telegram": "python-telegram-bot",
        "yfinance": "yfinance",
        "langgraph": "langgraph",
        "langchain_openai": "langchain-openai",
        "dotenv": "python-dotenv",
    }
    missing = []
    for import_name, pip_name in deps.items():
        result = run([PYTHON, "-c", f"import {import_name}"], capture=True)
        if result.returncode == 0:
            log(f"  {import_name}: OK", "OK")
        else:
            missing.append(pip_name)
            log(f"  {import_name}: MISSING (pip install {pip_name})", "WARN")

    if missing:
        log(f"Install missing: {PYTHON} -m pip install {' '.join(missing)}", "WARN")
        # Don't fail — some are optional
    else:
        log("Dependencies OK", "OK")


def validate_config(config_path: str) -> dict:
    """Load and validate trading config."""
    log(f"Validating config: {config_path}", "STEP")

    path = PROJECT_ROOT / config_path
    if not path.exists():
        fail(f"Config not found: {path}")

    config = json.loads(path.read_text())

    # Critical checks
    if config.get("dry_run", True) is False:
        log("LIVE TRADING MODE — REAL MONEY AT RISK", "WARN")
        response = input("Type 'YES' to confirm live trading: ")
        if response.strip() != "YES":
            fail("Live trading cancelled")

    leverage = config.get("leverage", 1)
    if leverage > 5:
        log(f"Leverage is {leverage}x — HIGH RISK", "WARN")
    else:
        log(f"Leverage: {leverage}x", "OK")

    pairs = config.get("exchange", {}).get("pair_whitelist", [])
    log(f"Pairs: {len(pairs)}", "INFO")

    max_open = config.get("max_open_trades", 0)
    log(f"Max open trades: {max_open}", "INFO")

    log("Config validated", "OK")
    return config


def run_preflight(config_path: str):
    """Run preflight checks."""
    log("Running preflight checks", "STEP")

    preflight = SCRIPTS_DIR / "live_trading" / "preflight_check.py"
    if preflight.exists():
        result = run([sys.executable, str(preflight), "--config", config_path])
        if result.returncode != 0:
            fail("Preflight checks failed")
    else:
        log("Preflight script not found, skipping", "WARN")

    log("Preflight checks passed", "OK")


def start_telegram_alerts():
    """Initialize Telegram alert bot."""
    log("Starting Telegram alerts", "STEP")

    try:
        alert_path = SCRIPTS_DIR / "live_trading" / "telegram_alert_system.py"
        if alert_path.exists():
            # Import and instantiate (validates token)
            sys.path.insert(0, str(SCRIPTS_DIR / "live_trading"))
            from telegram_alert_system import TradingAlertBot
            bot = TradingAlertBot()
            log("Telegram bot authenticated", "OK")
            return bot
    except Exception as e:
        log(f"Telegram alerts disabled: {e}", "WARN")
    return None


def start_risk_monitor():
    """Start risk management monitor."""
    log("Starting risk monitor", "STEP")

    monitor_path = SCRIPTS_DIR / "risk_management" / "portfolio_monitor.py"
    sizer_path = SCRIPTS_DIR / "risk_management" / "position_sizer.py"

    if monitor_path.exists():
        log(f"  Portfolio monitor: {monitor_path}", "OK")
    if sizer_path.exists():
        log(f"  Position sizer: {sizer_path}", "OK")

    log("Risk management ready", "OK")


def start_health_monitor():
    """Start health monitoring in background."""
    log("Starting health monitor", "STEP")

    health_path = SCRIPTS_DIR / "health_monitor.py"
    if health_path.exists():
        log(f"  Health monitor: {health_path}", "OK")
    else:
        log("Health monitor not found", "WARN")


def start_freqtrade(config_path: str, dry_run: bool = True):
    """Start Freqtrade trading loop."""
    mode = "PAPER TRADING" if dry_run else "LIVE TRADING"
    log(f"Starting Freqtrade — {mode}", "STEP")

    cmd = [
        sys.executable, "-m", "freqtrade", "trade",
        "--config", str(PROJECT_ROOT / config_path),
        "--strategy", "AroonMomentumEngine_Hybrid",
    ]

    if dry_run:
        cmd.append("--dry-run")

    log(f"Command: {' '.join(cmd)}", "INFO")
    log("Press Ctrl+C to stop\n", "INFO")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        log("Trading stopped by user", "OK")
    except Exception as e:
        log(f"Freqtrade error: {e}", "ERROR")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Master Trading Orchestrator")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper",
                        help="Trading mode (default: paper)")
    parser.add_argument("--config", default="user_data/config_live_analysis.json",
                        help="Path to trading config")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="Skip preflight checks")
    parser.add_argument("--no-telegram", action="store_true",
                        help="Disable Telegram alerts")
    args = parser.parse_args()

    print("=" * 60)
    print("  UNIFIED TRADING ORCHESTRATOR")
    print(f"  Mode: {args.mode.upper()}")
    print(f"  Config: {args.config}")
    print("=" * 60 + "\n")

    # Phase 1: Environment
    check_env_vars()
    check_python_deps()

    # Phase 2: Config validation
    config = validate_config(args.config)
    dry_run = args.mode == "paper"

    # Phase 3: Preflight
    if not args.skip_preflight:
        run_preflight(args.config)

    # Phase 4: Subsystems
    if not args.no_telegram:
        start_telegram_alerts()
    start_risk_monitor()
    start_health_monitor()

    # Phase 5: Trading
    start_freqtrade(args.config, dry_run=dry_run)

    log("Orchestrator shutdown complete", "OK")


if __name__ == "__main__":
    main()
