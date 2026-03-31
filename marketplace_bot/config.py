"""
Configuration module for Marketplace Monitor Bot.
Uses Pydantic Settings for environment variable management.
"""

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot
    bot_token: str = Field(..., description="Telegram bot token from @BotFather")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./bot.db",
        description="Database connection URL",
    )

    # Proxy Settings
    http_proxy: Optional[str] = Field(
        default=None,
        description="HTTP proxy URL",
    )
    https_proxy: Optional[str] = Field(
        default=None,
        description="HTTPS proxy URL",
    )

    # Playwright Settings
    playwright_headless: bool = Field(
        default=True,
        description="Run Playwright in headless mode",
    )
    playwright_timeout: int = Field(
        default=30000,
        description="Playwright page load timeout in milliseconds",
    )

    # Scraping Settings
    request_timeout: int = Field(
        default=30,
        description="HTTP request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retries for failed requests",
    )
    retry_delay: int = Field(
        default=2,
        description="Delay between retries in seconds",
    )

    # Scheduler Settings
    parsing_interval_minutes: int = Field(
        default=5,
        description="Interval between parsing runs in minutes",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        """Validate bot token format."""
        if not v or v == "your_bot_token_here":
            raise ValueError("BOT_TOKEN must be set to a valid Telegram bot token")
        if ":" not in v:
            raise ValueError("BOT_TOKEN must be in format '123456:ABC-DEF...'")
        return v

    @field_validator("parsing_interval_minutes")
    @classmethod
    def validate_parsing_interval(cls, v: int) -> int:
        """Ensure parsing interval is reasonable."""
        if v < 1:
            raise ValueError("PARSING_INTERVAL_MINUTES must be at least 1")
        if v > 60:
            raise ValueError("PARSING_INTERVAL_MINUTES should not exceed 60")
        return v

    @property
    def proxy_dict(self) -> Optional[dict[str, str]]:
        """Return proxy configuration as dictionary for aiohttp."""
        if self.http_proxy or self.https_proxy:
            return {
                "http": self.http_proxy or self.https_proxy or "",
                "https": self.https_proxy or self.http_proxy or "",
            }
        return None

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL database."""
        return "postgresql" in self.database_url.lower()


# Global settings instance
settings = Settings()
