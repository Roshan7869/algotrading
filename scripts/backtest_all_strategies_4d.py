"""
Backtest ALL strategies on last 4 days of data
  1h swing: V1 Original, V2 ATR, V3 EMA-Stack(adapted), V4 MTF-VP, V5 +Hedge
  5m short-term: ST-V2
"""

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_1H = PROJECT_ROOT / "user_data" / "data" / "binance"
DATA_5M = PROJECT_ROOT / "user_data" / "data" / "binance" / "futures"

# ─── Shared Parameters ────────────────────────────────────────────────────
SL_BUF = 0.002
TP1_RR = 1.0; TP2_RR = 2.0; TP3_RR = 3.0
TP1_QTY = 0.40; TP2_QTY = 0.35
VOL_MUL = 1.2; BODY_R = 0.40; MAX_WAIT = 10

# ST-V2 (5m) Parameters
ST_LOOKBACK = 30; ST_BINS = 20; ST_VA_PCT = 0.70
ST_SL_BUF = 0.0025; ST_TP1_RR = 1.2; ST_TP2_RR = 2.0
ST_TP1_QTY = 0.50; ST_VOL_MUL = 1.2; ST_BODY_R = 0.30; ST_MAX_WAIT = 8
ST_VP_STEP = 2


# ─── VP Engine ─────────────────────────────────────────────────────────────

def compute_vp(highs, lows, volumes, lb=50, bins=24, va_pct=0.70, step=5):
    n = len(highs)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    last_poc, last_vah, last_val = np.nan, np.nan, np.nan
    for i in range(lb - 1, n):
        poc[i], vah[i], val[i] = last_poc, last_vah, last_val
        if (i - lb + 1) % step != 0: continue
        start = i - lb + 1
        seg_h, seg_l, seg_v = highs[start:i+1], lows[start:i+1], volumes[start:i+1]
        h_hi, h_lo = seg_h.max(), seg_l.min()
        rng = h_hi - h_lo
        if rng <= 1e-10: continue
        norm_l = (seg_l - h_lo) / rng; norm_h = (seg_h - h_lo) / rng
        bin_vol = np.zeros(bins)
        for j in range(lb):
            if seg_v[j] <= 0 or norm_h[j] <= norm_l[j]: continue
            b_low = max(0, int(np.floor(norm_l[j] * bins)))
            b_high = min(bins, int(np.ceil(norm_h[j] * bins)))
            if b_low >= b_high: continue
            n_cov = b_high - b_low
            bin_vol[b_low:b_high] += seg_v[j] / n_cov
        pb = int(bin_vol.argmax())
        last_poc = h_lo + (pb + 0.5) * rng / bins
        tv = bin_vol.sum()
        if tv <= 0: continue
        target = tv * va_pct
        va_v = bin_vol[pb]; ui = di = pb
        while va_v < target:
            uv = bin_vol[ui+1] if ui+1 < bins else 0.0
            dv = bin_vol[di-1] if di-1 >= 0 else 0.0
            if uv == 0 and dv == 0: break
            if uv >= dv and ui+1 < bins: ui += 1; va_v += uv
            elif di-1 >= 0: di -= 1; va_v += dv
            else: break
        last_vah = h_lo + (ui+1) * rng / bins
        last_val = h_lo + di * rng / bins
    return poc, vah, val


# ─── Trade Management ──────────────────────────────────────────────────────

def manage_trade_long(t, i, h, l, c):
    if l[i] <= t["sl"]:
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        pnl = (t["sl"] - t["entry_price"]) * rem + sum(
            (p["price"] - t["entry_price"]) * p["qty"] for p in t["partials"])
        return "sl", pnl
    if h[i] >= t["tp3"] and not any(p.get("tp")==3 for p in t["partials"]):
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        t["partials"].append({"tp": 3, "price": t["tp3"], "qty": rem})
        pnl = sum((p["price"] - t["entry_price"]) * p["qty"] for p in t["partials"])
        return "tp3", pnl
    if h[i] >= t["tp2"] and not any(p.get("tp")==2 for p in t["partials"]):
        t["partials"].append({"tp": 2, "price": t["tp2"], "qty": TP2_QTY})
    if h[i] >= t["tp1"] and not any(p.get("tp")==1 for p in t["partials"]):
        t["partials"].append({"tp": 1, "price": t["tp1"], "qty": TP1_QTY})
    return None, 0.0

def manage_trade_short(t, i, h, l, c):
    if h[i] >= t["sl"]:
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        pnl = (t["entry_price"] - t["sl"]) * rem + sum(
            (t["entry_price"] - p["price"]) * p["qty"] for p in t["partials"])
        return "sl", pnl
    if l[i] <= t["tp3"] and not any(p.get("tp")==3 for p in t["partials"]):
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        t["partials"].append({"tp": 3, "price": t["tp3"], "qty": rem})
        pnl = sum((t["entry_price"] - p["price"]) * p["qty"] for p in t["partials"])
        return "tp3", pnl
    if l[i] <= t["tp2"] and not any(p.get("tp")==2 for p in t["partials"]):
        t["partials"].append({"tp": 2, "price": t["tp2"], "qty": TP2_QTY})
    if l[i] <= t["tp1"] and not any(p.get("tp")==1 for p in t["partials"]):
        t["partials"].append({"tp": 1, "price": t["tp1"], "qty": TP1_QTY})
    return None, 0.0

def manage_trade_long_st(t, i, h, l, c, tp1_qty=0.50):
    if l[i] <= t["sl"]:
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        pnl = (t["sl"] - t["entry_price"]) * rem + sum(
            (p["price"] - t["entry_price"]) * p["qty"] for p in t["partials"])
        return "sl", pnl
    if h[i] >= t["tp2"] and not any(p.get("tp")==2 for p in t["partials"]):
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        t["partials"].append({"tp": 2, "price": t["tp2"], "qty": rem})
        pnl = sum((p["price"] - t["entry_price"]) * p["qty"] for p in t["partials"])
        return "tp2", pnl
    if h[i] >= t["tp1"] and not any(p.get("tp")==1 for p in t["partials"]):
        t["partials"].append({"tp": 1, "price": t["tp1"], "qty": tp1_qty})
    return None, 0.0

def manage_trade_short_st(t, i, h, l, c, tp1_qty=0.50):
    if h[i] >= t["sl"]:
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        pnl = (t["entry_price"] - t["sl"]) * rem + sum(
            (t["entry_price"] - p["price"]) * p["qty"] for p in t["partials"])
        return "sl", pnl
    if l[i] <= t["tp2"] and not any(p.get("tp")==2 for p in t["partials"]):
        rem = 1 - sum(pt["qty"] for pt in t["partials"])
        t["partials"].append({"tp": 2, "price": t["tp2"], "qty": rem})
        pnl = sum((t["entry_price"] - p["price"]) * p["qty"] for p in t["partials"])
        return "tp2", pnl
    if l[i] <= t["tp1"] and not any(p.get("tp")==1 for p in t["partials"]):
        t["partials"].append({"tp": 1, "price": t["tp1"], "qty": tp1_qty})
    return None, 0.0


# ─── 1. V1: Original Pine Script Faithful ──────────────────────────────────

def run_v1(pair, df, lb=50):
    n = len(df); dates = df.index.to_numpy()
    h,l,c,o,v = (df[x].values.astype(np.float64) for x in ["high","low","close","open","volume"])
    poc, vah, val = compute_vp(h,l,v,lb=lb,step=2)
    ema200 = pd.Series(c).ewm(span=200,adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values
    trades = []; bs=ss=0; bb=sb=0; active=None; partials=[]

    for i in range(lb, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]): continue
        bt = (c[i] > ema200[i]) if not np.isnan(ema200[i]) else True
        st = (c[i] < ema200[i]) if not np.isnan(ema200[i]) else True
        vok = v[i] >= avg_v[i]*VOL_MUL if avg_v[i]>0 else True
        body = abs(c[i]-o[i]); br = body/(h[i]-l[i]) if h[i]>l[i] else 0
        bsw = l[i]<val[i] and c[i]>val[i] and vok
        ssw = h[i]>vah[i] and c[i]<vah[i] and vok
        brj = c[i]>o[i] and br>=BODY_R and l[i]<=val[i]*1.001
        srj = c[i]<o[i] and br>=BODY_R and h[i]>=vah[i]*0.999
        prc = i>0 and c[i]>poc[i] and c[i-1]<=poc[i]
        pls = i>0 and c[i]<poc[i] and c[i-1]>=poc[i]

        if bsw and bs==0: bs=1; bb=0
        if bs==1: bb+=1
        if bs==1 and brj: bs=2; bb=0
        if bs in(1,2) and (bb>MAX_WAIT or l[i]<val[i]*(1-SL_BUF*3)): bs=0
        if ssw and ss==0: ss=1; sb=0
        if ss==1: sb+=1
        if ss==1 and srj: ss=2; sb=0
        if ss in(1,2) and (sb>MAX_WAIT or h[i]>vah[i]*(1+SL_BUF*3)): ss=0

        buy = bs==2 and prc and bt; sell = ss==2 and pls and st
        if buy: bs=0
        if sell: ss=0

        if active:
            mg = manage_trade_long(active,i,h,l,c) if active["side"]=="long" else manage_trade_short(active,i,h,l,c)
            if mg[0]:
                r = abs(active["entry_price"]-active["sl"])
                trades.append({"pair":pair,"variant":"V1-Orig","tf":"1h",
                    "entry_date":str(pd.Timestamp(active["entry_date"])),
                    "exit_date":str(pd.Timestamp(dates[i])),
                    "side":active["side"],"entry_price":round(active["entry_price"],4),
                    "sl":round(active["sl"],4), "exit_reason":mg[0],"pnl":round(mg[1],4),
                    "r_multiple":round(mg[1]/r,2) if r>0 else 0})
                active=None; partials=[]

        if active is None and buy:
            r = c[i]-val[i]*(1-SL_BUF)
            active={"side":"long","entry_date":dates[i],"entry_price":c[i],
                "sl":val[i]*(1-SL_BUF),"tp1":c[i]+r,"tp2":c[i]+r*2,"tp3":c[i]+r*3, "partials": partials}
        elif active is None and sell:
            r = vah[i]*(1+SL_BUF)-c[i]
            active={"side":"short","entry_date":dates[i],"entry_price":c[i],
                "sl":vah[i]*(1+SL_BUF),"tp1":c[i]-r,"tp2":c[i]-r*2,"tp3":c[i]-r*3, "partials": partials}

    return trades


# ─── 2. V2: ATR Adaptive ───────────────────────────────────────────────────

def run_v2(pair, df, lb=50):
    n = len(df); dates = df.index.to_numpy()
    h,l,c,o,v = (df[x].values.astype(np.float64) for x in ["high","low","close","open","volume"])
    poc, vah, val = compute_vp(h,l,v,lb=lb,step=2)
    ema200 = pd.Series(c).ewm(span=200,adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values
    tr = np.maximum(h-l, np.abs(h-np.roll(c,1)))
    tr = np.maximum(tr, np.abs(l-np.roll(c,1)))
    atr = pd.Series(tr).rolling(14).mean().values
    trades = []; bs=ss=0; bb=sb=0; active=None; partials=[]

    for i in range(lb, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]) or np.isnan(atr[i]): continue
        bt = (c[i] > ema200[i]) if not np.isnan(ema200[i]) else True
        st = (c[i] < ema200[i]) if not np.isnan(ema200[i]) else True
        vok = v[i] >= avg_v[i]*VOL_MUL if avg_v[i]>0 else True
        body = abs(c[i]-o[i]); br = body/(h[i]-l[i]) if h[i]>l[i] else 0
        bsw = l[i]<val[i] and c[i]>val[i] and vok
        ssw = h[i]>vah[i] and c[i]<vah[i] and vok
        brj = c[i]>o[i] and br>=BODY_R and l[i]<=val[i]*1.001
        srj = c[i]<o[i] and br>=BODY_R and h[i]>=vah[i]*0.999
        prc = i>0 and c[i]>poc[i] and c[i-1]<=poc[i]
        pls = i>0 and c[i]<poc[i] and c[i-1]>=poc[i]
        if bsw and bs==0: bs=1; bb=0
        if bs==1: bb+=1
        if bs==1 and brj: bs=2; bb=0
        if bs in(1,2) and (bb>MAX_WAIT or l[i]<val[i]*(1-SL_BUF*3)): bs=0
        if ssw and ss==0: ss=1; sb=0
        if ss==1: sb+=1
        if ss==1 and srj: ss=2; sb=0
        if ss in(1,2) and (sb>MAX_WAIT or h[i]>vah[i]*(1+SL_BUF*3)): ss=0
        buy = bs==2 and prc and bt; sell = ss==2 and pls and st
        if buy: bs=0
        if sell: ss=0

        if active:
            mg = manage_trade_long(active,i,h,l,c) if active["side"]=="long" else manage_trade_short(active,i,h,l,c)
            if mg[0]:
                r = abs(active["entry_price"]-active["sl"])
                trades.append({"pair":pair,"variant":"V2-ATR","tf":"1h",
                    "entry_date":str(pd.Timestamp(active["entry_date"])),
                    "exit_date":str(pd.Timestamp(dates[i])),
                    "side":active["side"],"entry_price":round(active["entry_price"],4),
                    "sl":round(active["sl"],4),"exit_reason":mg[0],"pnl":round(mg[1],4),
                    "r_multiple":round(mg[1]/r,2) if r>0 else 0})
                active=None; partials=[]

        if active is None and buy:
            atr_buf = max(atr[i]/c[i] if not np.isnan(atr[i]) else SL_BUF, SL_BUF)
            sl = val[i]*(1-atr_buf)
            r = c[i]-sl
            active={"side":"long","entry_date":dates[i],"entry_price":c[i],
                "sl":sl,"tp1":c[i]+r,"tp2":c[i]+r*2,"tp3":c[i]+r*3, "partials": partials}
        elif active is None and sell:
            atr_buf = max(atr[i]/c[i] if not np.isnan(atr[i]) else SL_BUF, SL_BUF)
            sl = vah[i]*(1+atr_buf)
            r = sl-c[i]
            active={"side":"short","entry_date":dates[i],"entry_price":c[i],
                "sl":sl,"tp1":c[i]-r,"tp2":c[i]-r*2,"tp3":c[i]-r*3, "partials": partials}

    return trades


# ─── 3. V3: EMA Stack ──────────────────────────────────────────────────────

def run_v3(pair, df, lb=50):
    n = len(df); dates = df.index.to_numpy()
    h,l,c,o,v = (df[x].values.astype(np.float64) for x in ["high","low","close","open","volume"])
    poc, vah, val = compute_vp(h,l,v,lb=lb,step=2)
    ema20 = pd.Series(c).ewm(span=20,adjust=False).mean().values
    ema50 = pd.Series(c).ewm(span=50,adjust=False).mean().values
    ema200 = pd.Series(c).ewm(span=200,adjust=False).mean().values if n>=200 else np.full(n,np.nan)
    avg_v = pd.Series(v).rolling(20).mean().values
    trades = []; bs=ss=0; bb=sb=0; active=None; partials=[]

    for i in range(lb, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]): continue
        bt = c[i]>ema20[i]>ema50[i] if not np.isnan(ema50[i]) else True
        bt = bt and (c[i]>ema200[i] if not np.isnan(ema200[i]) else True)
        st = c[i]<ema20[i]<ema50[i] if not np.isnan(ema50[i]) else True
        st = st and (c[i]<ema200[i] if not np.isnan(ema200[i]) else True)
        vok = v[i] >= avg_v[i]*VOL_MUL if avg_v[i]>0 else True
        body = abs(c[i]-o[i]); br = body/(h[i]-l[i]) if h[i]>l[i] else 0
        bsw = l[i]<val[i] and c[i]>val[i] and vok
        ssw = h[i]>vah[i] and c[i]<vah[i] and vok
        brj = c[i]>o[i] and br>=BODY_R and l[i]<=val[i]*1.001
        srj = c[i]<o[i] and br>=BODY_R and h[i]>=vah[i]*0.999
        prc = i>0 and c[i]>poc[i] and c[i-1]<=poc[i]
        pls = i>0 and c[i]<poc[i] and c[i-1]>=poc[i]
        if bsw and bs==0: bs=1; bb=0
        if bs==1: bb+=1
        if bs==1 and brj: bs=2; bb=0
        if bs in(1,2) and (bb>MAX_WAIT or l[i]<val[i]*(1-SL_BUF*3)): bs=0
        if ssw and ss==0: ss=1; sb=0
        if ss==1: sb+=1
        if ss==1 and srj: ss=2; sb=0
        if ss in(1,2) and (sb>MAX_WAIT or h[i]>vah[i]*(1+SL_BUF*3)): ss=0
        buy = bs==2 and prc and bt; sell = ss==2 and pls and st
        if buy: bs=0
        if sell: ss=0

        if active:
            mg = manage_trade_long(active,i,h,l,c) if active["side"]=="long" else manage_trade_short(active,i,h,l,c)
            if mg[0]:
                r = abs(active["entry_price"]-active["sl"])
                trades.append({"pair":pair,"variant":"V3-EMA","tf":"1h",
                    "entry_date":str(pd.Timestamp(active["entry_date"])),
                    "exit_date":str(pd.Timestamp(dates[i])),
                    "side":active["side"],"entry_price":round(active["entry_price"],4),
                    "sl":round(active["sl"],4),"exit_reason":mg[0],"pnl":round(mg[1],4),
                    "r_multiple":round(mg[1]/r,2) if r>0 else 0})
                active=None; partials=[]

        if active is None and buy:
            r = c[i]-val[i]*(1-SL_BUF)
            active={"side":"long","entry_date":dates[i],"entry_price":c[i],
                "sl":val[i]*(1-SL_BUF),"tp1":c[i]+r,"tp2":c[i]+r*2,"tp3":c[i]+r*3, "partials": partials}
        elif active is None and sell:
            r = vah[i]*(1+SL_BUF)-c[i]
            active={"side":"short","entry_date":dates[i],"entry_price":c[i],
                "sl":vah[i]*(1+SL_BUF),"tp1":c[i]-r,"tp2":c[i]-r*2,"tp3":c[i]-r*3, "partials": partials}

    return trades


# ─── 4. V4: MTF VP ─────────────────────────────────────────────────────────

def run_v4(pair, df, lb=50):
    """Simplified MTF: use 3x VP lookback for daily bias."""
    n = len(df); dates = df.index.to_numpy()
    h,l,c,o,v = (df[x].values.astype(np.float64) for x in ["high","low","close","open","volume"])
    # Fast and slow VP
    poc_f, vah_f, val_f = compute_vp(h,l,v,lb=lb,step=2)          # fast: hourly window
    poc_s, vah_s, val_s = compute_vp(h,l,v,lb=min(lb*3,n//2),step=4)  # slow: larger window
    avg_v = pd.Series(v).rolling(20).mean().values
    trades = []; bs=ss=0; bb=sb=0; active=None; partials=[]

    for i in range(lb, n):
        if np.isnan(poc_f[i]) or np.isnan(vah_s[i]) or np.isnan(val_s[i]): continue
        bt = c[i] > poc_s[i] if not np.isnan(poc_s[i]) else True
        st = c[i] < poc_s[i] if not np.isnan(poc_s[i]) else True
        vok = v[i] >= avg_v[i]*VOL_MUL if avg_v[i]>0 else True
        body = abs(c[i]-o[i]); br = body/(h[i]-l[i]) if h[i]>l[i] else 0
        bsw = l[i]<val_s[i] and c[i]>val_s[i] and vok
        ssw = h[i]>vah_s[i] and c[i]<vah_s[i] and vok
        brj = c[i]>o[i] and br>=BODY_R and l[i]<=val_f[i]*1.001
        srj = c[i]<o[i] and br>=BODY_R and h[i]>=vah_f[i]*0.999
        prc = i>0 and c[i]>poc_f[i] and c[i-1]<=poc_f[i]
        pls = i>0 and c[i]<poc_f[i] and c[i-1]>=poc_f[i]
        if bsw and bs==0: bs=1; bb=0
        if bs==1: bb+=1
        if bs==1 and brj: bs=2; bb=0
        if bs in(1,2) and (bb>MAX_WAIT or l[i]<val_s[i]*(1-SL_BUF*3)): bs=0
        if ssw and ss==0: ss=1; sb=0
        if ss==1: sb+=1
        if ss==1 and srj: ss=2; sb=0
        if ss in(1,2) and (sb>MAX_WAIT or h[i]>vah_s[i]*(1+SL_BUF*3)): ss=0
        buy = bs==2 and prc and bt; sell = ss==2 and pls and st
        if buy: bs=0
        if sell: ss=0

        if active:
            mg = manage_trade_long(active,i,h,l,c) if active["side"]=="long" else manage_trade_short(active,i,h,l,c)
            if mg[0]:
                r = abs(active["entry_price"]-active["sl"])
                trades.append({"pair":pair,"variant":"V4-MTF","tf":"1h",
                    "entry_date":str(pd.Timestamp(active["entry_date"])),
                    "exit_date":str(pd.Timestamp(dates[i])),
                    "side":active["side"],"entry_price":round(active["entry_price"],4),
                    "sl":round(active["sl"],4),"exit_reason":mg[0],"pnl":round(mg[1],4),
                    "r_multiple":round(mg[1]/r,2) if r>0 else 0})
                active=None; partials=[]

        if active is None and buy:
            r = c[i]-val_f[i]*(1-SL_BUF)
            active={"side":"long","entry_date":dates[i],"entry_price":c[i],
                "sl":val_f[i]*(1-SL_BUF),"tp1":c[i]+r,"tp2":c[i]+r*2,"tp3":c[i]+r*3, "partials": partials}
        elif active is None and sell:
            r = vah_f[i]*(1+SL_BUF)-c[i]
            active={"side":"short","entry_date":dates[i],"entry_price":c[i],
                "sl":vah_f[i]*(1+SL_BUF),"tp1":c[i]-r,"tp2":c[i]-r*2,"tp3":c[i]-r*3, "partials": partials}

    return trades


# ─── 5. V5: +Hedge Momentum ────────────────────────────────────────────────

def run_v5(pair, df, lb=50):
    n = len(df); dates = df.index.to_numpy()
    h,l,c,o,v = (df[x].values.astype(np.float64) for x in ["high","low","close","open","volume"])
    poc, vah, val = compute_vp(h,l,v,lb=lb,step=2)
    ema12 = pd.Series(c).ewm(span=12,adjust=False).mean().values
    ema26 = pd.Series(c).ewm(span=26,adjust=False).mean().values
    macd_pct = (ema12-ema26)/c*100
    delta = pd.Series(c).diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14).mean().values
    loss = -delta.clip(upper=0).ewm(alpha=1/14).mean().values
    rsi = np.full(n,50.0)
    mask = loss>0; rsi[mask] = 100-100/(1+gain[mask]/loss[mask])
    avg_v = pd.Series(v).rolling(20).mean().values
    trades = []; bs=ss=0; bb=sb=0; active=None; partials=[]

    for i in range(lb, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]): continue
        hedge = macd_pct[i]>0.8 and rsi[i]>70
        vok = v[i] >= avg_v[i]*VOL_MUL if avg_v[i]>0 else True
        body = abs(c[i]-o[i]); br = body/(h[i]-l[i]) if h[i]>l[i] else 0
        bsw = l[i]<val[i] and c[i]>val[i] and vok and hedge
        ssw = h[i]>vah[i] and c[i]<vah[i] and vok and hedge
        brj = c[i]>o[i] and br>=BODY_R and l[i]<=val[i]*1.001
        srj = c[i]<o[i] and br>=BODY_R and h[i]>=vah[i]*0.999
        prc = i>0 and c[i]>poc[i] and c[i-1]<=poc[i]
        pls = i>0 and c[i]<poc[i] and c[i-1]>=poc[i]
        if bsw and bs==0: bs=1; bb=0
        if bs==1: bb+=1
        if bs==1 and brj: bs=2; bb=0
        if bs in(1,2) and (bb>MAX_WAIT or l[i]<val[i]*(1-SL_BUF*3)): bs=0
        if ssw and ss==0: ss=1; sb=0
        if ss==1: sb+=1
        if ss==1 and srj: ss=2; sb=0
        if ss in(1,2) and (sb>MAX_WAIT or h[i]>vah[i]*(1+SL_BUF*3)): ss=0
        buy = bs==2 and prc; sell = ss==2 and pls
        if buy: bs=0
        if sell: ss=0

        if active:
            mg = manage_trade_long(active,i,h,l,c) if active["side"]=="long" else manage_trade_short(active,i,h,l,c)
            if mg[0]:
                r = abs(active["entry_price"]-active["sl"])
                trades.append({"pair":pair,"variant":"V5-Hedge","tf":"1h",
                    "entry_date":str(pd.Timestamp(active["entry_date"])),
                    "exit_date":str(pd.Timestamp(dates[i])),
                    "side":active["side"],"entry_price":round(active["entry_price"],4),
                    "sl":round(active["sl"],4),"exit_reason":mg[0],"pnl":round(mg[1],4),
                    "r_multiple":round(mg[1]/r,2) if r>0 else 0})
                active=None; partials=[]

        if active is None and buy:
            r = c[i]-val[i]*(1-SL_BUF)
            active={"side":"long","entry_date":dates[i],"entry_price":c[i],
                "sl":val[i]*(1-SL_BUF),"tp1":c[i]+r,"tp2":c[i]+r*2,"tp3":c[i]+r*3, "partials": partials}
        elif active is None and sell:
            r = vah[i]*(1+SL_BUF)-c[i]
            active={"side":"short","entry_date":dates[i],"entry_price":c[i],
                "sl":vah[i]*(1+SL_BUF),"tp1":c[i]-r,"tp2":c[i]-r*2,"tp3":c[i]-r*3, "partials": partials}

    return trades


# ─── 6. ST-V2: Short-term 5m ───────────────────────────────────────────────

def run_stv2(pair, df):
    n = len(df); dates = df.index.to_numpy()
    h,l,c,o,v = (df[x].values.astype(np.float64) for x in ["high","low","close","open","volume"])
    poc, vah, val = compute_vp(h,l,v,lb=ST_LOOKBACK,bins=ST_BINS,va_pct=ST_VA_PCT,step=ST_VP_STEP)
    ema21 = pd.Series(c).ewm(span=21,adjust=False).mean().values
    ema55 = pd.Series(c).ewm(span=55,adjust=False).mean().values
    avg_v = pd.Series(v).rolling(20).mean().values
    trades = []; bs=ss=0; bb=sb=0; active=None; partials=[]
    tf1q = ST_TP1_QTY

    for i in range(ST_LOOKBACK, n):
        if np.isnan(poc[i]) or np.isnan(vah[i]) or np.isnan(val[i]): continue
        bt = c[i]>ema21[i]>ema55[i]; st = c[i]<ema21[i]<ema55[i]
        vok = v[i] >= avg_v[i]*ST_VOL_MUL if avg_v[i]>0 else True
        body = abs(c[i]-o[i]); br = body/(h[i]-l[i]) if h[i]>l[i] else 0
        bsw = l[i]<val[i] and c[i]>val[i] and vok; ssw = h[i]>vah[i] and c[i]<vah[i] and vok
        brj = c[i]>o[i] and br>=ST_BODY_R and l[i]<=val[i]*1.001
        srj = c[i]<o[i] and br>=ST_BODY_R and h[i]>=vah[i]*0.999
        prc = i>0 and c[i]>poc[i] and c[i-1]<=poc[i]
        pls = i>0 and c[i]<poc[i] and c[i-1]>=poc[i]
        if bsw and bs==0: bs=1; bb=0
        if bs==1: bb+=1
        if bs==1 and brj: bs=2; bb=0
        if bs in(1,2) and (bb>ST_MAX_WAIT or l[i]<val[i]*(1-ST_SL_BUF*3)): bs=0
        if ssw and ss==0: ss=1; sb=0
        if ss==1: sb+=1
        if ss==1 and srj: ss=2; sb=0
        if ss in(1,2) and (sb>ST_MAX_WAIT or h[i]>vah[i]*(1+ST_SL_BUF*3)): ss=0
        buy = bs==2 and prc and bt; sell = ss==2 and pls and st
        if buy: bs=0
        if sell: ss=0

        if active:
            if active["side"]=="long":
                mg = manage_trade_long_st(active,i,h,l,c,tf1q)
            else:
                mg = manage_trade_short_st(active,i,h,l,c,tf1q)
            if mg[0]:
                r = abs(active["entry_price"]-active["sl"])
                trades.append({"pair":pair,"variant":"ST-V2","tf":"5m",
                    "entry_date":str(pd.Timestamp(active["entry_date"])),
                    "exit_date":str(pd.Timestamp(dates[i])),
                    "side":active["side"],"entry_price":round(active["entry_price"],4),
                    "sl":round(active["sl"],4),"exit_reason":mg[0],"pnl":round(mg[1],4),
                    "r_multiple":round(mg[1]/r,2) if r>0 else 0})
                active=None; partials=[]

        if active is None and buy:
            r = c[i]-val[i]*(1-ST_SL_BUF)
            active={"side":"long","entry_date":dates[i],"entry_price":c[i],
                "sl":val[i]*(1-ST_SL_BUF),"tp1":c[i]+r*ST_TP1_RR,"tp2":c[i]+r*ST_TP2_RR,
                "partials":partials}
            partials=[]
        elif active is None and sell:
            r = vah[i]*(1+ST_SL_BUF)-c[i]
            active={"side":"short","entry_date":dates[i],"entry_price":c[i],
                "sl":vah[i]*(1+ST_SL_BUF),"tp1":c[i]-r*ST_TP1_RR,"tp2":c[i]-r*ST_TP2_RR,
                "partials":partials}

    return trades


# ─── Data Loading ──────────────────────────────────────────────────────────

def load_1h(pair: str, days: int = 4) -> Optional[pd.DataFrame]:
    f = DATA_1H / f"{pair}_USDT-1h.feather"
    if not f.exists():
        f = DATA_1H / "spot" / f"{pair}_USDT-1h.feather"
    if not f.exists():
        return None
    df = pd.read_feather(f)
    df.columns = [c.lower().strip() for c in df.columns]
    if "date" in df.columns:
        df["_date"] = pd.to_datetime(df["date"]); df = df.set_index("_date")
    elif "timestamp" in df.columns:
        df["_date"] = pd.to_datetime(df["timestamp"],unit="ms",utc=True); df = df.set_index("_date")
    col_map = {"o":"open","h":"high","l":"low","c":"close","v":"volume"}
    df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
    latest = df.index.max(); cutoff = latest - pd.Timedelta(days=days)
    return df[df.index >= cutoff].copy()

def load_5m(pair: str, days: int = 4) -> Optional[pd.DataFrame]:
    f = DATA_5M / f"{pair}_USDT_USDT-5m-futures.feather"
    if not f.exists():
        return None
    df = pd.read_feather(f)
    df.columns = [c.lower().strip() for c in df.columns]
    df["_date"] = pd.to_datetime(df["date"]); df = df.set_index("_date")
    col_map = {"o":"open","h":"high","l":"low","c":"close","v":"volume"}
    df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
    latest = df.index.max(); cutoff = latest - pd.Timedelta(days=days)
    return df[df.index >= cutoff].copy()


# ─── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PAIRS_1H = ["BTC","ETH","SOL","XRP","ADA","DOGE","DOT","LINK","LTC","AVAX","NEAR","BCH","XTZ"]
    PAIRS_5M = ["BTC","ETH","SOL","XRP","ADA","DOGE","DOT","LINK","LTC","AVAX","NEAR","BCH",
                "ATOM","ARB","APT","1000PEPE","1000SHIB","AAVE","ALGO","ENA","FIL","KAS","OP","STORJ","ZEC"]

    ONEH_STRATS = [
        ("V1-Orig", run_v1, 50),
        ("V2-ATR", run_v2, 50),
        ("V3-EMA", run_v3, 50),
        ("V4-MTF", run_v4, 50),
        ("V5-Hedge", run_v5, 50),
    ]

    all_trades = []

    print("=" * 100)
    print("  ALL STRATEGIES — Last 4 Days Backtest")
    print("=" * 100)

    # 1h strategies
    print(f"\n  ── 1h Swing Strategies ──")
    for sname, sfn, lb in ONEH_STRATS:
        for pair in PAIRS_1H:
            df = load_1h(pair)
            if df is None or len(df) < lb + 10:
                continue
            trades = sfn(pair, df)
            all_trades.extend(trades)
            if trades:
                p = sum(t["pnl"] for t in trades)
                print(f"  {sname:>10} {pair:6}: {len(trades):>3} trades, P&L {p:>+10.2f}")

    # ST-V2 on 5m
    print(f"\n  ── 5m Short-Term Strategy (ST-V2) ──")
    for pair in PAIRS_5M:
        df = load_5m(pair)
        if df is None or len(df) < 50:
            continue
        trades = run_stv2(pair, df)
        all_trades.extend(trades)
        if trades:
            p = sum(t["pnl"] for t in trades)
            print(f"  {'ST-V2':>10} {pair:6}: {len(trades):>3} trades, P&L {p:>+10.2f}")

    # ─── Summary ───
    print(f"\n  {'='*70}")
    from collections import defaultdict
    by_variant = defaultdict(lambda: {"trades": 0, "pnl": 0, "wins": 0, "sl": 0, "tp": 0})

    for t in all_trades:
        v = t["variant"]
        by_variant[v]["trades"] += 1
        by_variant[v]["pnl"] += t["pnl"]
        by_variant[v]["wins"] += 1 if t["pnl"] > 0 else 0
        by_variant[v]["sl"] += 1 if t["exit_reason"] == "sl" else 0
        by_variant[v]["tp"] += 1 if "tp" in t["exit_reason"] else 0

    if all_trades:
        print(f"  {'Variant':<12} {'Trades':>7} {'Win%':>7} {'Net P&L':>12} {'AvgR':>7} {'SL':>5} {'TP':>5}")
        print(f"  {'-'*52}")
        for v in sorted(by_variant.keys()):
            d = by_variant[v]
            wr = d["wins"]/d["trades"]*100
            avg_r = d["pnl"]/d["trades"]
            print(f"  {v:<12} {d['trades']:>7} {wr:>6.1f}% {d['pnl']:>+10.2f} {avg_r:>+6.2f} {d['sl']:>5} {d['tp']:>5}")

        total_t = len(all_trades)
        total_pnl = sum(t["pnl"] for t in all_trades)
        total_wins = sum(1 for t in all_trades if t["pnl"] > 0)
        total_sl = sum(1 for t in all_trades if t["exit_reason"] == "sl")
        total_tp = sum(1 for t in all_trades if "tp" in t["exit_reason"])
        print(f"  {'-'*52}")
        print(f"  {'TOTAL':<12} {total_t:>7} {total_wins/total_t*100:>6.1f}% {total_pnl:>+10.2f} {total_pnl/total_t:>+6.2f} {total_sl:>5} {total_tp:>5}")

        # By pair
        print(f"\n  ── By Pair ──")
        by_pair = defaultdict(lambda: {"trades":0,"pnl":0,"wins":0})
        for t in all_trades:
            p = t["pair"]; by_pair[p]["trades"]+=1; by_pair[p]["pnl"]+=t["pnl"]
            by_pair[p]["wins"]+=1 if t["pnl"]>0 else 0
        print(f"  {'Pair':<8} {'Trades':>7} {'Win%':>7} {'Net P&L':>12}")
        print(f"  {'-'*36}")
        for p in sorted(by_pair.keys(), key=lambda x: by_pair[x]["pnl"], reverse=True):
            d = by_pair[p]; wr = d["wins"]/d["trades"]*100
            print(f"  {p:<8} {d['trades']:>7} {wr:>6.1f}% {d['pnl']:>+10.2f}")
    else:
        print("  No trades generated")

    # Save CSV
    csv_path = PROJECT_ROOT / "scripts" / "all_strategies_4d.csv"
    if all_trades:
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_trades[0].keys())
            w.writeheader(); w.writerows(all_trades)
        print(f"\n  CSV: {csv_path}")
    print()
