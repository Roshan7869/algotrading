#!/usr/bin/env python3
"""NEXUS research harness — connects the strategy KB (ChromaDB), the Obsidian
finance vault (via the nexus CLI), and the algotrading platform into one
deterministic research pipeline. No LLM calls, no daemons, CPU-only.

Run with the algotrading venv python:
  .venv\\Scripts\\python.exe research\\harness.py kb "liquidity trap" --k 5
  .venv\\Scripts\\python.exe research\\harness.py brief "liquidity trap" --ticker BTC/USDT
  .venv\\Scripts\\python.exe research\\harness.py vault "risk sizing" --k 8

Subcommands:
  kb     query the strategy knowledge base only (chromadb)
  vault  query the Obsidian finance vault only (nexus --vault finance)
  brief  full brief: KB matches + vault knowledge + data availability +
         risk checklist + backtest template -> written into the vault
         (FINANCE/12-Research/research-<slug>.md) and reindexed, or printed
         with --print-only

Layers (the "assisting layers" of a trading setup):
  1. STRATEGY KB   strategy_db/chroma_db, collection 'trading_strategies'
                   (612 vectors, ONNX MiniLM, CPU)
  2. KNOWLEDGE     Obsidian finance vault through the nexus CLI
                   (nexus --vault finance search ... --json)
  3. PLATFORM      data availability (user_data/data feathers) + runbook refs
  4. OUTPUT        nexus-indexed note in FINANCE/12-Research
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = ROOT / "strategy_db" / "chroma_db"
COLLECTION = "trading_strategies"
FINANCE_VAULT = Path(os.environ.get("FINANCE_VAULT", r"D:\finance-vault"))
VAULT_SUBDIR = "FINANCE/12-Research"
DATA_DIR = ROOT / "user_data" / "data" / "binance"


# ---------------------------------------------------------------- helpers
def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "brief"


def get_collection():
    import chromadb  # noqa: PLC0415

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(COLLECTION)


def kb_query(query: str, k: int = 5, with_text: bool = True):
    col = get_collection()
    res = col.query(query_texts=[query], n_results=k, include=["metadatas", "documents", "distances"])
    rows = []
    for meta, doc, dist in zip(res["metadatas"][0], res["documents"][0], res["distances"][0]):
        rows.append({"meta": meta, "doc": doc, "score": round(1.0 - float(dist), 4)})
    return rows, col.count()


def nexus_cmd(args: list[str]) -> list[str]:
    exe = shutil.which("nexus")
    if exe:
        return [exe, *args]
    return [sys.executable, str(Path.home() / ".config" / "nexus" / "nexus.py"), *args]


def vault_search(query: str, k: int = 8):
    try:
        out = subprocess.run(
            nexus_cmd(["--vault", "finance", "search", query, "--limit", str(k), "--json"]),
            capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
        )
        if out.returncode != 0:
            return [{"error": (out.stderr or out.stdout).strip()[:200]}], ""
        return json.loads(out.stdout or "[]"), ""
    except Exception as e:  # noqa: BLE001
        return [{"error": f"{type(e).__name__}: {e}"[:200]}], ""


def vault_reindex() -> str:
    try:
        out = subprocess.run(nexus_cmd(["--vault", "finance", "reindex"]),
                             capture_output=True, text=True, timeout=120,
                             encoding="utf-8", errors="replace")
        return (out.stdout or "").strip().splitlines()[-1] if out.stdout else "reindex: no output"
    except Exception as e:  # noqa: BLE001
        return f"reindex failed: {e}"


def data_availability(ticker: str | None) -> list[dict]:
    if not ticker:
        return []
    base = ticker.upper().replace("/", "_").replace(":", "_")
    hits: dict[str, str] = {}
    for d in (DATA_DIR, DATA_DIR / "futures"):
        if not d.is_dir():
            continue
        for f in d.glob("*.feather"):
            name = f.name
            if name.startswith(base + "-") or name.startswith(base + "_"):
                parts = name.split("-")
                tf = parts[1] if len(parts) > 1 else "?"
                kind = "funding/mark" if ("funding" in name or "mark" in name) else ("futures" if "futures" in name or d.name == "futures" else "spot")
                hits[f"{tf} ({kind})"] = str(f.relative_to(ROOT))
    return [{"timeframe_kind": k, "path": v} for k, v in sorted(hits.items())]


CHECKLIST = [
    "[[position-sizing]] — risk % first, size second",
    "[[stop-losses-and-r-multiples]] — price-terms stop, R-multiple, expectancy",
    "[[fees-and-costs]] — round-trip cost vs required edge",
    "[[india-crypto-tax]] — gross-gains tax, no loss set-off",
    "[[drawdown-and-portfolio]] — portfolio heat before adding this setup",
]


# ---------------------------------------------------------------- rendering
def render_rows(rows: list[dict]) -> str:
    lines = ["| # | setup | type | market | keywords | score |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        m = r["meta"]
        kw = (m.get("keywords") or "")[:60]
        lines.append(f"| {i} | {m.get('setup_name','?')[:50]} | {m.get('setup_type','?')} | "
                     f"{m.get('market_condition', m.get('tf_norm','?'))[:20]} | {kw} | {r['score']} |")
    return "\n".join(lines)


def render_vault(rows: list[dict]) -> str:
    rows = [r for r in rows if isinstance(r, dict) and "error" not in r]
    if not rows:
        return "_no vault matches_"
    lines = ["| note | cluster | desc |", "|---|---|---|"]
    for r in rows[:10]:
        lines.append(f"| [[{r.get('name','?')}]] | {r.get('cluster','')} | {(r.get('desc') or '')[:80].replace(chr(124), '/')} |")
    return "\n".join(lines)


def render_data(rows: list[dict], ticker: str | None) -> str:
    if not ticker:
        return "_no ticker specified_"
    if not rows:
        return f"**No local data found for {ticker}** — run `freqtrade download-data` before backtesting."
    lines = ["| timeframe (kind) | path |", "|---|---|"]
    for r in rows:
        lines.append(f"| {r['timeframe_kind']} | `{r['path']}` |")
    return "\n".join(lines)


def build_note(query: str, ticker: str | None, kb_rows: list[dict], kb_total: int,
               vault_rows: list[dict], data_rows: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    slug = slugify(query)
    excerpt = kb_rows[0]["doc"] if kb_rows else ""
    note = f"""---
nexus_resource: "research-{slug}"
nexus_type: "note"
repo: "finance-kb"
cluster: "finance_research"
tokens: {max(300, len(excerpt) // 4)}
source: "harness:strategy_db+vault"
---

> Research brief for "{query}" — strategy-KB matches, vault knowledge, data availability, risk checklist (generated {now.strftime('%Y-%m-%d %H:%M UTC')}).

# Research brief: {query}

## 1. Strategy KB matches (ChromaDB — {kb_total} vectors)

{render_rows(kb_rows)}

### Top setup excerpt
```
{excerpt[:2500]}
```

## 2. Knowledge base (Obsidian finance vault via nexus)

{render_vault(vault_rows)}

## 3. Data availability{f" ({ticker})" if ticker else ""}

{render_data(data_rows, ticker)}

## 4. Risk checklist (department invariants)

{chr(10).join('- ' + item for item in CHECKLIST)}

## 5. Backtest template

```
freqtrade backtesting --strategy <StrategyClass> -c user_data/config_backtest.json \\
  --timerange {now.strftime('%Y%m%d')}- \\
  {'--config user_data/config_spot.json' if ticker and ':' not in ticker else ''}
```

## 6. Provenance

Generated by `research/harness.py` at {now.isoformat()} ·
KB collection `{COLLECTION}` ({CHROMA_DIR}) · vault `{FINANCE_VAULT}` via nexus CLI.
This is a research artifact, not a signal — validate in walk-forward + paper trading.
"""
    return note


# ---------------------------------------------------------------- commands
def cmd_kb(args) -> int:
    rows, total = kb_query(args.query, args.k)
    print(f"# KB matches for {args.query!r} ({total} vectors)\n")
    print(render_rows(rows))
    if rows:
        print("\n--- top excerpt ---\n")
        print(rows[0]["doc"][:4000])
    return 0


def cmd_vault(args) -> int:
    rows, err = vault_search(args.query, args.k)
    if err:
        print("vault search failed:", err)
        return 1
    print(render_vault(rows))
    return 0


def cmd_brief(args) -> int:
    t0 = time.time()
    kb_rows, kb_total = kb_query(args.query, args.k)
    vault_rows, _ = vault_search(args.query, args.vault_k)
    data_rows = data_availability(args.ticker)
    note = build_note(args.query, args.ticker, kb_rows, kb_total, vault_rows, data_rows)

    if args.print_only:
        print(note)
        return 0

    out_dir = FINANCE_VAULT / VAULT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"research-{slugify(args.query)}.md"
    out_path.write_text(note, encoding="utf-8")
    print(f"written: {out_path}")
    print(vault_reindex())
    print(f"done in {time.time() - t0:.1f}s — query it back with: nexus --vault finance search {args.query!r}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="harness", description="NEXUS research harness (KB + vault + platform)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("kb", "vault", "brief"):
        p = sub.add_parser(name)
        p.add_argument("query")
        p.add_argument("--k", type=int, default=5, help="KB results (kb/brief)")
        p.add_argument("--vault-k", type=int, default=8, help="vault results (brief)")
        if name == "brief":
            p.add_argument("--ticker", default=None, help="e.g. BTC/USDT or BTC/USDT:USDT")
            p.add_argument("--print-only", action="store_true", help="print instead of writing to the vault")
    args = ap.parse_args()
    return {"kb": cmd_kb, "vault": cmd_vault, "brief": cmd_brief}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
