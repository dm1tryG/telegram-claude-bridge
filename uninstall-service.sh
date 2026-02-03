#!/bin/bash
# Uninstall Telegram Claude Bridge LaunchAgent

PLIST_NAME="com.telegram-claude-bridge.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "🗑️  Uninstalling Telegram Claude Bridge..."

# Stop the service
if launchctl list | grep -q "com.telegram-claude-bridge"; then
    echo "⏹️  Stopping service..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Remove plist
if [ -f "$PLIST_DST" ]; then
    rm "$PLIST_DST"
    echo "✅ LaunchAgent removed"
else
    echo "ℹ️  LaunchAgent was not installed"
fi

echo "✅ Uninstall complete"
