#!/usr/bin/env python3
"""Phase 4.2 — executable KB coverage measure.

Measures how much of the strategy knowledge base talks about futures/perpetual
trading, using the keyword set fixed by the execution plan:

    futures | perpetual | funding | open interest | leverage | liquidation | 1h | 4h

A chunk counts as *futures-related* when at least one keyword matches its title
fields (``video_title``, ``setup_name``) or its document text, case-insensitively.

Baseline is today's measured fraction; the target is ``--target-multiplier``
(default 3x) times that baseline, printed as a percentage **and** as the number of
chunks that would have to match. Nothing here is a promise — re-run to re-measure.

Also reports, when the metadata keys exist, ``setup_id`` coverage and the
``tf_norm`` distribution (the keys are inspected on one record before use, so a
schema change degrades to "key absent" instead of a crash).

Output: a short markdown table in ``reports/phase4/kb_coverage.md`` (plus the same
numbers on stdout).

Usage:
    python scripts/kb_coverage.py
    python scripts/kb_coverage.py --target-multiplier 3 --out reports/phase4/kb_coverage.md
    python scripts/kb_coverage.py --fail-under-target   # exit 1 until the target is met
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "strategy_db" / "chroma_db"
DEFAULT_COLLECTION = "trading_strategies"
DEFAULT_OUT = REPO_ROOT / "reports" / "phase4" / "kb_coverage.md"

TITLE_FIELDS = ("video_title", "setup_name")

#: Literal, case-insensitive substrings.
KEYWORD_PATTERNS: dict[str, re.Pattern[str]] = {
    "futures": re.compile(r"futures", re.I),
    "perpetual": re.compile(r"perpetual", re.I),
    "funding": re.compile(r"funding", re.I),
    "open interest": re.compile(r"open[\s_-]+interest", re.I),
    "leverage": re.compile(r"leverage", re.I),
    "liquidation": re.compile(r"liquidations?", re.I),
    # timeframe tokens with a left boundary so "24h" cannot match "4h"
    "1h": re.compile(r"(?<![\w.])1h(?:r|our)?s?(?![\w])", re.I),
    "4h": re.compile(r"(?<![\w.])4h(?:r|our)?s?(?![\w])", re.I),
}

#: Timeframe keywords, reported separately because they also appear in non-futures
#: contexts; the plan's keyword list includes them, so they stay in the baseline.
TIMEFRAME_KEYWORDS = ("1h", "4h")


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def fetch_all(collection, batch: int) -> tuple[list[str], list[dict]]:
    """Batch-get every chunk (documents + metadata). Returns (docs, metas)."""
    total = collection.count()
    docs: list[str] = []
    metas: list[dict] = []
    offset = 0
    while offset < total:
        got = collection.get(
            limit=batch,
            offset=offset,
            include=["documents", "metadatas"],
        )
        batch_docs = got.get("documents") or []
        batch_metas = got.get("metadatas") or []
        if not batch_docs and not batch_metas:
            break
        docs.extend("" if d is None else d for d in batch_docs)
        metas.extend(m if isinstance(m, dict) else {} for m in batch_metas)
        offset += len(batch_docs) or len(batch_metas) or batch
    return docs, metas


def matched_keywords(*fields: str) -> set[str]:
    """Keyword names matching any of *fields* (empty fields are ignored)."""
    return {
        name
        for name, pat in KEYWORD_PATTERNS.items()
        if any(pat.search(field) for field in fields if field)
    }


def pct(value: float) -> str:
    return f"{value * 100:.4f}%"


def markdown_table(
    *,
    total: int,
    matched: int,
    fraction: float,
    target_fraction: float,
    target_chunks: int,
    per_keyword: Counter,
    title_hits: int,
    keyword_only_matched: int,
    setup_present: int | None,
    setup_distinct: int | None,
    tf_dist: Counter | None,
    collection: str,
    db_path: str,
    multiplier: float,
    sha: str,
) -> str:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# KB coverage — futures-related chunks (Phase 4.2)",
        "",
        f"Measured {now} · repo `{sha}` · collection `{collection}` · db `{db_path}`",
        "",
        "| metric | value |",
        "|---|---|",
        f"| total chunks | {total} |",
        f"| chunks mentioning futures keywords | {matched} |",
        f"| **baseline (measured fraction)** | **{pct(fraction)}** ({matched}/{total}) |",
        f"| target ({multiplier:g}x baseline) | {pct(target_fraction)} ({target_chunks}/{total} chunks) |",
        f"| gap to target | {max(0, target_chunks - matched)} chunks |",
        "",
        "| keyword | chunks matched |",
        "|---|---|",
    ]
    for name in KEYWORD_PATTERNS:
        lines.append(f"| {name} | {per_keyword.get(name, 0)} |")
    lines += [
        "",
        "| supplementary | value |",
        "|---|---|",
        f"| matched via title alone | {title_hits} |",
        f"| matched without the 1h/4h timeframe keywords | {keyword_only_matched} |",
    ]
    if setup_present is not None and total:
        lines.append(
            f"| `setup_id` coverage | {pct(setup_present / total)} ({setup_present}/{total}, "
            f"{setup_distinct} distinct) |"
        )
    else:
        lines.append("| `setup_id` coverage | key absent from metadata |")
    if tf_dist is not None and total:
        top = ", ".join(f"`{k}` {v}" for k, v in tf_dist.most_common())
        lines.append(f"| `tf_norm` distribution | {top} |")
    else:
        lines.append("| `tf_norm` distribution | key absent from metadata |")
    lines += [
        "",
        "Method: a chunk counts once when any of "
        + ", ".join(f"`{k}`" for k in KEYWORD_PATTERNS)
        + " matches its `video_title`/`setup_name` or document text (case-insensitive; "
        "`1h`/`4h` use a left word boundary so `24h` does not match `4h`). "
        "Baseline is the measured value above, not a target; the target is "
        f"{multiplier:g}x that number and is only met when a re-run reports it.",
        "",
        "Reproduce: `python scripts/kb_coverage.py`",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase 4.2 executable KB coverage measure.")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="chromadb persist dir")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION, help="collection name")
    ap.add_argument("--batch", type=int, default=200, help="batch size for chunked get()")
    ap.add_argument("--target-multiplier", type=float, default=3.0, help="target = N x baseline")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="markdown output path")
    ap.add_argument("--no-write", action="store_true", help="print only, write no markdown")
    ap.add_argument(
        "--fail-under-target",
        action="store_true",
        help="exit 1 when the measured fraction is below the target fraction",
    )
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_dir():
        print(f"kb_coverage: chromadb dir not found: {db_path}", file=sys.stderr)
        return 2
    try:
        import chromadb  # noqa: PLC0415 — optional dependency, installed in .venv
    except ImportError as exc:  # pragma: no cover - environment guard
        print(f"kb_coverage: chromadb not importable ({exc}); use .venv/Scripts/python.exe",
              file=sys.stderr)
        return 2

    try:
        client = chromadb.PersistentClient(path=str(db_path))
        collection = client.get_collection(args.collection)
    except Exception as exc:  # noqa: BLE001 — surface chroma errors verbatim
        print(f"kb_coverage: cannot open collection '{args.collection}': {exc}", file=sys.stderr)
        return 2

    total_declared = collection.count()
    docs, metas = fetch_all(collection, max(1, args.batch))
    total = min(len(docs), len(metas))
    if total != total_declared:
        print(
            f"kb_coverage: WARNING fetched {total} chunks but collection.count()={total_declared}",
            file=sys.stderr,
        )

    # Inspect one record before trusting metadata keys.
    sample = metas[0] if metas else {}
    has_setup_id = "setup_id" in sample
    has_tf_norm = "tf_norm" in sample

    per_keyword: Counter = Counter()
    matched = 0
    title_hits = 0
    keyword_only_matched = 0
    setup_present = 0
    setup_ids: set[str] = set()
    tf_dist: Counter = Counter()

    for doc, meta in zip(docs, metas):
        title = " ".join(str(meta.get(f) or "") for f in TITLE_FIELDS)
        text = doc or ""
        hits = matched_keywords(title, text)
        if hits:
            matched += 1
            per_keyword.update(hits)
            if matched_keywords(title):
                title_hits += 1
            if hits - set(TIMEFRAME_KEYWORDS):
                keyword_only_matched += 1
        if has_setup_id:
            sid = str(meta.get("setup_id") or "").strip()
            if sid:
                setup_present += 1
                setup_ids.add(sid)
        if has_tf_norm:
            tf_dist[str(meta.get("tf_norm") or "missing")] += 1

    fraction = (matched / total) if total else 0.0
    target_fraction = fraction * args.target_multiplier
    target_chunks = math.ceil(args.target_multiplier * matched) if total else 0
    target_chunks = min(target_chunks, total)

    print(f"KB coverage — {db_path} :: {args.collection}")
    print(f"  total chunks                 : {total} (collection.count()={total_declared})")
    print(f"  futures-keyword chunks       : {matched}")
    print(f"  per keyword                  : "
          + ", ".join(f"{k}={v}" for k, v in sorted(per_keyword.items())))
    print(f"  matched via title only       : {title_hits}")
    print(f"  matched w/o 1h/4h keywords   : {keyword_only_matched}")
    print(f"  BASELINE                     : {pct(fraction)} ({matched}/{total})")
    print(f"  TARGET ({args.target_multiplier:g}x)               : {pct(target_fraction)} "
          f"({target_chunks}/{total} chunks, +{max(0, target_chunks - matched)})")
    if has_setup_id:
        print(f"  setup_id coverage            : {setup_present}/{total} "
              f"({pct(setup_present / total) if total else 'n/a'}), {len(setup_ids)} distinct")
    else:
        print("  setup_id coverage            : key absent")
    if has_tf_norm:
        print("  tf_norm distribution         : "
              + ", ".join(f"{k}={v}" for k, v in tf_dist.most_common()))
    else:
        print("  tf_norm distribution         : key absent")

    md = markdown_table(
        total=total,
        matched=matched,
        fraction=fraction,
        target_fraction=target_fraction,
        target_chunks=target_chunks,
        per_keyword=per_keyword,
        title_hits=title_hits,
        keyword_only_matched=keyword_only_matched,
        setup_present=setup_present if has_setup_id else None,
        setup_distinct=len(setup_ids) if has_setup_id else None,
        tf_dist=tf_dist if has_tf_norm else None,
        collection=args.collection,
        db_path=str(db_path),
        multiplier=args.target_multiplier,
        sha=git_sha(),
    )
    if not args.no_write:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"  wrote                        : {out_path}")

    if args.fail_under_target and fraction < target_fraction:
        print(f"kb_coverage: FAIL below target ({pct(fraction)} < {pct(target_fraction)})",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
