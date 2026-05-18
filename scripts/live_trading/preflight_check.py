"""
Pre-Flight Validation Script
Run this before starting live trading to ensure everything is configured correctly.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def load_dotenv_if_present(path: str = ".env"):
    """Minimal .env loader so preflight works without python-dotenv."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class PreFlightValidator:
    """Validate system readiness for live trading."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.errors = []
        self.warnings = []
        self.passed = []

    def run_all_checks(self) -> bool:
        """Run all validation checks."""
        print(f"\n{BLUE}{'=' * 60}{RESET}")
        print(f"{BLUE}PRE-FLIGHT VALIDATION - LIVE TRADING READINESS{RESET}")
        print(f"{BLUE}{'=' * 60}{RESET}\n")

        checks = [
            ("Configuration File", self.check_config_file),
            ("Strategy File", self.check_strategy_file),
            ("Telegram Credentials", self.check_telegram),
            ("Exchange API Keys", self.check_api_keys),
            ("Data Availability", self.check_data),
            ("Risk Limits", self.check_risk_limits),
            ("Leverage Settings", self.check_leverage),
            ("Order Types", self.check_order_types),
        ]

        for check_name, check_func in checks:
            self._run_check(check_name, check_func)

        # Print summary
        self._print_summary()

        return len(self.errors) == 0

    def _run_check(self, name: str, func):
        """Run a single check."""
        try:
            func()
            self.passed.append(name)
            print(f"{GREEN}[PASS]{RESET} {name}")
        except Exception as e:
            self.errors.append((name, str(e)))
            print(f"{RED}[FAIL]{RESET} {name}: {e}")

    def check_config_file(self):
        """Validate config file exists and is valid JSON."""
        if not os.path.exists(self.config_path):
            raise Exception(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = json.load(f)

        # Store for other checks
        self.config = config

    def _resolve_secret(self, value: str) -> str:
        """Resolve ${ENV_VAR} placeholders used by Freqtrade configs."""
        if not isinstance(value, str):
            return ""
        if value.startswith("${") and value.endswith("}"):
            return os.getenv(value[2:-1], "")
        return value

    def check_strategy_file(self):
        """Validate strategy file exists."""
        strategy_name = self.config.get("strategy")
        if not strategy_name:
            raise Exception("No strategy specified in config")

        strategy_path = (
            Path(self.config_path).parent / "strategies" / f"{strategy_name}.py"
        )
        if not strategy_path.exists():
            raise Exception(f"Strategy file not found: {strategy_path}")

        if strategy_name != "AroonMomentumEngine_Hybrid":
            self.warnings.append(
                f"Using strategy: {strategy_name} (expected AroonMomentumEngine_Hybrid)"
            )

    def check_telegram(self):
        """Validate Telegram configuration."""
        telegram = self.config.get("telegram", {})

        if not telegram.get("enabled"):
            self.warnings.append("Telegram alerts are DISABLED")
            return

        token = self._resolve_secret(telegram.get("token", ""))
        chat_id = self._resolve_secret(telegram.get("chat_id", ""))

        if not token or token == "YOUR_BOT_TOKEN_HERE":
            raise Exception("Telegram bot token not configured")

        if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
            raise Exception("Telegram chat_id not configured")

    def check_api_keys(self):
        """Validate exchange API keys."""
        exchange = self.config.get("exchange", {})

        # For dry_run, API keys are optional
        if self.config.get("dry_run", True):
            self.warnings.append("Running in DRY RUN mode (paper trading)")
            return

        key = self._resolve_secret(exchange.get("key", ""))
        secret = self._resolve_secret(exchange.get("secret", ""))

        if not key or not secret:
            raise Exception("Exchange API keys not configured for LIVE trading")

    def check_data(self):
        """Check if required data files exist."""
        pairs = self.config.get("exchange", {}).get("pair_whitelist", [])

        if not pairs:
            raise Exception("No pairs in whitelist")

        if len(pairs) > 12:
            self.warnings.append(f"Watchlist has {len(pairs)} pairs (recommended <= 12)")

        # Check for required pairs
        required_pairs = ["RENDER/USDT:USDT", "DOGE/USDT:USDT", "1000PEPE/USDT:USDT"]
        missing = [p for p in required_pairs if p not in pairs]
        if missing:
            self.warnings.append(f"Missing recommended pairs: {missing}")

    def check_risk_limits(self):
        """Validate risk management settings."""
        max_trades = self.config.get("max_open_trades", 0)

        if max_trades > 3:
            self.warnings.append(f"max_open_trades is {max_trades} (recommended: 3 for rollout)")

        if max_trades > 10:
            raise Exception(
                f"max_open_trades too high: {max_trades} (max recommended: 10)"
            )

    def check_leverage(self):
        """Validate leverage settings."""
        leverage = self.config.get("leverage", 1)

        if leverage > 3:
            self.warnings.append(f"Leverage is {leverage}x (recommended <= 3x for rollout)")

        if leverage > 12:
            raise Exception(f"Leverage too high: {leverage}x (max recommended: 12x)")

    def check_order_types(self):
        """Validate order type configuration."""
        strategy_name = self.config.get("strategy", "")
        exit_pricing = self.config.get("exit_pricing", {})

        if strategy_name == "AroonMomentumEngine_Hybrid":
            if exit_pricing.get("price_side") != "other":
                raise Exception(
                    "exit_pricing.price_side must be 'other' because strategy exits use market orders"
                )

        # For v2_Optimized, exit should be market
        if "v2_Optimized" in strategy_name:
            if exit_pricing.get("price_side") != "other":
                raise Exception(
                    "exit_pricing.price_side must be 'other' for market exits"
                )

    def _print_summary(self):
        """Print validation summary."""
        print(f"\n{BLUE}{'=' * 60}{RESET}")
        print(f"{BLUE}VALIDATION SUMMARY{RESET}")
        print(f"{BLUE}{'=' * 60}{RESET}\n")

        print(f"{GREEN}[PASS] Passed:{RESET} {len(self.passed)}")
        print(f"{YELLOW}[WARN] Warnings:{RESET} {len(self.warnings)}")
        print(f"{RED}[FAIL] Errors:{RESET} {len(self.errors)}\n")

        if self.warnings:
            print(f"{YELLOW}Warnings:{RESET}")
            for warning in self.warnings:
                print(f"  [!] {warning}")
            print()

        if self.errors:
            print(f"{RED}Errors (MUST FIX):{RESET}")
            for name, error in self.errors:
                print(f"  [X] {name}: {error}")
            print()

        if len(self.errors) == 0:
            print(f"{GREEN}{'=' * 60}{RESET}")
            print(f"{GREEN}ALL CHECKS PASSED - READY FOR DEPLOYMENT{RESET}")
            print(f"{GREEN}{'=' * 60}{RESET}\n")
        else:
            print(f"{RED}{'=' * 60}{RESET}")
            print(f"{RED}VALIDATION FAILED - FIX ERRORS BEFORE DEPLOYMENT{RESET}")
            print(f"{RED}{'=' * 60}{RESET}\n")


def main():
    """Main entry point."""
    import argparse

    load_dotenv_if_present()

    parser = argparse.ArgumentParser(
        description="Pre-Flight Validation for Live Trading"
    )
    parser.add_argument(
        "--config",
        default="user_data/config_live_trading_10x.json",
        help="Path to config file",
    )

    args = parser.parse_args()

    validator = PreFlightValidator(config_path=args.config)
    success = validator.run_all_checks()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
