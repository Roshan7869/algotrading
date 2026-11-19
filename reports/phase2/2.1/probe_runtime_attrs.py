"""Phase 2.1 — what freqtrade actually resolves for the two candidates.

The strategy *file* is not the runtime truth: a config-level `stoploss` overrides the class
attribute (freqtrade/resolvers/strategy_resolver.py `_override_attribute_helper`, prevalence
"Configuration > Strategy > default"), and `use_custom_stoploss` defaults to False
(freqtrade/strategy/interface.py:85) so `custom_stoploss()` is never called unless the class
declares the flag.

Usage: .venv/Scripts/python.exe reports/phase2/2.1/probe_runtime_attrs.py
"""
from __future__ import annotations

import logging

logging.getLogger("freqtrade").setLevel(logging.WARNING)

from freqtrade.configuration import Configuration  # noqa: E402
from freqtrade.resolvers import StrategyResolver  # noqa: E402

for name in ("SupertrendEmaStrategy", "BollingerMeanReversion"):
    cfg = Configuration.from_files(["user_data/config_backtest.json"])
    cfg["strategy"] = name
    s = StrategyResolver.load_strategy(cfg)
    lev = s.leverage("BTC/USDT:USDT", None, 100.0, 6.0, 75.0, None, "long")
    print(f"{name}")
    print(f"  use_custom_stoploss      = {s.use_custom_stoploss}"
          f"   -> custom_stoploss() is {'CALLED' if s.use_custom_stoploss else 'NEVER CALLED'}")
    print(f"  stoploss (effective)     = {s.stoploss}"
          f"   -> price stop at {lev}x = {abs(s.stoploss) / lev:.4%}")
    print(f"  trailing_stop            = {s.trailing_stop}")
    print(f"  trailing_stop_positive   = {s.trailing_stop_positive}  (ratio, divided by leverage"
          f" -> {s.trailing_stop_positive / lev:.4%} price)")
    print(f"  trailing_stop_offset     = {s.trailing_stop_positive_offset}  (compared to"
          f" current_profit, which calc_profit_ratio() multiplies by leverage)")
    print(f"  minimal_roi              = {s.minimal_roi}  (equity ROI -> /{lev} in price terms)")
    print(f"  leverage()               = {lev}")
    print()
