# Telegram Bot Setup Guide

## Overview

This guide explains how to set up and configure Telegram notifications for your Freqtrade trading bot.

## Prerequisites

- Telegram account
- Basic understanding of Telegram bots

## Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Start a conversation and send `/newbot`
3. Follow the prompts:
   - Choose a name for your bot (e.g., "My Trading Bot")
   - Choose a username (must end in 'bot', e.g., "my_trading_bot")
4. **Save the bot token** - you'll need this later
   - Example: `7553420615:AAGXB2ORviX1AA1gXpSfwZC0l8tZKWjHW7M`

## Step 2: Get Your Chat ID

### Method 1: Using @userinfobot

1. Search for **@userinfobot** in Telegram
2. Start a conversation
3. The bot will send you your chat ID
4. **Save this number** - you'll need it later
   - Example: `1990546056`

### Method 2: Using @RawDataBot

1. Search for **@RawDataBot** in Telegram
2. Send any message to the bot
3. Look for `"id":` in the response
4. Save this number

## Step 3: Configure Environment Variables

1. Open the `.env` file in your project root:

   ```bash
   notepad .env
   ```

2. Update the Telegram credentials:

   ```bash
   TELEGRAM_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

3. Save the file

## Step 4: Verify Configuration

Run the test script to verify your setup:

```bash
python scripts/live_trading/telegram_alert_system.py --test
```

You should receive test messages in Telegram.

## Configuration Files

### Live Trading Config

Only **one** config file should have Telegram enabled at a time:

**File:** `user_data/config_live_trading_6x.json`

```json
{
  "telegram": {
    "enabled": true,
    "token": "7553420615:AAGXB2ORviX1AA1gXpSfwZC0l8tZKWjHW7M",
    "chat_id": "1990546056",
    "notification_settings": {
      "status": "on",
      "warning": "on",
      "startup": "on",
      "entry": "on",
      "exit": "on",
      "entry_cancel": "on",
      "exit_cancel": "on"
    }
  }
}
```

### Backtest Configs

All backtest configs should have Telegram **disabled**:

```json
{
  "telegram": {
    "enabled": false
  }
}
```

## Notification Types

### Entry Signals

Sent when the bot enters a trade:

```
🟢 LONG ENTRY SIGNAL

Pair: RENDER/USDT:USDT
Side: LONG
Entry Price: $2.4500
Reason: Aroon+MACD bullish cross
Time: 2026-02-04 01:30:00
```

### Exit Signals

Sent when the bot exits a trade:

```
🟢 EXIT SIGNAL

Pair: RENDER/USDT:USDT
Exit Price: $2.5500
P&L: +4.08%
Reason: profit_target_reached
Time: 2026-02-04 02:15:00
```

### Portfolio Updates

Daily summary of your trading performance:

```
📈 DAILY PORTFOLIO UPDATE

Balance: $1,250.00 USDT
Open Trades: 3
Daily P&L: +$45.50 USDT
Total P&L: +25.00%
Time: 2026-02-04 00:00:00
```

### Emergency Alerts

Critical warnings about your bot:

```
🚨 EMERGENCY ALERT 🚨

Maximum drawdown exceeded: -15%
Consider stopping the bot!

Time: 2026-02-04 03:00:00
```

## Troubleshooting

### Error: "Conflict: terminated by other getUpdates request"

**Cause:** Multiple bot instances are trying to use the same Telegram token simultaneously.

**Solution:**

1. Stop all running Freqtrade instances:

   ```bash
   docker stop $(docker ps -q --filter "ancestor=freqtradeorg/freqtrade")
   ```

2. Remove all containers:

   ```bash
   docker rm $(docker ps -aq --filter "ancestor=freqtradeorg/freqtrade")
   ```

3. Ensure only ONE config has Telegram enabled:

   ```bash
   python scripts/disable_telegram_in_backtests.py
   ```

4. Start only ONE instance:

   ```bash
   python scripts/live_trading/start_paper_trading.py
   ```

### Error: "Unauthorized"

**Cause:** Invalid bot token.

**Solution:**

1. Verify your token is correct in `.env`
2. Make sure there are no extra spaces
3. Create a new bot if needed

### Error: "Chat not found"

**Cause:** Invalid chat ID or bot hasn't been started.

**Solution:**

1. Start a conversation with your bot in Telegram
2. Send `/start` to the bot
3. Verify your chat ID is correct

### No Messages Received

**Checklist:**

- [ ] Telegram is enabled in config (`"enabled": true`)
- [ ] Bot token is correct
- [ ] Chat ID is correct
- [ ] You've started a conversation with the bot
- [ ] Only ONE instance is running
- [ ] Notification settings are "on"

## Best Practices

### Security

1. **Never commit credentials to git**
   - Use `.env` file (already in `.gitignore`)
   - Never hardcode tokens in config files

2. **Protect your bot token**
   - Treat it like a password
   - Regenerate if compromised (via @BotFather)

3. **Limit bot access**
   - Only share your bot with trusted people
   - Use `/setjoingroups` in @BotFather to disable group adds

### Performance

1. **Rate limiting**
   - Telegram limits: 30 messages/second
   - Our bot automatically handles this

2. **Message batching**
   - Group related notifications
   - Avoid spamming during high volatility

### Reliability

1. **Single instance only**
   - Always use process manager
   - Never run multiple instances with same token

2. **Monitor bot health**
   - Check logs regularly
   - Test connection before trading

3. **Fallback notifications**
   - Set up email alerts as backup
   - Monitor logs even with Telegram working

## Advanced Configuration

### Custom Notification Format

Edit `scripts/live_trading/telegram_alert_system.py` to customize message format.

### Webhook Mode (Alternative to Polling)

To avoid polling conflicts entirely, use webhook mode:

1. Set up a public HTTPS endpoint
2. Configure webhook in bot code
3. Telegram pushes updates instead of polling

**Note:** Requires public server with HTTPS certificate.

## Support

If you encounter issues:

1. Check the [Freqtrade Telegram documentation](https://www.freqtrade.io/en/stable/telegram-usage/)
2. Review logs: `docker logs freqtrade`
3. Test with: `python scripts/live_trading/telegram_alert_system.py --test`

## References

- [Telegram Bot API Documentation](https://core.telegram.org/bots/api)
- [Freqtrade Telegram Setup](https://www.freqtrade.io/en/stable/telegram-usage/)
- [BotFather Commands](https://core.telegram.org/bots#6-botfather)
