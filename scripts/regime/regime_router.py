#!/usr/bin/env python3
"""
regime_router.py — Maps detected market regime to the optimal strategy.

Reads market_regime.json (from hmm_regime.py), consults regime_config.json
for the strategy assignment, and updates Freqtrade config dynamically.

Usage:
  python3 scripts/regime/regime_router.py                          # Show current mapping
  python3 scripts/regime/regime_router.py --apply                  # Apply to config
  python3 scripts/regime/regime_router.py --map trending_up EmaTrendFollowing  # Set mapping
"""

import argparse
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SHARED_DIR = BASE_DIR / "shared_config"
REGIME_PATH = SHARED_DIR / "market_regime.json"
CONFIG_PATH = SHARED_DIR / "regime_config.json"
FREQTRADE_CONFIG = BASE_DIR / "user_data" / "config_base.json"

DEFAULT_MAP = {
    "trending_up": "EmaTrendFollowing",
    "trending_down": "DmiAdxStrategy",
    "ranging": "BollingerMeanReversion",
    "volatile": "EnsembleStrategy",
    "unknown": "AroonMomentumEngine_Hybrid",
}


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(config: dict):
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


def load_regime() -> str:
    if REGIME_PATH.exists():
        data = json.loads(REGIME_PATH.read_text())
        return data.get("regime", "unknown")
    return "unknown"


def cmd_show():
    config = load_config()
    regime = load_regime()
    print(f"Current regime: {regime}")
    print(f"\nRegime → Strategy mapping:")
    mapping = {**DEFAULT_MAP, **config.get("mapping", {})}
    for r, s in mapping.items():
        active = " << ACTIVE" if r == regime else ""
        print(f"  {r:20s} → {s}{active}")


def cmd_apply():
    config = load_config()
    regime = load_regime()
    mapping = {**DEFAULT_MAP, **config.get("mapping", {})}
    strategy = mapping.get(regime, DEFAULT_MAP["unknown"])

    if not FREQTRADE_CONFIG.exists():
        print(f"[router] Freqtrade config not found at {FREQTRADE_CONFIG}")
        return

    ft_config = json.loads(FREQTRADE_CONFIG.read_text())
    ft_config["strategy"] = strategy
    FREQTRADE_CONFIG.write_text(json.dumps(ft_config, indent=2))
    print(f"[router] Applied: regime='{regime}' → strategy='{strategy}'")


def cmd_map(regime: str, strategy: str):
    config = load_config()
    if "mapping" not in config:
        config["mapping"] = {}
    config["mapping"][regime] = strategy
    save_config(config)
    print(f"[router] Set: '{regime}' → '{strategy}'")


def main():
    parser = argparse.ArgumentParser(description="Regime-aware strategy router")
    parser.add_argument("--apply", action="store_true", help="Apply mapping to Freqtrade config")
    parser.add_argument("--map", nargs=2, metavar=("REGIME", "STRATEGY"), help="Set regime → strategy mapping")
    args = parser.parse_args()

    if args.apply:
        cmd_apply()
    elif args.map:
        cmd_map(args.map[0], args.map[1])
    else:
        cmd_show()


if __name__ == "__main__":
    main()
