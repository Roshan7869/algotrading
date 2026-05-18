#!/usr/bin/env python3
"""Extract ALL 300d GODMODE backtest results from zip files - FIXED."""
import json, zipfile, glob, os

os.chdir('/home/roshan/Downloads/Algotrading/user_data/backtest_results')
results = {}

for meta in sorted(glob.glob('backtest-result-2026-05-16_1[5-6]*.meta.json')):
    d = json.load(open(meta))
    strat = list(d.keys())[0]
    ts = meta.replace('backtest-result-','').replace('.meta.json','')
    zpath = meta.replace('.meta.json','.zip')
    
    # Only keep latest per strategy  
    if strat not in results or ts > results[strat]['ts']:
        try:
            with zipfile.ZipFile(zpath) as zf:
                for name in zf.namelist():
                    if name.endswith('.json') and 'meta' not in name:
                        data = json.loads(zf.read(name))
                        if 'strategy' in data:
                            for sname, sdata in data['strategy'].items():
                                trades = sdata.get('total_trades', 0)
                                wins = sdata.get('wins', 0)
                                wr = (wins / trades * 100) if trades > 0 else 0
                                results[strat] = {
                                    'ts': ts,
                                    'trades': trades,
                                    'profit_pct': round(sdata.get('profit_total', 0) * 100, 2),
                                    'profit_abs': round(sdata.get('profit_total_abs', 0), 2),
                                    'win_rate': round(wr, 1),
                                    'drawdown_pct': round(abs(sdata.get('max_drawdown_account', 0)) * 100, 2),
                                    'sharpe': round(sdata.get('sharpe', 0), 2),
                                    'sortino': round(sdata.get('sortino', 0), 2),
                                    'calmar': round(sdata.get('calmar', 0), 2),
                                    'profit_factor': round(sdata.get('profit_factor', 0), 2),
                                    'long_trades': sdata.get('trade_count_long', 0),
                                    'short_trades': sdata.get('trade_count_short', 0),
                                    'max_consec_wins': sdata.get('max_consecutive_wins', 0),
                                }
        except Exception as e:
            results[strat] = {'ts': ts, 'trades': 0, 'profit_pct': 0, 'error': str(e)}

# Filter only 300d timerange results (backtest_start_ts after July 2025)
ranked = sorted(results.items(), key=lambda x: x[1].get('profit_pct', 0), reverse=True)

hdr = "{:40s} {:>6} {:>9} {:>6} {:>7} {:>7} {:>7} {:>7}".format(
    'Strategy', 'Trades', 'Profit%', 'WR%', 'DD%acc', 'Sharpe', 'Sortino', 'PF')
print(hdr)
print('-' * len(hdr))

for s, r in ranked:
    if 'error' in r:
        print("{:40s} ERROR: {}".format(s, r['error'][:50]))
        continue
    line = "{:40s} {:>6} {:>+9.1f} {:>6.1f} {:>7.2f} {:>7.2f} {:>7.2f} {:>7.2f}".format(
        s[:40], r.get('trades',0), r.get('profit_pct',0), r.get('win_rate',0),
        r.get('drawdown_pct',0), r.get('sharpe',0), r.get('sortino',0), r.get('profit_factor',0))
    print(line)

print("\nTotal strategies: {}".format(len(ranked)))

# Save
with open('/home/roshan/Downloads/Algotrading/godmode_300d_results_summary.json', 'w') as f:
    json.dump(dict(ranked), f, indent=2)