"""Phase 2.1 — exit-reason and realised-stop diagnostics for one backtest label.

Shows what the stop machinery actually did: how many trades left through the stop vs the
trailing stop vs ROI, and the realised adverse excursion of stop exits in *price* terms
(the ratio freqtrade stores is equity terms and divided by leverage).

Usage:  .venv/Scripts/python.exe reports/phase2/2.1/analyze_trades.py <label>
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main() -> int:
    label = sys.argv[1]
    z = sorted((OUT / "raw" / label).glob("*.zip"), key=lambda p: p.stat().st_mtime)[-1]
    with zipfile.ZipFile(z) as zf:
        names = [n for n in zf.namelist()
                 if n.endswith(".json") and "_config" not in n and "_market_change" not in n]
        payload = json.loads(zf.read(names[0]))
    strat, trades = next(iter(payload["strategy"].items()))
    rows = trades["trades"]
    print(f"{label}: {len(rows)} trades, strategy={strat}")
    if not rows:
        return 0

    reasons = collections.Counter(t["exit_reason"] for t in rows)
    print(f"exit reasons: {dict(reasons)}")

    init_px = [(t["initial_stop_loss_abs"] / t["open_rate"] - 1) * (1 if t["is_short"] else 1)
               for t in rows if t.get("initial_stop_loss_abs")]
    print(f"initial stop distance (price, %): mean={statistics.mean(init_px) * 100:.3f} "
          f"min={min(init_px) * 100:.3f} max={max(init_px) * 100:.3f}  "
          f"(stored ratio={rows[0]['initial_stop_loss_ratio']}, leverage={rows[0]['leverage']})")

    for reason, group in sorted(collections.Counter(t["exit_reason"] for t in rows).items()):
        g = [t for t in rows if t["exit_reason"] == reason]
        px = [((t["close_rate"] / t["open_rate"] - 1) * (-1 if t["is_short"] else 1)) for t in g]
        stake = [t["profit_ratio"] for t in g]
        print(f"  {reason:22s} n={len(g):3d} "
              f"price move mean={statistics.mean(px) * 100:+.3f}% "
              f"(min {min(px) * 100:+.3f} max {max(px) * 100:+.3f}) | "
              f"stake mean={statistics.mean(stake) * 100:+.3f}%")
    dur = [t["trade_duration"] for t in rows]
    print(f"holding minutes: mean={statistics.mean(dur):.0f} median={statistics.median(dur):.0f} max={max(dur)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
