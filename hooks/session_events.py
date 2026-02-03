#!/usr/bin/env python3
"""
Claude Code session events hook.

This script sends session state updates to the bridge daemon.
It handles SessionStart, Notification, Stop, and SessionEnd events.
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BRIDGE_URL = "http://127.0.0.1:8765"
TIMEOUT = 5  # Short timeout - don't block Claude Code


def get_tty():
    """Get the TTY of the Claude process (parent)."""
    import subprocess

    ppid = os.getppid()

    try:
        result = subprocess.run(
            ["ps", "-p", str(ppid), "-o", "tty="],
            capture_output=True,
            text=True,
            timeout=2
        )
        tty = result.stdout.strip()
        if tty and tty != "??" and tty != "-":
            if not tty.startswith("/dev/"):
                tty = "/dev/" + tty
            return tty
    except Exception:
        pass

    try:
        return os.ttyname(sys.stdin.fileno())
    except (OSError, AttributeError):
        pass

    return None


def send_event(data: dict) -> None:
    """Send event to bridge daemon."""
    try:
        request_body = json.dumps(data).encode("utf-8")
        req = Request(
            f"{BRIDGE_URL}/session",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=TIMEOUT) as response:
            response.read()
    except (HTTPError, URLError, TimeoutError, Exception):
        # Silently fail - don't block Claude Code
        pass


def main():
    """Process session event from Claude Code."""
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = data.get("session_id", "unknown")
    event = data.get("hook_event_name", "")
    cwd = data.get("cwd", "")

    # Get process info
    claude_pid = os.getppid()
    tty = get_tty()

    # Build event payload
    payload = {
        "session_id": session_id,
        "event": event,
        "tty": tty,
        "cwd": cwd,
        "pid": claude_pid,
    }

    # Add event-specific data
    if event == "SessionStart":
        payload["status"] = "processing"

    elif event == "Notification":
        notification_type = data.get("notification_type")
        payload["notification_type"] = notification_type
        payload["message"] = data.get("message")

        if notification_type == "idle_prompt":
            payload["status"] = "waiting_for_input"
        else:
            payload["status"] = "notification"

    elif event == "Stop":
        payload["status"] = "waiting_for_input"
        payload["message"] = data.get("message")

    elif event == "SessionEnd":
        payload["status"] = "ended"

    elif event == "PreToolUse":
        payload["status"] = "running_tool"
        payload["tool"] = data.get("tool_name")

    elif event == "PostToolUse":
        payload["status"] = "processing"
        payload["tool"] = data.get("tool_name")

    else:
        # Unknown event, skip
        sys.exit(0)

    # Send to bridge
    send_event(payload)


if __name__ == "__main__":
    main()
