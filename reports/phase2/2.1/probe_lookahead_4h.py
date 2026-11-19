"""Phase 2.1 evidence probe — is SupertrendEmaStrategy's 4h merge a lookahead?

It does not need freqtrade's backtester: the claim is structural.

1. A 4h candle *stamped* D covers [D, D+4h); its close is only known at D+4h.
2. SupertrendEmaStrategy.populate_indicators merges that 4h row onto every 1h row with
   the same stamp D and then forward-fills it (lines 122-132), so the 1h rows at
   D, D+1h, D+2h consume a close that happens 3h, 2h, 1h in the future.
   Only the D+3h row is clean (its own close *is* D+4h).
3. The one-line fix freqtrade ships is merge_informative_pair(), which moves the
   informative stamp forward by one 4h candle (strategy_helper.py:17-25, 48-62).
   The strategy imports it (line 19) and never calls it.

Run:  .venv/Scripts/python.exe reports/phase2/2.1/probe_lookahead_4h.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow.feather as feather

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "user_data" / "strategies"))

from SupertrendEmaStrategy import SupertrendEmaStrategy  # noqa: E402

DATA = REPO / "user_data" / "data" / "binance" / "futures"
PAIR_FILE = "BTC_USDT_USDT"
START, END = "2026-01-01", "2026-02-01"  # one validation month is enough to count


def load(tf: str) -> pd.DataFrame:
    df = feather.read_feather(DATA / f"{PAIR_FILE}-{tf}-futures.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df[(df["date"] >= pd.Timestamp(START, tz="UTC")) & (df["date"] < pd.Timestamp(END, tz="UTC"))]


h1 = load("1h")
h4 = load("4h")
print(f"1h rows={len(h1)} 4h rows={len(h4)} window={START}..{END}")

# ---- 1. the 4h row at D carries the 1h close at D+3h -------------------------------
print("\n[1] proof that a 4h row stamped D contains future prices")
last_in_bucket = h4.assign(date=h4["date"] + pd.Timedelta(hours=3)).merge(
    h1[["date", "close"]].rename(columns={"close": "close_1h_at_D3"}), on="date", how="left")
check = pd.DataFrame({
    "bucket_start": h4["date"].values,
    "close_4h": h4["close"].values,
    "close_1h_at_D+3h": last_in_bucket["close"].values,
})
check["equal"] = (check["close_4h"] - check["close_1h_at_D+3h"]).abs() < 1e-9
print(check.head(6).to_string(index=False))
print(f"4h.close == 1h.close[D+3h] for {int(check['equal'].sum())}/{len(check)} buckets")

# ---- 2. reproduce the strategy merge, tag every row with its lookahead -------------
st = SupertrendEmaStrategy.supertrend(None, h4.copy(), 10, 3.0)
inf = st[["date", "supertrend_direction"]].rename(columns={"supertrend_direction": "st_direction_4h"})
df = h1.merge(inf, on="date", how="left")
df["st_direction_4h"] = df["st_direction_4h"].ffill()          # line 131 of the strategy
df["bucket_start"] = df["date"].dt.floor("4h")
# the value was knowable at bucket_start + 4h; the row's own close is date + 1h
df["known_at"] = df["bucket_start"] + pd.Timedelta(hours=4)
df["row_close_at"] = df["date"] + pd.Timedelta(hours=1)
df["peeks_ahead"] = df["known_at"] > df["row_close_at"]
n, leak = len(df), int(df["peeks_ahead"].sum())
print(f"\n[2] rows whose 4h value is known only after the row closes: {leak}/{n} = {leak / n:.1%}")

# ---- 3. how often does the leaked value disagree with the last CLOSED 4h candle? ---
# correct alignment == what merge_informative_pair does: 4h stamp shifted +4h
correct = st[["date", "supertrend_direction"]].copy()
correct["date"] = correct["date"] + pd.Timedelta(hours=4)
correct = correct.rename(columns={"supertrend_direction": "st_direction_4h_clean"})
df = df.merge(correct, on="date", how="left")
df["st_direction_4h_clean"] = df["st_direction_4h_clean"].ffill()
valid = df.dropna(subset=["st_direction_4h", "st_direction_4h_clean"])
same = (valid["st_direction_4h"] == valid["st_direction_4h_clean"])
print(f"[3] leaked 4h direction vs last-closed 4h direction: "
      f"{int((~same).sum())}/{len(valid)} rows differ ({(~same).mean():.1%})")

# ---- 4. does it reach the entry condition? ----------------------------------------
# long_conditions requires st_direction_4h == 1 (line 169); count rows where the guard
# flips because of the leak.
clean_rows = valid[valid["st_direction_4h_clean"] == 1]
lost = clean_rows[clean_rows["st_direction_4h"] != 1]
gained = valid[(valid["st_direction_4h_clean"] != 1) & (valid["st_direction_4h"] == 1)]
print(f"[4] mtf_ok (st_direction_4h==1) true only because of the leak: {len(gained)} rows; "
      f"false only because of the leak: {len(lost)} rows")
print("\nVERDICT: the 4h merge reads future prices; SupertrendEmaStrategy is lookahead-SUSPECT.")
