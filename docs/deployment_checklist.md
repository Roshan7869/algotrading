# Deployment Checklist

## Pre-Deployment Validation

### 1. Environment Setup

- [ ] Python 3.9+ installed
- [ ] Docker installed and running
- [ ] WSL configured (if on Windows)
- [ ] All dependencies installed: `pip install -r requirements.txt`
- [ ] `.env` file created with correct credentials

### 2. Configuration Validation

- [ ] **CRITICAL:** Only ONE config has Telegram enabled

  ```bash
  # Run this to verify:
  grep -r '"enabled": true' user_data/*.json | grep telegram
  # Should return only: user_data/config_live_trading_6x.json
  ```

- [ ] Telegram credentials are correct in `.env`
- [ ] Exchange API keys are valid (if live trading)
- [ ] Leverage settings are appropriate for risk tolerance
- [ ] Stake amount configured correctly
- [ ] Pair whitelist is up to date

### 3. Strategy Validation

- [ ] Strategy file exists and is error-free
- [ ] Backtest results are satisfactory
- [ ] Risk management parameters are set:
  - [ ] Stop loss configured
  - [ ] Take profit configured  
  - [ ] Maximum open trades set
  - [ ] Position sizing appropriate

### 4. Data Preparation

- [ ] Historical data downloaded for all pairs

  ```bash
  freqtrade download-data --config user_data/config_live_trading_6x.json --timerange 20240101-
  ```

- [ ] Data quality verified (no gaps)
- [ ] Sufficient data for strategy indicators

### 5. Process Management

- [ ] No existing Freqtrade containers running

  ```bash
  docker ps -a | grep freqtrade
  # Should return empty
  ```

- [ ] Process manager tested

  ```bash
  python scripts/live_trading/process_manager.py --check
  ```

- [ ] PID file location is writable

## Deployment Steps

### Step 1: Pre-Flight Check

Run the automated pre-flight validation:

```bash
python scripts/live_trading/preflight_check.py --config user_data/config_live_trading_6x.json
```

**Expected output:** All checks should pass ✅

### Step 2: Test Telegram Connection

```bash
python scripts/live_trading/telegram_alert_system.py --test
```

**Expected output:** Test messages received in Telegram

### Step 3: Start Paper Trading (Recommended First)

```bash
python scripts/live_trading/start_paper_trading.py --config user_data/config_live_trading_6x.json
```

**Monitor for:**

- [ ] Bot starts without errors
- [ ] Telegram notifications are received
- [ ] No "Conflict" errors in logs
- [ ] Trades are being analyzed

### Step 4: Monitor Initial Operation

**First 30 minutes:**

- [ ] Check logs every 5 minutes
- [ ] Verify Telegram alerts are working
- [ ] Confirm no error messages
- [ ] Check process is stable

**First 24 hours:**

- [ ] Monitor trade entries/exits
- [ ] Verify P&L calculations
- [ ] Check for any unexpected behavior
- [ ] Review Telegram notifications

### Step 5: Transition to Live Trading (Optional)

> [!CAUTION]
> **ONLY proceed to live trading after successful paper trading!**

1. **Stop paper trading:**

   ```bash
   # Press Ctrl+C or:
   python scripts/live_trading/process_manager.py --stop
   ```

2. **Update configuration:**
   - Set `"dry_run": false` in config
   - Verify exchange API keys are correct
   - Double-check all risk parameters

3. **Start with minimal capital:**
   - Use small position sizes initially
   - Gradually increase as confidence grows

4. **Start live trading:**

   ```bash
   python scripts/live_trading/start_paper_trading.py --config user_data/config_live_trading_6x.json --live
   ```

## Post-Deployment Monitoring

### Daily Checks

- [ ] Review Telegram notifications
- [ ] Check portfolio performance
- [ ] Verify no error messages in logs
- [ ] Confirm bot is still running
- [ ] Review open positions

### Weekly Checks

- [ ] Analyze trade performance
- [ ] Review strategy effectiveness
- [ ] Check for any market regime changes
- [ ] Update data if needed
- [ ] Review and adjust parameters if necessary

### Monthly Checks

- [ ] Full performance audit
- [ ] Strategy optimization review
- [ ] Risk management assessment
- [ ] Update dependencies: `pip install --upgrade -r requirements.txt`
- [ ] Review and update documentation

## Troubleshooting Guide

### Bot Won't Start

**Check:**

1. Docker is running: `docker ps`
2. No existing instances: `docker ps -a | grep freqtrade`
3. Config file is valid JSON
4. All required fields are present

**Solution:**

```bash
# Clean up containers
docker stop $(docker ps -q --filter "ancestor=freqtradeorg/freqtrade")
docker rm $(docker ps -aq --filter "ancestor=freqtradeorg/freqtrade")

# Restart
python scripts/live_trading/start_paper_trading.py
```

### Telegram Conflict Error

**Error:** `Conflict: terminated by other getUpdates request`

**Solution:**

1. Stop ALL instances
2. Run: `python scripts/disable_telegram_in_backtests.py`
3. Verify only one config has Telegram enabled
4. Start single instance

### No Trades Being Executed

**Check:**

1. Market conditions match strategy criteria
2. Sufficient balance available
3. Pair whitelist includes active pairs
4. No exchange connectivity issues

**Debug:**

```bash
# Check logs
docker logs freqtrade

# Verify strategy
freqtrade backtesting --config user_data/config_live_trading_6x.json --timerange 20260201-20260204
```

### High Memory Usage

**Causes:**

- Too many pairs in whitelist
- Insufficient RAM
- Memory leak in strategy

**Solutions:**

- Reduce number of pairs
- Increase Docker memory limit
- Restart bot periodically

### Connection Issues

**Symptoms:**

- "Connection refused" errors
- Timeouts
- Failed API calls

**Solutions:**

1. Check internet connection
2. Verify exchange API status
3. Check firewall settings
4. Restart Docker

## Rollback Procedures

### Emergency Stop

```bash
# Stop immediately
docker stop $(docker ps -q --filter "ancestor=freqtradeorg/freqtrade")

# Or use process manager
python scripts/live_trading/process_manager.py --stop
```

### Revert to Previous Version

```bash
# Stop current version
docker stop freqtrade

# Pull previous version
docker pull freqtradeorg/freqtrade:stable-previous

# Restart with previous version
docker run -d --name freqtrade freqtradeorg/freqtrade:stable-previous ...
```

### Restore from Backup

```bash
# Stop bot
docker stop freqtrade

# Restore database
cp user_data/backups/tradesv3.sqlite.backup user_data/tradesv3.sqlite

# Restore config
cp user_data/backups/config_live_trading_6x.json.backup user_data/config_live_trading_6x.json

# Restart
python scripts/live_trading/start_paper_trading.py
```

## Backup Procedures

### Daily Backups

```bash
# Create backup directory
mkdir -p user_data/backups/$(date +%Y%m%d)

# Backup database
cp user_data/tradesv3.sqlite user_data/backups/$(date +%Y%m%d)/

# Backup configs
cp user_data/config_*.json user_data/backups/$(date +%Y%m%d)/
```

### Automated Backup Script

Create `scripts/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="user_data/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup database
cp user_data/tradesv3.sqlite "$BACKUP_DIR/"

# Backup configs
cp user_data/config_*.json "$BACKUP_DIR/"

# Backup strategies
cp -r user_data/strategies "$BACKUP_DIR/"

echo "Backup completed: $BACKUP_DIR"
```

Run daily via cron:

```bash
0 0 * * * /path/to/Algotrading/scripts/backup.sh
```

## Security Checklist

- [ ] `.env` file is in `.gitignore`
- [ ] No credentials in config files
- [ ] API keys have appropriate permissions only
- [ ] Telegram bot token is private
- [ ] Docker containers run with minimal privileges
- [ ] Firewall configured appropriately
- [ ] Regular security updates applied

## Performance Optimization

### Resource Monitoring

```bash
# Monitor Docker resources
docker stats freqtrade

# Monitor system resources
htop  # or Task Manager on Windows
```

### Optimization Tips

1. **Reduce pair count** if CPU usage is high
2. **Increase timeframe** to reduce data processing
3. **Optimize strategy code** for efficiency
4. **Use SSD** for database storage
5. **Allocate sufficient RAM** (minimum 2GB recommended)

## Compliance & Legal

- [ ] Understand local regulations for algorithmic trading
- [ ] Comply with exchange terms of service
- [ ] Keep accurate records for tax purposes
- [ ] Understand risks of leveraged trading
- [ ] Have appropriate risk management in place

## Support Resources

- **Freqtrade Documentation:** <https://www.freqtrade.io/>
- **Freqtrade Discord:** <https://discord.gg/freqtrade>
- **Project Issues:** Check `docs/` folder
- **Logs Location:** `docker logs freqtrade`

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-04 | Initial deployment checklist |

---

**Remember:** Always test in paper trading mode first before risking real capital!
