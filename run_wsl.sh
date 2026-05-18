#!/bin/bash

# Clear screen
clear

echo "==================================================="
echo "   Freqtrade Algotrading Bot - WSL Launcher"
echo "   FAULT-TOLERANT MODE (10x Leverage, -12% SL)"
echo "==================================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "Error: Docker is not running."
  echo "Please start Docker Desktop on Windows and ensure WSL integration is enabled."
  exit 1
fi

echo "Optimized 10x Leverage Configuration Loaded."
echo "Default: 10x Leverage | -12% Stoploss | AroonMomentumEngine_Hybrid"
echo ""
echo "Select an action:"
echo "1) Download Backtest Data (300 Days)"
echo "2) Run Backtest (300 Days, 10x Leverage)"
echo "3) Run Live/Dry-Run with Orchestrator (FAULT-TOLERANT - RECOMMENDED)"
echo "4) Simulation: Backtest Last 24 Hours"
echo "5) Run Live/Dry-Run (Direct Docker - Legacy)"
echo "6) Exit"
echo ""
read -p "Enter choice [1-6]: " choice

DOCKER_CMD="docker run --rm --env-file $(pwd)/.env -v $(pwd)/user_data:/freqtrade/user_data freqtradeorg/freqtrade:stable"

case $choice in
    1)
        echo "Starting Data Download (300 Days)..."
        $DOCKER_CMD download-data --config /freqtrade/user_data/config_backtest_300d_10x.json --days 300
        ;;
    2)
        echo "Starting Backtest (10x Optimized Strategy)..."
        $DOCKER_CMD backtesting --config /freqtrade/user_data/config_backtest_300d_10x.json --strategy AroonMomentumEngine_Hybrid
        ;;
    3)
        echo "======================================================="
        echo "   STARTING FAULT-TOLERANT ORCHESTRATOR"
        echo "======================================================="
        echo ""
        echo "Config: config_live_trading_10x.json"
        echo "Leverage: 10x | Stoploss: -12%"
        echo "Features: Auto-recovery, Isolated Telegram, Health Monitoring"
        echo ""
        echo "Press Ctrl+C to stop gracefully."
        echo ""
        
        # Step 1: Clean zombies
        echo "[1/3] Cleaning zombie processes..."
        bash scripts/kill_zombies.sh
        
        # Step 2: Start orchestrator
        echo ""
        echo "[2/3] Starting Trading Orchestrator..."
        echo ""
        python3 scripts/trading_orchestrator.py user_data/config_live_trading_10x.json
        
        echo ""
        echo "[3/3] Orchestrator stopped."
        ;;
    4)
        echo "Starting Simulation (Last 2 Days)..."
        # Download recent data
        $DOCKER_CMD download-data --config /freqtrade/user_data/config_dryrun_wsl_10x.json --days 2
        # Backtest
        $DOCKER_CMD backtesting --config /freqtrade/user_data/config_dryrun_wsl_10x.json --strategy AroonMomentumEngine_Hybrid
        ;;
    5)
        echo "Starting Live Dry-Run (Direct Docker - Legacy Mode)..."
        echo "WARNING: No fault tolerance! Use Option 3 for production."
        echo "Press Ctrl+C to stop."
        $DOCKER_CMD trade --config /freqtrade/user_data/config_live_trading_10x.json --strategy AroonMomentumEngine_Hybrid
        ;;
    6)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice."
        exit 1
        ;;
esac

echo ""
echo "Done."

