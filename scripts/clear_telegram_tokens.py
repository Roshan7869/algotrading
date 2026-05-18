"""
Remove hardcoded Telegram tokens from all config files.
This script clears tokens and chat IDs, replacing them with empty strings.
"""

import json
from pathlib import Path


def clear_telegram_credentials(config_path):
    """Clear Telegram credentials from a config file."""
    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        modified = False

        if "telegram" in config:
            if config["telegram"].get("token") and config["telegram"]["token"] != "":
                if len(config["telegram"]["token"]) > 10:  # Has actual token
                    config["telegram"]["token"] = ""
                    modified = True

            if (
                config["telegram"].get("chat_id")
                and config["telegram"]["chat_id"] != ""
            ):
                if str(config["telegram"]["chat_id"]).isdigit():  # Has actual chat ID
                    config["telegram"]["chat_id"] = ""
                    modified = True

        if modified:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=4)
            return True

        return False

    except Exception as e:
        print(f"❌ Error processing {config_path.name}: {e}")
        return None


if __name__ == "__main__":
    config_dir = Path("user_data")

    print("\n" + "=" * 60)
    print("Clearing Hardcoded Telegram Credentials")
    print("=" * 60 + "\n")

    cleared = []
    skipped = []
    errors = []

    for config_file in sorted(config_dir.glob("config*.json")):
        result = clear_telegram_credentials(config_file)

        if result is True:
            cleared.append(config_file.name)
            print(f"[OK] Cleared credentials from {config_file.name}")
        elif result is False:
            skipped.append(config_file.name)
            print(f"[INFO] No credentials to clear in {config_file.name}")
        else:
            errors.append(config_file.name)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"[OK] Cleared: {len(cleared)}")
    print(f"[INFO] Skipped: {len(skipped)}")
    print(f"[ERROR] Errors: {len(errors)}")

    if cleared:
        print(f"\n[SECURITY] Credentials cleared from:")
        for name in cleared:
            print(f"   - {name}")

    print("\n[WARN] IMPORTANT: Update your .env file with new credentials!")
    print("       Then configs can reference them with ${TELEGRAM_TOKEN}\n")
