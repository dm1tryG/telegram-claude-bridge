"""State management for pending permission requests."""

import asyncio
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PendingRequest:
    """A pending permission request waiting for user response."""

    request_id: str
    tool: str
    command: str
    session_id: str | None
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Literal["allow", "deny"] | None = None
    reason: str | None = None
    message_id: int | None = None


class StateManager:
    """Manages pending permission requests."""

    def __init__(self):
        self._pending: dict[str, PendingRequest] = {}

    def add(self, request: PendingRequest) -> None:
        """Add a pending request."""
        self._pending[request.request_id] = request

    def get(self, request_id: str) -> PendingRequest | None:
        """Get a pending request by ID."""
        return self._pending.get(request_id)

    def remove(self, request_id: str) -> PendingRequest | None:
        """Remove and return a pending request."""
        return self._pending.pop(request_id, None)

    def all(self) -> list[PendingRequest]:
        """Get all pending requests."""
        return list(self._pending.values())

    def count(self) -> int:
        """Get count of pending requests."""
        return len(self._pending)


state = StateManager()
