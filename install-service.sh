#!/bin/bash
# Install Telegram Claude Bridge as a LaunchAgent

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.telegram-claude-bridge.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "🔧 Installing Telegram Claude Bridge..."

# Check if .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "❌ Error: .env file not found. Please create it first:"
    echo "   cp .env.example .env"
    echo "   # Edit .env with your Telegram credentials"
    exit 1
fi

# Stop existing service if running
if launchctl list | grep -q "com.telegram-claude-bridge"; then
    echo "⏹️  Stopping existing service..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
echo "📋 Installing LaunchAgent..."
cp "$PLIST_SRC" "$PLIST_DST"

# Load the service
echo "🚀 Starting service..."
launchctl load "$PLIST_DST"

# Check if it's running
sleep 2
if launchctl list | grep -q "com.telegram-claude-bridge"; then
    echo "✅ Telegram Claude Bridge installed and running!"
    echo ""
    echo "📝 Logs: tail -f /tmp/telegram-claude-bridge.log"
    echo "⏹️  Stop: launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
    echo "▶️  Start: launchctl load ~/Library/LaunchAgents/$PLIST_NAME"
    echo "🗑️  Uninstall: ./uninstall-service.sh"
else
    echo "❌ Failed to start service. Check logs:"
    echo "   cat /tmp/telegram-claude-bridge.log"
    exit 1
fi
