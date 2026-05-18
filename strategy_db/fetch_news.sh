#!/usr/bin/env bash
# fetch_news.sh - Cron job script for fetching and embedding crypto news sentiment
# Usage: ./fetch_news.sh
# Crontab example (every 30 minutes):
#   */30 * * * * /home/roshan/Downloads/Algotrading/strategy_db/fetch_news.sh >> /tmp/fetch_news.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG="[fetch_news]"

echo "$LOG_TAG $(date -Iseconds) Starting news fetch pipeline..."

cd "$SCRIPT_DIR"

# Run the news pipeline fetch
python3 news_pipeline.py --fetch

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "$LOG_TAG $(date -Iseconds) News fetch completed successfully."
else
    echo "$LOG_TAG $(date -Iseconds) News fetch FAILED with exit code $EXIT_CODE" >&2
fi

exit $EXIT_CODE