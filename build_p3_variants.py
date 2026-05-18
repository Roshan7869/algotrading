#!/usr/bin/env python3
"""Build P3D and P3E variant strategies from P2★ base."""
import sys

BASE_PATH = "user_data/strategies/VectorStrategy.py"

with open(BASE_PATH) as f:
    base = f.read()

# ═══════════════════════════════════════════════════════════════
# P3D: Kill Zone Session Filter
# ═══════════════════════════════════════════════════════════════
p3d = base.replace(
    '"""ChromaDB Vector Strategy Backtest',
    '"""ChromaDB Vector Strategy — P3D: Kill Zone Session Filter\n'
    '========================================================\n'
    'P2 baseline + Kill Zone session filtering on entries.\n\n'
    'Enhancement:\n'
    '  - Crypto kill zones: London 07:00-09:00 UTC, NY 13:30-16:00 UTC\n'
    '  - Filter: allow entries only during kill zones OR when confluence >= 3\n'
    '  - kill_zone_only BooleanParameter for hyperopt testing\n'
    '  - ChromaDB Kill Zones score 0.591 for trending_down regime\n\n'
    'All other logic identical to P2 champion config.\n\n'
    'ChromaDB Vector Strategy Backtest'
)

p3d = p3d.replace(
    'class VectorStrategy(IStrategy):',
    'class VectorStrategy_P3D_KILL_ZONE_FILTER(IStrategy):'
)

p3d = p3d.replace(
    '    min_confluence = IntParameter(1, 3, default=2, space="buy", optimize=True, load=True)',
    '    min_confluence = IntParameter(1, 3, default=2, space="buy", optimize=True, load=True)\n'
    '    kill_zone_only = BooleanParameter(default=False, space="buy", optimize=True, load=True)'
)

# Add _is_kill_zone method before populate_entry_trend
kill_zone_method = '''
    # ── Kill Zone Session Filter ──────────────────────────────────
    def _is_kill_zone(self, dataframe: DataFrame) -> pd.Series:
        """Crypto kill zones: London 07-09 UTC, NY 13:30-16:00 UTC.
        Allow entries during kill zones OR when confluence is high (>=3)."""
        hours = dataframe["date"].dt.hour if "date" in dataframe.columns else pd.Series(dataframe.index.hour, index=dataframe.index)
        minutes = dataframe["date"].dt.minute if "date" in dataframe.columns else pd.Series(dataframe.index.minute, index=dataframe.index)
        london = (hours >= 7) & (hours < 9)
        ny_session = ((hours == 13) & (minutes >= 30)) | ((hours >= 14) & (hours < 16))
        return london | ny_session

'''

p3d = p3d.replace(
    '    # ── Populate Entry Trend ───────────────────────────────────────\n'
    '    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:',
    kill_zone_method +
    '    # ── Populate Entry Trend ───────────────────────────────────────\n'
    '    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:'
)

# Modify long entry to add kill zone filter
p3d = p3d.replace(
    '        dataframe.loc[\n'
    '            (long_score >= self.min_confluence.value) & (dataframe["volume"] > 0),\n'
    '            ["enter_long", "enter_tag"]\n'
    '        ] = (1, "vector_long")',
    '        # Kill zone filter: if kill_zone_only, require kill zone OR high confluence\n'
    '        long_kill_ok = ~self.kill_zone_only.value | self._is_kill_zone(dataframe) | (long_score >= 3)\n'
    '        dataframe.loc[\n'
    '            (long_score >= self.min_confluence.value) & (long_kill_ok) & (dataframe["volume"] > 0),\n'
    '            ["enter_long", "enter_tag"]\n'
    '        ] = (1, "vector_long")'
)

# Modify short entry similarly
p3d = p3d.replace(
    '        dataframe.loc[\n'
    '            (short_score >= self.min_confluence.value) & (dataframe["volume"] > 0),\n'
    '            ["enter_short", "enter_tag"]\n'
    '        ] = (1, "vector_short")',
    '        short_kill_ok = ~self.kill_zone_only.value | self._is_kill_zone(dataframe) | (short_score >= 3)\n'
    '        dataframe.loc[\n'
    '            (short_score >= self.min_confluence.value) & (short_kill_ok) & (dataframe["volume"] > 0),\n'
    '            ["enter_short", "enter_tag"]\n'
    '        ] = (1, "vector_short")'
)

with open('user_data/strategies/VectorStrategy_P3D_KILL_ZONE_FILTER.py', 'w') as f:
    f.write(p3d)
print(f"P3D written: {len(p3d)} chars, {p3d.count(chr(10))} lines")

# ═══════════════════════════════════════════════════════════════
# P3E: Key Level Confluence Boost
# ═══════════════════════════════════════════════════════════════
p3e = base.replace(
    '"""ChromaDB Vector Strategy Backtest',
    '"""ChromaDB Vector Strategy — P3E: Key Level Confluence Boost\n'
    '==========================================================\n'
    'P2 baseline + key level proximity confluence boost.\n\n'
    'Enhancement:\n'
    '  - When dist_to_support < 0.5 for longs: confluence_score += 1\n'
    '  - When dist_to_resistance < 0.5 for shorts: confluence_score += 1\n'
    '  - ChromaDB 200 MA + Structure Confluence — entries at key levels stack probability\n'
    '  - Key levels provide institutional entry zones that stack with other signals\n\n'
    'All other logic identical to P2 champion config.\n\n'
    'ChromaDB Vector Strategy Backtest'
)

p3e = p3e.replace(
    'class VectorStrategy(IStrategy):',
    'class VectorStrategy_P3E_KEY_LEVEL_BOOST(IStrategy):'
)

# Add key level boost to long scoring
p3e = p3e.replace(
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

# Add key level boost to short scoring
p3e = p3e.replace(
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

with open('user_data/strategies/VectorStrategy_P3E_KEY_LEVEL_BOOST.py', 'w') as f:
    f.write(p3e)
print(f"P3E written: {len(p3e)} chars, {p3e.count(chr(10))} lines")