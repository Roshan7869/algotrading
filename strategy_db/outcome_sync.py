#!/usr/bin/env python3
"""
Outcome Sync — Trade Outcome → ChromaDB Metadata Feedback Loop

Reads outcome_history.json chunk_stats, computes per-setup win rates,
and updates ChromaDB chunk metadata with outcome_win_rate fields.

Called from:
  - VectorStrategy._record_outcome() after each trade close
  - VectorStrategy.bot_loop_start() after backtest completes
  - gcode_bridge.py CLI: python3 gcode_bridge.py outcome-sync
"""

import json
import sys
import os
from pathlib import Path

OUTCOME_PATH = Path(__file__).parent / "outcome_history.json"


def load_chunk_stats() -> dict:
    """Load chunk_stats from outcome_history.json."""
    if not OUTCOME_PATH.exists():
        return {}
    with open(OUTCOME_PATH, "r") as f:
        data = json.load(f)
    return data.get("chunk_stats", {})


def compute_setup_win_rates(chunk_stats: dict | None = None) -> dict[str, dict]:
    """
    Compute {setup_name: {win_rate, total_trades, wins, losses, avg_pnl}}.

    Returns dict keyed by setup_name.
    """
    if chunk_stats is None:
        chunk_stats = load_chunk_stats()

    result = {}
    for name, stats in chunk_stats.items():
        total = stats.get("total_trades", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total_pnl = stats.get("total_pnl", 0)
        win_rate = round(wins / total, 4) if total > 0 else 0.0
        avg_pnl = round(total_pnl / total, 4) if total > 0 else 0.0
        result[name] = {
            "win_rate": win_rate,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "avg_pnl": avg_pnl,
        }
    return result


def sync_to_chromadb(chunk_stats: dict | None = None, verbose: bool = True) -> dict:
    """
    Update ChromaDB chunk metadata with outcome_win_rate for all chunks
    whose setup_name matches a key in chunk_stats.

    Returns summary: {synced: int, skipped: int, errors: int, win_rates: dict}
    """
    if chunk_stats is None:
        chunk_stats = load_chunk_stats()

    win_rates = compute_setup_win_rates(chunk_stats)

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from search import _get_collection
        collection = _get_collection()
    except Exception as e:
        if verbose:
            print(f"[outcome_sync] ChromaDB unavailable: {e}")
        return {"synced": 0, "skipped": 0, "errors": 1, "win_rates": win_rates}

    all_meta = collection.get(include=["metadatas", "documents"])
    ids = all_meta["ids"]
    metadatas = all_meta["metadatas"]

    synced = 0
    skipped = 0
    errors = 0

    for i, meta in enumerate(metadatas):
        setup_name = meta.get("setup_name", "")
        if setup_name not in win_rates:
            skipped += 1
            continue

        wr = win_rates[setup_name]
        new_meta = {
            **meta,
            "outcome_win_rate": wr["win_rate"],
            "outcome_total_trades": wr["total_trades"],
            "outcome_wins": wr["wins"],
            "outcome_losses": wr["losses"],
            "outcome_avg_pnl": wr["avg_pnl"],
        }
        try:
            collection.update(
                ids=[ids[i]],
                metadatas=[new_meta],
            )
            synced += 1
        except Exception as e:
            errors += 1
            if verbose:
                print(f"[outcome_sync] Failed to update '{setup_name}': {e}")

    if verbose:
        print(f"[outcome_sync] synced={synced}, skipped={skipped}, errors={errors}")
        for name, wr in sorted(win_rates.items(), key=lambda x: -x[1]["win_rate"]):
            bar = "█" * int(wr["win_rate"] * 20)
            print(f"  {name:40s} {wr['win_rate']:.0%} ({wr['total_trades']:3d} trades) {bar}")

    return {"synced": synced, "skipped": skipped, "errors": errors, "win_rates": win_rates}


if __name__ == "__main__":
    sync_to_chromadb(verbose=True)
