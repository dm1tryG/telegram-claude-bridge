"""Session tracking for Claude Code sessions."""

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


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
        """Send input text to the session's TTY."""
        if not self.tty:
            logger.error(f"No TTY for session {self.session_id}")
            return False

        try:
            # Write to TTY with newline to submit
            with open(self.tty, 'w') as tty_file:
                tty_file.write(text + '\n')
                tty_file.flush()
            logger.info(f"Sent input to {self.tty}: {text[:50]}...")
            return True
        except PermissionError:
            logger.error(f"Permission denied writing to {self.tty}")
            return False
        except FileNotFoundError:
            logger.error(f"TTY not found: {self.tty}")
            return False
        except Exception as e:
            logger.error(f"Failed to send input to {self.tty}: {e}")
            return False

    @property
    def display_cwd(self) -> str:
        """Get shortened cwd for display."""
        if not self.cwd:
            return "unknown"
        # Replace home dir with ~
        home = subprocess.run(
            ["echo", "$HOME"],
            capture_output=True,
            text=True,
            shell=True
        ).stdout.strip()
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

    def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def get_by_tty(self, tty: str) -> Optional[Session]:
        """Get a session by TTY."""
        for session in self._sessions.values():
            if session.tty == tty:
                return session
        return None

    def create_or_update(self, session_id: str, **kwargs) -> Session:
        """Create a new session or update existing one."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.update(**kwargs)
        else:
            session = Session(session_id=session_id, **kwargs)
            self._sessions[session_id] = session
            logger.info(f"New session: {session_id}")
        return session

    def remove(self, session_id: str) -> None:
        """Remove a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Session removed: {session_id}")

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
