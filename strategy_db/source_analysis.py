#!/usr/bin/env python3
"""Analyze the JSON source file and strategy directory."""
import json, os

# Fabio chunks
with open('fabio_valentino_scalping_chunks.json') as f:
    fabio = json.load(f)
print(f'=== FABIO VALENTINO SCALPING CHUNKS ===')
print(f'Total chunks: {len(fabio)}')
setup_types = sorted(set(c.get("setup_type", "?") for c in fabio))
print(f'Setup types: {setup_types}')
market_conditions = sorted(set(c.get("market_condition", "?") for c in fabio))
print(f'Market conditions: {market_conditions}')
strategy_styles = sorted(set(c.get("strategy_style", "?") for c in fabio))
print(f'Strategy styles: {strategy_styles}')
print()
print('CHUNK LIST:')
for c in fabio:
    tn = c.get("setup_type", "?")
    sn = c.get("setup_name", "?")[:60]
    mc = c.get("market_condition", "?")
    print(f'  [{tn:20s}] {sn:60s} | mkt={mc}')

# Strategy dir
strategy_dir = 'strategy'
if os.path.exists(strategy_dir):
    files = os.listdir(strategy_dir)
    md_files = [f for f in files if f.endswith('.md')]
    txt_files = [f for f in files if f.endswith('.txt')]
    json_files = [f for f in files if f.endswith('.json')]
    print(f'\n=== STRATEGY DIR ===')
    print(f'MD files: {len(md_files)}')
    print(f'TXT files: {len(txt_files)}')
    print(f'JSON files: {len(json_files)}')
    for f in sorted(md_files):
        p = os.path.join(strategy_dir, f)
        sz = os.path.getsize(p)
        print(f'  MD: {f} ({sz:,} bytes)')
    for f in sorted(txt_files):
        p = os.path.join(strategy_dir, f)
        sz = os.path.getsize(p)
        print(f'  TXT: {f} ({sz:,} bytes)')
    for f in sorted(json_files):
        p = os.path.join(strategy_dir, f)
        sz = os.path.getsize(p)
        print(f'  JSON: {f} ({sz:,} bytes)')

# Count unique setup_names in ChromaDB
import sys
sys.path.insert(0, 'strategy_db')
from search import _get_collection
col = _get_collection()
results = col.get(include=['metadatas'])
unique_names = set()
for meta in results['metadatas']:
    unique_names.add(meta.get('setup_name', '?'))
print(f'\n=== CHROMADB TOTAL ===')
print(f'Total chunks: {len(results["ids"])}')
print(f'Unique setup names: {len(unique_names)}')

# Count chunks from fabio source specifically
fabio_chunks = [m for m in results['metadatas'] if m.get('source_name', '') != 'unknown']
non_fabio = [m for m in results['metadatas'] if m.get('source_name', '') == 'unknown']
print(f'Fabio-sourced chunks: {len(fabio_chunks)}')
print(f'Non-Fabio (unknown source) chunks: {len(non_fabio)}')