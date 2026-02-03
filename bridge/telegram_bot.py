"""Telegram bot for permission approvals."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from .config import settings
from .state import state, PendingRequest

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot that handles permission requests."""

    def __init__(self):
        self.app: Application | None = None
        self._initialized = False

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
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

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

    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "🤖 *Claude Code Permission Bridge*\n\n"
            "I'll forward permission requests from Claude Code for your approval.\n\n"
            "*Commands:*\n"
            "/status - Show bridge status\n"
            "/pending - Show pending requests",
            parse_mode="Markdown",
        )

    async def _cmd_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        pending_count = state.count()
        status_emoji = "🟢" if pending_count == 0 else "🟡"

        await update.message.reply_text(
            f"{status_emoji} *Bridge Status*\n\n"
            f"Pending requests: {pending_count}\n"
            f"Timeout: {settings.permission_timeout}s",
            parse_mode="Markdown",
        )

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

    async def _handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()

        data = query.data
        if ":" not in data:
            return

        action, request_id = data.split(":", 1)

        request = state.get(request_id)
        if not request:
            await query.edit_message_text("⚠️ Request expired or already handled.")
            return

        if action in ("allow", "allow_session"):
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
