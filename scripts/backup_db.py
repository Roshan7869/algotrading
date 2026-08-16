#!/usr/bin/env python3
"""
backup_db.py — Daily auto-backup of Freqtrade trade database.

Runs via cron at 23:00 daily. Copies tradesv3.sqlite to dated backup.

Usage:
  python3 scripts/backup_db.py
  python3 scripts/backup_db.py --path /custom/path/tradesv3.sqlite
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path(__file__).resolve().parent.parent / "user_data" / "backups"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "user_data" / "tradesv3.sqlite"


def main():
    parser = argparse.ArgumentParser(description="Daily DB backup")
    parser.add_argument("--path", default=str(DEFAULT_DB), help="Path to tradesv3.sqlite")
    args = parser.parse_args()

    src = Path(args.path)
    if not src.exists():
        alt = src.parent / "tradesv3.dryrun.sqlite"
        if alt.exists():
            src = alt
        else:
            print(f"[backup] No database found at {src} or {alt}")
            return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    dst = BACKUP_DIR / f"tradesv3_{date_str}.sqlite"

    shutil.copy2(src, dst)
    print(f"[backup] Copied {src} → {dst} ({dst.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
