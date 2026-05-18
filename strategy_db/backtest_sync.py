"""
Phase 4.2: Backtest Sync — Write backtest results back to ChromaDB metadata.

Maps generated strategies back to source chunk IDs via the blueprint, then
updates each chunk's metadata with performance results.
"""
import json
import os
from pathlib import Path
from collections import defaultdict

import chromadb
from chromadb.config import Settings

BASE = Path(__file__).resolve().parent.parent
DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
BLUEPRINTS_PATH = os.path.join(os.path.dirname(__file__), "strategy_blueprints.json")
COLLECTION_NAME = "trading_strategies"


def load_blueprints() -> list:
    with open(BLUEPRINTS_PATH) as f:
        data = json.load(f)
    return data["blueprints"]


def load_results(results_path: str) -> dict:
    with open(results_path) as f:
        return json.load(f)


def sync_results(results_path: str, mode: str = "futures", dry_run: bool = True):
    """Sync backtest results for a given mode back to ChromaDB chunk metadata."""
    blueprints = load_blueprints()
    results = load_results(results_path)

    mode_results = results.get(mode, {})
    if not mode_results:
        print(f"No results found for mode '{mode}'")
        return

    # Build chunk_id -> performance mapping
    chunk_updates = defaultdict(list)

    for bp in blueprints:
        sid = bp["strategy_id"]
        # Try both with and without GenStrategy_ prefix
        result_key = f"GenStrategy_{sid}"
        if sid not in mode_results and result_key in mode_results:
            sid = result_key
        if sid not in mode_results:
            continue

        r = mode_results[sid]
        perf = {
            f"backtest_{mode}_trades": r.get("trades", 0),
            f"backtest_{mode}_profit_pct": round(r.get("profit_pct", 0), 2),
            f"backtest_{mode}_win_rate": round(r.get("win_rate", 0), 1),
            f"backtest_{mode}_dd_pct": round(r.get("dd_pct", 0), 2),
            f"backtest_{mode}_status": r.get("status", ""),
        }

        for cid in bp.get("chunk_ids", []):
            chunk_updates[cid].append(perf)

    print(f"Updates to apply: {len(chunk_updates)} chunks")

    if dry_run:
        print("DRY RUN — no changes written to ChromaDB")
        for cid, perfs in list(chunk_updates.items())[:5]:
            print(f"  {cid}: {perfs[0]}")
        return

    # Connect to ChromaDB
    client = chromadb.PersistentClient(
        path=DB_DIR, settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection(name=COLLECTION_NAME)

    for cid, perfs in chunk_updates.items():
        # Merge perf dicts (take first strategy's results per chunk)
        merged = perfs[0]
        collection.update(ids=[cid], metadatas=[merged])

    print(f"Synced {len(chunk_updates)} chunks with {mode} results.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync backtest results to ChromaDB")
    parser.add_argument("results_file", help="Path to results JSON file")
    parser.add_argument("--mode", choices=["futures", "spot"], default="futures")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually write to ChromaDB")
    args = parser.parse_args()

    sync_results(args.results_file, args.mode, dry_run=not args.no_dry_run)
