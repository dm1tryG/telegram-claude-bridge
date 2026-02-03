"""Configuration management for the bridge service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Bridge configuration loaded from environment variables."""

    telegram_bot_token: str
    telegram_chat_id: int
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8765
    permission_timeout: int = 300  # 5 minutes

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
