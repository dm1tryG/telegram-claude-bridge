#!/bin/bash
# Install Claude Code hooks for Telegram permission bridge

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_PATH="$SCRIPT_DIR/permission_request.py"
CLAUDE_SETTINGS_DIR="$HOME/.claude"
CLAUDE_SETTINGS_FILE="$CLAUDE_SETTINGS_DIR/settings.json"

echo "🔧 Installing Claude Code Telegram Bridge Hooks"
echo ""

# Make hook executable
chmod +x "$HOOK_PATH"

# Ensure .claude directory exists
mkdir -p "$CLAUDE_SETTINGS_DIR"

# Create or update settings.json
if [ -f "$CLAUDE_SETTINGS_FILE" ]; then
    echo "📄 Found existing settings.json"

    # Check if jq is available for JSON manipulation
    if command -v jq &> /dev/null; then
        # Use jq to add/update the hook
        TEMP_FILE=$(mktemp)

        jq --arg hook_path "$HOOK_PATH" '
            .hooks //= {} |
            .hooks.PermissionRequest = [
                {
                    "matcher": ".*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": ("python3 " + $hook_path)
                        }
                    ]
                }
            ]
        ' "$CLAUDE_SETTINGS_FILE" > "$TEMP_FILE"

        mv "$TEMP_FILE" "$CLAUDE_SETTINGS_FILE"
        echo "✅ Updated settings.json with jq"
    else
        echo "⚠️  jq not found, creating backup and replacing settings"
        cp "$CLAUDE_SETTINGS_FILE" "$CLAUDE_SETTINGS_FILE.backup"

        cat > "$CLAUDE_SETTINGS_FILE" << EOF
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOOK_PATH"
          }
        ]
      }
    ]
  }
}
EOF
        echo "✅ Created new settings.json (backup saved)"
    fi
else
    echo "📄 Creating new settings.json"

    cat > "$CLAUDE_SETTINGS_FILE" << EOF
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOOK_PATH"
          }
        ]
      }
    ]
  }
}
EOF
    echo "✅ Created settings.json"
fi

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Set environment variables:"
echo "     export TELEGRAM_BOT_TOKEN='your-bot-token'"
echo "     export TELEGRAM_CHAT_ID='your-chat-id'"
echo ""
echo "  2. Start the bridge daemon:"
echo "     cd $(dirname "$SCRIPT_DIR")"
echo "     uv run telegram-claude-bridge"
echo ""
echo "  3. Start a new Claude Code session:"
echo "     claude"
