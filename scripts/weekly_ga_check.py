#!/usr/bin/env python3
"""
weekly_ga_check.py — Weekly GA re-optimization trigger.

Checks the latest strategy performance. If win rate < 50% or PF < 1.0,
triggers GeneTrader re-run on latest 90 days of data.

Usage:
  python3 scripts/weekly_ga_check.py --dry-run   # Check without triggering
  python3 scripts/weekly_ga_check.py --run       # Trigger re-optimization
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FREQTRADE_DB = BASE_DIR / "user_data" / "tradesv3.sqlite"
GENE_TRADER_DIR = Path("/tmp/genetrader")


def get_recent_metrics(days: int = 7) -> dict:
    """Query Freqtrade DB for recent win rate and profit factor."""
    try:
        import sqlite3
        if not FREQTRADE_DB.exists():
            alt = FREQTRADE_DB.parent / "tradesv3.dryrun.sqlite"
            if alt.exists():
                db_path = alt
            else:
                return {"error": "No trade database found"}
        else:
            db_path = FREQTRADE_DB

        conn = sqlite3.connect(str(db_path))
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT close_profit FROM trades WHERE close_date > ? AND is_open=0",
            (cutoff,),
        ).fetchall()
        conn.close()

        if not rows:
            return {"error": f"No closed trades in last {days} days"}

        profits = [r[0] for r in rows if r[0] is not None]
        if not profits:
            return {"error": "No profit data available"}

        wins = sum(1 for p in profits if p > 0)
        total = len(profits)
        wr = wins / total
        avg_win = sum(p for p in profits if p > 0) / wins if wins > 0 else 0
        avg_loss = sum(p for p in profits if p < 0) / (total - wins) if total > wins else 0
        pf = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        return {"win_rate": wr, "profit_factor": pf, "total_trades": total}
    except Exception as e:
        return {"error": str(e)}


def trigger_ga_rerun():
    """Trigger GeneTrader re-run on latest 90 days."""
    if not GENE_TRADER_DIR.exists():
        return {"status": "error", "message": "GeneTrader not cloned. Run: git clone https://github.com/imsatoshi/GeneTrader.git /tmp/genetrader"}

    end = datetime.now()
    start = end - timedelta(days=90)
    timerange = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"

    cmd = [
        sys.executable, str(GENE_TRADER_DIR / "main.py"),
        "--config", str(BASE_DIR / "ga.json"),
        "--download",
        "--timerange", timerange,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        return {"status": "ok", "output": result.stdout[-500:]}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "GA timed out after 1 hour"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Weekly GA re-optimization check")
    parser.add_argument("--dry-run", action="store_true", help="Check without triggering")
    parser.add_argument("--run", action="store_true", help="Trigger re-optimization if needed")
    parser.add_argument("--days", type=int, default=7, help="Lookback days for metrics")
    args = parser.parse_args()

    metrics = get_recent_metrics(args.days)

    if "error" in metrics:
        print(f"[weekly_ga] SKIP: {metrics['error']}")
        return

    print(f"[weekly_ga] Last {args.days}d: WR={metrics['win_rate']:.1%} PF={metrics['profit_factor']:.2f} trades={metrics['total_trades']}")

    needs_opt = metrics["win_rate"] < 0.50 or metrics["profit_factor"] < 1.0

    if needs_opt:
        print(f"[weekly_ga] Performance below threshold — re-optimization needed")
        if args.run:
            result = trigger_ga_rerun()
            print(f"[weekly_ga] Trigger: {result.get('status', 'unknown')}")
        else:
            print(f"[weekly_ga] Use --run to trigger GeneTrader re-optimization")
    else:
        print(f"[weekly_ga] Performance OK — no action needed")


if __name__ == "__main__":
    main()
