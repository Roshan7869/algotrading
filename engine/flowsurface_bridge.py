"""Flowsurface Bridge — Export Algotrading data to NDJSON format for Flowsurface LocalConnector."""

import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

DATA_ROOT = Path(__file__).parent.parent
BACKTEST_DIR = DATA_ROOT / "user_data" / "backtest_results"
OHLCV_DIR = DATA_ROOT / "user_data" / "data"
TRADES_DB = DATA_ROOT / "user_data" / "tradesv3.sqlite"
OUTCOME_FILE = DATA_ROOT / "strategy_db" / "outcome_history.json"

DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "flowsurface" / "market_data" / "algotrading"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_ohlcv(
    pair: str,
    timeframe: str = "1h",
    output_dir: Optional[Path] = None,
    max_rows: Optional[int] = None,
) -> Path:
    """Export OHLCV feather data to NDJSON kline format."""
    output_dir = _ensure_dir(output_dir or DEFAULT_OUTPUT_DIR)

    normalized = pair.replace("/", "_")
    futures_path = OHLCV_DIR / "binance" / "futures" / f"{normalized}_USDT-{timeframe}-futures.feather"
    spot_path = OHLCV_DIR / "binance" / f"{normalized}-{timeframe}.feather"

    feather_path = None
    if futures_path.exists():
        feather_path = futures_path
    elif spot_path.exists():
        feather_path = spot_path
    else:
        available = list(OHLCV_DIR / "binance").glob(f"{normalized}*")
        if not available:
            raise FileNotFoundError(f"No OHLCV data found for {pair}")

    df = pd.read_feather(feather_path)
    if max_rows:
        df = df.tail(max_rows)

    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    ticker = normalized
    out_path = output_dir / f"{ticker}_{timeframe}_kline.jsonl"

    count = 0
    with open(out_path, "w") as f:
        for _, row in df.iterrows():
            ts = row["date"]
            if isinstance(ts, datetime):
                ts_ms = int(ts.timestamp() * 1000)
            elif isinstance(ts, pd.Timestamp):
                ts_ms = int(ts.timestamp() * 1000)
            else:
                continue

            f.write(json.dumps({
                "ticker": ticker,
                "timeframe": timeframe,
                "timestamp_ms": ts_ms,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }) + "\n")
            count += 1

    log.info(f"Exported {count} klines to {out_path}")
    return out_path


def export_backtest_trades(
    pair: str,
    output_dir: Optional[Path] = None,
    max_trades: Optional[int] = None,
) -> Path:
    """Export backtest trade data to NDJSON trade format."""
    output_dir = _ensure_dir(output_dir or DEFAULT_OUTPUT_DIR)

    zip_files = sorted(BACKTEST_DIR.glob("backtest-result-*.zip"), reverse=True)
    if not zip_files:
        raise FileNotFoundError("No backtest result ZIPs found")

    latest_zip = zip_files[0]
    import zipfile

    with zipfile.ZipFile(latest_zip, "r") as zf:
        json_files = [n for n in zf.namelist() if n.endswith(".json") and "config" not in n.lower()]
        if not json_files:
            raise FileNotFoundError(f"No backtest JSON found in {latest_zip}")

        raw = json.loads(zf.read(json_files[0]))
        strategies = raw.get("strategy", {})
        if not strategies:
            raise ValueError("No strategies in backtest result")

        strategy_name = next(iter(strategies))
        trades = strategies[strategy_name].get("trades", [])
        if not trades:
            raise ValueError(f"No trades for {strategy_name}")

    ticker = pair.replace("/", "_")
    out_path = output_dir / f"{ticker}_trades.jsonl"

    if max_trades:
        trades = trades[-max_trades:]

    count = 0
    with open(out_path, "w") as f:
        for trade in trades:
            open_ts = trade.get("open_timestamp", 0)
            if isinstance(open_ts, str):
                try:
                    open_ts = int(pd.Timestamp(open_ts).timestamp() * 1000)
                except Exception:
                    open_ts = 0

            is_short = trade.get("is_short", False)
            amount = float(trade.get("amount", 0))
            price = float(trade.get("open_rate", 0))

            f.write(json.dumps({
                "ticker": ticker,
                "timestamp_ms": open_ts,
                "price": price,
                "qty": amount,
                "is_sell": is_short,
                "profit_ratio": float(trade.get("profit_ratio", 0)),
                "exit_reason": trade.get("exit_reason", ""),
            }) + "\n")
            count += 1

    log.info(f"Exported {count} trades to {out_path}")
    return out_path


def export_live_trades(
    output_dir: Optional[Path] = None,
    limit: int = 200,
) -> Optional[Path]:
    """Export trades from sqlite database."""
    output_dir = _ensure_dir(output_dir or DEFAULT_OUTPUT_DIR)

    if not TRADES_DB.exists():
        log.warning(f"Trades DB not found: {TRADES_DB}")
        return None

    conn = sqlite3.connect(str(TRADES_DB))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM trades ORDER BY open_date DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()

    if not rows:
        log.info("No trades in database")
        return None

    pairs_seen = {}
    for row in rows:
        pair = row["pair"]
        if pair not in pairs_seen:
            pairs_seen[pair] = []
        pairs_seen[pair].append(row)

    out_paths = []
    for pair, trades in pairs_seen.items():
        ticker = pair.replace("/", "_")
        out_path = output_dir / f"{ticker}_trades.jsonl"

        with open(out_path, "w") as f:
            for trade in trades:
                open_ts = trade["open_date"]
                ts_ms = int(pd.Timestamp(open_ts).timestamp() * 1000)

                f.write(json.dumps({
                    "ticker": ticker,
                    "timestamp_ms": ts_ms,
                    "price": trade["open_rate"],
                    "qty": trade["amount"],
                    "is_sell": bool(trade.get("is_short")),
                    "profit_ratio": trade.get("close_profit"),
                    "exit_reason": trade.get("exit_reason", ""),
                }) + "\n")

        out_paths.append(out_path)

    log.info(f"Exported live trades: {out_paths}")
    return out_paths[0] if out_paths else None


def export_all(
    pairs: Optional[list] = None,
    timeframes: Optional[list] = None,
    output_dir: Optional[Path] = None,
    max_rows: int = 10000,
) -> dict:
    """Export all available data for given pairs."""
    output_dir = _ensure_dir(output_dir or DEFAULT_OUTPUT_DIR)
    if pairs is None:
        pairs = ["BTC/USDT", "ETH/USDT"]
    if timeframes is None:
        timeframes = ["1h"]

    results = {"kline": [], "trades": [], "errors": []}

    for pair in pairs:
        for tf in timeframes:
            try:
                path = export_ohlcv(pair, tf, output_dir=output_dir, max_rows=max_rows)
                results["kline"].append(str(path))
            except Exception as e:
                results["errors"].append(f"OHLCV {pair} {tf}: {e}")

        try:
            path = export_backtest_trades(pair, output_dir=output_dir)
            results["trades"].append(str(path))
        except Exception as e:
            results["errors"].append(f"Backtest {pair}: {e}")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = export_all()
    print(json.dumps(results, indent=2))
