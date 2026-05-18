#!/usr/bin/env python3
"""Build P3D_FORCED strategy with kill_zone_only default=True (hardcoded)."""
BASE_PATH = "user_data/strategies/VectorStrategy_P3D_KILL_ZONE_FILTER.py"

with open(BASE_PATH) as f:
    base = f.read()

# Change the default from False to True
p3d_forced = base.replace(
    'P2 baseline + Kill Zone session filtering on entries.',
    'P2 baseline + Kill Zone session filtering on entries (kill_zone_only FORCED True).'
)
p3d_forced = p3d_forced.replace(
    'kill_zone_only = BooleanParameter(default=False,',
    'kill_zone_only = BooleanParameter(default=True,'
)
p3d_forced = p3d_forced.replace(
    'class VectorStrategy_P3D_KILL_ZONE_FILTER(IStrategy):',
    'class VectorStrategy_P3D_KILL_ZONE_FORCED(IStrategy):'
)

with open('user_data/strategies/VectorStrategy_P3D_KILL_ZONE_FORCED.py', 'w') as f:
    f.write(p3d_forced)
print(f"P3D_FORCED written: {len(p3d_forced)} chars, {p3d_forced.count(chr(10))} lines")