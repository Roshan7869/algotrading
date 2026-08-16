#!/usr/bin/env python3
"""
index_regen.py — Regenerate backtest database index after each new backtest run.

Usage:
  python3 scripts/analytics/index_regen.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_db import cmd_rebuild

if __name__ == "__main__":
    print("[index_regen] Regenerating backtest index from all ZIPs...")
    cmd_rebuild()
    print("[index_regen] Done")
