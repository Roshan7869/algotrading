#!/usr/bin/env python3
"""Quick single-token backtest test"""

import subprocess
import json

CONFIG_FILE = "user_data/config_backtest_100.json"
STRATEGY = "AroonMomentumEngine_Shorts"
DOCKER_CMD = "docker compose -f infrastructure/docker-compose.backtest.yml run --rm freqtrade-backtest"

# Load base config
with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

# Single token: BTC
config["exchange"]["pair_whitelist"] = ["BTC/USDT:USDT"]

# Save temp config
temp_config_path = "user_data/temp_backtest_config.json"
with open(temp_config_path, "w") as f:
    json.dump(config, f, indent=2)

print(f"✅ Created {temp_config_path}")
print(json.dumps(config, indent=2))

# Run backtest
cmd = f"{DOCKER_CMD} backtesting --config {temp_config_path} --strategy {STRATEGY} --timerange 20250401- --timeframe 1h"
print(f"\n🔍 Running: {cmd}\n")

result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
