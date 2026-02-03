# Telegram ↔ Claude Code Permission Bridge

A daemon service that forwards Claude Code permission requests to Telegram for approval.

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   Claude Code   │────▶│   Bridge Service     │────▶│    Telegram     │
│                 │◀────│   (Python daemon)    │◀────│      Bot        │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
        │                         │
        │ Hook stdin/stdout       │ In-memory state
        │                         │ (pending requests)
        ▼                         ▼
   Permission                  FastAPI
   Decision                    Server
```

## Setup

### 1. Install dependencies

```bash
cd telegram-claude-bridge
uv sync
```

### 2. Create Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the bot token

### 3. Get your Chat ID

1. Message your new bot
2. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find your `chat.id` in the response

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

Or export directly:

```bash
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
```

### 5. Install Claude Code hooks

```bash
./hooks/install.sh
```

### 6. Start the bridge daemon

```bash
uv run telegram-claude-bridge
```

### 7. Start Claude Code

```bash
claude
```

## Usage

When Claude Code requests permission to execute a tool, you'll receive a Telegram message:

```
🔐 Permission Request

Tool: Bash
Command:
rm -rf node_modules

[✅ Allow]  [❌ Deny]
[✅ Allow All Session]
```

- **Allow** - Permit this single action
- **Deny** - Block this action
- **Allow All Session** - Allow all similar actions in this session

## Telegram Commands

- `/start` - Show welcome message
- `/status` - Show bridge status
- `/pending` - List pending requests

## API Endpoints

The bridge exposes a REST API:

- `GET /health` - Health check
- `POST /permission` - Request permission (used by hook)

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | Required |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | Required |
| `BRIDGE_HOST` | Host to bind to | `127.0.0.1` |
| `BRIDGE_PORT` | Port to listen on | `8765` |
| `PERMISSION_TIMEOUT` | Timeout in seconds | `300` |

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## License

MIT
