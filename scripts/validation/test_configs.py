"""
Automated config validation tests.
Run before any live trading to ensure all configs are correct.
"""

import os
import json
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def test_env_variables():
    """Test that all required environment variables are set."""
    print("\n[TEST] Checking environment variables...")

    required_vars = [
        "TELEGRAM_TOKEN",
        "TELEGRAM_CHAT_ID",
    ]

    optional_vars = [
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
    ]

    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    missing_optional = []
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)

    if missing:
        print(f"{RED}[FAIL]{RESET} Missing required environment variables: {missing}")
        return False

    if missing_optional:
        print(
            f"{YELLOW}[WARN]{RESET} Missing optional environment variables: {missing_optional}"
        )
        print(f"        (Required for live trading, OK for paper trading)")

    print(f"{GREEN}[PASS]{RESET} All required environment variables set")
    return True


def test_no_hardcoded_secrets():
    """Test that no configs have hardcoded secrets."""
    print("\n[TEST] Checking for hardcoded secrets...")

    config_dir = Path("user_data")

    issues = []
    for config_file in config_dir.glob("config*.json"):
        try:
            with open(config_file, "r") as f:
                content = f.read()

            # Check for hardcoded tokens (starts with numbers)
            if '"token": "7' in content or '"token":"7' in content:
                issues.append(f"{config_file.name}: Hardcoded Telegram token")

            # Check for hardcoded API keys (long alphanumeric strings in key field)
            if '"key": "' in content:
                key_value = content.split('"key": "')[1].split('"')[0]
                if len(key_value) > 20 and not (
                    key_value.startswith("${") and key_value.endswith("}")
                ):
                    issues.append(f"{config_file.name}: Hardcoded API key")
        except Exception as e:
            print(f"{YELLOW}[WARN]{RESET} Could not read {config_file.name}: {e}")

    if issues:
        print(f"{RED}[FAIL]{RESET} Hardcoded secrets found:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    print(f"{GREEN}[PASS]{RESET} No hardcoded secrets found")
    return True


def test_config_consistency():
    """Test that live configs have consistent settings."""
    print("\n[TEST] Checking config consistency...")

    live_configs = [
        "user_data/config_live_trading_10x.json",
        "user_data/config_live_real.json",
    ]

    issues = []
    warnings = []

    for config_path in live_configs:
        if not Path(config_path).exists():
            warnings.append(
                f"{Path(config_path).name}: File not found (OK if not using)"
            )
            continue

        try:
            with open(config_path, "r") as f:
                config = json.load(f)

            # Check leverage
            if config.get("leverage") != 10:
                issues.append(
                    f"{Path(config_path).name}: Leverage should be 10, found {config.get('leverage')}"
                )

            # Check stoploss (if present)
            if "stoploss" in config and config.get("stoploss") != -0.12:
                warnings.append(
                    f"{Path(config_path).name}: Stoploss should be -0.12, found {config.get('stoploss')}"
                )

            # Check strategy
            if config.get("strategy") != "AroonMomentumEngine_Hybrid":
                issues.append(
                    f"{Path(config_path).name}: Strategy should be AroonMomentumEngine_Hybrid"
                )

            # Check max_open_trades
            if config.get("max_open_trades") != 7:
                warnings.append(
                    f"{Path(config_path).name}: max_open_trades should be 7, found {config.get('max_open_trades')}"
                )

        except Exception as e:
            issues.append(f"{Path(config_path).name}: Error reading config: {e}")

    if warnings:
        for warning in warnings:
            print(f"{YELLOW}[WARN]{RESET} {warning}")

    if issues:
        print(f"{RED}[FAIL]{RESET} Config inconsistencies:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    print(f"{GREEN}[PASS]{RESET} All configs consistent")
    return True


def test_strategy_loads():
    """Test that the strategy file loads without errors."""
    print("\n[TEST] Checking strategy file...")

    try:
        import sys

        sys.path.insert(0, "user_data/strategies")
        from AroonMomentumEngine_Hybrid import AroonMomentumEngine_Hybrid

        # Check for duplicate methods
        methods = [m for m in dir(AroonMomentumEngine_Hybrid) if not m.startswith("_")]
        method_counts = {}
        for method in methods:
            method_counts[method] = method_counts.get(method, 0) + 1

        duplicates = [m for m, count in method_counts.items() if count > 1]
        if duplicates:
            print(f"{RED}[FAIL]{RESET} Duplicate methods found: {duplicates}")
            return False

        print(f"{GREEN}[PASS]{RESET} Strategy loads successfully")
        return True

    except Exception as e:
        print(f"{RED}[FAIL]{RESET} Strategy failed to load: {e}")
        return False


def test_gitignore_security():
    """Test that .gitignore properly protects sensitive files."""
    print("\n[TEST] Checking .gitignore security...")

    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists():
        print(f"{RED}[FAIL]{RESET} .gitignore file not found")
        return False

    with open(gitignore_path, "r") as f:
        gitignore_content = f.read()

    required_patterns = [
        ".env",
        "config_live_real.json",
        "config_*live*.json",
    ]

    missing = []
    for pattern in required_patterns:
        if pattern not in gitignore_content:
            missing.append(pattern)

    if missing:
        print(f"{RED}[FAIL]{RESET} Missing .gitignore patterns: {missing}")
        return False

    print(f"{GREEN}[PASS]{RESET} .gitignore properly configured")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CONFIGURATION VALIDATION TESTS")
    print("=" * 60)

    tests = [
        ("Environment Variables", test_env_variables),
        ("Hardcoded Secrets", test_no_hardcoded_secrets),
        ("Config Consistency", test_config_consistency),
        ("Strategy Loading", test_strategy_loads),
        (".gitignore Security", test_gitignore_security),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} {test_name} crashed: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"\nTests Passed: {passed}/{total}")

    if all(results):
        print(f"\n{GREEN}[OK] ALL TESTS PASSED - SYSTEM READY{RESET}\n")
        exit(0)
    else:
        print(
            f"\n{RED}[FAIL] SOME TESTS FAILED - FIX ISSUES BEFORE PROCEEDING{RESET}\n"
        )
        exit(1)
