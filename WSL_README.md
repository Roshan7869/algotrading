# Running Algotrading in WSL (Windows Subsystem for Linux)

This guide helps you run the bot using WSL 2 (Ubuntu/Debian) on Windows.

## 1. Prerequisites

- **WSL 2 Installed**: Run `wsl --install` in PowerShell/CMD if not already done.
- **Docker Desktop**: Installed on Windows and configured to "Use the WSL 2 based engine" (Settings -> General).
- **Integration**: Ensure your distro is enabled in Docker Settings -> Resources -> WSL Integration.

## 2. Setup

1. Open your terminal (Ubuntu/WSL).
2. Navigate to your project folder:

   ```bash
   cd /mnt/c/Users/USER/Desktop/Algotrading
   ```

   *(Note: WSL mounts your Windows C: drive at `/mnt/c`)*

## 3. The "One-Click" Script

We have created a master script `run_wsl.sh` to handle everything.

### Make it executable (First time only)

```bash
chmod +x run_wsl.sh
```

### Run the Project

```bash
./run_wsl.sh
```

## 4. Manual Commands (If needed)

If you prefer running commands manually without the script:

**Download Data (300 Days):**

```bash
docker run --rm -v "$(pwd)/user_data:/freqtrade/user_data" freqtradeorg/freqtrade:stable download-data --config /freqtrade/user_data/config_backtest_300d_6x.json --days 300
```

**Run Backtest:**

```bash
docker run --rm -v "$(pwd)/user_data:/freqtrade/user_data" freqtradeorg/freqtrade:stable backtesting --config /freqtrade/user_data/config_backtest_300d_6x.json --strategy AroonMomentumEngine_Hybrid
```

**Run Dry-Run (Paper Trading):**

```bash
docker run --rm -v "$(pwd)/user_data:/freqtrade/user_data" freqtradeorg/freqtrade:stable trade --config /freqtrade/user_data/config_live_trading_6x.json --strategy AroonMomentumEngine_Hybrid
```
