"""
Scheduler manager for automated jobs.

Handles all scheduled tasks:
- Daily standup (9 AM)
- EOD reminder (6 PM)
- Weekly summary (Friday 5 PM)
- Monthly report (1st of month)
- Deadline reminders (2 hours before)
- Overdue alerts (every 4 hours)
- Conversation timeout checks
"""

import logging
from typing import Optional
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from config import settings
from .reminders import get_reminder_service
from ..integrations.sheets import get_sheets_integration
from ..integrations.discord import get_discord_integration
from ..integrations.gmail import get_gmail_integration
from ..ai.deepseek import get_deepseek_client
from ..ai.email_summarizer import get_email_summarizer
from ..memory.context import get_conversation_context
from ..models.task import TaskStatus
from ..database.repositories.recurring import get_recurring_repository, RecurrenceCalculator

logger = logging.getLogger(__name__)


class SchedulerManager:
    """
    Manages all scheduled jobs for the workflow automation.
    """

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.timezone = pytz.timezone(settings.timezone)
        self.reminders = get_reminder_service()
        self.sheets = get_sheets_integration()
        self.discord = get_discord_integration()
        self.gmail = get_gmail_integration()
        self.ai = get_deepseek_client()
        self.email_summarizer = get_email_summarizer()
        self.context = get_conversation_context()

    def start(self) -> None:
        """Start the scheduler with all jobs."""
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)

        # Daily standup at 9 AM
        self.scheduler.add_job(
            self._daily_standup_job,
            CronTrigger(
                hour=settings.daily_standup_hour,
                minute=0,
                timezone=self.timezone
            ),
            id="daily_standup",
            name="Daily Standup Summary",
            replace_existing=True
        )

        # EOD reminder at 6 PM
        self.scheduler.add_job(
            self._eod_reminder_job,
            CronTrigger(
                hour=settings.eod_reminder_hour,
                minute=0,
                timezone=self.timezone
            ),
            id="eod_reminder",
            name="End of Day Reminder",
            replace_existing=True
        )

        # Weekly summary on Friday at 5 PM
        self.scheduler.add_job(
            self._weekly_summary_job,
            CronTrigger(
                day_of_week=settings.weekly_summary_day[:3].lower(),
                hour=settings.weekly_summary_hour,
                minute=0,
                timezone=self.timezone
            ),
            id="weekly_summary",
            name="Weekly Summary Report",
            replace_existing=True
        )

        # Monthly report on the 1st at 9 AM
        self.scheduler.add_job(
            self._monthly_report_job,
            CronTrigger(
                day=1,
                hour=9,
                minute=0,
                timezone=self.timezone
            ),
            id="monthly_report",
            name="Monthly Report",
            replace_existing=True
        )

        # Deadline reminders every 30 minutes
        self.scheduler.add_job(
            self._deadline_reminder_job,
            IntervalTrigger(minutes=30),
            id="deadline_reminders",
            name="Deadline Reminders Check",
            replace_existing=True
        )

        # Overdue alerts every 4 hours
        self.scheduler.add_job(
            self._overdue_alert_job,
            IntervalTrigger(hours=settings.overdue_alert_interval_hours),
            id="overdue_alerts",
            name="Overdue Alerts",
            replace_existing=True
        )

        # Conversation timeout check every 15 minutes
        self.scheduler.add_job(
            self._conversation_timeout_job,
            IntervalTrigger(minutes=15),
            id="conversation_timeout",
            name="Conversation Timeout Check",
            replace_existing=True
        )

        # Recurring tasks check every 5 minutes
        self.scheduler.add_job(
            self._recurring_tasks_job,
            IntervalTrigger(minutes=5),
            id="recurring_tasks",
            name="Recurring Tasks Check",
            replace_existing=True
        )

        # Auto-archive completed tasks weekly (Sunday at midnight)
        self.scheduler.add_job(
            self._archive_tasks_job,
            CronTrigger(
                day_of_week='sun',
                hour=0,
                minute=0,
                timezone=self.timezone
            ),
            id="archive_tasks",
            name="Archive Completed Tasks",
            replace_existing=True
        )

        # Morning email digest
        if settings.enable_email_digest:
            self.scheduler.add_job(
                self._morning_email_digest_job,
                CronTrigger(
                    hour=settings.morning_digest_hour,
                    minute=0,
                    timezone=self.timezone
                ),
                id="morning_email_digest",
                name="Morning Email Digest",
                replace_existing=True
            )

            # Evening email digest
            self.scheduler.add_job(
                self._evening_email_digest_job,
                CronTrigger(
                    hour=settings.evening_digest_hour,
                    minute=0,
                    timezone=self.timezone
                ),
                id="evening_email_digest",
                name="Evening Email Digest",
                replace_existing=True
            )
            logger.info(f"Email digests scheduled: {settings.morning_digest_hour}:00 and {settings.evening_digest_hour}:00")

        self.scheduler.start()
        logger.info("Scheduler started with all jobs")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    async def _daily_standup_job(self) -> None:
        """Generate and post daily standup summary."""
        logger.info("Running daily standup job")

        try:
            # Get today's tasks
            today_tasks = await self.sheets.get_daily_tasks()

            # Get yesterday's completed tasks
            from datetime import date, timedelta
            yesterday = date.today() - timedelta(days=1)
            yesterday_completed = []  # Would need to filter by completion date

            # Generate AI summary
            summary = await self.ai.generate_daily_standup(
                tasks=today_tasks[:20],
                completed_yesterday=yesterday_completed[:10]
            )

            # Post to Discord
            await self.discord.post_standup(summary)

            # Send to Telegram
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    f"☀️ **Daily Standup**\n\n{summary}"
                )

            logger.info("Daily standup completed")

        except Exception as e:
            logger.error(f"Error in daily standup job: {e}")

    async def _eod_reminder_job(self) -> None:
        """Send end of day reminder."""
        logger.info("Running EOD reminder job")

        try:
            await self.reminders.send_eod_reminder()
            logger.info("EOD reminder sent")

        except Exception as e:
            logger.error(f"Error in EOD reminder job: {e}")

    async def _weekly_summary_job(self) -> None:
        """Generate and post weekly summary."""
        logger.info("Running weekly summary job")

        try:
            # Get weekly overview
            overview = await self.sheets.generate_weekly_overview()

            if not overview:
                logger.warning("Could not generate weekly overview")
                return

            # Get completed tasks this week
            completed = await self.sheets.get_tasks_by_status(TaskStatus.COMPLETED)

            # Generate AI summary
            summary = await self.ai.generate_weekly_summary(
                weekly_stats=overview,
                tasks_by_status={"completed": completed[:30]},
                team_performance=overview.get('by_assignee', {})
            )

            # Post to Discord
            await self.discord.post_weekly_summary(summary)

            # Update weekly sheet
            await self.sheets.update_weekly_sheet(overview)

            # Send to Telegram
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    f"📊 **Weekly Summary**\n\n{summary}"
                )

            logger.info("Weekly summary completed")

        except Exception as e:
            logger.error(f"Error in weekly summary job: {e}")

    async def _monthly_report_job(self) -> None:
        """Generate monthly report."""
        logger.info("Running monthly report job")

        try:
            # Get last month's data (this would need more sophisticated logic)
            overview = await self.sheets.generate_weekly_overview()

            message = f"""📈 **Monthly Report**

Here's your monthly productivity summary:

**Tasks Completed:** {overview.get('completed', 0)}
**Completion Rate:** {overview.get('completion_rate', 0)}%

Detailed report available in Google Sheets.

Keep up the great work!"""

            # Post to Discord
            await self.discord.post_alert(
                title="Monthly Report Available",
                message="Check Google Sheets for the full monthly report",
                alert_type="info"
            )

            # Send to Telegram
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    message
                )

            logger.info("Monthly report completed")

        except Exception as e:
            logger.error(f"Error in monthly report job: {e}")

    async def _deadline_reminder_job(self) -> None:
        """Check and send deadline reminders."""
        try:
            count = await self.reminders.check_and_send_deadline_reminders()
            if count > 0:
                logger.info(f"Sent {count} deadline reminders")

        except Exception as e:
            logger.error(f"Error in deadline reminder job: {e}")

    async def _overdue_alert_job(self) -> None:
        """Check and send overdue alerts."""
        try:
            count = await self.reminders.check_and_send_overdue_alerts()
            if count > 0:
                logger.info(f"Sent {count} overdue alerts")

        except Exception as e:
            logger.error(f"Error in overdue alert job: {e}")

    async def _conversation_timeout_job(self) -> None:
        """Check for timed-out and auto-finalize conversations."""
        logger.debug("Checking conversation timeouts")

        try:
            # Check for timed out conversations (30 min)
            timed_out = await self.context.get_timed_out_conversations()
            for conv in timed_out:
                await self.reminders.send_conversation_timeout_reminder(
                    conv.user_id,
                    conv.conversation_id
                )

            # Check for auto-finalize (2 hours)
            to_finalize = await self.context.get_conversations_to_auto_finalize()
            for conv in to_finalize:
                # Auto-finalize logic would go here
                # This would require integration with ConversationManager
                logger.info(f"Would auto-finalize conversation {conv.conversation_id}")

        except Exception as e:
            logger.error(f"Error in conversation timeout job: {e}")

    async def _archive_tasks_job(self) -> None:
        """Archive old completed tasks."""
        logger.info("Running task archive job")

        try:
            count = await self.sheets.archive_completed_tasks(days_old=7)
            logger.info(f"Archived {count} completed tasks")

        except Exception as e:
            logger.error(f"Error in archive tasks job: {e}")

    async def _recurring_tasks_job(self) -> None:
        """Check and create recurring task instances."""
        logger.debug("Running recurring tasks check")

        try:
            recurring_repo = get_recurring_repository()

            # Get tasks that are due to run
            due_tasks = await recurring_repo.get_due_now()

            if not due_tasks:
                return

            logger.info(f"Found {len(due_tasks)} recurring tasks due")

            from ..database.repositories import get_task_repository
            task_repo = get_task_repository()

            for recurring in due_tasks:
                try:
                    # Create task instance
                    task_data = {
                        "title": recurring.title,
                        "description": recurring.description or f"Auto-created from recurring task {recurring.recurring_id}",
                        "assignee": recurring.assignee,
                        "priority": recurring.priority,
                        "task_type": recurring.task_type,
                        "estimated_effort": recurring.estimated_effort,
                        "tags": recurring.tags,
                        "created_by": recurring.created_by,
                        "source": "recurring",
                        "recurring_id": recurring.recurring_id,
                    }

                    new_task = await task_repo.create(task_data)

                    if new_task:
                        logger.info(f"Created task {new_task.task_id} from recurring {recurring.recurring_id}")

                        # Post to Discord
                        try:
                            await self.discord.post_alert(
                                title=f"🔄 Recurring Task: {recurring.title[:40]}",
                                message=f"Assignee: {recurring.assignee or 'Unassigned'}\nPriority: {recurring.priority}",
                                alert_type="info"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to post recurring task to Discord: {e}")

                        # Update recurring task with next run time
                        await recurring_repo.update_after_run(recurring.recurring_id)

                except Exception as e:
                    logger.error(f"Error creating task from recurring {recurring.recurring_id}: {e}")

        except Exception as e:
            logger.error(f"Error in recurring tasks job: {e}")

    async def _morning_email_digest_job(self) -> None:
        """Generate and send morning email digest."""
        logger.info("Running morning email digest job")

        try:
            # Initialize Gmail if needed
            if not self.gmail._initialized:
                await self.gmail.initialize()

            # Get emails from overnight (last 12 hours)
            emails = await self.gmail.get_emails_since(
                hours=settings.morning_digest_hours_back,
                max_results=50
            )

            if not emails:
                logger.info("No new emails for morning digest")
                return

            # Convert to summary format
            email_dicts = [e.to_summary_dict() for e in emails]

            # Generate summary with DeepSeek
            summary_result = await self.email_summarizer.summarize_emails(
                emails=email_dicts,
                period="morning"
            )

            # Generate formatted message
            unread_count = sum(1 for e in emails if e.is_unread)
            digest_message = await self.email_summarizer.generate_digest_message(
                summary_result=summary_result,
                period="morning",
                total_emails=len(emails),
                unread_count=unread_count
            )

            # Send to Telegram
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    digest_message
                )

            # Also post to Discord if configured
            if settings.discord_webhook_url:
                await self.discord.post_alert(
                    title="☀️ Morning Email Digest",
                    message=summary_result.summary + (
                        f"\n\n**{len(emails)}** emails | **{unread_count}** unread"
                    ),
                    alert_type="info"
                )

            logger.info(f"Morning email digest sent: {len(emails)} emails summarized")

        except Exception as e:
            logger.error(f"Error in morning email digest job: {e}", exc_info=True)

    async def _evening_email_digest_job(self) -> None:
        """Generate and send evening email digest."""
        logger.info("Running evening email digest job")

        try:
            # Initialize Gmail if needed
            if not self.gmail._initialized:
                await self.gmail.initialize()

            # Get today's emails (last 12 hours from evening)
            emails = await self.gmail.get_emails_since(
                hours=settings.evening_digest_hours_back,
                max_results=50
            )

            if not emails:
                logger.info("No new emails for evening digest")
                return

            # Convert to summary format
            email_dicts = [e.to_summary_dict() for e in emails]

            # Generate summary with DeepSeek
            summary_result = await self.email_summarizer.summarize_emails(
                emails=email_dicts,
                period="evening"
            )

            # Generate formatted message
            unread_count = sum(1 for e in emails if e.is_unread)
            digest_message = await self.email_summarizer.generate_digest_message(
                summary_result=summary_result,
                period="evening",
                total_emails=len(emails),
                unread_count=unread_count
            )

            # Send to Telegram
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    digest_message
                )

            # Also post to Discord if configured
            if settings.discord_webhook_url:
                await self.discord.post_alert(
                    title="🌙 Evening Email Digest",
                    message=summary_result.summary + (
                        f"\n\n**{len(emails)}** emails | **{unread_count}** unread"
                    ),
                    alert_type="info"
                )

            logger.info(f"Evening email digest sent: {len(emails)} emails summarized")

        except Exception as e:
            logger.error(f"Error in evening email digest job: {e}", exc_info=True)

    def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a job."""
        if not self.scheduler:
            return False

        job = self.scheduler.get_job(job_id)
        if job:
            job.modify(next_run_time=datetime.now(self.timezone))
            return True

        return False

    def get_job_status(self) -> dict:
        """Get status of all scheduled jobs."""
        if not self.scheduler:
            return {}

        jobs = {}
        for job in self.scheduler.get_jobs():
            jobs[job.id] = {
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }

        return jobs


# Singleton instance
scheduler_manager = SchedulerManager()


def get_scheduler_manager() -> SchedulerManager:
    """Get the scheduler manager instance."""
    return scheduler_manager
