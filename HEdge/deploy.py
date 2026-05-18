#!/usr/bin/env python3
"""
Deploy HEdge strategies to user_data/strategies/ for backtesting.
Copies all 9 strategies (7 individual + 1 meta + 1 champion) to the
freqtrade user_data/strategies/ directory.

Usage:
  python3 deploy.py                      # Deploy all strategies
  python3 deploy.py --dry-run            # Show what would be deployed
  python3 deploy.py --list               # List available strategies
"""

import sys
import shutil
from pathlib import Path

HEDGE_DIR = Path(__file__).parent
STRATEGIES_DIR = HEDGE_DIR / "strategies"
DEPLOY_DIR = Path(HEDGE_DIR.parent) / "user_data" / "strategies"

STRATEGIES = [
    "hedge_01_fixed_fractional.py",
    "hedge_02_risk_to_zero.py",
    "hedge_03_half_kelly.py",
    "hedge_04_consec_loss_protect.py",
    "hedge_05_scale_out.py",
    "hedge_06_anti_martingale.py",
    "hedge_07_win_rate_adaptive.py",
    "hedge_meta_7in1.py",
    "hedge_champion_p3f.py",
]


def list_strategies():
    print("=== Available HEdge Strategies ===")
    for s in STRATEGIES:
        path = STRATEGIES_DIR / s
        exists = "✓" if path.exists() else "✗"
        print(f"  {exists} {s}")
    print(f"\nDeploy target: {DEPLOY_DIR}")


def deploy(dry_run=False):
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for s in STRATEGIES:
        src = STRATEGIES_DIR / s
        if not src.exists():
            print(f"  SKIP {s} (not found)")
            continue
        dst = DEPLOY_DIR / s
        if dry_run:
            print(f"  WOULD COPY: {src} → {dst}")
        else:
            shutil.copy2(src, dst)
            print(f"  COPIED: {s}")
        count += 1
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Deployed {count}/{len(STRATEGIES)} strategies to {DEPLOY_DIR}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_strategies()
    elif "--dry-run" in sys.argv:
        deploy(dry_run=True)
    else:
        deploy()
