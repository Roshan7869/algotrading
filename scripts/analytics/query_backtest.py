#!/usr/bin/env python3
"""
query_backtest.py — Query the backtest SQLite database.

Usage:
  python3 scripts/analytics/query_backtest.py --list-strategies
  python3 scripts/analytics/query_backtest.py --strategy AroonMomentum --month 2025-05 --metric wr
  python3 scripts/analytics/query_backtest.py --strategy AroonMomentum --compare
  python3 scripts/analytics/query_backtest.py --top 5
"""

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data" / "analytics" / "backtests.db"


def get_conn():
    if not DB_PATH.exists():
        print(f"[query] No database found at {DB_PATH}")
        print("[query] Run `python3 scripts/analytics/backtest_db.py --rebuild` first")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list_strategies():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT strategy FROM backtests ORDER BY strategy").fetchall()
    print("Strategies:")
    for r in rows:
        count = conn.execute("SELECT COUNT(*) FROM backtests WHERE strategy=?", (r[0],)).fetchone()[0]
        print(f"  {r[0]:40s} ({count} backtests)")
    conn.close()


def cmd_strategy_month(args):
    conn = get_conn()
    like_pat = f"%{args.month}%" if args.month else "%"
    rows = conn.execute(
        """SELECT filename, timerange_start, timerange_end, profit_factor, win_rate,
                  total_trades, max_drawdown, total_profit_pct
           FROM backtests
           WHERE strategy LIKE ? AND (timerange_start LIKE ? OR timerange_end LIKE ?)
           ORDER BY timerange_start DESC""",
        (f"%{args.strategy}%", like_pat, like_pat),
    ).fetchall()

    if not rows:
        print(f"No results for strategy='{args.strategy}' month='{args.month or 'all'}'")
        return

    print(f"{'Backtest':50s} {'PF':>6s} {'WR':>5s} {'Trades':>7s} {'DD':>6s} {'Profit':>8s}")
    print("-" * 90)
    for r in rows:
        print(
            f"{r['filename']:50s} {r['profit_factor']:>6.2f} {r['win_rate']:>5.1%} "
            f"{r['total_trades']:>7d} {r['max_drawdown']:>6.1%} {r['total_profit_pct']:>8.2f}"
        )
    conn.close()


def cmd_compare(args):
    conn = get_conn()
    rows = conn.execute(
        """SELECT strategy,
                  AVG(profit_factor) as avg_pf, AVG(win_rate) as avg_wr,
                  SUM(total_trades) as total_t, AVG(max_drawdown) as avg_dd
           FROM backtests
           GROUP BY strategy
           ORDER BY avg_pf DESC""",
    ).fetchall()

    print(f"{'Strategy':40s} {'Avg PF':>7s} {'Avg WR':>7s} {'Trades':>8s} {'Avg DD':>7s}")
    print("-" * 75)
    for r in rows:
        print(
            f"{r['strategy']:40s} {r['avg_pf']:>7.2f} {r['avg_wr']:>7.1%} "
            f"{r['total_t']:>8d} {r['avg_dd']:>7.1%}"
        )
    conn.close()


def cmd_top(n: int):
    conn = get_conn()
    rows = conn.execute(
        """SELECT filename, strategy, profit_factor, win_rate, total_profit_pct
           FROM backtests
           ORDER BY profit_factor DESC
           LIMIT ?""",
        (n,),
    ).fetchall()
    print(f"Top {n} backtests by profit factor:")
    print(f"{'Backtest':50s} {'Strategy':30s} {'PF':>6s} {'WR':>5s} {'Profit':>8s}")
    print("-" * 105)
    for r in rows:
        print(
            f"{r['filename']:50s} {r['strategy']:30s} {r['profit_factor']:>6.2f} "
            f"{r['win_rate']:>5.1%} {r['total_profit_pct']:>8.2f}"
        )
    conn.close()


def main():
    import sys
    parser = argparse.ArgumentParser(description="Query backtest database")
    parser.add_argument("--list-strategies", action="store_true", help="List all strategies")
    parser.add_argument("--strategy", help="Strategy name filter")
    parser.add_argument("--month", help="Month filter (e.g., 2025-05)")
    parser.add_argument("--metric", choices=["pf", "wr", "dd", "profit"], help="Metric to display")
    parser.add_argument("--compare", action="store_true", help="Compare all strategies")
    parser.add_argument("--top", type=int, help="Show top N backtests by PF")
    args = parser.parse_args()

    if args.list_strategies:
        cmd_list_strategies()
    elif args.compare:
        cmd_compare(args)
    elif args.top:
        cmd_top(args.top)
    elif args.strategy:
        cmd_strategy_month(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
