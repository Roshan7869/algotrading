import os
import hashlib
from pathlib import Path
from typing import Dict, List, Set


def get_file_hash(filepath: Path) -> str:
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()


def scan_for_duplicates(directory: Path) -> Dict[str, List[str]]:
    """Scan directory for duplicate files based on content hash."""
    hashes: Dict[str, List[str]] = {}

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".pyc") or file.startswith("__"):
                continue

            filepath = Path(root) / file
            file_hash = get_file_hash(filepath)

            if file_hash not in hashes:
                hashes[file_hash] = []
            hashes[file_hash].append(str(filepath))

    return {k: v for k, v in hashes.items() if len(v) > 1}


def audit_strategies(project_root: Path):
    """Audit the strategies directory."""
    strategies_dir = project_root / "user_data" / "strategies"
    if not strategies_dir.exists():
        print(f"Directory not found: {strategies_dir}")
        return

    print(f"Scanning {strategies_dir} for duplicates...")
    duplicates = scan_for_duplicates(strategies_dir)

    if not duplicates:
        print("No exact duplicates found.")
    else:
        print(f"Found {len(duplicates)} sets of duplicate files:")
        for file_hash, paths in duplicates.items():
            print(f"  Hash {file_hash[:8]}:")
            for path in paths:
                print(f"    - {path}")


def main():
    project_root = Path(__file__).resolve().parent.parent
    print(f"Auditing Project at: {project_root}")

    audit_strategies(project_root)

    # Check for config files in user_data/strategies
    strategies_dir = project_root / "user_data" / "strategies"
    config_files = list(strategies_dir.glob("*config*.json"))
    if config_files:
        print(
            "\n[WARNING] Config files found in strategies folder (should be in user_data):"
        )
        for f in config_files:
            print(f"  - {f.name}")
    else:
        print("\nNo config files found in strategies folder (Good).")


if __name__ == "__main__":
    main()
