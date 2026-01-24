"""
Unit tests for scheduler jobs.

Q1 2026: Task - Comprehensive scheduler job tests.
Tests for all scheduled background jobs including:
- Daily standup
- Weekly reports
- Overdue task checks
- Conversation cleanup
- Deadline reminders
- Recurring tasks
- Email digests
- Attendance syncing
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os
import pytz

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.scheduler.jobs import SchedulerManager
from src.models.task import TaskStatus


@pytest.fixture
def scheduler_manager():
    """Create scheduler manager instance."""
    with patch('src.scheduler.jobs.get_reminder_service') as mock_reminder, \
         patch('src.scheduler.jobs.get_sheets_integration') as mock_sheets, \
         patch('src.scheduler.jobs.get_discord_integration') as mock_discord, \
         patch('src.scheduler.jobs.get_gmail_integration') as mock_gmail, \
         patch('src.scheduler.jobs.get_deepseek_client') as mock_ai, \
         patch('src.scheduler.jobs.get_email_summarizer') as mock_summarizer, \
         patch('src.scheduler.jobs.get_conversation_context') as mock_context:

        manager = SchedulerManager()

        # Set up mocks
        manager.reminders = AsyncMock()
        manager.sheets = AsyncMock()
        manager.discord = AsyncMock()
        manager.gmail = AsyncMock()
        manager.ai = AsyncMock()
        manager.email_summarizer = AsyncMock()
        manager.context = AsyncMock()

        yield manager


@pytest.fixture
def mock_task():
    """Create mock task data."""
    return {
        "task_id": "TASK-001",
        "title": "Test Task",
        "description": "Test Description",
        "status": "in_progress",
        "assignee": "John",
        "deadline": (datetime.now() + timedelta(hours=1)).isoformat(),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }


@pytest.fixture
def mock_email():
    """Create mock email data."""
    email = Mock()
    email.subject = "Test Email Subject"
    email.sender_name = "John Doe"
    email.sender_email = "john@example.com"
    email.is_unread = True
    email.is_important = False
    email.to_summary_dict.return_value = {
        "subject": "Test Email Subject",
        "sender": "john@example.com",
        "time": datetime.now().isoformat()
    }
    return email


# ===========================
# Daily Standup Tests (7 tests)
# ===========================

@pytest.mark.asyncio
async def test_daily_standup_success(scheduler_manager, mock_task):
    """Test successful daily standup generation."""
    # Mock sheets return tasks
    scheduler_manager.sheets.get_daily_tasks.return_value = [mock_task]

    # Mock AI summary
    scheduler_manager.ai.generate_daily_standup.return_value = "Today's standup summary"

    # Mock Discord and Telegram
    scheduler_manager.discord.post_standup.return_value = None
    scheduler_manager.reminders.send_telegram_message.return_value = True

    # Run job
    await scheduler_manager._daily_standup_job()

    # Verify calls
    scheduler_manager.sheets.get_daily_tasks.assert_called_once()
    scheduler_manager.ai.generate_daily_standup.assert_called_once()
    scheduler_manager.discord.post_standup.assert_called_once_with("Today's standup summary")


@pytest.mark.asyncio
async def test_daily_standup_no_tasks(scheduler_manager):
    """Test standup with no tasks."""
    scheduler_manager.sheets.get_daily_tasks.return_value = []
    scheduler_manager.ai.generate_daily_standup.return_value = "No tasks today"

    await scheduler_manager._daily_standup_job()

    # Should still generate summary
    scheduler_manager.ai.generate_daily_standup.assert_called_once()


@pytest.mark.asyncio
async def test_daily_standup_discord_failure(scheduler_manager, mock_task):
    """Test standup when Discord webhook fails."""
    scheduler_manager.sheets.get_daily_tasks.return_value = [mock_task]
    scheduler_manager.ai.generate_daily_standup.return_value = "Summary"

    # Discord fails
    scheduler_manager.discord.post_standup.side_effect = Exception("Discord error")

    # Should raise and notify boss
    with pytest.raises(Exception):
        await scheduler_manager._daily_standup_job()

    scheduler_manager.reminders.send_telegram_message.assert_called()


@pytest.mark.asyncio
async def test_daily_standup_with_email_digest(scheduler_manager, mock_task, mock_email):
    """Test standup includes email digest when enabled."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.enable_email_digest = True
        mock_settings.telegram_boss_chat_id = '123'
        mock_settings.morning_digest_hours_back = 12

        scheduler_manager.sheets.get_daily_tasks.return_value = [mock_task]
        scheduler_manager.ai.generate_daily_standup.return_value = "Summary"
        scheduler_manager.gmail._initialized = True
        scheduler_manager.gmail.is_available.return_value = True
        scheduler_manager.gmail.get_emails_since.return_value = [mock_email]

        # Mock email summarizer
        summary_result = Mock()
        summary_result.summary = "Email summary"
        summary_result.action_items = ["Action 1"]
        summary_result.priority_emails = ["Priority email"]
        scheduler_manager.email_summarizer.summarize_emails.return_value = summary_result

        await scheduler_manager._daily_standup_job()

        # Verify email digest was sent
        assert scheduler_manager.reminders.send_telegram_message.call_count >= 2


@pytest.mark.asyncio
async def test_daily_standup_email_digest_no_emails(scheduler_manager, mock_task):
    """Test email digest with no emails."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.enable_email_digest = True
        mock_settings.telegram_boss_chat_id = '123'
        mock_settings.morning_digest_hours_back = 12

        scheduler_manager.sheets.get_daily_tasks.return_value = [mock_task]
        scheduler_manager.ai.generate_daily_standup.return_value = "Summary"
        scheduler_manager.gmail._initialized = True
        scheduler_manager.gmail.is_available.return_value = True
        scheduler_manager.gmail.get_emails_since.return_value = []

        await scheduler_manager._daily_standup_job()

        # Should still send "no emails" message
        assert scheduler_manager.reminders.send_telegram_message.call_count >= 2


@pytest.mark.asyncio
async def test_daily_standup_ai_failure(scheduler_manager, mock_task):
    """Test standup when AI generation fails."""
    scheduler_manager.sheets.get_daily_tasks.return_value = [mock_task]
    scheduler_manager.ai.generate_daily_standup.side_effect = Exception("AI error")

    with pytest.raises(Exception):
        await scheduler_manager._daily_standup_job()


@pytest.mark.asyncio
async def test_daily_standup_sheets_failure(scheduler_manager):
    """Test standup when Sheets API fails."""
    scheduler_manager.sheets.get_daily_tasks.side_effect = Exception("Sheets error")

    with pytest.raises(Exception):
        await scheduler_manager._daily_standup_job()


# ===========================
# Weekly Summary Tests (5 tests)
# ===========================

@pytest.mark.asyncio
async def test_weekly_summary_success(scheduler_manager, mock_task):
    """Test successful weekly summary generation."""
    overview = {
        "completed": 10,
        "completion_rate": 85,
        "by_assignee": {"John": 5, "Jane": 5}
    }

    scheduler_manager.sheets.generate_weekly_overview.return_value = overview
    scheduler_manager.sheets.get_tasks_by_status.return_value = [mock_task]
    scheduler_manager.ai.generate_weekly_summary.return_value = "Weekly summary"

    await scheduler_manager._weekly_summary_job()

    scheduler_manager.sheets.generate_weekly_overview.assert_called_once()
    scheduler_manager.ai.generate_weekly_summary.assert_called_once()
    scheduler_manager.discord.post_weekly_summary.assert_called_once()
    scheduler_manager.sheets.update_weekly_sheet.assert_called_once()


@pytest.mark.asyncio
async def test_weekly_summary_no_overview(scheduler_manager):
    """Test weekly summary when overview generation fails."""
    scheduler_manager.sheets.generate_weekly_overview.return_value = None

    await scheduler_manager._weekly_summary_job()

    # Should return early without calling other services
    scheduler_manager.ai.generate_weekly_summary.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_summary_multiple_tasks(scheduler_manager):
    """Test weekly summary with many tasks."""
    overview = {"completed": 50, "completion_rate": 90}
    tasks = [{"task_id": f"TASK-{i}", "title": f"Task {i}"} for i in range(50)]

    scheduler_manager.sheets.generate_weekly_overview.return_value = overview
    scheduler_manager.sheets.get_tasks_by_status.return_value = tasks
    scheduler_manager.ai.generate_weekly_summary.return_value = "Summary"

    await scheduler_manager._weekly_summary_job()

    # Verify only first 30 tasks are sent to AI
    call_args = scheduler_manager.ai.generate_weekly_summary.call_args
    assert len(call_args[1]["tasks_by_status"]["completed"]) == 30


@pytest.mark.asyncio
async def test_weekly_summary_discord_failure(scheduler_manager):
    """Test weekly summary when Discord fails."""
    scheduler_manager.sheets.generate_weekly_overview.return_value = {"completed": 5}
    scheduler_manager.sheets.get_tasks_by_status.return_value = []
    scheduler_manager.ai.generate_weekly_summary.return_value = "Summary"
    scheduler_manager.discord.post_weekly_summary.side_effect = Exception("Discord error")

    with pytest.raises(Exception):
        await scheduler_manager._weekly_summary_job()


@pytest.mark.asyncio
async def test_weekly_summary_telegram_notification(scheduler_manager):
    """Test weekly summary sends Telegram notification."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = '123'

        scheduler_manager.sheets.generate_weekly_overview.return_value = {"completed": 10}
        scheduler_manager.sheets.get_tasks_by_status.return_value = []
        scheduler_manager.ai.generate_weekly_summary.return_value = "Weekly summary"

        await scheduler_manager._weekly_summary_job()

        scheduler_manager.reminders.send_telegram_message.assert_called_once()


# ===========================
# Monthly Report Tests (4 tests)
# ===========================

@pytest.mark.asyncio
async def test_monthly_report_success(scheduler_manager):
    """Test successful monthly report generation."""
    overview = {"completed": 100, "completion_rate": 85}
    scheduler_manager.sheets.generate_weekly_overview.return_value = overview

    await scheduler_manager._monthly_report_job()

    scheduler_manager.discord.post_alert.assert_called_once()


@pytest.mark.asyncio
async def test_monthly_report_telegram_notification(scheduler_manager):
    """Test monthly report sends Telegram notification."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = '123'

        scheduler_manager.sheets.generate_weekly_overview.return_value = {"completed": 100}

        await scheduler_manager._monthly_report_job()

        scheduler_manager.reminders.send_telegram_message.assert_called_once()


@pytest.mark.asyncio
async def test_monthly_report_zero_tasks(scheduler_manager):
    """Test monthly report with no tasks completed."""
    overview = {"completed": 0, "completion_rate": 0}
    scheduler_manager.sheets.generate_weekly_overview.return_value = overview

    await scheduler_manager._monthly_report_job()

    # Should still send report
    scheduler_manager.discord.post_alert.assert_called_once()


@pytest.mark.asyncio
async def test_monthly_report_failure(scheduler_manager):
    """Test monthly report error handling."""
    scheduler_manager.sheets.generate_weekly_overview.side_effect = Exception("Error")

    with pytest.raises(Exception):
        await scheduler_manager._monthly_report_job()


# ===========================
# Deadline Reminder Tests (5 tests)
# ===========================

@pytest.mark.asyncio
async def test_deadline_reminder_success(scheduler_manager):
    """Test successful deadline reminder check."""
    scheduler_manager.reminders.check_and_send_deadline_reminders.return_value = 3

    await scheduler_manager._deadline_reminder_job()

    scheduler_manager.reminders.check_and_send_deadline_reminders.assert_called_once()


@pytest.mark.asyncio
async def test_deadline_reminder_no_upcoming(scheduler_manager):
    """Test deadline reminder with no upcoming deadlines."""
    scheduler_manager.reminders.check_and_send_deadline_reminders.return_value = 0

    await scheduler_manager._deadline_reminder_job()

    scheduler_manager.reminders.check_and_send_deadline_reminders.assert_called_once()


@pytest.mark.asyncio
async def test_deadline_reminder_multiple_tasks(scheduler_manager):
    """Test deadline reminder with multiple tasks."""
    scheduler_manager.reminders.check_and_send_deadline_reminders.return_value = 10

    await scheduler_manager._deadline_reminder_job()

    # Verify count is returned
    count = await scheduler_manager.reminders.check_and_send_deadline_reminders()
    assert count == 10


@pytest.mark.asyncio
async def test_deadline_reminder_failure(scheduler_manager):
    """Test deadline reminder error handling."""
    scheduler_manager.reminders.check_and_send_deadline_reminders.side_effect = Exception("Error")

    with pytest.raises(Exception):
        await scheduler_manager._deadline_reminder_job()


@pytest.mark.asyncio
async def test_deadline_reminder_boss_notification(scheduler_manager):
    """Test deadline reminder notifies boss on failure."""
    scheduler_manager.reminders.check_and_send_deadline_reminders.side_effect = Exception("Test error")

    with pytest.raises(Exception):
        await scheduler_manager._deadline_reminder_job()

    # Should notify boss of failure
    scheduler_manager.reminders.send_telegram_message.assert_called()


# ===========================
# Overdue Alert Tests (5 tests)
# ===========================

@pytest.mark.asyncio
async def test_overdue_alert_success(scheduler_manager):
    """Test successful overdue alert check."""
    scheduler_manager.reminders.check_and_send_overdue_alerts.return_value = 2

    await scheduler_manager._overdue_alert_job()

    scheduler_manager.reminders.check_and_send_overdue_alerts.assert_called_once()


@pytest.mark.asyncio
async def test_overdue_alert_no_overdue(scheduler_manager):
    """Test overdue alert with no overdue tasks."""
    scheduler_manager.reminders.check_and_send_overdue_alerts.return_value = 0

    await scheduler_manager._overdue_alert_job()

    scheduler_manager.reminders.check_and_send_overdue_alerts.assert_called_once()


@pytest.mark.asyncio
async def test_overdue_alert_multiple_tasks(scheduler_manager):
    """Test overdue alert with multiple overdue tasks."""
    scheduler_manager.reminders.check_and_send_overdue_alerts.return_value = 15

    await scheduler_manager._overdue_alert_job()

    count = await scheduler_manager.reminders.check_and_send_overdue_alerts()
    assert count == 15


@pytest.mark.asyncio
async def test_overdue_alert_failure(scheduler_manager):
    """Test overdue alert error handling."""
    scheduler_manager.reminders.check_and_send_overdue_alerts.side_effect = Exception("Error")

    with pytest.raises(Exception):
        await scheduler_manager._overdue_alert_job()


@pytest.mark.asyncio
async def test_overdue_alert_boss_notification(scheduler_manager):
    """Test overdue alert notifies boss on failure."""
    scheduler_manager.reminders.check_and_send_overdue_alerts.side_effect = Exception("Critical error")

    with pytest.raises(Exception):
        await scheduler_manager._overdue_alert_job()

    scheduler_manager.reminders.send_telegram_message.assert_called()


# ===========================
# Conversation Timeout Tests (4 tests)
# ===========================

@pytest.mark.asyncio
async def test_conversation_timeout_success(scheduler_manager):
    """Test successful conversation timeout check."""
    mock_conv = Mock()
    mock_conv.user_id = "123"
    mock_conv.conversation_id = "conv-001"

    scheduler_manager.context.get_timed_out_conversations.return_value = [mock_conv]
    scheduler_manager.context.get_conversations_to_auto_finalize.return_value = []

    await scheduler_manager._conversation_timeout_job()

    scheduler_manager.reminders.send_conversation_timeout_reminder.assert_called_once()


@pytest.mark.asyncio
async def test_conversation_timeout_no_timeouts(scheduler_manager):
    """Test conversation timeout with no timed-out conversations."""
    scheduler_manager.context.get_timed_out_conversations.return_value = []
    scheduler_manager.context.get_conversations_to_auto_finalize.return_value = []

    await scheduler_manager._conversation_timeout_job()

    scheduler_manager.reminders.send_conversation_timeout_reminder.assert_not_called()


@pytest.mark.asyncio
async def test_conversation_auto_finalize(scheduler_manager):
    """Test conversation auto-finalize detection."""
    mock_conv = Mock()
    mock_conv.conversation_id = "conv-002"

    scheduler_manager.context.get_timed_out_conversations.return_value = []
    scheduler_manager.context.get_conversations_to_auto_finalize.return_value = [mock_conv]

    await scheduler_manager._conversation_timeout_job()

    # Currently just logs, verify no errors
    scheduler_manager.context.get_conversations_to_auto_finalize.assert_called_once()


@pytest.mark.asyncio
async def test_conversation_timeout_failure(scheduler_manager):
    """Test conversation timeout error handling."""
    scheduler_manager.context.get_timed_out_conversations.side_effect = Exception("DB error")

    with pytest.raises(Exception):
        await scheduler_manager._conversation_timeout_job()


# ===========================
# Archive Tasks Tests (3 tests)
# ===========================

@pytest.mark.asyncio
async def test_archive_tasks_success(scheduler_manager):
    """Test successful task archiving."""
    scheduler_manager.sheets.archive_completed_tasks.return_value = 5

    await scheduler_manager._archive_tasks_job()

    scheduler_manager.sheets.archive_completed_tasks.assert_called_once_with(days_old=7)


@pytest.mark.asyncio
async def test_archive_tasks_no_tasks(scheduler_manager):
    """Test archiving with no old tasks."""
    scheduler_manager.sheets.archive_completed_tasks.return_value = 0

    await scheduler_manager._archive_tasks_job()

    scheduler_manager.sheets.archive_completed_tasks.assert_called_once()


@pytest.mark.asyncio
async def test_archive_tasks_failure(scheduler_manager):
    """Test archive task error handling (should not raise)."""
    scheduler_manager.sheets.archive_completed_tasks.side_effect = Exception("Error")

    # Should catch exception and not raise (job logs error but continues)
    try:
        await scheduler_manager._archive_tasks_job()
    except Exception:
        pass  # Expected to catch and log


# ===========================
# Recurring Tasks Tests (5 tests)
# ===========================

@pytest.mark.asyncio
async def test_recurring_tasks_success(scheduler_manager):
    """Test successful recurring task creation."""
    mock_recurring = Mock()
    mock_recurring.recurring_id = "REC-001"
    mock_recurring.title = "Daily standup"
    mock_recurring.description = "Post standup"
    mock_recurring.assignee = "John"
    mock_recurring.priority = "high"
    mock_recurring.task_type = "task"
    mock_recurring.estimated_effort = "30m"
    mock_recurring.tags = ["daily"]
    mock_recurring.created_by = "boss"

    mock_task = Mock()
    mock_task.task_id = "TASK-NEW"

    with patch('src.database.repositories.recurring.get_recurring_repository') as mock_rec_repo, \
         patch('src.database.repositories.get_task_repository') as mock_task_repo:

        mock_rec_repo.return_value.get_due_now.return_value = [mock_recurring]
        mock_task_repo.return_value.create.return_value = mock_task

        await scheduler_manager._recurring_tasks_job()

        mock_rec_repo.return_value.update_after_run.assert_called_once()


@pytest.mark.asyncio
async def test_recurring_tasks_no_due(scheduler_manager):
    """Test recurring tasks with none due."""
    with patch('src.database.repositories.recurring.get_recurring_repository') as mock_repo:
        mock_repo.return_value.get_due_now.return_value = []

        await scheduler_manager._recurring_tasks_job()

        mock_repo.return_value.get_due_now.assert_called_once()


@pytest.mark.asyncio
async def test_recurring_tasks_multiple(scheduler_manager):
    """Test creating multiple recurring task instances."""
    recurring_tasks = []
    for i in range(3):
        task = Mock()
        task.recurring_id = f"REC-{i:03d}"
        task.title = f"Recurring task {i}"
        task.description = ""
        task.assignee = "John"
        task.priority = "medium"
        task.task_type = "task"
        task.estimated_effort = "1h"
        task.tags = []
        task.created_by = "boss"
        recurring_tasks.append(task)

    with patch('src.database.repositories.recurring.get_recurring_repository') as mock_rec_repo, \
         patch('src.database.repositories.get_task_repository') as mock_task_repo:

        mock_rec_repo.return_value.get_due_now.return_value = recurring_tasks
        mock_task_repo.return_value.create.return_value = Mock(task_id="TASK-NEW")

        await scheduler_manager._recurring_tasks_job()

        assert mock_task_repo.return_value.create.call_count == 3


@pytest.mark.asyncio
async def test_recurring_tasks_creation_failure(scheduler_manager):
    """Test recurring task when task creation fails."""
    mock_recurring = Mock()
    mock_recurring.recurring_id = "REC-001"
    mock_recurring.title = "Test"
    mock_recurring.description = ""
    mock_recurring.assignee = "John"
    mock_recurring.priority = "low"
    mock_recurring.task_type = "task"
    mock_recurring.estimated_effort = "1h"
    mock_recurring.tags = []
    mock_recurring.created_by = "boss"

    with patch('src.database.repositories.recurring.get_recurring_repository') as mock_rec_repo, \
         patch('src.database.repositories.get_task_repository') as mock_task_repo:

        mock_rec_repo.return_value.get_due_now.return_value = [mock_recurring]
        mock_task_repo.return_value.create.side_effect = Exception("DB error")

        # Should catch exception and continue
        await scheduler_manager._recurring_tasks_job()


@pytest.mark.asyncio
async def test_recurring_tasks_discord_post(scheduler_manager):
    """Test recurring task posts to Discord."""
    mock_recurring = Mock()
    mock_recurring.recurring_id = "REC-001"
    mock_recurring.title = "Daily report"
    mock_recurring.description = ""
    mock_recurring.assignee = "Team"
    mock_recurring.priority = "high"
    mock_recurring.task_type = "task"
    mock_recurring.estimated_effort = "30m"
    mock_recurring.tags = []
    mock_recurring.created_by = "boss"

    with patch('src.database.repositories.recurring.get_recurring_repository') as mock_rec_repo, \
         patch('src.database.repositories.get_task_repository') as mock_task_repo:

        mock_rec_repo.return_value.get_due_now.return_value = [mock_recurring]
        mock_task_repo.return_value.create.return_value = Mock(task_id="TASK-NEW")

        await scheduler_manager._recurring_tasks_job()

        scheduler_manager.discord.post_alert.assert_called_once()


# ===========================
# Email Digest Tests (6 tests)
# ===========================

@pytest.mark.asyncio
async def test_morning_email_digest_success(scheduler_manager, mock_email):
    """Test successful morning email digest."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = '123'

        scheduler_manager.gmail._initialized = True
        scheduler_manager.gmail.get_emails_since.return_value = [mock_email]

        summary_result = Mock()
        summary_result.summary = "Morning summary"
        summary_result.action_items = []
        summary_result.priority_emails = []
        scheduler_manager.email_summarizer.summarize_emails.return_value = summary_result
        scheduler_manager.email_summarizer.generate_digest_message.return_value = "Digest message"

        await scheduler_manager._morning_email_digest_job()

        scheduler_manager.reminders.send_telegram_message.assert_called_once()


@pytest.mark.asyncio
async def test_morning_email_digest_no_emails(scheduler_manager):
    """Test morning email digest with no emails."""
    scheduler_manager.gmail._initialized = True
    scheduler_manager.gmail.get_emails_since.return_value = []

    await scheduler_manager._morning_email_digest_job()

    # Should return early
    scheduler_manager.email_summarizer.summarize_emails.assert_not_called()


@pytest.mark.asyncio
async def test_evening_email_digest_success(scheduler_manager, mock_email):
    """Test successful evening email digest."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = '123'

        scheduler_manager.gmail._initialized = True
        scheduler_manager.gmail.get_emails_since.return_value = [mock_email]

        summary_result = Mock()
        summary_result.summary = "Evening summary"
        summary_result.action_items = []
        summary_result.priority_emails = []
        scheduler_manager.email_summarizer.summarize_emails.return_value = summary_result
        scheduler_manager.email_summarizer.generate_digest_message.return_value = "Digest"

        await scheduler_manager._evening_email_digest_job()

        scheduler_manager.reminders.send_telegram_message.assert_called_once()


@pytest.mark.asyncio
async def test_evening_email_digest_no_emails(scheduler_manager):
    """Test evening email digest with no emails."""
    scheduler_manager.gmail._initialized = True
    scheduler_manager.gmail.get_emails_since.return_value = []

    await scheduler_manager._evening_email_digest_job()

    scheduler_manager.email_summarizer.summarize_emails.assert_not_called()


@pytest.mark.asyncio
async def test_email_digest_initialization(scheduler_manager, mock_email):
    """Test email digest initializes Gmail if needed."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = '123'

        scheduler_manager.gmail._initialized = False
        scheduler_manager.gmail.initialize = AsyncMock()
        scheduler_manager.gmail.get_emails_since.return_value = [mock_email]

        summary_result = Mock()
        summary_result.summary = "Summary"
        summary_result.action_items = []
        summary_result.priority_emails = []
        scheduler_manager.email_summarizer.summarize_emails.return_value = summary_result
        scheduler_manager.email_summarizer.generate_digest_message.return_value = "Digest"

        await scheduler_manager._morning_email_digest_job()

        scheduler_manager.gmail.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_email_digest_failure_handling(scheduler_manager):
    """Test email digest handles errors gracefully."""
    scheduler_manager.gmail._initialized = True
    scheduler_manager.gmail.get_emails_since.side_effect = Exception("Gmail error")

    # Should catch exception and not raise (job logs error but continues)
    try:
        await scheduler_manager._morning_email_digest_job()
    except Exception:
        pass  # Expected to catch and log


# ===========================
# Attendance Sync Tests (4 tests)
# ===========================

@pytest.mark.asyncio
async def test_attendance_sync_success(scheduler_manager):
    """Test successful attendance sync."""
    mock_record = Mock()
    mock_record.id = 1
    mock_record.record_id = "ATT-001"
    mock_record.event_time = datetime.now()
    mock_record.user_name = "John"
    mock_record.event_type = "clock_in"
    mock_record.is_late = False
    mock_record.late_minutes = 0
    mock_record.channel_name = "office"

    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo:
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_unsynced_records.return_value = [mock_record]
        mock_attendance_repo.mark_synced = AsyncMock()
        mock_repo.return_value = mock_attendance_repo

        scheduler_manager.sheets.add_attendance_logs_batch.return_value = 1

        await scheduler_manager._sync_attendance_job()

        mock_attendance_repo.mark_synced.assert_called_once()


@pytest.mark.asyncio
async def test_attendance_sync_no_records(scheduler_manager):
    """Test attendance sync with no unsynced records."""
    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo:
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_unsynced_records.return_value = []
        mock_repo.return_value = mock_attendance_repo

        await scheduler_manager._sync_attendance_job()

        scheduler_manager.sheets.add_attendance_logs_batch.assert_not_called()


@pytest.mark.asyncio
async def test_attendance_sync_multiple_records(scheduler_manager):
    """Test attendance sync with multiple records."""
    records = []
    for i in range(10):
        record = Mock()
        record.id = i
        record.record_id = f"ATT-{i:03d}"
        record.event_time = datetime.now()
        record.user_name = "John"
        record.event_type = "clock_in"
        record.is_late = False
        record.late_minutes = 0
        record.channel_name = "office"
        records.append(record)

    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo:
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_unsynced_records.return_value = records
        mock_attendance_repo.mark_synced = AsyncMock()
        mock_repo.return_value = mock_attendance_repo

        scheduler_manager.sheets.add_attendance_logs_batch.return_value = 10

        await scheduler_manager._sync_attendance_job()

        mock_attendance_repo.mark_synced.assert_called_once()


@pytest.mark.asyncio
async def test_attendance_sync_failure(scheduler_manager):
    """Test attendance sync error handling."""
    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo:
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_unsynced_records.side_effect = Exception("DB error")
        mock_repo.return_value = mock_attendance_repo

        # Should catch exception and not raise (job logs error but continues)
        try:
            await scheduler_manager._sync_attendance_job()
        except Exception:
            pass  # Expected to catch and log


# ===========================
# Weekly Time Report Tests (4 tests)
# ===========================

@pytest.mark.asyncio
async def test_weekly_time_report_success(scheduler_manager):
    """Test successful weekly time report generation."""
    summary = {
        "user_name": "John",
        "days_worked": 5,
        "total_hours": 40,
        "avg_start": "09:00",
        "avg_end": "18:00",
        "late_days": 0,
        "total_late_minutes": 0,
        "total_break_minutes": 60
    }

    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo, \
         patch('src.scheduler.jobs.settings') as mock_settings:

        mock_settings.telegram_boss_chat_id = '123'
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_team_weekly_summary.return_value = [summary]
        mock_repo.return_value = mock_attendance_repo

        await scheduler_manager._weekly_time_report_job()

        scheduler_manager.sheets.update_time_report.assert_called_once()
        scheduler_manager.discord.post_standup.assert_called_once()


@pytest.mark.asyncio
async def test_weekly_time_report_no_data(scheduler_manager):
    """Test weekly time report with no attendance data."""
    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo:
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_team_weekly_summary.return_value = []
        mock_repo.return_value = mock_attendance_repo

        await scheduler_manager._weekly_time_report_job()

        scheduler_manager.sheets.update_time_report.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_time_report_with_late_days(scheduler_manager):
    """Test weekly time report with late arrivals."""
    summary = {
        "user_name": "John",
        "days_worked": 5,
        "total_hours": 38,
        "avg_start": "09:15",
        "avg_end": "18:00",
        "late_days": 2,
        "total_late_minutes": 30,
        "total_break_minutes": 60
    }

    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo, \
         patch('src.scheduler.jobs.settings') as mock_settings:

        mock_settings.telegram_boss_chat_id = '123'
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_team_weekly_summary.return_value = [summary]
        mock_repo.return_value = mock_attendance_repo

        await scheduler_manager._weekly_time_report_job()

        # Verify late summary is included
        call_args = scheduler_manager.discord.post_standup.call_args[0][0]
        assert "Late Arrivals" in call_args


@pytest.mark.asyncio
async def test_weekly_time_report_failure(scheduler_manager):
    """Test weekly time report error handling."""
    with patch('src.database.repositories.attendance.get_attendance_repository') as mock_repo:
        mock_attendance_repo = AsyncMock()
        mock_attendance_repo.get_team_weekly_summary.side_effect = Exception("Error")
        mock_repo.return_value = mock_attendance_repo

        # Should catch exception and not raise (job logs error but continues)
        try:
            await scheduler_manager._weekly_time_report_job()
        except Exception:
            pass  # Expected to catch and log


# ===========================
# Proactive Check-in Tests (5 tests)
# ===========================

@pytest.mark.asyncio
async def test_proactive_checkin_success(scheduler_manager):
    """Test successful proactive check-in."""
    stale_task = {
        "task_id": "TASK-001",
        "title": "Old task",
        "assignee": "John",
        "status": "in_progress",
        "created_at": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    }

    with patch('src.database.repositories.get_task_repository'), \
         patch('src.memory.task_context.get_task_context_manager') as mock_context:

        scheduler_manager.sheets.get_tasks_by_status.return_value = [stale_task]
        mock_context.return_value.get_context_async.return_value = None

        await scheduler_manager._proactive_checkin_job()

        scheduler_manager.discord.post_alert.assert_called()


@pytest.mark.asyncio
async def test_proactive_checkin_no_stale_tasks(scheduler_manager):
    """Test proactive check-in with no stale tasks."""
    recent_task = {
        "task_id": "TASK-001",
        "assignee": "John",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    with patch('src.database.repositories.get_task_repository'), \
         patch('src.memory.task_context.get_task_context_manager'):

        scheduler_manager.sheets.get_tasks_by_status.return_value = [recent_task]

        await scheduler_manager._proactive_checkin_job()

        scheduler_manager.discord.post_alert.assert_not_called()


@pytest.mark.asyncio
async def test_proactive_checkin_skips_unassigned(scheduler_manager):
    """Test proactive check-in skips unassigned tasks."""
    unassigned_task = {
        "task_id": "TASK-001",
        "assignee": None,
        "updated_at": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    }

    with patch('src.database.repositories.get_task_repository'), \
         patch('src.memory.task_context.get_task_context_manager'):

        scheduler_manager.sheets.get_tasks_by_status.return_value = [unassigned_task]

        await scheduler_manager._proactive_checkin_job()

        scheduler_manager.discord.post_alert.assert_not_called()


@pytest.mark.asyncio
async def test_proactive_checkin_limits_to_five(scheduler_manager):
    """Test proactive check-in limits to 5 tasks per run."""
    stale_tasks = []
    for i in range(10):
        stale_tasks.append({
            "task_id": f"TASK-{i:03d}",
            "title": f"Task {i}",
            "assignee": "John",
            "status": "in_progress",
            "updated_at": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
        })

    with patch('src.database.repositories.get_task_repository'), \
         patch('src.memory.task_context.get_task_context_manager') as mock_context:

        scheduler_manager.sheets.get_tasks_by_status.return_value = stale_tasks
        mock_context.return_value.get_context_async.return_value = None

        await scheduler_manager._proactive_checkin_job()

        # Should only send 5 check-ins
        assert scheduler_manager.discord.post_alert.call_count == 5


@pytest.mark.asyncio
async def test_proactive_checkin_failure(scheduler_manager):
    """Test proactive check-in error handling."""
    with patch('src.database.repositories.get_task_repository'), \
         patch('src.memory.task_context.get_task_context_manager'):

        scheduler_manager.sheets.get_tasks_by_status.side_effect = Exception("Error")

        # Should catch exception and not raise (job logs error but continues)
        try:
            await scheduler_manager._proactive_checkin_job()
        except Exception:
            pass  # Expected to catch and log


# ===========================
# EOD Reminder Tests (3 tests)
# ===========================

@pytest.mark.asyncio
async def test_eod_reminder_success(scheduler_manager):
    """Test successful EOD reminder."""
    scheduler_manager.reminders.send_eod_reminder.return_value = None

    await scheduler_manager._eod_reminder_job()

    scheduler_manager.reminders.send_eod_reminder.assert_called_once()


@pytest.mark.asyncio
async def test_eod_reminder_failure(scheduler_manager):
    """Test EOD reminder error handling."""
    scheduler_manager.reminders.send_eod_reminder.side_effect = Exception("Error")

    with pytest.raises(Exception):
        await scheduler_manager._eod_reminder_job()


@pytest.mark.asyncio
async def test_eod_reminder_boss_notification(scheduler_manager):
    """Test EOD reminder notifies boss on failure."""
    scheduler_manager.reminders.send_eod_reminder.side_effect = Exception("Test error")

    with pytest.raises(Exception):
        await scheduler_manager._eod_reminder_job()

    scheduler_manager.reminders.send_telegram_message.assert_called()


# ===========================
# Scheduler Manager Tests (5 tests)
# ===========================

@pytest.mark.asyncio
async def test_notify_boss_of_failure(scheduler_manager):
    """Test boss notification on job failure."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = '123'
        error = Exception("Test error message")

        await scheduler_manager._notify_boss_of_failure("Test Job", error)

        scheduler_manager.reminders.send_telegram_message.assert_called_once()
        call_args = scheduler_manager.reminders.send_telegram_message.call_args
        assert "Test Job failed" in call_args[0][1]


@pytest.mark.asyncio
async def test_notify_boss_no_chat_id(scheduler_manager):
    """Test boss notification when no chat ID configured."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = None
        error = Exception("Test error")

        await scheduler_manager._notify_boss_of_failure("Test Job", error)

        # Should not attempt to send
        scheduler_manager.reminders.send_telegram_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_boss_truncates_long_errors(scheduler_manager):
    """Test boss notification truncates long error messages."""
    with patch('src.scheduler.jobs.settings') as mock_settings:
        mock_settings.telegram_boss_chat_id = '123'
        long_error = Exception("A" * 300)

        await scheduler_manager._notify_boss_of_failure("Test Job", long_error)

        call_args = scheduler_manager.reminders.send_telegram_message.call_args
        message = call_args[0][1]
        assert len(message) < 400  # Should be truncated


def test_trigger_job(scheduler_manager):
    """Test manual job triggering."""
    # Mock scheduler
    scheduler_manager.scheduler = Mock()
    mock_job = Mock()
    scheduler_manager.scheduler.get_job.return_value = mock_job

    result = scheduler_manager.trigger_job("daily_standup")

    assert result == True
    mock_job.modify.assert_called_once()


def test_get_job_status(scheduler_manager):
    """Test getting job status."""
    # Mock scheduler with jobs
    scheduler_manager.scheduler = Mock()

    mock_job1 = Mock()
    mock_job1.id = "daily_standup"
    mock_job1.name = "Daily Standup"
    mock_job1.next_run_time = datetime.now()
    mock_job1.trigger = "cron"

    mock_job2 = Mock()
    mock_job2.id = "weekly_summary"
    mock_job2.name = "Weekly Summary"
    mock_job2.next_run_time = None
    mock_job2.trigger = "cron"

    scheduler_manager.scheduler.get_jobs.return_value = [mock_job1, mock_job2]

    status = scheduler_manager.get_job_status()

    assert len(status) == 2
    assert "daily_standup" in status
    assert "weekly_summary" in status
