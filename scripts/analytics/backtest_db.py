#!/usr/bin/env python3
"""
backtest_db.py — Extract Freqtrade backtest ZIP files into queryable SQLite database.

Usage:
  python3 scripts/analytics/backtest_db.py --rebuild   # Full rebuild from all ZIPs
  python3 scripts/analytics/backtest_db.py --stats     # Show DB stats
"""

import argparse
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

BACKTEST_DIR = Path(__file__).resolve().parent.parent.parent / "user_data" / "backtest_results"
ANALYTICS_DIR = Path(__file__).resolve().parent.parent.parent / "user_data" / "analytics"
DB_PATH = ANALYTICS_DIR / "backtests.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE,
    strategy TEXT,
    timerange_start TEXT,
    timerange_end TEXT,
    profit_factor REAL,
    win_rate REAL,
    total_trades INTEGER,
    max_drawdown REAL,
    avg_trade_duration REAL,
    sharpe REAL,
    sortino REAL,
    total_profit_pct REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id INTEGER REFERENCES backtests(id),
    pair TEXT,
    open_date TEXT,
    close_date TEXT,
    profit_pct REAL,
    exit_reason TEXT,
    duration_minutes INTEGER,
    stake_amount REAL
);

CREATE INDEX IF NOT EXISTS idx_backtests_strategy ON backtests(strategy);
CREATE INDEX IF NOT EXISTS idx_backtests_timerange ON backtests(timerange_start, timerange_end);
CREATE INDEX IF NOT EXISTS idx_trades_backtest ON trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair);
"""


def get_conn():
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def extract_zip_metrics(zip_path: Path) -> dict | None:
    """Extract strategy metrics from a Freqtrade backtest ZIP."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if "strategy" not in zf.namelist():
                return None
            data = json.loads(zf.read("strategy"))
    except (json.JSONDecodeError, KeyError, zipfile.BadZipFile):
        return None

    strat_name = data.get("strategy_name", "unknown")
    total_trades = data.get("total_trades", 0)
    profit_factor = data.get("profit_factor", 0.0)
    win_rate = data.get("win_rate", 0.0)
    max_dd = data.get("max_drawdown", 0.0)
    avg_dur = data.get("avg_trade_duration", 0.0)
    sharpe = data.get("sharpe", 0.0)
    sortino = data.get("sortino", 0.0)
    total_profit = data.get("profit_total", 0.0)

    timerange = data.get("timerange", "")
    tr_parts = timerange.split("-") if timerange else ["", ""]
    tr_start = tr_parts[0] if len(tr_parts) > 0 else ""
    tr_end = tr_parts[1] if len(tr_parts) > 1 else ""

    return {
        "filename": zip_path.name,
        "strategy": strat_name,
        "timerange_start": tr_start,
        "timerange_end": tr_end,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "max_drawdown": max_dd,
        "avg_trade_duration": avg_dur,
        "sharpe": sharpe,
        "sortino": sortino,
        "total_profit_pct": total_profit,
    }


def extract_trades(zip_path: Path, backtest_id: int, conn: sqlite3.Connection) -> int:
    """Extract individual trades from a ZIP."""
    count = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if "trades" not in zf.namelist():
                return 0
            trades = json.loads(zf.read("trades"))
    except Exception:
        return 0

    for t in trades:
        try:
            conn.execute(
                """INSERT INTO trades
                   (backtest_id, pair, open_date, close_date, profit_pct, exit_reason, duration_minutes, stake_amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    backtest_id,
                    t.get("pair", ""),
                    t.get("open_date", ""),
                    t.get("close_date", ""),
                    t.get("profit_ratio", 0) * 100,
                    t.get("exit_reason", ""),
                    t.get("trade_duration_minutes", 0),
                    t.get("stake_amount", 0),
                ),
            )
            count += 1
        except Exception:
            pass
    return count


def cmd_rebuild():
    conn = get_conn()
    conn.execute("DELETE FROM trades")
    conn.execute("DELETE FROM backtests")
    conn.commit()

    zips = sorted(BACKTEST_DIR.glob("backtest-result-*.zip"))
    print(f"[backtest_db] Found {len(zips)} ZIP files")

    total_backtests = 0
    total_trades = 0

    for zp in zips:
        metrics = extract_zip_metrics(zp)
        if not metrics:
            continue
        try:
            cur = conn.execute(
                """INSERT INTO backtests
                   (filename, strategy, timerange_start, timerange_end, profit_factor,
                    win_rate, total_trades, max_drawdown, avg_trade_duration, sharpe, sortino, total_profit_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(metrics.values()),
            )
            backtest_id = cur.lastrowid
            n_trades = extract_trades(zp, backtest_id, conn)
            total_backtests += 1
            total_trades += n_trades
            print(f"  {zp.name}: {metrics['strategy']:40s} PF={metrics['profit_factor']:.2f} WR={metrics['win_rate']:.1%} trades={n_trades}")
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()
    print(f"\n[backtest_db] Rebuild complete: {total_backtests} backtests, {total_trades} trades")
    print(f"[backtest_db] Database: {DB_PATH}")


def cmd_stats():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM backtests").fetchone()[0]
    trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    strategies = conn.execute("SELECT DISTINCT strategy FROM backtests ORDER BY strategy").fetchall()
    print(f"Backtests: {count}")
    print(f"Trades: {trade_count}")
    print(f"Strategies: {[r[0] for r in strategies]}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Extract backtest ZIPs into SQLite")
    parser.add_argument("--rebuild", action="store_true", help="Full rebuild from all ZIPs")
    parser.add_argument("--stats", action="store_true", help="Show DB stats")
    args = parser.parse_args()

    if args.rebuild:
        cmd_rebuild()
    elif args.stats:
        cmd_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
