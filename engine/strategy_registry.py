"""
Strategy Registry — dynamic strategy discovery, selection, and performance tracking.

Scans user_data/strategies/ for IStrategy subclasses, maintains registry
with metadata, and supports strategy selection by market regime or performance.
"""

import importlib
import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core import StrategyInfo

STRATEGIES_DIR = Path(__file__).parent.parent / "user_data" / "strategies"
PERFORMANCE_DB = Path(__file__).parent.parent / "user_data" / "strategy_performance_db.json"


class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[str, StrategyInfo] = {}
        self._scanned = False

    def scan(self, force: bool = False):
        if self._scanned and not force:
            return
        self._strategies.clear()
        self._scan_directory(STRATEGIES_DIR)
        self._load_performance()
        self._scanned = True

    def _scan_directory(self, directory: Path):
        sys.path.insert(0, str(directory.parent))
        for fpath in sorted(directory.glob("*.py")):
            if fpath.stem.startswith("_"):
                continue
            module_name = f"user_data.strategies.{fpath.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, str(fpath))
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for name, cls in inspect.getmembers(mod, inspect.isclass):
                    if name == "IStrategy":
                        continue
                    for base in cls.__mro__:
                        if base.__name__ == "IStrategy" and base.__module__.startswith("freqtrade"):
                            info = StrategyInfo(
                                name=name,
                                module_path=str(fpath),
                                description=(cls.__doc__ or "").strip()[:200],
                                timeframe=getattr(cls, "timeframe", "1h"),
                                can_short=getattr(cls, "can_short", False),
                                is_active=fpath.stem in {"AroonMomentumEngine_Hybrid"},
                            )
                            self._strategies[name] = info
                            break
            except Exception:
                continue

    def _load_performance(self):
        if not PERFORMANCE_DB.exists():
            return
        try:
            data = json.loads(PERFORMANCE_DB.read_text())
            for name, perf in data.items():
                if name in self._strategies:
                    self._strategies[name].trades = perf.get("trades", 0)
                    self._strategies[name].win_rate = perf.get("win_rate", 0.0)
                    self._strategies[name].total_pnl = perf.get("total_pnl", 0.0)
        except (json.JSONDecodeError, OSError):
            pass

    def save_performance(self):
        data = {}
        for name, info in self._strategies.items():
            data[name] = {
                "trades": info.trades,
                "win_rate": info.win_rate,
                "total_pnl": info.total_pnl,
                "is_active": info.is_active,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        PERFORMANCE_DB.parent.mkdir(parents=True, exist_ok=True)
        PERFORMANCE_DB.write_text(json.dumps(data, indent=2))

    def list_strategies(self, active_only: bool = False) -> list[StrategyInfo]:
        self.scan()
        strategies = list(self._strategies.values())
        if active_only:
            strategies = [s for s in strategies if s.is_active]
        return sorted(strategies, key=lambda s: s.name)

    def get(self, name: str) -> Optional[StrategyInfo]:
        self.scan()
        return self._strategies.get(name)

    def set_active(self, name: str, active: bool = True):
        self.scan()
        if name in self._strategies:
            self._strategies[name].is_active = active
            self.save_performance()

    def update_performance(self, name: str, won: bool, pnl: float):
        self.scan()
        if name not in self._strategies:
            return
        info = self._strategies[name]
        info.trades += 1
        info.total_pnl += pnl
        if won:
            info.win_rate = ((info.win_rate * (info.trades - 1)) + 1) / info.trades
        else:
            info.win_rate = ((info.win_rate * (info.trades - 1)) + 0) / info.trades
        self.save_performance()

    def select_by_regime(self, regime: str) -> list[StrategyInfo]:
        self.scan()
        regime_map = {
            "trending": ["EmaTrendFollowing", "AroonMomentumEngine_Hybrid", "SupertrendEmaStrategy"],
            "ranging": ["BollingerMeanReversion", "MacdRsiStrategy", "VectorOmni_MeanRevEV"],
            "volatile": ["VectorOmni_ATRBoost", "VectorOmni_LiquidTrap", "RsiDivergenceStrategy"],
            "reversal": ["RsiDivergenceStrategy", "VectorOmni_FVG_OB_v2", "DmiAdxStrategy"],
        }
        candidates = regime_map.get(regime, [])
        return [self._strategies[n] for n in candidates if n in self._strategies]
