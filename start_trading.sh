#!/bin/bash
# Quick start script for fault-tolerant trading system
# Uses config_live_trading_10x.json with 10x leverage and -12% stoploss

clear
echo "======================================================="
echo "   FAULT-TOLERANT TRADING ORCHESTRATOR"
echo "   10x Leverage | -12% Stoploss | AroonMomentumEngine"
echo "======================================================="
echo ""

# Step 1: Clean zombies
echo "[1/3] Cleaning zombie processes..."
bash scripts/kill_zombies.sh

echo ""
echo "[2/3] Starting Trading Orchestrator..."
echo "Config: config_live_trading_10x.json"
echo "Press Ctrl+C to stop gracefully"
echo ""

# Step 2: Start orchestrator with default 10x config
python3 scripts/trading_orchestrator.py user_data/config_live_trading_10x.json

echo ""
echo "[3/3] Orchestrator stopped."
echo "Review logs in logs/ directory"
