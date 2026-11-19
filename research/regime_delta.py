"""Regime-gate DELTA experiment (EXECUTION_PLAN option 1 pre-check).

Question: does a Wasserstein-k-means regime gate improve expectancy on OUR trades?
Design (strict, no leakage):
  - Centroids fit ONLY on 2025 windows (per pair), k=2, deterministic init (5th/95th pct std).
  - Labels applied causally: label at entry uses the window ending at the last completed bar
    before the entry candle (open_date - 1h), inclusive.
  - Evaluation slice: 2026-01-01..2026-07-01 (the scoreboard VALIDATION window; selection window,
    legitimately usable). The sealed holdout is NOT touched by this script's conclusions.
  - Trades: the walkforward trade exports (same fills, 10bps all-in cost model, per-strategy).
  - Variants: baseline (all trades) | gate=calm (allow only lower-vol centroid) | gate=volatile.
  - Metrics: trades, exp/trade, winrate, PF, sum profit_abs (fixed stake), maxDD of cumulative
    profit_abs. Equity-path effects of compound stake are NOT modeled here (trade-filter pass);
    a positive result must be re-validated in the native backtester before any gate decision.

Outputs: reports/phase2/regime-gate/DELTA.md + delta.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "user_data/data/binance/futures"
TRADES = ROOT / "reports/walkforward-20261119-1313/trades"
OUT = ROOT / "reports/phase2/regime-gate"
OUT.mkdir(parents=True, exist_ok=True)

H1 = 168          # window = 1 week of 1h bars
QS = np.linspace(0.025, 0.975, 21)
FIT_START = pd.Timestamp("2025-01-01", tz="UTC")
FIT_END = pd.Timestamp("2026-01-01", tz="UTC")
EVAL_START = pd.Timestamp("2026-01-01", tz="UTC")
EVAL_END = pd.Timestamp("2026-07-01", tz="UTC")

STRATEGIES = ["EmaTrendFollowing", "AroonMomentumEngine_V2", "BollingerMeanReversion"]


def pair_file(pair: str) -> Path:
    return DATA / (pair.replace("/", "_").replace(":", "_") + "-1h-futures.feather")


def build_labels(pair: str) -> pd.DataFrame:
    df = pd.read_feather(pair_file(pair))[["date", "close"]].sort_values("date")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    r = np.log(df["close"].to_numpy(dtype=np.float64))
    r = np.diff(r)
    dates = df["date"].dt.tz_localize(None).to_numpy()[1:]  # naive datetime64 for array compares
    n = len(r)
    if n < H1 + 10:
        return pd.DataFrame()
    win = np.lib.stride_tricks.sliding_window_view(r, H1)          # (n-H1+1, H1)
    ends = dates[H1 - 1:]                                          # end date per window
    q = np.quantile(win, QS, axis=1).T.astype(np.float32)          # (W, 21)
    wstd = win.std(axis=1).astype(np.float32)

    in_fit = (ends >= FIT_START.tz_localize(None).to_datetime64()) & \
             (ends < FIT_END.tz_localize(None).to_datetime64())
    qf, sf = q[in_fit], wstd[in_fit]
    if len(qf) < 50:
        return pd.DataFrame()

    def init(idx):
        return qf[idx].copy()

    c1 = init(int(np.argmin(np.abs(np.quantile(sf, 0.05) - sf))))
    c2 = init(int(np.argmin(np.abs(np.quantile(sf, 0.95) - sf))))
    C = np.vstack([c1, c2])
    lab_f = None
    for _ in range(15):
        d1 = np.abs(qf - C[0]).mean(axis=1)
        d2 = np.abs(qf - C[1]).mean(axis=1)
        lab_f = (d2 < d1).astype(np.int8)
        for k in (0, 1):
            m = lab_f == k
            if m.sum() > 0:
                C[k] = np.median(qf[m], axis=0)
    calm = 0 if sf[lab_f == 0].mean() < sf[lab_f == 1].mean() else 1

    d1 = np.abs(q - C[0]).mean(axis=1)
    d2 = np.abs(q - C[1]).mean(axis=1)
    lab = (d2 < d1).astype(np.int8)
    return pd.DataFrame({
        "pair": pair,
        "window_end": pd.to_datetime(ends, utc=True),
        "label": lab,
        "calm_label": calm,
        "wstd": wstd,
    })


def metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"trades": 0}
    pr = df["profit_ratio"].astype(float)
    pa = df["profit_abs"].astype(float)
    wins, losses = pr[pr > 0], pr[pr <= 0]
    pf = float(wins.sum() / abs(losses.sum())) if abs(losses.sum()) > 1e-12 else float("inf")
    cum = pa.sort_index().cumsum()
    dd = float((cum.cummax() - cum).max()) if len(cum) else 0.0
    return {
        "trades": int(len(df)),
        "exp_pct": float(pr.mean() * 100),
        "win_pct": float((pr > 0).mean() * 100),
        "pf": float(pf) if np.isfinite(pf) else None,
        "sum_profit_abs": float(pa.sum()),
        "maxdd_abs": dd,
    }


def main() -> None:
    labels_all = []
    pairs = sorted({pd.read_csv(TRADES / f"{s}.csv", usecols=["pair"])["pair"].iat[0]
                    for s in STRATEGIES}) if False else None
    # collect all pairs actually traded
    used = set()
    for s in STRATEGIES:
        p = TRADES / f"{s}.csv"
        if p.stat().st_size > 0:
            used |= set(pd.read_csv(p, usecols=["pair"])["pair"].unique())
    print(f"pairs traded: {len(used)}")
    for pair in sorted(used):
        lb = build_labels(pair)
        if len(lb):
            labels_all.append(lb)
    labels = pd.concat(labels_all, ignore_index=True)
    labels["window_end"] = labels["window_end"].astype("datetime64[ns, UTC]")
    print(f"label rows: {len(labels)}")

    report, js = {}, {"meta": {
        "fit_window": "2025-01-01..2026-01-01", "eval_window": "2026-01-01..2026-07-01",
        "H1": H1, "quantiles": int(len(QS)), "cost_model": "10bps all-in (inherited from walkforward fills)",
        "note": "trade-filter delta; equity-path not modeled; holdout untouched"},
        "strategies": {}}

    lines = ["# Regime-gate DELTA — does the Wasserstein paper help OUR trades?", "",
             "| Slice | Strategy | Variant | Trades | Exp/trade % | Win % | PF | Σ profit (abs, fixed stake) | MaxDD (abs) |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for strat in STRATEGIES:
        td = pd.read_csv(TRADES / f"{strat}.csv")
        if td.empty:
            continue
        td["open_date"] = pd.to_datetime(td["open_date"], utc=True)
        td = td.sort_values("open_date")
        # label at last completed bar before entry
        td["label_date"] = (td["open_date"] - pd.Timedelta(hours=1)).astype("datetime64[ns, UTC]")
        m = pd.merge_asof(td, labels.sort_values("window_end"),
                          left_on="label_date", right_on="window_end",
                          by="pair", direction="backward", tolerance=pd.Timedelta(hours=48))
        val = m[(m["open_date"] >= EVAL_START) & (m["open_date"] < EVAL_END)].copy()
        if val.empty:
            continue
        val["calm"] = val["calm_label"] == val["label"]
        variants = {
            "baseline (all)": val,
            "gate=calm-only": val[val["calm"]],
            "gate=volatile-only": val[~val["calm"]],
        }
        js["strategies"][strat] = {}
        for name, d in variants.items():
            mm = metrics(d)
            js["strategies"][strat][name] = mm
            lines.append(f"| validation | {strat} | {name} | {mm.get('trades',0)} | "
                         f"{mm.get('exp_pct',0):.3f} | {mm.get('win_pct',0):.1f} | "
                         f"{mm.get('pf') if mm.get('pf') is not None else float('nan'):.3f} | "
                         f"{mm.get('sum_profit_abs',0):.1f} | {mm.get('maxdd_abs',0):.1f} |")

    # insight block: expectancy of blocked vs kept trades
    lines += ["", "## Gate quality (validation slice)", "",
              "| Strategy | Kept (calm) exp% | Blocked (volatile) exp% | Delta if blocked removed (pp) |",
              "|---|---:|---:|---:|"]
    for strat in STRATEGIES:
        s = js["strategies"].get(strat)
        if not s or "gate=calm-only" not in s:
            continue
        b = s["baseline (all)"]["exp_pct"]
        c = s["gate=calm-only"]["exp_pct"]
        v = s["gate=volatile-only"]["exp_pct"]
        lines.append(f"| {strat} | {c:.3f} | {v:.3f} | **{c - b:+.3f}** |")

    (OUT / "DELTA.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "delta.json").write_text(json.dumps(js, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
