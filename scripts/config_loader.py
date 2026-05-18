"""
Configuration loader with environment variable support.
Loads config files and replaces ${VAR_NAME} with environment variables.
"""

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def load_config_with_env(config_path: str) -> dict:
    """
    Load JSON config and replace ${VAR_NAME} with environment variables.

    Args:
        config_path: Path to JSON config file

    Returns:
        dict: Config with environment variables substituted
    """
    with open(config_path, "r") as f:
        config_str = f.read()

    # Replace ${VAR_NAME} with environment variable values
    def replace_env_var(match):
        var_name = match.group(1)
        value = os.getenv(var_name)
        if value is None:
            raise ValueError(f"Environment variable {var_name} not found in .env file")
        return value

    config_str = re.sub(r"\$\{([A-Z_]+)\}", replace_env_var, config_str)

    return json.loads(config_str)


def save_config_template(config_path: str, output_path: str):
    """
    Convert config with hardcoded values to template with ${VAR_NAME}.

    Args:
        config_path: Path to config with hardcoded values
        output_path: Path to save template
    """
    with open(config_path, "r") as f:
        config = json.load(f)

    # Replace sensitive values with environment variable references
    if "telegram" in config:
        if config["telegram"].get("token"):
            config["telegram"]["token"] = "${TELEGRAM_TOKEN}"
        if config["telegram"].get("chat_id"):
            config["telegram"]["chat_id"] = "${TELEGRAM_CHAT_ID}"

    if "exchange" in config:
        if config["exchange"].get("key"):
            config["exchange"]["key"] = "${BINANCE_API_KEY}"
        if config["exchange"].get("secret"):
            config["exchange"]["secret"] = "${BINANCE_API_SECRET}"

    with open(output_path, "w") as f:
        json.dump(config, f, indent=4)

    print(f"✅ Template saved to {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        try:
            config = load_config_with_env(config_path)
            print(f"✅ Config loaded successfully from {config_path}")
            print(f"   Strategy: {config.get('strategy', 'Not specified')}")
            print(f"   Leverage: {config.get('leverage', 'Not specified')}")
            print(
                f"   Telegram enabled: {config.get('telegram', {}).get('enabled', False)}"
            )
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            sys.exit(1)
    else:
        print("Usage: python config_loader.py <config_path>")
        print("Example: python config_loader.py user_data/config_live_trading_10x.json")
