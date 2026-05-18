#!/usr/bin/env python3
"""
Pre-Backtest Validation Script
Checks if all requirements are met before running backtest
"""

import sys
from pathlib import Path
import json


def check_strategy_exists(strategy_name):
    """Verify strategy file exists"""
    strategy_path = Path(f"user_data/strategies/{strategy_name}.py")
    return strategy_path.exists()


def check_data_exists(pairs, timeframes):
    """Verify data files exist for all pair/timeframe combinations"""
    data_dir = Path("user_data/data/binance/futures")
    missing = []

    for pair in pairs:
        pair_file = pair.replace("/", "_").replace(":", "_")
        for tf in timeframes:
            data_file = data_dir / f"{pair_file}-{tf}-futures.feather"
            if not data_file.exists():
                missing.append(f"{pair} - {tf}")

    return missing


def check_config_valid(config_path):
    """Verify config file is valid JSON"""
    try:
        with open(config_path) as f:
            config = json.load(f)
        return True, config
    except Exception as e:
        return False, str(e)


def main():
    print("🔍 Pre-Backtest Validation")
    print("=" * 60)

    # Load config
    config_path = "user_data/config_market_ready.json"
    valid, config = check_config_valid(config_path)

    if not valid:
        print(f"❌ Config invalid: {config}")
        return False

    print(f"✅ Config valid: {config_path}")

    # Check strategy
    strategy = config.get("strategy", "AroonMomentumEngine_Hybrid")
    if check_strategy_exists(strategy):
        print(f"✅ Strategy exists: {strategy}")
    else:
        print(f"❌ Strategy NOT found: {strategy}")
        return False

    # Check data
    pairs = config["exchange"]["pair_whitelist"]
    timeframes = ["1h", "4h"]

    missing = check_data_exists(pairs, timeframes)
    if missing:
        print(f"❌ Missing data for:")
        for m in missing:
            print(f"   - {m}")
        return False
    else:
        print(
            f"✅ All data present ({len(pairs)} pairs × {len(timeframes)} timeframes)"
        )

    print("\n" + "=" * 60)
    print("✅ ALL CHECKS PASSED - Ready for backtest!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
