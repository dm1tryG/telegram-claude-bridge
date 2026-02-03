#!/bin/bash
# Install Claude Code hooks for Telegram permission bridge

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PERMISSION_HOOK="$SCRIPT_DIR/permission_request.py"
SESSION_HOOK="$SCRIPT_DIR/session_events.py"
CLAUDE_SETTINGS_DIR="$HOME/.claude"
CLAUDE_SETTINGS_FILE="$CLAUDE_SETTINGS_DIR/settings.json"

echo "🔧 Installing Claude Code Telegram Bridge Hooks"
echo ""

# Make hooks executable
chmod +x "$PERMISSION_HOOK"
chmod +x "$SESSION_HOOK"

# Ensure .claude directory exists
mkdir -p "$CLAUDE_SETTINGS_DIR"

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "❌ jq is required but not installed."
    echo "   Install with: brew install jq"
    exit 1
fi

# Create settings if doesn't exist
if [ ! -f "$CLAUDE_SETTINGS_FILE" ]; then
    echo '{}' > "$CLAUDE_SETTINGS_FILE"
fi

echo "📄 Updating settings.json..."

# Update settings.json with both hooks
TEMP_FILE=$(mktemp)

jq --arg perm_hook "python3 $PERMISSION_HOOK" \
   --arg sess_hook "python3 $SESSION_HOOK" '
    .hooks //= {} |

    # PermissionRequest hook
    .hooks.PermissionRequest = [
        {
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": $perm_hook
                }
            ]
        }
    ] |

    # SessionStart hook
    .hooks.SessionStart = [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": $sess_hook
                }
            ]
        }
    ] |

    # Notification hook
    .hooks.Notification = (
        (.hooks.Notification // []) + [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": $sess_hook
                    }
                ]
            }
        ] | unique_by(.hooks[0].command)
    ) |

    # Stop hook
    .hooks.Stop = [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": $sess_hook
                }
            ]
        }
    ] |

    # SessionEnd hook
    .hooks.SessionEnd = [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": $sess_hook
                }
            ]
        }
    ]
' "$CLAUDE_SETTINGS_FILE" > "$TEMP_FILE"

mv "$TEMP_FILE" "$CLAUDE_SETTINGS_FILE"

echo "✅ Hooks installed:"
echo "   - PermissionRequest → permission_request.py"
echo "   - SessionStart → session_events.py"
echo "   - Notification → session_events.py"
echo "   - Stop → session_events.py"
echo "   - SessionEnd → session_events.py"
echo ""
echo "🎉 Installation complete!"
echo ""
echo "Make sure the bridge daemon is running:"
echo "   ./status.sh"
