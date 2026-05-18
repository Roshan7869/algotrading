#!/usr/bin/env python3
"""Sample ChromaDB document content for variety analysis."""
import sys
sys.path.insert(0, "strategy_db")
from search import _get_collection
from collections import defaultdict

col = _get_collection()
results = col.get(include=["metadatas", "documents"])

by_type = defaultdict(list)
for doc, meta in zip(results["documents"], results["metadatas"]):
    by_type[meta.get("setup_type", "?")].append((doc, meta))

print("=== SAMPLE DOCUMENT CONTENT (1 per type) ===")
sep = "=" * 70
for st in ["entry", "filter", "confirmation", "market_structure", "risk_management", "psychology", "trade_management", "exit"]:
    if st not in by_type:
        continue
    items = by_type[st]
    # Pick the most keyword-rich one
    best = max(items, key=lambda x: len(x[1].get("keywords", "")))
    meta = best[1]
    doc = best[0]
    print(f"\n{sep}")
    print(f"TYPE: {st} | NAME: {meta.get('setup_name', '?')}")
    print(f"KEYWORDS: {meta.get('keywords', '?')[:120]}")
    print(f"MARKET: {meta.get('market_condition', '?')} | STYLE: {meta.get('strategy_style', '?')}")
    print(f"CONTENT (first 600 chars):")
    print(doc[:600])
    print("...")

# Also: what unique strategy "concepts" span multiple types?
print(f"\n\n{'='*70}")
print("=== CROSS-TYPE CONCEPT FAMILIES ===")
print("=" * 70)

# Group by common keyword prefixes
concept_families = {
    "ICT/SMT Concepts": ["ICT", "smart_money", "order_block", "breaker_block", "fair_value_gap", "FVG", "liquidity_sweep", "optimal_trade_entry", "OTE", "kill_zone", "PO3", "power_of_3", "AMD"],
    "Mean Reversion": ["mean_reversion", "right_side_of_V", "equilibrium", "reversion", "snapback"],
    "Volume/OrderFlow": ["absorption", "order_flow", "volume_profile", "CVD", "delta", "footprint", "LVN", "point_of_control", "value_area"],
    "Fibonacci": ["fibonacci", "382", "0.5", "61.8", "78.6", "retracement", "extension"],
    "Candlestick Patterns": ["engulfing", "hammer", "doji", "shooting_star", "candlestick", "close_above", "close_below"],
    "Moving Averages": ["20MA", "50MA", "200MA", "EMA", "moving_average", "dual_MA", "triple_MA"],
    "RSI/Momentum": ["RSI", "divergence", "overbought", "oversold", "momentum"],
    "Bollinger Bands": ["bollinger_band", "squeeze", "compression", "expansion"],
    "Risk/Reward": ["risk_reward", "R_multiple", "1.75R", "break_even", "stop_loss", "position_sizing"],
    "Crypto Macro": ["Bitcoin", "ETH", "Solana", "debasement", "institutional_adoption", "store_of_value"],
    "Market Structure": ["higher_highs", "lower_lows", "swing_high", "swing_low", "break_of_structure", "MSS"],
    "Psychology/Mindset": ["psychology", "discipline", "FOMO", "journaling", "patience", "emotional_control"],
    "Session/Time": ["kill_zone", "London_open", "NY_session", "first_hour", "5PM_EST", "session_filter"],
}

col_obj = _get_collection()
all_results = col_obj.get(include=["metadatas"])
for family_name, family_kws in concept_families.items():
    count = 0
    matching_setups = set()
    for meta in all_results["metadatas"]:
        kws = meta.get("keywords", "")
        for kw in family_kws:
            if kw.lower() in kws.lower():
                count += 1
                matching_setups.add(meta.get("setup_name", "?"))
                break
    print(f"\n  {family_name}: {count} chunks, {len(matching_setups)} unique setups")
    for s in sorted(list(matching_setups))[:8]:
        print(f"    - {s[:65]}")
    if len(matching_setups) > 8:
        print(f"    ... +{len(matching_setups)-8} more")