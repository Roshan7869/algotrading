"""Normalize the trading_strategies ChromaDB collection's metadata labels.

Adds four derived fields to every chunk, preserving all existing metadata:

  tf_norm        canonical timeframe bucket from the raw free-text ``timeframe``
                 field. One of: 1m, 5m, 15m, 30m, 1h, 4h, 1d, intraday, multi,
                 unknown (the raw field has ~98 distinct spellings).
  channel_clean  ``channel_name`` with missing/placeholder values -> 'unknown'
  setup_id       lowercase hyphen slug of ``setup_name`` (max 48 chars)
  has_title      bool: ``video_title`` non-empty after strip

Mapping policy (deterministic, order-stable):
  1. empty / 'not specified' / 'n/a' / 'unknown'        -> unknown
  2. 'universal' / 'any' / 'multi-timeframe' / 'fractal' -> multi
     (timeframe-agnostic: not tied to one bucket, so it is not 'unknown')
  3. explicit numeric timeframes are snapped to the nearest canonical bucket;
     two or more *distinct* buckets in one string -> multi
        <=3.5 min -> 1m, <=10 -> 5m, <=22 -> 15m, <=45 -> 30m, <=90 -> 1h
        hours: <=1.5 -> 1h, <=6 -> 4h, else -> 1d; days/weeks+ -> 1d
  4. no numbers: keyword groups (intraday/session ..., hourly, daily/swing/...);
     two or more distinct groups -> multi
  5. otherwise -> unknown

Usage:
    cd strategy_db
    ../.venv/Scripts/python.exe normalize_kb.py [--dry-run]
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter

import chromadb
from chromadb.config import Settings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import COLLECTION_NAME, DB_DIR  # noqa: E402

BATCH = 64

EMPTY_VALUES = {"", "not specified", "not-specified", "none", "n/a", "na",
                "unknown", "?", "-", "not applicable"}

# --- timeframe mapping -------------------------------------------------------
RE_MULTI_ANY = re.compile(
    r"(universal|multi[- ]?timeframe|multiple timeframes|\bany\b|agnostic|fractal)",
    re.I)
NUM_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*[- ]?\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|"
    r"days?|d|weeks?|w|months?|years?|yrs?|y)\b", re.I)
KW_GROUPS = [
    (re.compile(r"(intraday|session|pre[- ]?market|pre[- ]?trade|opening range|"
                r"0dte|prime window|time[- ]based)", re.I), "intraday"),
    (re.compile(r"(hourly|per hour)", re.I), "1h"),
    (re.compile(r"(daily|weekly|monthly|quarterly|yearly|positional|swing|"
                r"long[- ]term|medium[- ]term|multi[- ]year|close[- ]to[- ]open|"
                r"rolling window)", re.I), "1d"),
]


def _snap_minutes(x: float) -> str:
    if x <= 3.5:
        return "1m"
    if x <= 10:
        return "5m"
    if x <= 22:
        return "15m"
    if x <= 45:
        return "30m"
    if x <= 90:
        return "1h"
    return "4h"


def _bucket_from_token(value: float, unit: str) -> str:
    u = unit.lower()
    if u.startswith(("sec", "s")):
        return _snap_minutes(value / 60.0)
    if u.startswith(("min", "m")):
        return _snap_minutes(value)
    if u.startswith(("hour", "hr", "h")):
        if value <= 1.5:
            return "1h"
        if value <= 6:
            return "4h"
        return "1d"
    return "1d"  # day / week / month / year


def tf_norm(raw) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    if s in EMPTY_VALUES:
        return "unknown"
    if RE_MULTI_ANY.search(s):
        return "multi"

    buckets = set()
    for m in NUM_TOKEN.finditer(s):
        buckets.add(_bucket_from_token(float(m.group(1)), m.group(2)))
    if len(buckets) > 1:
        return "multi"
    if len(buckets) == 1:
        return buckets.pop()

    kw_buckets = {b for rx, b in KW_GROUPS if rx.search(s)}
    if len(kw_buckets) > 1:
        return "multi"
    if kw_buckets:
        return kw_buckets.pop()
    return "unknown"


def channel_clean(raw) -> str:
    s = (raw or "").strip()
    return "unknown" if s.lower() in EMPTY_VALUES else s


def setup_id(raw) -> str:
    s = unicodedata.normalize("NFKD", raw or "")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = s[:48].strip("-")
    return s or "unknown"


def has_title(raw) -> bool:
    return bool((raw or "").strip())


PLACEHOLDER_TITLES = {"not specified", "unknown", "n/a", "none", "-"}


def build_fields(md: dict) -> dict:
    return {
        "tf_norm": tf_norm(md.get("timeframe")),
        "channel_clean": channel_clean(md.get("channel_name")),
        "setup_id": setup_id(md.get("setup_name")),
        "has_title": has_title(md.get("video_title")),
    }


def stats(metadatas: list[dict]) -> dict:
    tf_raw = Counter((m.get("timeframe") or "").strip() for m in metadatas)
    tf = Counter(m.get("tf_norm") or tf_norm(m.get("timeframe")) for m in metadatas)
    ch = Counter(m.get("channel_clean") or channel_clean(m.get("channel_name"))
                 for m in metadatas)
    sid = {(m.get("setup_id") or setup_id(m.get("setup_name"))) for m in metadatas}
    sname = {(m.get("setup_name") or "").strip() for m in metadatas}
    yes = sum(1 for m in metadatas
              if (m["has_title"] if "has_title" in m else has_title(m.get("video_title"))))
    real = sum(1 for m in metadatas
               if (m.get("video_title") or "").strip().lower() not in PLACEHOLDER_TITLES
               and (m.get("video_title") or "").strip() != "")
    n = len(metadatas)
    return {
        "n": n,
        "distinct_timeframe_raw": len(tf_raw),
        "tf_norm": dict(tf.most_common()),
        "unknown_channel": ch.get("unknown", 0),
        "unknown_channel_pct": round(100.0 * ch.get("unknown", 0) / n, 1) if n else 0.0,
        "distinct_channel": len(ch),
        "distinct_setup_id": len(sid),
        "distinct_setup_name": len(sname),
        "has_title": yes,
        "has_title_pct": round(100.0 * yes / n, 1) if n else 0.0,
        "has_title_real": real,
        "has_title_real_pct": round(100.0 * real / n, 1) if n else 0.0,
    }


def main() -> int:
    dry = "--dry-run" in sys.argv
    client = chromadb.PersistentClient(path=DB_DIR,
                                       settings=Settings(anonymized_telemetry=False))
    col = client.get_collection(COLLECTION_NAME)
    total = col.count()
    print(f"Collection '{COLLECTION_NAME}' at {DB_DIR}: {total} vectors")

    before_meta: list[dict] = []
    for off in range(0, total, BATCH):
        res = col.get(include=["metadatas"], limit=BATCH, offset=off)
        before_meta.extend(res["metadatas"])
    before = stats(before_meta)
    print("\nBEFORE:", json.dumps(before, indent=2))

    written = 0
    for off in range(0, total, BATCH):
        res = col.get(include=["metadatas"], limit=BATCH, offset=off)
        ids, metas = [], []
        for cid, md in zip(res["ids"], res["metadatas"]):
            new = dict(md or {})
            new.update(build_fields(md or {}))
            ids.append(cid)
            metas.append(new)
        if not dry:
            col.update(ids=ids, metadatas=metas)
        written += len(ids)
        print(f"  {'would update' if dry else 'updated'} {written}/{total}")
    if dry:
        print("\n--dry-run: no writes issued")
        return 0

    after_meta: list[dict] = []
    for off in range(0, total, BATCH):
        res = col.get(include=["metadatas"], limit=BATCH, offset=off)
        after_meta.extend(res["metadatas"])
    after = stats(after_meta)
    print("\nAFTER:", json.dumps(after, indent=2))
    print(f"\nDone. {col.count()} vectors, {written} metadata records normalized")

    out = {"collection": COLLECTION_NAME, "db_dir": DB_DIR, "total": col.count(),
           "before": before, "after": after}
    outdir = r"D:/nexus-data/audits/algotrading"
    if os.path.isdir(outdir):
        with open(os.path.join(outdir, "kb_normalize_stats.json"), "w",
                  encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"stats written to {os.path.join(outdir, 'kb_normalize_stats.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
