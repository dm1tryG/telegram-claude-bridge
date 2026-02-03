#!/bin/bash
# Check status of Telegram Claude Bridge service

echo "📊 Telegram Claude Bridge Status"
echo "================================="

# Check if service is loaded
if launchctl list | grep -q "com.telegram-claude-bridge"; then
    PID=$(launchctl list | grep "com.telegram-claude-bridge" | awk '{print $1}')
    if [ "$PID" != "-" ]; then
        echo "✅ Status: Running (PID: $PID)"
    else
        echo "⚠️  Status: Loaded but not running"
    fi
else
    echo "❌ Status: Not installed"
    exit 0
fi

# Check health endpoint
echo ""
echo "🔍 Health Check:"
HEALTH=$(curl -s http://127.0.0.1:8765/health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "   $HEALTH"
else
    echo "   ❌ Cannot connect to bridge"
fi

# Show recent logs
echo ""
echo "📝 Recent Logs:"
if [ -f /tmp/telegram-claude-bridge.log ]; then
    tail -5 /tmp/telegram-claude-bridge.log | sed 's/^/   /'
else
    echo "   No logs found"
fi
