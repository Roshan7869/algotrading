#!/usr/bin/env python3
"""
Build freqtrade config JSON files for all HEdge strategies.
Outputs to HEdge/configs/ directory.
Usage: python3 build_configs.py
"""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "user_data"
OUT = Path(__file__).parent / "configs"
OUT.mkdir(parents=True, exist_ok=True)

P2_PAIRS = [
    "NEAR/USDT:USDT", "VET/USDT:USDT", "ENA/USDT:USDT", "ONDO/USDT:USDT",
    "DOT/USDT:USDT", "LINK/USDT:USDT", "WLD/USDT:USDT", "ARB/USDT:USDT",
    "AVAX/USDT:USDT", "1000SHIB/USDT:USDT", "OP/USDT:USDT", "KAS/USDT:USDT",
    "SUI/USDT:USDT", "DOGE/USDT:USDT", "ALGO/USDT:USDT", "TRX/USDT:USDT",
    "XLM/USDT:USDT"
]

BLACKLIST = [
    "AAVE/USDT:USDT", "HBAR/USDT:USDT", "XMR/USDT:USDT", "XTZ/USDT:USDT",
    "ZEC/USDT:USDT", "1000PEPE/USDT:USDT", "SOL/USDT:USDT", "BCH/USDT:USDT",
    "RENDER/USDT:USDT"
]

HEDGE_STRATEGIES = [
    ("Hedge01FixedFractional",      "hedge_01_fixed_fractional"),
    ("Hedge02RiskToZero",           "hedge_02_risk_to_zero"),
    ("Hedge03HalfKelly",            "hedge_03_half_kelly"),
    ("Hedge04ConsecLossProtect",    "hedge_04_consec_loss_protect"),
    ("Hedge05ScaleOut",             "hedge_05_scale_out"),
    ("Hedge06AntiMartingale",       "hedge_06_anti_martingale"),
    ("Hedge07WinRateAdaptive",      "hedge_07_win_rate_adaptive"),
    ("HedgeMeta7in1",               "hedge_meta_7in1"),
    ("HedgeChampionP3F",            "hedge_champion_p3f"),
]

BASE_CONFIG = {
    "trading_mode": "futures",
    "margin_mode": "isolated",
    "max_open_trades": 14,  # 7 long + 7 short
    "stake_currency": "USDT",
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 1.0,  # Use full capital (50/50 split)
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
    "leverage": 10,
}

def build_configs():
    print("=== Building HEdge Configs ===\n")
    for class_name, file_stem in HEDGE_STRATEGIES:
        config = dict(BASE_CONFIG)
        config["strategy"] = class_name
        fname = f"config_hedge_{file_stem.replace('hedge_', '')}.json"
        path = OUT / fname
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"  {fname:45s} → {class_name}")
    print(f"\nWritten {len(HEDGE_STRATEGIES)} configs to {OUT}")

if __name__ == "__main__":
    build_configs()
