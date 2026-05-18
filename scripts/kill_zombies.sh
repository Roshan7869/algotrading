#!/bin/bash
# Kill all Freqtrade zombie processes

echo "🔍 Searching for Freqtrade processes..."

if pgrep -f "freqtrade.*trade" > /dev/null; then
    echo "⚠️  Found running Freqtrade processes:"
    ps aux | grep -i "[f]reqtrade.*trade"
    
    read -p "Kill all Freqtrade processes? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill -9 -f "freqtrade.*trade"
        echo "✅ Processes terminated"
    fi
else
    echo "✅ No Freqtrade processes found"
fi

# Remove stale PID files
if [ -f /tmp/freqtrade_orchestrator.pid ]; then
    echo "🗑️  Removing stale PID file"
    rm /tmp/freqtrade_orchestrator.pid
fi

echo "Done!"
