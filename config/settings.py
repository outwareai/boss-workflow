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

    # OpenAI (for Whisper voice transcription)
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")

    # Discord Bot Configuration (Required - uses Bot API instead of webhooks)
    discord_bot_token: str = Field(default="", env="DISCORD_BOT_TOKEN")

    # Discord - Dev Category Channel IDs (Primary)
    # Forum for specs/detailed tasks (creates threads per task)
    discord_dev_forum_channel_id: str = Field(default="1459834094304104653", env="DISCORD_DEV_FORUM_CHANNEL_ID")
    # Tasks text channel for regular tasks, overdue, cancel notifications
    discord_dev_tasks_channel_id: str = Field(default="1461760665873158349", env="DISCORD_DEV_TASKS_CHANNEL_ID")
    # Report channel for standup and reports
    discord_dev_report_channel_id: str = Field(default="1461760697334632651", env="DISCORD_DEV_REPORT_CHANNEL_ID")
    # General messages channel
    discord_dev_general_channel_id: str = Field(default="1461760791719182590", env="DISCORD_DEV_GENERAL_CHANNEL_ID")

    # Discord - Admin Category Channel IDs (Future)
    discord_admin_forum_channel_id: str = Field(default="", env="DISCORD_ADMIN_FORUM_CHANNEL_ID")
    discord_admin_tasks_channel_id: str = Field(default="", env="DISCORD_ADMIN_TASKS_CHANNEL_ID")
    discord_admin_report_channel_id: str = Field(default="", env="DISCORD_ADMIN_REPORT_CHANNEL_ID")
    discord_admin_general_channel_id: str = Field(default="", env="DISCORD_ADMIN_GENERAL_CHANNEL_ID")

    # Discord - Marketing Category Channel IDs (Future)
    discord_marketing_forum_channel_id: str = Field(default="", env="DISCORD_MARKETING_FORUM_CHANNEL_ID")
    discord_marketing_tasks_channel_id: str = Field(default="", env="DISCORD_MARKETING_TASKS_CHANNEL_ID")
    discord_marketing_report_channel_id: str = Field(default="", env="DISCORD_MARKETING_REPORT_CHANNEL_ID")
    discord_marketing_general_channel_id: str = Field(default="", env="DISCORD_MARKETING_GENERAL_CHANNEL_ID")

    # Discord - Design Category Channel IDs (Future)
    discord_design_forum_channel_id: str = Field(default="", env="DISCORD_DESIGN_FORUM_CHANNEL_ID")
    discord_design_tasks_channel_id: str = Field(default="", env="DISCORD_DESIGN_TASKS_CHANNEL_ID")
    discord_design_report_channel_id: str = Field(default="", env="DISCORD_DESIGN_REPORT_CHANNEL_ID")
    discord_design_general_channel_id: str = Field(default="", env="DISCORD_DESIGN_GENERAL_CHANNEL_ID")

    # Legacy webhooks (deprecated - kept for backward compatibility)
    discord_webhook_url: str = Field(default="", env="DISCORD_WEBHOOK_URL")
    discord_tasks_channel_webhook: str = Field(default="", env="DISCORD_TASKS_CHANNEL_WEBHOOK")
    discord_standup_channel_webhook: str = Field(default="", env="DISCORD_STANDUP_CHANNEL_WEBHOOK")
    discord_specs_channel_webhook: str = Field(default="", env="DISCORD_SPECS_CHANNEL_WEBHOOK")

    # Google Sheets
    google_credentials_json: str = Field(default="", env="GOOGLE_CREDENTIALS_JSON")
    google_sheet_id: str = Field(default="", env="GOOGLE_SHEET_ID")

    # Database (PostgreSQL)
    database_url: str = Field(default="", env="DATABASE_URL")

    # Redis (optional - set empty to disable)
    redis_url: str = Field(default="", env="REDIS_URL")

    # Scheduler Settings
    timezone: str = Field(default="Asia/Bangkok", env="TIMEZONE")
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

    # Auto-Review Settings
    submission_quality_threshold: int = Field(default=70, env="SUBMISSION_QUALITY_THRESHOLD")
    enable_auto_review: bool = Field(default=True, env="ENABLE_AUTO_REVIEW")
    require_notes_for_submission: bool = Field(default=True, env="REQUIRE_NOTES_FOR_SUBMISSION")

    # Google Calendar
    google_calendar_id: str = Field(default="primary", env="GOOGLE_CALENDAR_ID")

    # Gmail / Email Digest Settings
    gmail_user_email: str = Field(default="corporationout@gmail.com", env="GMAIL_USER_EMAIL")
    gmail_oauth_credentials: str = Field(default="", env="GMAIL_OAUTH_CREDENTIALS")
    gmail_oauth_token: str = Field(default="", env="GMAIL_OAUTH_TOKEN")  # OAuth token JSON
    enable_email_digest: bool = Field(default=False, env="ENABLE_EMAIL_DIGEST")
    morning_digest_hour: int = Field(default=10, env="MORNING_DIGEST_HOUR")
    evening_digest_hour: int = Field(default=21, env="EVENING_DIGEST_HOUR")
    morning_digest_hours_back: int = Field(default=12, env="MORNING_DIGEST_HOURS_BACK")
    evening_digest_hours_back: int = Field(default=11, env="EVENING_DIGEST_HOURS_BACK")

    # Google Drive Settings
    enable_drive_storage: bool = Field(default=True, env="ENABLE_DRIVE_STORAGE")
    drive_folder_id: str = Field(default="", env="DRIVE_FOLDER_ID")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the application settings."""
    return settings
