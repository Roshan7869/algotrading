"""
Live Market Scanner
Fetches real-time data from Binance and scans for entry signals using the strategy.
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from freqtrade.configuration import Configuration
from freqtrade.resolvers import StrategyResolver
from freqtrade.data.converter import ohlcv_to_dataframe
from freqtrade.plugins.pairlist.pairlist_helpers import expand_pairlist
from freqtrade.exchange import Exchange

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


class LiveScanner:
    """Scans live market for strategy signals."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._load_config()
        self._init_exchange()
        self._init_strategy()

    def _load_config(self):
        """Load Freqtrade configuration."""
        print(f"Loading config: {self.config_path}")
        self.config = Configuration.from_files([self.config_path])
        self.config["dry_run"] = True  # Safety

    def _init_exchange(self):
        """Initialize Exchange."""
        print("Initializing Exchange...")
        self.exchange = Exchange(self.config, validate=False)

    def _init_strategy(self):
        """Initialize Strategy."""
        print(f"Loading Strategy: {self.config['strategy']}")
        self.strategy = StrategyResolver.load_strategy(self.config)
        self.strategy.dp = None  # We'll feed data manually

    def scan(self):
        """Run the scan."""
        print(f"\n{BLUE}{'=' * 70}{RESET}")
        print(
            f"{BLUE}🚀 LIVE MARKET SCANNER - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}"
        )
        print(f"{BLUE}{'=' * 70}{RESET}\n")

        pairs = self.config["exchange"]["pair_whitelist"]
        timeframe = self.config["timeframe"]

        print(f"Scanning {len(pairs)} pairs on {timeframe} timeframe...\n")

        # Get BTC data first for correlation filter
        btc_data = self._get_data("BTC/USDT:USDT", timeframe)
        if btc_data is not None:
            # Analyze BTC to get indicators
            btc_analyzed = self.strategy.populate_indicators(
                btc_data, {"pair": "BTC/USDT:USDT"}
            )
        else:
            btc_analyzed = None
            print(
                f"{YELLOW}⚠️ Could not fetch BTC data - correlation filter valid check skipped{RESET}"
            )

        # Hack to make the strategy use this BTC data if needed
        # (The strategy usually uses self.dp.get_pair_dataframe, which we don't have here easily)
        # So we might need to rely on the strategy not failing if dp is missing,
        # OR we mock the dp.

        # For v2_optimized, it uses self.dp to get BTC data.
        # We need to mock self.dp
        self._mock_dp(btc_analyzed)

        for pair in pairs:
            self._scan_pair(pair, timeframe)

    def _mock_dp(self, btc_dataframe):
        """Mock DataProvider for strategy."""

        class MockDP:
            def __init__(self, btc_df):
                self.btc_df = btc_df

            def get_pair_dataframe(self, pair, timeframe):
                if "BTC" in pair and self.btc_df is not None:
                    return self.btc_df
                return pd.DataFrame()

            def current_whitelist(self):
                return []

        self.strategy.dp = MockDP(btc_dataframe)

    def _get_data(self, pair: str, timeframe: str) -> pd.DataFrame:
        """Fetch historical data for a pair."""
        try:
            # Calculate since_ms (500 candles back)
            # minimal calc: 1h = 60m, 4h = 240m
            tf_minutes = 60
            if "4h" in timeframe:
                tf_minutes = 240
            elif "1d" in timeframe:
                tf_minutes = 1440
            elif "5m" in timeframe:
                tf_minutes = 5

            duration_ms = 500 * tf_minutes * 60 * 1000
            since_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - duration_ms

            # Fetch data using correct API signature
            ohlcv = self.exchange.get_historic_ohlcv(
                pair=pair, timeframe=timeframe, since_ms=since_ms
            )

            df = ohlcv_to_dataframe(
                ohlcv, timeframe, pair, fill_missing=True, drop_incomplete=True
            )
            return df
        except Exception as e:
            print(f"{RED}Error fetching data for {pair}: {e}{RESET}")
            return None

    def _scan_pair(self, pair: str, timeframe: str):
        """Analyze a single pair."""
        print(f"Analyzing {BOLD}{pair:<18}{RESET} ... ", end="", flush=True)

        df = self._get_data(pair, timeframe)
        if df is None or df.empty:
            print(f"{RED}No Data{RESET}")
            return

        try:
            # Run strategy analysis
            analyzed = self.strategy.populate_indicators(df, {"pair": pair})
            analyzed = self.strategy.populate_entry_trend(analyzed, {"pair": pair})

            last = analyzed.iloc[-1]
            prev = analyzed.iloc[-2]

            # Check signals
            long_signal = last["enter_long"] == 1
            short_signal = last["enter_short"] == 1

            # extract indicators
            aroon_down = last.get("aroondown", 0)
            macd = last.get("macd", 0)
            atr_expanding = last.get("atr_increasing", False)
            btc_safe = not last.get("btc_parabolic", False)

            status = f"{YELLOW}NEUTRAL{RESET}"
            if long_signal:
                status = f"{GREEN}🟢 LONG SIGNAL{RESET}"
            elif short_signal:
                status = f"{RED}🔴 SHORT SIGNAL{RESET}"

            print(f"[{status}]")

            # Print indicator details
            print(
                f"   Aroon Down: {aroon_down:.1f} | MACD: {macd:.4f} | ATR Exp: {atr_expanding} | BTC Safe: {btc_safe}"
            )

            # Print Close Price
            print(f"   Price: ${last['close']:.4f}")
            print("")

        except Exception as e:
            print(f"{RED}Error analyzing: {e}{RESET}")
            # traceback.print_exc()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="user_data/config_live_trading_10x.json")
    args = parser.parse_args()

    try:
        scanner = LiveScanner(args.config)
        scanner.scan()
    except Exception as e:
        print(f"\n{RED}Critical Error: {e}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
