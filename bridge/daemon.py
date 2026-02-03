"""Main daemon that runs the bridge service."""

import asyncio
import logging
import signal
import sys
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from .config import settings
from .state import state, PendingRequest
from .sessions import sessions
from .telegram_bot import bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class PermissionRequestInput(BaseModel):
    """Input model for permission requests."""

    request_id: str | None = None
    tool: str
    command: str
    session_id: str | None = None


class PermissionResponse(BaseModel):
    """Response model for permission decisions."""

    decision: str
    reason: str | None = None


class SessionEvent(BaseModel):
    """Input model for session events from hooks."""

    session_id: str
    event: str  # SessionStart, Notification, Stop, etc.
    status: str | None = None
    tty: str | None = None
    cwd: str | None = None
    pid: int | None = None
    tool: str | None = None
    message: str | None = None
    notification_type: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info("Starting Telegram Claude Bridge...")
    await bot.initialize()
    logger.info(
        f"Bridge listening on http://{settings.bridge_host}:{settings.bridge_port}"
    )

    yield

    # Shutdown
    logger.info("Shutting down...")
    await bot.shutdown()


app = FastAPI(
    title="Telegram Claude Bridge",
    description="Permission bridge between Claude Code and Telegram",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "pending": state.count(), "sessions": sessions.count()}


@app.post("/session")
async def session_event(data: SessionEvent):
    """
    Receive session events from Claude Code hooks.

    This tracks session state and sends notifications to Telegram.
    """
    logger.info(f"Session event: {data.event} for {data.session_id[:8]}...")

    # Update session state
    session = sessions.create_or_update(
        session_id=data.session_id,
        tty=data.tty,
        cwd=data.cwd,
        pid=data.pid,
        status=data.status,
        last_tool=data.tool,
    )

    # Handle specific events
    if data.event == "SessionStart":
        await bot.notify_session_start(session)

    elif data.event == "Notification":
        if data.notification_type == "idle_prompt":
            # Session is waiting for input - update message and notify
            session.update(status="waiting_for_input", last_message=data.message)
            await bot.notify_session_idle(session)

    elif data.event == "Stop":
        session.update(status="waiting_for_input", last_message=data.message)
        await bot.notify_session_idle(session)

    elif data.event == "SessionEnd":
        session.update(status="ended")
        await bot.notify_session_end(session)
        # Keep session for a bit for reference, then remove
        # sessions.remove(data.session_id)

    return {"status": "ok"}


@app.post("/permission", response_model=PermissionResponse)
async def request_permission(data: PermissionRequestInput) -> PermissionResponse:
    """
    Request permission for a Claude Code action.

    This endpoint is called by the Claude Code hook. It sends a message
    to Telegram and waits for user response.
    """
    request_id = data.request_id or str(uuid.uuid4())

    logger.info(f"Permission request: {data.tool} - {data.command[:50]}...")

    # Create pending request
    request = PendingRequest(
        request_id=request_id,
        tool=data.tool,
        command=data.command,
        session_id=data.session_id,
    )
    state.add(request)

    # Send to Telegram
    message_id = await bot.send_permission_request(request)
    if message_id:
        request.message_id = message_id

    # Wait for response with timeout
    try:
        await asyncio.wait_for(
            request.event.wait(),
            timeout=settings.permission_timeout,
        )
        decision = request.decision or "deny"
        reason = request.reason
        logger.info(f"Permission {decision} for {request_id}")
    except asyncio.TimeoutError:
        decision = "deny"
        reason = "Timeout - no response received"
        logger.warning(f"Permission timeout for {request_id}")

        # Update Telegram message to show timeout
        if request.message_id:
            await bot.update_message(
                request.message_id,
                f"⏰ *Timeout*\n\n*Tool:* `{request.tool}`\n*Command:* `{request.command[:100]}...`",
            )
    finally:
        state.remove(request_id)

    return PermissionResponse(decision=decision, reason=reason)


def main():
    """Entry point for the daemon."""

    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    uvicorn.run(
        app,
        host=settings.bridge_host,
        port=settings.bridge_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
