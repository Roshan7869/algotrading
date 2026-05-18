#!/usr/bin/env python3
"""Build P3E_HYPEROPT variant with key_level_threshold as DecimalParameter."""
BASE_PATH = "user_data/strategies/VectorStrategy_P3E_KEY_LEVEL_BOOST.py"

with open(BASE_PATH) as f:
    base = f.read()

p3e_hyp = base.replace(
    'class VectorStrategy_P3E_KEY_LEVEL_BOOST(IStrategy):',
    'class VectorStrategy_P3E_HYPEROPT(IStrategy):'
)
p3e_hyp = p3e_hyp.replace(
    '"""ChromaDB Vector Strategy — P3E: Key Level Confluence Boost',
    '"""ChromaDB Vector Strategy — P3E Hyperopt: Key Level Confluence Boost\n'
    '=============================================================\n'
    'Same as P3E but with key_level_threshold as DecimalParameter for hyperopt.'
)
# Add the parameter after existing params
p3e_hyp = p3e_hyp.replace(
    '    min_confluence = IntParameter(1, 3, default=2, space="buy", optimize=True, load=True)',
    '    min_confluence = IntParameter(1, 3, default=2, space="buy", optimize=True, load=True)\n'
    '    key_level_threshold = DecimalParameter(0.1, 1.0, default=0.5, decimals=2, space="buy", optimize=True, load=True)'
)
# Replace hardcoded 0.5 with the parameter for longs
p3e_hyp = p3e_hyp.replace(
    'key_level_boost_long = (dataframe["dist_to_support"] < 0.5).astype(int)',
    'key_level_boost_long = (dataframe["dist_to_support"] < self.key_level_threshold.value).astype(int)'
)
# Replace hardcoded 0.5 with the parameter for shorts
p3e_hyp = p3e_hyp.replace(
    'key_level_boost_short = (dataframe["dist_to_resistance"] < 0.5).astype(int)',
    'key_level_boost_short = (dataframe["dist_to_resistance"] < self.key_level_threshold.value).astype(int)'
)

with open('user_data/strategies/VectorStrategy_P3E_HYPEROPT.py', 'w') as f:
    f.write(p3e_hyp)
print(f"P3E_HYPEROPT written: {len(p3e_hyp)} chars, {p3e_hyp.count(chr(10))} lines")