"""
Disable Telegram in Backtest Configurations
This script updates all backtest config files to disable Telegram notifications.
"""

import json
import sys
from pathlib import Path

# Config files to update (disable Telegram)
CONFIGS_TO_DISABLE = [
    "user_data/config_backtest_100.json",
    "user_data/config_backtest_20tokens_shorts.json",
    "user_data/config_backtest_300d_10x.json",
    "user_data/config_backtest_300d_12x.json",
    "user_data/config_backtest_300d_6x.json",
    "user_data/config_backtest_300d_9x.json",
    "user_data/config_backtest_300day_STANDARD.json",
    "user_data/config_backtest_6x.json",
    "user_data/config_backtest_9x.json",
    "user_data/config_backtest_9x_top_tokens.json",
    "user_data/config_live_analysis.json",
    "user_data/config_dryrun_wsl_10x.json",
    "user_data/config_aroon_300day_backtest.json",
    "user_data/config_aroon_300day_backtest_9x.json",
    "user_data/config_aroon_momentum_engine.json",
    "user_data/config_aroonmacd_optimized.json",
]

# Config files to keep enabled (live trading only)
CONFIGS_TO_KEEP_ENABLED = [
    "user_data/config_live_trading_6x.json",
    "user_data/config_live_real.json",
]


def disable_telegram_in_config(config_path: Path) -> bool:
    """
    Disable Telegram in a config file.

    Args:
        config_path: Path to config file

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        if not config_path.exists():
            print(f"[WARN] Config not found: {config_path}")
            return False

        # Read config
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Check if telegram section exists
        if "telegram" not in config:
            print(f"[INFO] No telegram section in {config_path.name}")
            return True

        # Disable telegram
        was_enabled = config["telegram"].get("enabled", False)
        config["telegram"]["enabled"] = False

        # Write back
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        if was_enabled:
            print(f"[OK] Disabled Telegram in {config_path.name}")
        else:
            print(f"[INFO] Telegram already disabled in {config_path.name}")

        return True

    except Exception as e:
        print(f"[ERROR] Error updating {config_path.name}: {e}")
        return False


def main():
    """Main entry point."""
    project_root = Path(__file__).parent.parent

    print("=" * 60)
    print("  Disabling Telegram in Backtest Configurations")
    print("=" * 60)
    print()

    success_count = 0
    fail_count = 0

    for config_file in CONFIGS_TO_DISABLE:
        config_path = project_root / config_file
        if disable_telegram_in_config(config_path):
            success_count += 1
        else:
            fail_count += 1

    print()
    print("=" * 60)
    print(f"  Summary: {success_count} updated, {fail_count} failed")
    print("=" * 60)
    print()
    print("[OK] Telegram is now disabled in all backtest configs")
    print("[INFO] Telegram remains enabled in:")
    for config_file in CONFIGS_TO_KEEP_ENABLED:
        print(f"   - {config_file}")
    print()
    print("[WARN] IMPORTANT: Only run ONE live trading instance at a time!")
    print()


if __name__ == "__main__":
    main()
