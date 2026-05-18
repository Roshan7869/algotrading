#!/usr/bin/env python3
"""Build unified P3 configs for fair comparison and new variant tests."""
import json
from pathlib import Path

BASE = "/home/roshan/Downloads/Algotrading/user_data"

# Use the P2★ original 17 curated pairs (the actual P2 champion pairs)
P2_PAIRS = [
    "NEAR/USDT:USDT", "VET/USDT:USDT", "ENA/USDT:USDT", "ONDO/USDT:USDT",
    "DOT/USDT:USDT", "LINK/USDT:USDT", "WLD/USDT:USDT", "ARB/USDT:USDT",
    "AVAX/USDT:USDT", "1000SHIB/USDT:USDT", "OP/USDT:USDT", "KAS/USDT:USDT",
    "SUI/USDT:USDT", "DOGE/USDT:USDT", "ALGO/USDT:USDT", "TRX/USDT:USDT",
    "XLM/USDT:USDT"
]

BLACKLIST = ["AAVE/USDT:USDT", "HBAR/USDT:USDT", "XMR/USDT:USDT", "XTZ/USDT:USDT",
             "ZEC/USDT:USDT", "1000PEPE/USDT:USDT", "SOL/USDT:USDT", "BCH/USDT:USDT",
             "RENDER/USDT:USDT"]

def make_config(strategy, name, max_open=7, balance_ratio=0.7, extra_params=None):
    config = {
        "strategy": strategy,
        "trading_mode": "futures",
        "margin_mode": "isolated",
        "max_open_trades": max_open,
        "stake_currency": "USDT",
        "stake_amount": "unlimited",
        "tradable_balance_ratio": balance_ratio,
        "dry_run_wallet": 1000,
        "timeframe": "1h",
        "exchange": {
            "name": "binance",
            "key": "",
            "secret": "",
            "ccxt_config": {"enableRateLimit": True},
            "ccxt_async_config": {"enableRateLimit": True},
            "pair_whitelist": P2_PAIRS,
            "pair_blacklist": BLACKLIST
        },
        "entry_pricing": {"price_side": "same", "use_order_book": True, "order_book_top": 1},
        "exit_pricing": {"price_side": "other", "use_order_book": True, "order_book_top": 1},
        "pairlists": [{"method": "StaticPairList"}],
        "leverage": 3
    }
    if extra_params:
        config.update(extra_params)
    path = f"{BASE}/config_backtest_{name}.json"
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"  Written: config_backtest_{name}.json -> {strategy}")
    return path

print("=== Building Unified P3 Configs (P2★ pairs, max_open=7, balance=0.7) ===\n")

# 1. P2 baseline re-validation (same pairs, same config as original champion)
print("[1] P2 baseline re-validation")
make_config("VectorStrategy", "godmode_p2_reval", max_open=7, balance_ratio=0.7)

# 2. P3D with kill_zone_only forced True
print("\n[2] P3D kill_zone_only=True forced")
make_config("VectorStrategy_P3D_KILL_ZONE_FILTER", "godmode_p3d_forced",
            extra_params={"kill_zone_only": True})

# 3. P3E on P2 pairs (fair comparison)
print("\n[3] P3E on P2★ pairs (fair comparison)")
make_config("VectorStrategy_P3E_KEY_LEVEL_BOOST", "godmode_p3e_p2pairs")

# 4. P3F: P3E key level + P3B tighter trail combo
# Need to build the P3F strategy first (P3E base + tighter trail)
print("\n[4] P3F combo will use P3E strategy with tighter trail params")

print("\n=== Done ===")