"""Session tracking for Claude Code sessions."""

import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def find_tmux() -> Optional[str]:
    """Find tmux executable path."""
    # Try shutil.which first (respects PATH)
    tmux_path = shutil.which("tmux")
    if tmux_path:
        return tmux_path

    # Common installation paths
    common_paths = [
        "/opt/homebrew/bin/tmux",  # macOS ARM Homebrew
        "/usr/local/bin/tmux",      # macOS Intel Homebrew / Linux manual
        "/usr/bin/tmux",            # Linux package manager
    ]
    for path in common_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return None


TMUX_PATH = find_tmux()


@dataclass
class Session:
    """Represents an active Claude Code session."""

    session_id: str
    tty: Optional[str] = None
    cwd: Optional[str] = None
    pid: Optional[int] = None
    status: str = "unknown"  # processing, waiting_for_input, running_tool, ended
    last_message: Optional[str] = None
    last_tool: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def update(self, **kwargs):
        """Update session fields."""
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)
        self.updated_at = datetime.now()

    def send_input(self, text: str) -> bool:
        """Send input text to the session.

        Tries multiple methods:
        1. tmux send-keys (works with Claude Code!)
        2. iTerm2 write text (fallback, doesn't submit in Claude Code)
        """
        if not self.tty:
            logger.error(f"No TTY for session {self.session_id}")
            return False

        # Method 1: Try tmux send-keys (this actually works with Claude Code!)
        if not TMUX_PATH:
            logger.debug("tmux not found, skipping tmux method")
        else:
            try:
                # First try to find pane by TTY
                result = subprocess.run(
                    [TMUX_PATH, 'list-panes', '-a', '-F', '#{pane_tty} #{session_name}:#{window_index}.#{pane_index}'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                tmux_target = None
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line and self.tty and self.tty in line:
                            parts = line.split(' ', 1)
                            if len(parts) == 2:
                                tmux_target = parts[1]
                                break

                    # If not found by TTY, look for session named "claude"
                    if not tmux_target:
                        for line in result.stdout.strip().split('\n'):
                            if line and 'claude:' in line:
                                parts = line.split(' ', 1)
                                if len(parts) == 2:
                                    tmux_target = parts[1]
                                    logger.info(f"Using tmux session 'claude': {tmux_target}")
                                    break

                    if tmux_target:
                        # Send text first
                        send_result = subprocess.run(
                            [TMUX_PATH, 'send-keys', '-t', tmux_target, '-l', text],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if send_result.returncode != 0:
                            logger.warning(f"tmux send-keys text failed: {send_result.stderr}")

                        # Then send Enter separately
                        enter_result = subprocess.run(
                            [TMUX_PATH, 'send-keys', '-t', tmux_target, 'Enter'],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if send_result.returncode == 0 and enter_result.returncode == 0:
                            logger.info(f"Sent input via tmux to {tmux_target}: {text[:50]}...")
                            return True
                        else:
                            logger.warning(f"tmux send Enter failed: {enter_result.stderr}")
            except FileNotFoundError:
                logger.debug("tmux not found, trying iTerm2")
            except Exception as e:
                logger.warning(f"tmux method failed: {e}")

        # Method 2: iTerm2 write text (text appears but doesn't submit in Claude Code)
        try:
            tty_name = self.tty.replace("/dev/", "")
            escaped_text = text.replace('\\', '\\\\').replace('"', '\\"')

            iterm_script = f'''
            tell application "iTerm2"
                repeat with w in windows
                    repeat with t in tabs of w
                        repeat with s in sessions of t
                            if tty of s contains "{tty_name}" then
                                tell s
                                    write text "{escaped_text}" newline yes
                                end tell
                                return "ok"
                            end if
                        end repeat
                    end repeat
                end repeat
                return "not found"
            end tell
            '''

            result = subprocess.run(
                ['osascript', '-e', iterm_script],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0 and result.stdout.strip() == "ok":
                logger.info(f"Sent input via iTerm2 (note: may need manual Enter for Claude Code): {text[:50]}...")
                return True

            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.error(f"iTerm2 write text failed: {error_msg}")
            return False

        except Exception as e:
            logger.error(f"Failed to send input: {e}")
            return False

    @property
    def display_cwd(self) -> str:
        """Get shortened cwd for display."""
        if not self.cwd:
            return "unknown"
        # Replace home dir with ~
        home = str(Path.home())
        if home and self.cwd.startswith(home):
            return "~" + self.cwd[len(home):]
        return self.cwd

    @property
    def status_emoji(self) -> str:
        """Get emoji for current status."""
        return {
            "processing": "⚙️",
            "waiting_for_input": "💬",
            "running_tool": "🔧",
            "ended": "✅",
            "compacting": "📦",
        }.get(self.status, "❓")


class SessionManager:
    """Manages active Claude Code sessions."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._allowed_sessions: set[str] = set()  # Sessions with "Allow All" enabled

    def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def get_by_tty(self, tty: str) -> Optional[Session]:
        """Get a session by TTY."""
        for session in self._sessions.values():
            if session.tty == tty:
                return session
        return None

    async def create_or_update(self, session_id: str, **kwargs) -> Session:
        """Create a new session or update existing one."""
        async with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.update(**kwargs)
            else:
                session = Session(session_id=session_id, **kwargs)
                self._sessions[session_id] = session
                logger.info(f"New session: {session_id}")
            return session

    async def remove(self, session_id: str) -> None:
        """Remove a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Session removed: {session_id}")
            # Also remove from allowed sessions
            self._allowed_sessions.discard(session_id)

    def allow_session(self, session_id: str) -> None:
        """Mark a session as allowed for all future requests."""
        self._allowed_sessions.add(session_id)
        logger.info(f"Session {session_id} marked as allow-all")

    def is_session_allowed(self, session_id: str) -> bool:
        """Check if a session has allow-all enabled."""
        return session_id in self._allowed_sessions

    def all(self) -> list[Session]:
        """Get all active sessions."""
        return list(self._sessions.values())

    def active(self) -> list[Session]:
        """Get sessions that are not ended."""
        return [s for s in self._sessions.values() if s.status != "ended"]

    def waiting_for_input(self) -> list[Session]:
        """Get sessions waiting for user input."""
        return [s for s in self._sessions.values() if s.status == "waiting_for_input"]

    def count(self) -> int:
        """Count active sessions."""
        return len(self.active())


# Global session manager instance
sessions = SessionManager()
