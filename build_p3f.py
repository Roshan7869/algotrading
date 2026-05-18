#!/usr/bin/env python3
"""Build P3F combo strategy: P3E (key level boost) + P3B (tighter trail)."""
BASE_PATH = "user_data/strategies/VectorStrategy.py"

with open(BASE_PATH) as f:
    base = f.read()

p3f = base.replace(
    '"""ChromaDB Vector Strategy Backtest',
    '"""ChromaDB Vector Strategy — P3F: Key Level Boost + Tighter Trail\n'
    '===============================================================\n'
    'P2 baseline + P3E key level confluence boost + P3B tighter trailing.\n\n'
    'Enhancement:\n'
    '  - Key Level Boost: +1 confluence when dist_to_support < 0.5 (longs)\n'
    '    or dist_to_resistance < 0.5 (shorts) — ChromaDB score 0.612\n'
    '  - Tighter trail activation: trailing_stop_positive_offset 0.03 (was 0.04)\n'
    '    "Risk to Zero ASAP" concept from ChromaDB\n'
    '  - Combines the two best independent P3 variants\n\n'
    'ChromaDB Vector Strategy Backtest'
)

p3f = p3f.replace(
    'class VectorStrategy(IStrategy):',
    'class VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL(IStrategy):'
)

# Tighter trail
p3f = p3f.replace(
    '    trailing_stop_positive_offset = 0.04',
    '    trailing_stop_positive_offset = 0.03'
)

# Key level boost for longs
p3f = p3f.replace(
    '        long_signals = [\n'
    '            squeeze_breakout_long.astype(int),\n'
    '            mean_reversion_long.astype(int),\n'
    '            ema_alignment_long.astype(int),\n'
    '            expansion_long.astype(int),\n'
    '            key_level_long.astype(int),\n'
    '        ]\n'
    '        long_score = sum(long_signals)',
    '        # Key Level Boost: proximity to pivot support adds +1 confluence\n'
    '        key_level_boost_long = (dataframe["dist_to_support"] < 0.5).astype(int)\n'
    '        long_signals = [\n'
    '            squeeze_breakout_long.astype(int),\n'
    '            mean_reversion_long.astype(int),\n'
    '            ema_alignment_long.astype(int),\n'
    '            expansion_long.astype(int),\n'
    '            key_level_long.astype(int),\n'
    '        ]\n'
    '        long_score = sum(long_signals) + key_level_boost_long'
)

# Key level boost for shorts
p3f = p3f.replace(
    '        short_signals = [\n'
    '            squeeze_breakout_short.astype(int),\n'
    '            mean_reversion_short.astype(int),\n'
    '            ema_alignment_short.astype(int),\n'
    '            expansion_short.astype(int),\n'
    '            key_level_short.astype(int),\n'
    '        ]\n'
    '        short_score = sum(short_signals)',
    '        # Key Level Boost: proximity to pivot resistance adds +1 confluence\n'
    '        key_level_boost_short = (dataframe["dist_to_resistance"] < 0.5).astype(int)\n'
    '        short_signals = [\n'
    '            squeeze_breakout_short.astype(int),\n'
    '            mean_reversion_short.astype(int),\n'
    '            ema_alignment_short.astype(int),\n'
    '            expansion_short.astype(int),\n'
    '            key_level_short.astype(int),\n'
    '        ]\n'
    '        short_score = sum(short_signals) + key_level_boost_short'
)

with open('user_data/strategies/VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL.py', 'w') as f:
    f.write(p3f)
print(f"P3F written: {len(p3f)} chars, {p3f.count(chr(10))} lines")