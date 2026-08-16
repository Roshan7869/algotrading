---
name: freqtrade-rpc
description: RPC system for Telegram, API, and notifications
version: 1.0.0
category: trading
tags: [freqtrade, rpc, telegram, api, notifications]
---

# Freqtrade RPC

Remote Procedure Call system providing external interfaces: Telegram bot, REST API, and webhook notifications.

## Interfaces
- **Telegram Bot**: Trade notifications, manual controls, status queries
- **REST API**: JSON API for external integrations (port 8080)
- **Webhooks**: Outbound trade event notifications

## Trigger Phrases
- "send trade alert to Telegram", "check API status"
- "configure RPC settings", "test webhook"
