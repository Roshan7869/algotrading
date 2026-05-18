"""QuantDinger 5-Tier Risk Classification Gate

Reads freqtrade trade history and classifies current risk into 5 tiers:
  Tier 0 (SAFE):    Kelly > 0.2, WR > 50%, DD < 10%   → Full size
  Tier 1 (CAUTION): Kelly 0.1-0.2, WR 45-50%, DD 10-20% → 75% size
  Tier 2 (RESTRICT): Kelly 0-0.1, WR 40-45%, DD 20-35% → 50% size
  Tier 3 (HALT):     Kelly < 0, WR < 40%, DD > 35%     → 0% size, halt new entries
  Tier 4 (LIQUIDATE): DD > 50% OR 3 consecutive SL    → Close all, manual restart

The gate writes to shared_config/circuit_breaker.json which EnsembleStrategy
and AroonMomentumEngine_Hybrid already read in bot_loop_start().
"""

import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


SHARED_DIR = Path(os.getenv("SHARED_CONFIG_DIR", "/home/roshan/Downloads/Algotrading/shared_config"))
TRADES_DB = Path(os.getenv("TRADES_DB", "/home/roshan/Downloads/Algotrading/user_data/tradesv3.sqlite"))


def _read_trades():
    """Read closed trades from freqtrade SQLite DB."""
    if not TRADES_DB.exists():
        return []
    conn = sqlite3.connect(str(TRADES_DB))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT is_short, close_profit, stake_amount, profit_ratio, id
        FROM trades
        WHERE close_date IS NOT NULL
        ORDER BY close_date DESC
        LIMIT 200
    """)
    trades = [dict(r) for r in c.fetchall()]
    conn.close()
    return trades


def compute_kelly(trades):
    """Kelly Criterion: f* = (bp - q) / b
    b = avg_win / avg_loss, p = win_rate, q = 1-p
    """
    if not trades:
        return None
    wins = [t for t in trades if t.get("close_profit", 0) > 0]
    losses = [t for t in trades if t.get("close_profit", 0) <= 0]
    if not wins or not losses:
        return None
    avg_win = sum(t["close_profit"] for t in wins) / len(wins)
    avg_loss = abs(sum(t["close_profit"] for t in losses) / len(losses))
    if avg_loss == 0:
        return None
    p = len(wins) / len(trades)
    b = avg_win / avg_loss
    q = 1 - p
    kelly = (b * p - q) / b if b != 0 else -1.0
    return round(kelly, 3)


def compute_metrics(trades):
    if not trades:
        return {"win_rate": None, "avg_profit": None, "max_dd": None, "kelly": None, "consecutive_sl": 0}
    wins = [t for t in trades if t.get("close_profit", 0) > 0]
    losses = [t for t in trades if t.get("close_profit", 0) <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    avg_profit = sum(t.get("close_profit", 0) for t in trades) / len(trades)
    # Approximate max DD from running equity
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for t in reversed(trades):
        equity += t.get("close_profit", 0)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak
        if dd > max_dd:
            max_dd = dd
    # Consecutive stop-losses
    consecutive_sl = 0
    for t in trades:
        if t.get("close_profit", 0) <= 0:
            consecutive_sl += 1
        else:
            break
    return {
        "win_rate": round(win_rate, 3),
        "avg_profit": round(avg_profit, 4),
        "max_dd": round(max_dd, 3),
        "kelly": compute_kelly(trades),
        "consecutive_sl": consecutive_sl,
    }


def classify_tier(metrics):
    """Return tier number (0-4) and human label."""
    kelly = metrics.get("kelly") or -1.0
    wr = metrics.get("win_rate") or 0.0
    dd = metrics.get("max_dd") or 0.0
    csl = metrics.get("consecutive_sl", 0)

    if dd > 0.50 or csl >= 3:
        return 4, "LIQUIDATE"
    if kelly < 0 or wr < 0.40 or dd > 0.35:
        return 3, "HALT"
    if kelly < 0.10 or wr < 0.45 or dd > 0.20:
        return 2, "RESTRICT"
    if kelly < 0.20 or wr < 0.50 or dd > 0.10:
        return 1, "CAUTION"
    return 0, "SAFE"


def update_circuit_breaker(tier, label, metrics):
    """Write circuit breaker state to shared config."""
    breaker = {
        "state": label,
        "tier": tier,
        "drawdown_pct": round(metrics["max_dd"] * 100, 1),
        "win_rate": metrics.get("win_rate"),
        "kelly": metrics.get("kelly"),
        "consecutive_sl": metrics.get("consecutive_sl"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "_written_by": "quantdinger_risk_gate",
    }
    path = SHARED_DIR / "circuit_breaker.json"
    path.write_text(json.dumps(breaker, indent=2))
    return breaker


def main():
    trades = _read_trades()
    metrics = compute_metrics(trades)
    tier, label = classify_tier(metrics)
    breaker = update_circuit_breaker(tier, label, metrics)
    print(json.dumps(breaker, indent=2))
    return tier


if __name__ == "__main__":
    exit(main())
