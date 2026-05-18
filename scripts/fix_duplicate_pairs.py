"""
Fix duplicate pairs in config files.
Scans all config files and removes duplicate entries from pair_whitelist.
"""

import json
from pathlib import Path
from collections import Counter


def fix_duplicate_pairs(config_path):
    """Remove duplicate pairs from a config file."""
    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        if "exchange" not in config or "pair_whitelist" not in config["exchange"]:
            return None, "No pair_whitelist found"

        original_pairs = config["exchange"]["pair_whitelist"]
        original_count = len(original_pairs)

        # Find duplicates
        pair_counts = Counter(original_pairs)
        duplicates = [pair for pair, count in pair_counts.items() if count > 1]

        if not duplicates:
            return False, "No duplicates"

        # Remove duplicates while preserving order
        seen = set()
        unique_pairs = []
        for pair in original_pairs:
            if pair not in seen:
                seen.add(pair)
                unique_pairs.append(pair)

        config["exchange"]["pair_whitelist"] = unique_pairs

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        removed = original_count - len(unique_pairs)
        return True, f"Removed {removed} duplicate(s): {duplicates}"

    except Exception as e:
        return None, f"Error: {e}"


if __name__ == "__main__":
    config_dir = Path("user_data")

    print("\n" + "=" * 60)
    print("Fixing Duplicate Pairs in Config Files")
    print("=" * 60 + "\n")

    fixed = []
    clean = []
    errors = []

    for config_file in sorted(config_dir.glob("config*.json")):
        result, message = fix_duplicate_pairs(config_file)

        if result is True:
            fixed.append((config_file.name, message))
            print(f"[FIXED] {config_file.name}: {message}")
        elif result is False:
            clean.append(config_file.name)
            print(f"[OK] {config_file.name}: {message}")
        else:
            errors.append((config_file.name, message))
            print(f"[ERROR] {config_file.name}: {message}")

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"[FIXED] Fixed: {len(fixed)}")
    print(f"[OK] Clean: {len(clean)}")
    print(f"[ERROR] Errors: {len(errors)}")

    if fixed:
        print(f"\n[INFO] Fixed files:")
        for name, msg in fixed:
            print(f"   - {name}: {msg}")

    print()
