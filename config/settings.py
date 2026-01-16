"""
Configuration settings for Boss Workflow Automation System.
All sensitive values are loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Boss Workflow Automation"
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="production", env="ENVIRONMENT")

    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    webhook_base_url: str = Field(default="", env="WEBHOOK_BASE_URL")

    # Telegram
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    telegram_boss_chat_id: str = Field(default="", env="TELEGRAM_BOSS_CHAT_ID")

    # DeepSeek AI
    deepseek_api_key: str = Field(default="", env="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1", env="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", env="DEEPSEEK_MODEL")

    # Discord
    discord_webhook_url: str = Field(default="", env="DISCORD_WEBHOOK_URL")
    discord_tasks_channel_webhook: str = Field(default="", env="DISCORD_TASKS_CHANNEL_WEBHOOK")
    discord_standup_channel_webhook: str = Field(default="", env="DISCORD_STANDUP_CHANNEL_WEBHOOK")
    discord_bot_token: Optional[str] = Field(default=None, env="DISCORD_BOT_TOKEN")

    # Google Sheets
    google_credentials_json: str = Field(default="", env="GOOGLE_CREDENTIALS_JSON")
    google_sheet_id: str = Field(default="", env="GOOGLE_SHEET_ID")

    # Database (PostgreSQL)
    database_url: str = Field(default="", env="DATABASE_URL")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")

    # Scheduler Settings
    timezone: str = Field(default="America/New_York", env="TIMEZONE")
    daily_standup_hour: int = Field(default=9, env="DAILY_STANDUP_HOUR")
    eod_reminder_hour: int = Field(default=18, env="EOD_REMINDER_HOUR")
    weekly_summary_day: str = Field(default="friday", env="WEEKLY_SUMMARY_DAY")
    weekly_summary_hour: int = Field(default=17, env="WEEKLY_SUMMARY_HOUR")

    # Conversation Settings
    conversation_timeout_minutes: int = Field(default=30, env="CONVERSATION_TIMEOUT_MINUTES")
    auto_finalize_hours: int = Field(default=2, env="AUTO_FINALIZE_HOURS")

    # Reminder Settings
    deadline_reminder_hours_before: int = Field(default=2, env="DEADLINE_REMINDER_HOURS")
    overdue_alert_interval_hours: int = Field(default=4, env="OVERDUE_ALERT_INTERVAL_HOURS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the application settings."""
    return settings
