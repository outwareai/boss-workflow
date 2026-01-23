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
from ..database.repositories.attendance import get_attendance_repository

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

        # Attendance sync to Google Sheets (every 15 minutes)
        self.scheduler.add_job(
            self._sync_attendance_job,
            IntervalTrigger(minutes=settings.attendance_sync_interval_minutes),
            id="sync_attendance",
            name="Sync Attendance to Sheets",
            replace_existing=True
        )

        # Weekly time report (Monday at 10 AM)
        self.scheduler.add_job(
            self._weekly_time_report_job,
            CronTrigger(
                day_of_week='mon',
                hour=10,
                minute=0,
                timezone=self.timezone
            ),
            id="weekly_time_report",
            name="Weekly Time Report",
            replace_existing=True
        )
        logger.info("Attendance jobs scheduled: sync every 15 min, weekly report Mon 10 AM")

        # Proactive check-ins - every hour, check for tasks with no updates in 4+ hours
        self.scheduler.add_job(
            self._proactive_checkin_job,
            IntervalTrigger(hours=1),
            id="proactive_checkins",
            name="Proactive Task Check-ins",
            replace_existing=True
        )
        logger.info("Proactive check-ins scheduled: every 1 hour")

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

            # Send email digest as separate message (Telegram only)
            await self._send_standup_email_digest()

        except Exception as e:
            logger.error(f"Error in daily standup job: {e}")

    async def _send_standup_email_digest(self) -> None:
        """
        Send comprehensive email digest as separate message after standup.
        Only sent to Telegram (boss), not Discord.
        """
        if not settings.enable_email_digest:
            logger.debug("Email digest disabled, skipping standup email summary")
            return

        if not settings.telegram_boss_chat_id:
            return

        try:
            # Initialize Gmail if needed
            if not self.gmail._initialized:
                await self.gmail.initialize()

            if not self.gmail.is_available():
                logger.warning("Gmail not available for standup email digest")
                return

            # Get emails from last 12 hours (overnight emails)
            emails = await self.gmail.get_emails_since(
                hours=settings.morning_digest_hours_back,
                max_results=50
            )

            if not emails:
                # Send a brief "no emails" message
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    "📧 **Email Summary**\n\n_No new emails since yesterday._"
                )
                logger.info("No emails for standup digest")
                return

            # Convert to summary format
            email_dicts = [e.to_summary_dict() for e in emails]

            # Generate comprehensive summary with DeepSeek
            summary_result = await self.email_summarizer.summarize_emails(
                emails=email_dicts,
                period="morning"
            )

            # Build comprehensive email message
            unread_count = sum(1 for e in emails if e.is_unread)
            important_count = sum(1 for e in emails if e.is_important)

            # Format individual email summaries
            email_details = []
            for i, email in enumerate(emails[:15], 1):  # Top 15 emails
                status_icons = []
                if email.is_unread:
                    status_icons.append("🔵")
                if email.is_important:
                    status_icons.append("⭐")

                status_str = " ".join(status_icons) if status_icons else ""

                # Truncate subject if too long
                subject = email.subject[:60] + "..." if len(email.subject) > 60 else email.subject
                sender = email.sender_name or email.sender_email.split('@')[0]

                email_details.append(f"{i}. {status_str} **{sender}**: {subject}")

            # Build the comprehensive message
            digest_message = f"""📧 **Comprehensive Email Summary**

📊 **Overview**
• Total: **{len(emails)}** emails
• Unread: **{unread_count}** 🔵
• Important: **{important_count}** ⭐

📝 **AI Summary**
{summary_result.summary}

{"📌 **Action Items**" if summary_result.action_items else ""}
{chr(10).join(f"• {item}" for item in summary_result.action_items) if summary_result.action_items else ""}

{"🚨 **Priority Emails**" if summary_result.priority_emails else ""}
{chr(10).join(f"• {email}" for email in summary_result.priority_emails[:5]) if summary_result.priority_emails else ""}

📬 **Latest Emails**
{chr(10).join(email_details)}

_🔵 = Unread | ⭐ = Important_"""

            # Send to Telegram ONLY (not Discord)
            await self.reminders.send_telegram_message(
                settings.telegram_boss_chat_id,
                digest_message
            )

            logger.info(f"Standup email digest sent to Telegram: {len(emails)} emails summarized")

        except Exception as e:
            logger.error(f"Error in standup email digest: {e}", exc_info=True)
            # Don't fail the whole standup if email digest fails
            try:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    "📧 **Email Summary**\n\n⚠️ _Could not fetch emails. Check Gmail configuration._"
                )
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f"Error in scheduled job: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in scheduled job: {e}")

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

            # Send to Telegram ONLY (boss only, not Discord)
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    digest_message
                )

            logger.info(f"Morning email digest sent to Telegram: {len(emails)} emails summarized")

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

            # Send to Telegram ONLY (boss only, not Discord)
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    digest_message
                )

            logger.info(f"Evening email digest sent to Telegram: {len(emails)} emails summarized")

        except Exception as e:
            logger.error(f"Error in evening email digest job: {e}", exc_info=True)

    async def _sync_attendance_job(self) -> None:
        """Sync unsynced attendance records to Google Sheets."""
        logger.debug("Running attendance sync job")

        try:
            attendance_repo = get_attendance_repository()

            # Get unsynced records
            unsynced = await attendance_repo.get_unsynced_records(limit=100)

            if not unsynced:
                logger.debug("No unsynced attendance records")
                return

            logger.info(f"Syncing {len(unsynced)} attendance records to Sheets")

            # Convert to sheet format
            records = []
            for record in unsynced:
                # Map event type to sheet format
                event_map = {
                    "clock_in": "in",
                    "clock_out": "out",
                    "break_start": "break in",
                    "break_end": "break out",
                }

                records.append({
                    "record_id": record.record_id,
                    "date": record.event_time.strftime("%Y-%m-%d"),
                    "time": record.event_time.strftime("%H:%M"),
                    "name": record.user_name,
                    "event": event_map.get(record.event_type, record.event_type),
                    "late": "Yes" if record.is_late else ("No" if record.event_type == "clock_in" else "-"),
                    "late_min": record.late_minutes,
                    "channel": record.channel_name,
                })

            # Batch add to sheets
            count = await self.sheets.add_attendance_logs_batch(records)

            if count > 0:
                # Mark as synced
                record_ids = [r.id for r in unsynced[:count]]
                await attendance_repo.mark_synced(record_ids)
                logger.info(f"Synced {count} attendance records to Sheets")

        except Exception as e:
            logger.error(f"Error in attendance sync job: {e}", exc_info=True)

    async def _weekly_time_report_job(self) -> None:
        """Generate weekly time reports for all team members."""
        logger.info("Running weekly time report job")

        try:
            from datetime import date

            attendance_repo = get_attendance_repository()

            # Get the start of last week (Monday)
            today = date.today()
            days_since_monday = today.weekday()  # Monday = 0
            last_monday = today - timedelta(days=days_since_monday + 7)  # Previous week's Monday

            logger.info(f"Generating time report for week starting {last_monday}")

            # Get all team summaries
            summaries = await attendance_repo.get_team_weekly_summary(last_monday)

            if not summaries:
                logger.info("No attendance data for weekly time report")
                return

            # Convert to sheet format
            week_num = last_monday.isocalendar()[1]
            year = last_monday.year

            sheet_summaries = []
            for summary in summaries:
                sheet_summaries.append({
                    "name": summary.get("user_name", "Unknown"),
                    "days_worked": summary.get("days_worked", 0),
                    "total_hours": summary.get("total_hours", 0),
                    "avg_start": summary.get("avg_start", ""),
                    "avg_end": summary.get("avg_end", ""),
                    "late_days": summary.get("late_days", 0),
                    "total_late_minutes": summary.get("total_late_minutes", 0),
                    "break_minutes": summary.get("total_break_minutes", 0),
                    "notes": "",
                })

            # Update sheets
            await self.sheets.update_time_report(week_num, year, sheet_summaries)

            # Post summary to Discord standup channel
            late_summary = ""
            for s in sheet_summaries:
                if s["late_days"] > 0:
                    late_summary += f"• {s['name']}: {s['late_days']} late day(s), {s['total_late_minutes']} min total\n"

            summary_message = f"""📊 **Weekly Time Report - Week {week_num}**

**Team Summary:**
"""
            for s in sheet_summaries:
                summary_message += f"• {s['name']}: {s['days_worked']} days, {s['total_hours']:.1f}h worked\n"

            if late_summary:
                summary_message += f"\n**Late Arrivals:**\n{late_summary}"

            summary_message += "\n_Full report available in Google Sheets._"

            # Post to Discord standup channel
            try:
                await self.discord.post_standup(summary_message)
            except Exception as e:
                logger.warning(f"Failed to post time report to Discord: {e}")

            # Send to Telegram
            if settings.telegram_boss_chat_id:
                await self.reminders.send_telegram_message(
                    settings.telegram_boss_chat_id,
                    summary_message
                )

            logger.info(f"Weekly time report generated: {len(sheet_summaries)} team members")

        except Exception as e:
            logger.error(f"Error in weekly time report job: {e}", exc_info=True)

    async def _proactive_checkin_job(self) -> None:
        """
        Check for active tasks with no updates in 4+ hours and send friendly check-ins.

        This helps keep tasks moving and catches stalled work early.
        """
        logger.debug("Running proactive check-in job")

        try:
            from ..database.repositories import get_task_repository
            from ..memory.task_context import get_task_context_manager

            task_repo = get_task_repository()
            context_manager = get_task_context_manager()

            # Get all active tasks (in_progress, pending with assignee)
            active_statuses = [TaskStatus.IN_PROGRESS, TaskStatus.PENDING]

            # Calculate cutoff time - 4 hours ago
            cutoff_time = datetime.now(self.timezone) - timedelta(hours=4)

            tasks_needing_checkin = []

            for status in active_statuses:
                try:
                    tasks = await self.sheets.get_tasks_by_status(status)

                    for task in tasks:
                        # Skip unassigned tasks
                        if not task.get("assignee"):
                            continue

                        # Check last update time
                        last_updated_str = task.get("updated_at") or task.get("created_at")
                        if not last_updated_str:
                            continue

                        try:
                            # Parse the timestamp
                            if isinstance(last_updated_str, str):
                                # Try common formats
                                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
                                    try:
                                        last_updated = datetime.strptime(last_updated_str, fmt)
                                        last_updated = self.timezone.localize(last_updated)
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    continue
                            else:
                                last_updated = last_updated_str
                                if last_updated.tzinfo is None:
                                    last_updated = self.timezone.localize(last_updated)

                            # Check if stale (no update in 4+ hours)
                            if last_updated < cutoff_time:
                                tasks_needing_checkin.append(task)

                        except Exception as e:
                            logger.debug(f"Could not parse timestamp for {task.get('task_id')}: {e}")

                except Exception as e:
                    logger.warning(f"Error fetching {status} tasks: {e}")

            if not tasks_needing_checkin:
                logger.debug("No tasks need check-ins")
                return

            logger.info(f"Found {len(tasks_needing_checkin)} tasks needing check-ins")

            # Check each task and send check-in if not recently checked
            for task in tasks_needing_checkin[:5]:  # Limit to 5 per run to avoid spam
                task_id = task.get("task_id")
                assignee = task.get("assignee", "Team")
                title = task.get("title", "")[:50]

                try:
                    # Check if we have a context with recent check-in
                    context = await context_manager.get_context_async(task_id)

                    # Skip if checked in last 4 hours
                    if context:
                        last_checkin = context.get("last_checkin")
                        if last_checkin:
                            try:
                                checkin_time = datetime.fromisoformat(last_checkin)
                                if checkin_time.tzinfo is None:
                                    checkin_time = self.timezone.localize(checkin_time)
                                if checkin_time > cutoff_time:
                                    logger.debug(f"Skipping {task_id} - recently checked")
                                    continue
                            except (ValueError, KeyError, AttributeError) as e:
                                logger.warning(f"Error in scheduled job: {e}")
                            except Exception as e:
                                logger.error(f"Unexpected error in scheduled job: {e}")

                    # Send friendly check-in via Discord
                    checkin_message = f"""👋 **Friendly Check-in: {task_id}**

Hey {assignee}! Just checking in on **{title}**

No updates in the last 4+ hours. How's it going?

• Making progress? Great - drop a quick update!
• Stuck on something? Let me know and I can escalate.
• Need more time? No worries, just update the status.

_Reply in this thread with your update!_"""

                    # Try to post to task's Discord thread
                    thread_id = None
                    if context:
                        thread_id = context.get("thread_id")

                    if thread_id:
                        # Post to existing thread
                        try:
                            from ..integrations.discord_bot import get_discord_bot
                            discord_bot = get_discord_bot()
                            await discord_bot.send_message_to_thread(
                                thread_id=int(thread_id),
                                content=checkin_message
                            )
                            logger.info(f"Sent check-in for {task_id} to thread {thread_id}")
                        except Exception as e:
                            logger.warning(f"Could not send to thread for {task_id}: {e}")
                            # Fall back to main channel
                            await self.discord.post_alert(
                                title=f"Check-in: {task_id}",
                                message=f"@{assignee} - How's **{title}** going? No updates in 4+ hours.",
                                alert_type="info"
                            )
                    else:
                        # No thread, post to main channel
                        await self.discord.post_alert(
                            title=f"Check-in: {task_id}",
                            message=f"@{assignee} - How's **{title}** going? No updates in 4+ hours.",
                            alert_type="info"
                        )

                    # Record the check-in time
                    if context:
                        context["last_checkin"] = datetime.now(self.timezone).isoformat()
                        await context_manager.update_context_async(task_id, context)

                except Exception as e:
                    logger.error(f"Error sending check-in for {task_id}: {e}")

            logger.info(f"Completed proactive check-ins for {min(len(tasks_needing_checkin), 5)} tasks")

        except Exception as e:
            logger.error(f"Error in proactive check-in job: {e}", exc_info=True)

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
