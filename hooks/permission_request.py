#!/usr/bin/env python3
"""
Claude Code PermissionRequest hook.

This script is called by Claude Code when it needs permission to execute
a tool. It sends the request to the bridge daemon and waits for user
approval via Telegram.
"""

import json
import sys
import uuid
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BRIDGE_URL = "http://127.0.0.1:8765"
TIMEOUT = 310  # Slightly longer than bridge timeout


def main():
    """Process permission request from Claude Code."""
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # If we can't parse input, deny by default
        output_deny("Failed to parse hook input")
        return

    # Extract relevant information
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    session_id = input_data.get("session_id")

    # Get the command or description based on tool type
    if tool_name == "Bash":
        command = tool_input.get("command", str(tool_input))
    elif tool_name == "Write":
        command = f"Write to: {tool_input.get('file_path', 'unknown')}"
    elif tool_name == "Edit":
        command = f"Edit: {tool_input.get('file_path', 'unknown')}"
    else:
        command = json.dumps(tool_input, indent=2)[:500]

    request_id = str(uuid.uuid4())

    # Send request to bridge
    try:
        request_body = json.dumps({
            "request_id": request_id,
            "tool": tool_name,
            "command": command,
            "session_id": session_id,
        }).encode("utf-8")

        req = Request(
            f"{BRIDGE_URL}/permission",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))

        decision = result.get("decision", "deny")

        if decision == "allow":
            output_allow()
        else:
            reason = result.get("reason", "Denied via Telegram")
            output_deny(reason)

    except HTTPError as e:
        # Bridge error - fallback to normal Claude Code UI
        sys.exit(0)
    except URLError as e:
        # Bridge not running - fallback to normal Claude Code UI
        sys.exit(0)
    except TimeoutError:
        output_deny("Telegram approval timeout")
    except Exception as e:
        # Unknown error - fallback to normal Claude Code UI
        sys.exit(0)


def output_allow():
    """Output allow decision to Claude Code."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"},
        }
    }
    print(json.dumps(output))


def output_deny(reason: str):
    """Output deny decision to Claude Code."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "deny",
                "message": reason,
            },
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
