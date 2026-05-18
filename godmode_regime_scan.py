#!/usr/bin/env python3
"""GODMODE: Run HMM regime detection on all 30 downloaded pairs."""
import pandas as pd
import os
import glob
import sys

sys.path.insert(0, '/home/roshan/Downloads/Algotrading')
from strategy_db.regime_detector_hmm import HMMRegimeDetector

base = '/home/roshan/Downloads/Algotrading/user_data/data/binance/futures/'
pairs = sorted(glob.glob(base + '*_USDT_USDT-1h-futures.feather'))

regime_map = {'trending_down': 0, 'trending_up': 0, 'ranging': 0, 'volatile': 0}
results = []

for pf in pairs:
    pair = os.path.basename(pf).split('_USDT_USDT')[0]
    try:
        df = pd.read_feather(pf)
        df = df.tail(100)
        det = HMMRegimeDetector()
        result = det.predict(df)
        # predict() returns (label, dict)
        if isinstance(result, tuple):
            label, data = result
            probs = data.get('regime_probs', {})
        elif isinstance(result, dict):
            label = result.get('regime', 'unknown')
            probs = result.get('regime_probs', {})
        else:
            label = str(result)
            probs = {}
        
        top_prob = max(probs.values()) if probs else 0.0
        regime_map[label] = regime_map.get(label, 0) + 1
        results.append((pair, label, float(top_prob)))
    except Exception as e:
        results.append((pair, 'error', 0.0))

print(f"{'PAIR':12s} {'REGIME':15s} {'CONF':>8s}")
print("-" * 37)
for pair, regime, conf in results:
    print(f"{pair:12s} {regime:15s} {conf:>8.4f}")

print()
print("=== REGIME DISTRIBUTION ===")
for regime, count in sorted(regime_map.items(), key=lambda x: -x[1]):
    pct = count / len(results) * 100
    print(f"  {regime:15s} {count:3d} pairs ({pct:.0f}%)")