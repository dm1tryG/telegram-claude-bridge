"""Telegram bot for permission approvals and session management."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import settings
from .state import state, PendingRequest
from .sessions import sessions, Session

logger = logging.getLogger(__name__)


def authorized_only(func):
    """Decorator to restrict handlers to authorized chat_id only."""
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != settings.telegram_chat_id:
            logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
            if update.message:
                await update.message.reply_text("⛔ Unauthorized. This bot is private.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Unauthorized", show_alert=True)
            return
        return await func(self, update, context)
    return wrapper


class TelegramBot:
    """Telegram bot that handles permission requests and sessions."""

    def __init__(self):
        self.app: Application | None = None
        self._initialized = False
        # Track which session each user is replying to
        self._reply_targets: dict[int, str] = {}  # chat_id -> session_id

    async def initialize(self) -> None:
        """Initialize the Telegram bot application."""
        if self._initialized:
            return

        self.app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )

        # Register handlers
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("pending", self._cmd_pending))
        self.app.add_handler(CommandHandler("sessions", self._cmd_sessions))
        self.app.add_handler(CommandHandler("cancel", self._cmd_cancel))
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))
        # Handle text messages for session replies
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_text_message
        ))

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

        self._initialized = True
        logger.info("Telegram bot started")

    async def shutdown(self) -> None:
        """Shutdown the bot gracefully."""
        if self.app and self._initialized:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self._initialized = False
            logger.info("Telegram bot stopped")

    async def send_permission_request(self, request: PendingRequest) -> int | None:
        """Send a permission request message with buttons."""
        if not self.app:
            logger.error("Bot not initialized")
            return None

        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Allow", callback_data=f"allow:{request.request_id}"
                ),
                InlineKeyboardButton(
                    "❌ Deny", callback_data=f"deny:{request.request_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "✅ Allow All Session",
                    callback_data=f"allow_session:{request.request_id}",
                ),
            ],
        ]

        # Truncate long commands for display
        command_display = request.command
        if len(command_display) > 500:
            command_display = command_display[:500] + "..."

        text = (
            f"🔐 *Permission Request*\n\n"
            f"*Tool:* `{request.tool}`\n"
            f"*Command:*\n```\n{command_display}\n```"
        )

        if request.session_id:
            text += f"\n*Session:* `{request.session_id[:8]}...`"

        try:
            message = await self.app.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )
            return message.message_id
        except Exception as e:
            logger.error(f"Failed to send permission request: {e}")
            return None

    async def update_message(self, message_id: int, text: str) -> None:
        """Update a message to show the decision."""
        if not self.app:
            return

        try:
            await self.app.bot.edit_message_text(
                chat_id=settings.telegram_chat_id,
                message_id=message_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to update message: {e}")

    @authorized_only
    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "🤖 *Claude Code Permission Bridge*\n\n"
            "I'll forward permission requests from Claude Code for your approval.\n\n"
            "*Commands:*\n"
            "/status - Show bridge status\n"
            "/sessions - Show active sessions\n"
            "/pending - Show pending permission requests\n"
            "/cancel - Cancel current reply mode",
            parse_mode="Markdown",
        )

    @authorized_only
    async def _cmd_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        pending_count = state.count()
        sessions_count = sessions.count()
        status_emoji = "🟢" if pending_count == 0 else "🟡"

        await update.message.reply_text(
            f"{status_emoji} *Bridge Status*\n\n"
            f"Active sessions: {sessions_count}\n"
            f"Pending requests: {pending_count}\n"
            f"Timeout: {settings.permission_timeout}s",
            parse_mode="Markdown",
        )

    @authorized_only
    async def _cmd_pending(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /pending command."""
        pending = state.all()

        if not pending:
            await update.message.reply_text("No pending requests.")
            return

        text = "*Pending Requests:*\n\n"
        for req in pending:
            cmd_short = req.command[:50] + "..." if len(req.command) > 50 else req.command
            text += f"• `{req.tool}`: `{cmd_short}`\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    @authorized_only
    async def _cmd_sessions(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /sessions command."""
        active = sessions.active()

        if not active:
            await update.message.reply_text("No active sessions.")
            return

        text = "*Active Sessions:*\n\n"
        for s in active:
            text += f"{s.status_emoji} `{s.session_id[:8]}...`\n"
            text += f"   📁 {s.display_cwd}\n"
            if s.status == "waiting_for_input" and s.last_message:
                msg_short = s.last_message[:100] + "..." if len(s.last_message) > 100 else s.last_message
                text += f"   💬 _{msg_short}_\n"
            text += "\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    @authorized_only
    async def _cmd_cancel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /cancel command - cancel reply mode."""
        chat_id = update.effective_chat.id
        if chat_id in self._reply_targets:
            del self._reply_targets[chat_id]
            await update.message.reply_text("✅ Reply mode cancelled.")
        else:
            await update.message.reply_text("No active reply mode.")

    @authorized_only
    async def _handle_text_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle text messages - send to target session if in reply mode."""
        chat_id = update.effective_chat.id

        if chat_id not in self._reply_targets:
            await update.message.reply_text(
                "💡 To send a message to a session, tap the *Reply* button "
                "on a session notification first.",
                parse_mode="Markdown"
            )
            return

        session_id = self._reply_targets[chat_id]
        session = sessions.get(session_id)

        if not session:
            del self._reply_targets[chat_id]
            await update.message.reply_text("⚠️ Session no longer exists.")
            return

        text = update.message.text
        success = session.send_input(text)

        if success:
            # Clear reply target after sending
            del self._reply_targets[chat_id]
            await update.message.reply_text(
                f"✅ Sent to session `{session_id[:8]}...`\n\n"
                f"```\n{text[:200]}\n```",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to send to session. TTY may be closed."
            )

    async def notify_session_start(self, session: Session) -> None:
        """Notify about a new session starting."""
        if not self.app:
            return

        text = (
            f"🆕 *New Session*\n\n"
            f"📁 `{session.display_cwd}`\n"
            f"🔑 `{session.session_id[:8]}...`"
        )

        try:
            await self.app.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to notify session start: {e}")

    async def notify_session_idle(self, session: Session) -> None:
        """Notify that a session is waiting for input."""
        if not self.app:
            return

        keyboard = [[
            InlineKeyboardButton(
                "📝 Reply",
                callback_data=f"reply:{session.session_id}"
            ),
        ]]

        # Truncate message for display
        msg_display = session.last_message or "No message"
        if len(msg_display) > 500:
            msg_display = msg_display[:500] + "..."

        text = (
            f"💬 *Session waiting for input*\n\n"
            f"📁 `{session.display_cwd}`\n\n"
            f"*Claude:*\n{msg_display}"
        )

        try:
            await self.app.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to notify session idle: {e}")

    async def notify_session_end(self, session: Session) -> None:
        """Notify that a session has ended."""
        if not self.app:
            return

        text = (
            f"✅ *Session ended*\n\n"
            f"📁 `{session.display_cwd}`"
        )

        try:
            await self.app.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to notify session end: {e}")

    @authorized_only
    async def _handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()

        data = query.data
        if ":" not in data:
            return

        action, target_id = data.split(":", 1)

        # Handle session reply action
        if action == "reply":
            session = sessions.get(target_id)
            if not session:
                await query.edit_message_text("⚠️ Session no longer exists.")
                return

            chat_id = update.effective_chat.id
            self._reply_targets[chat_id] = target_id

            await query.edit_message_text(
                f"📝 *Reply mode active*\n\n"
                f"📁 `{session.display_cwd}`\n\n"
                f"Type your message and I'll send it to this session.\n"
                f"Use /cancel to exit reply mode.",
                parse_mode="Markdown",
            )
            return

        # Handle permission actions
        request = state.get(target_id)
        if not request:
            await query.edit_message_text("⚠️ Request expired or already handled.")
            return

        if action == "allow_session":
            # Mark session for allow-all future requests
            if request.session_id:
                sessions.allow_session(request.session_id)
            request.decision = "allow"
            emoji = "✅"
            status = "Allowed (all session)"
        elif action == "allow":
            request.decision = "allow"
            emoji = "✅"
            status = "Allowed"
        else:
            request.decision = "deny"
            request.reason = "Denied via Telegram"
            emoji = "❌"
            status = "Denied"

        # Truncate command for final message
        cmd_short = request.command[:100] + "..." if len(request.command) > 100 else request.command

        await query.edit_message_text(
            f"{emoji} *{status}*\n\n"
            f"*Tool:* `{request.tool}`\n"
            f"*Command:* `{cmd_short}`",
            parse_mode="Markdown",
        )

        # Signal the waiting coroutine
        request.event.set()


bot = TelegramBot()
