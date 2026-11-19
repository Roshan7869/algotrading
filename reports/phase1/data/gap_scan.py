#!/usr/bin/env python
"""Phase 1.3 gap verification for the 20-pair canonical futures universe (1h).

Reads user_data/data/<venue>/futures/<BASE>_USDT_USDT-1h-futures.feather
Emits reports/phase1/data/gap_scan.json and a markdown table on stdout.

Metric definitions (per EXECUTION_PLAN 1.3), TWO denominators:

  A. LISTING WINDOW (the gate denominator — "expected = candles between first and
     last bar for that pair's listing window", listing date from fapi onboardDate):
       expected_listing = ((last - listing) // 1h) + 1
       missing_listing  = max(0, expected_listing - rows)   # includes truncated file start
  B. IN-FILE SPAN (integrity of what exists):
       expected_span = ((last - first) // 1h) + 1
       missing_span  = expected_span - rows
       gap%_span     = missing_span / expected_span * 100
  max_gap_h = largest delta between consecutive bar timestamps, in hours
              (crypto perps trade 24/7, so every delta > 1h is a real hole).
"""
from __future__ import annotations

import glob
import json
import os
import sys

import pandas as pd

UNIVERSE = ("BTC ETH SOL XRP DOGE BNB ADA AVAX LINK DOT LTC TRX "
            "ATOM NEAR APT ARB OP SUI INJ SEI").split()
HOUR_MS = 3_600_000
VENUE = sys.argv[1] if len(sys.argv) > 1 else "binance"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATADIR = os.path.join(ROOT, "user_data", "data", VENUE, "futures")
OUTDIR = os.path.join(ROOT, "reports", "phase1", "data")


def load_onboard() -> dict:
    """symbol -> onboardDate (ms) from the saved fapi exchangeInfo snapshot."""
    hits = sorted(glob.glob(os.path.join(OUTDIR, "fapi_exchangeInfo_*.json")))
    if not hits:
        return {}
    with open(hits[-1], encoding="utf-8") as fh:
        data = json.load(fh)
    return {s["symbol"]: s.get("onboardDate") for s in data.get("symbols", [])}


def scan(base: str, onboard: dict) -> dict:
    fn = f"{base}_USDT_USDT-1h-futures.feather"
    path = os.path.join(DATADIR, fn)
    ob_ms = onboard.get(f"{base}USDT")
    rec = {"base": base, "pair": f"{base}/USDT:USDT", "file": fn,
           "exists": os.path.exists(path),
           "listing_utc": pd.Timestamp(ob_ms, unit="ms", tz="UTC").isoformat() if ob_ms else None}
    if not rec["exists"]:
        rec.update(rows=0, first=None, last=None, expected_listing=None, missing_listing=None,
                   gap_pct_listing=None, expected_span=0, missing_span=0, gap_pct_span=None,
                   max_gap_h=None, status="MISSING_FILE")
        return rec

    df = pd.read_feather(path)
    col = "date" if "date" in df.columns else df.columns[0]
    ts = pd.to_datetime(df[col], utc=True).sort_values().reset_index(drop=True)
    n = int(len(ts))
    rec["file_mtime"] = pd.Timestamp(os.path.getmtime(path), unit="s", tz="UTC").isoformat()
    rec["columns"] = list(df.columns)
    if n == 0:
        rec.update(rows=0, first=None, last=None, expected_listing=None, missing_listing=None,
                   gap_pct_listing=None, expected_span=0, missing_span=0, gap_pct_span=None,
                   max_gap_h=None, status="EMPTY")
        return rec

    first, last = ts.iloc[0], ts.iloc[-1]
    span_ms = int((last.value - first.value) // 1_000_000)
    expected = span_ms // HOUR_MS + 1
    deltas = ts.diff().dropna().dt.total_seconds() / 3600.0
    max_gap = float(deltas.max()) if len(deltas) else 0.0
    exp_l = miss_l = gap_l = None
    if ob_ms:
        exp_l = int(((last.value - ob_ms * 1_000_000) // 1_000_000) // HOUR_MS) + 1
        miss_l = max(0, exp_l - n)
        gap_l = round(miss_l / exp_l * 100, 4)
    # largest gap expressed as *missing bars* inside the gap (max_gap_h - 1)
    rec.update(
        rows=n,
        first=first.isoformat(),
        last=last.isoformat(),
        expected_listing=exp_l,
        missing_listing=miss_l,
        gap_pct_listing=gap_l,
        expected_span=int(expected),
        missing_span=int(expected - n),
        gap_pct_span=round((expected - n) / expected * 100, 4) if expected else None,
        max_gap_h=round(max_gap, 2),
        max_gap_missing_bars=int(round(max_gap - 1)) if max_gap >= 1 else 0,
        duplicates=int(n - ts.nunique()),
        monotonic=bool(ts.is_monotonic_increasing),
        status="OK",
    )
    return rec


def main() -> int:
    onboard = load_onboard()
    recs = [scan(b, onboard) for b in UNIVERSE]
    os.makedirs(OUTDIR, exist_ok=True)
    payload = {"venue": VENUE, "datadir": DATADIR, "timeframe": "1h",
               "trading_mode": "futures", "universe_size": len(UNIVERSE),
               "listing_source": "fapi exchangeInfo onboardDate",
               "generated_utc": pd.Timestamp.now("UTC").isoformat(), "pairs": recs}
    with open(os.path.join(OUTDIR, "gap_scan.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    hdr = ("| Pair | Listing (UTC) | First candle | Last candle | Rows | Expected (listing→last) "
           "| Missing | Gap % (listing) | Gap % (in-file) | Max gap (h) |")
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    print(hdr)
    print(sep)
    for r in recs:
        if r["status"] != "OK":
            print(f"| {r['pair']} | {r.get('listing_utc') or '—'} | — | — | 0 | — | — | — | — | — |")
            continue
        lst = (r["listing_utc"] or "—")[:10]
        gl = f"{r['gap_pct_listing']:.2f}" if r["gap_pct_listing"] is not None else "—"
        ml = r["missing_listing"] if r["missing_listing"] is not None else "—"
        print(f"| {r['pair']} | {lst} | {r['first'][:16].replace('T', ' ')} "
              f"| {r['last'][:16].replace('T', ' ')} | {r['rows']} | {r['expected_listing'] or '—'} "
              f"| {ml} | {gl} | {r['gap_pct_span']:.2f} | {r['max_gap_h']:.1f} |")

    ok = [r for r in recs if r["status"] == "OK"]
    total_rows = sum(r["rows"] for r in ok)
    over1 = [r["pair"] for r in ok if (r["gap_pct_listing"] or 0) > 1.0]
    over1_span = [r["pair"] for r in ok if (r["gap_pct_span"] or 0) > 1.0]
    worst = max(ok, key=lambda r: (r["gap_pct_listing"] or 0)) if ok else None
    print()
    print(f"coverage: {len(ok)}/{len(UNIVERSE)} pairs present, {total_rows} rows total")
    print(f"pairs with listing-window gap% > 1.0: {len(over1)} -> {over1 if over1 else 'none'}")
    print(f"pairs with in-file gap% > 1.0: {len(over1_span)} -> {over1_span if over1_span else 'none'}")
    if worst:
        print(f"worst pair by listing-window gap%: {worst['pair']} "
              f"gap%={worst['gap_pct_listing']:.2f} missing={worst['missing_listing']} "
              f"first={worst['first'][:10]} listing={(worst['listing_utc'] or '?')[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
