"""
Google Sheets integration for task tracking and reporting.

Uses native gspread API for compatibility with gspread 6.x.
Sheet names match setup_sheets.py with emoji prefixes.
"""

import json
import logging
from ..utils.retry import with_google_api_retry

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from collections import Counter
import gspread
from google.oauth2.service_account import Credentials

from config.settings import settings

logger = logging.getLogger(__name__)


# ============================================
# SHEET NAME CONSTANTS (must match setup_sheets.py)
# ============================================
SHEET_DAILY_TASKS = "📋 Daily Tasks"
SHEET_DASHBOARD = "📊 Dashboard"
SHEET_TEAM = "👥 Team"
SHEET_WEEKLY = "📅 Weekly Reports"
SHEET_MONTHLY = "📆 Monthly Reports"
SHEET_NOTES = "📝 Notes Log"
SHEET_ARCHIVE = "🗃️ Archive"
SHEET_SETTINGS = "⚙️ Settings"
SHEET_TIME_LOGS = "⏰ Time Logs"
SHEET_TIME_REPORTS = "📊 Time Reports"


class GoogleSheetsIntegration:
    """
    Google Sheets integration for Boss Workflow task tracking.

    All sheet operations use the correct sheet names and column structures
    as defined in setup_sheets.py.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    def __init__(self):
        self.client: Optional[gspread.Client] = None
        self.spreadsheet: Optional[gspread.Spreadsheet] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the Google Sheets client."""
        if self._initialized:
            return True

        try:
            creds_json = settings.google_credentials_json
            if not creds_json:
                logger.error("No Google credentials configured")
                return False

            creds_data = await asyncio.to_thread(json.loads, creds_json)
            credentials = Credentials.from_service_account_info(
                creds_data,
                scopes=self.SCOPES
            )

            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(settings.google_sheet_id)

            self._initialized = True
            logger.info(f"Google Sheets connected: {self.spreadsheet.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            return False

    # ============================================
    # DAILY TASKS OPERATIONS
    # ============================================
    # Columns: ID, Title, Description, Assignee, Priority, Status, Type,
    #          Deadline, Created, Updated, Effort, Progress, Tags, Created By, Notes, Blocked By

    @with_google_api_retry
    async def add_task(self, task_data: Dict[str, Any]) -> Optional[int]:
        """
        Add a task to the Daily Tasks sheet.

        task_data should contain: id, title, description, assignee, priority,
        status, task_type, deadline, created_at, updated_at, effort, tags, created_by
        
        Q2 2026: Added retry logic with exponential backoff.
        """
        if not await self.initialize():
            return None

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)

            row_data = [
                task_data.get('id', ''),
                task_data.get('title', ''),
                task_data.get('description', ''),
                task_data.get('assignee', ''),
                task_data.get('priority', 'medium'),
                task_data.get('status', 'pending'),
                task_data.get('task_type', 'task'),
                task_data.get('deadline', ''),
                task_data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M')),
                task_data.get('updated_at', datetime.now().strftime('%Y-%m-%d %H:%M')),
                task_data.get('effort', ''),
                task_data.get('progress', '0%'),
                task_data.get('tags', ''),
                task_data.get('created_by', 'Boss'),
                '0',  # Notes count
                task_data.get('blocked_by', '')
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            row_num = len(worksheet.get_all_values())

            logger.info(f"Added task {task_data.get('id')} to row {row_num}")
            return row_num

        except Exception as e:
            logger.error(f"Error adding task: {e}")
            return None

    @with_google_api_retry
    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a task by ID.
        
        Q2 2026: Added retry logic with exponential backoff.
        """
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)
            cell = worksheet.find(task_id, in_column=1)

            if not cell:
                logger.warning(f"Task {task_id} not found")
                return False

            row_num = cell.row
            current_row = worksheet.row_values(row_num)

            # Column mapping (0-indexed)
            col_map = {
                'title': 1, 'description': 2, 'assignee': 3, 'priority': 4,
                'status': 5, 'task_type': 6, 'deadline': 7, 'updated_at': 9,
                'effort': 10, 'progress': 11, 'tags': 12, 'blocked_by': 15
            }

            # Update specific columns
            for key, col_idx in col_map.items():
                if key in updates:
                    while len(current_row) <= col_idx:
                        current_row.append('')
                    current_row[col_idx] = str(updates[key])

            # Always update the updated_at timestamp
            current_row[9] = datetime.now().strftime('%Y-%m-%d %H:%M')

            worksheet.update(f'A{row_num}:P{row_num}', [current_row[:16]], value_input_option='USER_ENTERED')
            logger.info(f"Updated task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating task: {e}")
            return False

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID."""
        if not await self.initialize():
            return None

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)
            cell = worksheet.find(task_id, in_column=1)

            if not cell:
                return None

            row = worksheet.row_values(cell.row)
            headers = worksheet.row_values(1)

            return dict(zip(headers, row))

        except Exception as e:
            logger.error(f"Error getting task: {e}")
            return None

    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task row from the Daily Tasks sheet.

        Args:
            task_id: The task ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)
            cell = worksheet.find(task_id, in_column=1)

            if not cell:
                logger.warning(f"Task {task_id} not found in sheets for deletion")
                return False

            row_num = cell.row

            # Don't delete the header row
            if row_num <= 1:
                logger.warning(f"Cannot delete header row for task {task_id}")
                return False

            worksheet.delete_rows(row_num)
            logger.info(f"Deleted task {task_id} from row {row_num}")
            return True

        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            return False

    async def delete_tasks(self, task_ids: List[str]) -> Tuple[int, int]:
        """
        Delete multiple task rows from the Daily Tasks sheet.

        Deletes in reverse order to preserve row numbers.

        Args:
            task_ids: List of task IDs to delete

        Returns:
            Tuple of (deleted_count, failed_count)
        """
        if not await self.initialize():
            return (0, len(task_ids))

        deleted = 0
        failed = 0

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)

            # Find all rows first, then delete in reverse order
            rows_to_delete = []
            for task_id in task_ids:
                try:
                    cell = worksheet.find(task_id, in_column=1)
                    if cell and cell.row > 1:  # Skip header
                        rows_to_delete.append((cell.row, task_id))
                except Exception as e:
                    logger.warning(f"Could not find task {task_id}: {e}")
                    failed += 1

            # Sort by row number descending (delete from bottom up)
            rows_to_delete.sort(key=lambda x: x[0], reverse=True)

            for row_num, task_id in rows_to_delete:
                try:
                    worksheet.delete_rows(row_num)
                    logger.info(f"Deleted task {task_id} from row {row_num}")
                    deleted += 1
                except Exception as e:
                    logger.error(f"Failed to delete task {task_id}: {e}")
                    failed += 1

            return (deleted, failed)

        except Exception as e:
            logger.error(f"Error in bulk delete: {e}")
            return (deleted, len(task_ids) - deleted)

    @with_google_api_retry
    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """
        Get all tasks from Daily Tasks sheet.
        
        Q2 2026: Added retry logic with exponential backoff.
        """
        if not await self.initialize():
            return []

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)
            return worksheet.get_all_records()
        except Exception as e:
            logger.error(f"Error getting all tasks: {e}")
            return []

    async def get_tasks_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get tasks filtered by status."""
        all_tasks = await self.get_all_tasks()
        return [t for t in all_tasks if t.get('Status', '').lower() == status.lower()]

    async def get_tasks_by_assignee(self, assignee: str) -> List[Dict[str, Any]]:
        """Get tasks assigned to a specific person."""
        all_tasks = await self.get_all_tasks()
        return [t for t in all_tasks if t.get('Assignee', '').lower() == assignee.lower()]

    async def get_daily_tasks(self) -> List[Dict[str, Any]]:
        """Get today's tasks. Alias for get_all_tasks for now."""
        return await self.get_all_tasks()

    # ============================================
    # NOTES LOG OPERATIONS
    # ============================================
    # Columns: Timestamp, Task ID, Task Title, Author, Type, Content, Pinned

    async def add_note(self, task_id: str, task_title: str, author: str,
                       note_type: str, content: str, pinned: bool = False) -> bool:
        """Add a note to the Notes Log."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_NOTES)

            row_data = [
                datetime.now().strftime('%Y-%m-%d %H:%M'),
                task_id,
                task_title,
                author,
                note_type,  # update, question, blocker, resolution, general
                content,
                'Yes' if pinned else 'No'
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')

            # Update notes count in Daily Tasks
            await self._increment_notes_count(task_id)

            logger.info(f"Added note for task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding note: {e}")
            return False

    async def _increment_notes_count(self, task_id: str) -> None:
        """Increment the notes count for a task."""
        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)
            cell = worksheet.find(task_id, in_column=1)
            if cell:
                notes_cell = worksheet.cell(cell.row, 15)  # Column O (Notes)
                current = int(notes_cell.value or 0)
                worksheet.update_cell(cell.row, 15, str(current + 1))
        except Exception as e:
            logger.error(f"Error incrementing notes count: {e}")

    # ============================================
    # WEEKLY REPORTS
    # ============================================
    # Columns: Week #, Year, Start Date, End Date, Generated,
    #          Tasks Created, Tasks Completed, Tasks Pending, Tasks Blocked, Completion Rate,
    #          Urgent Done, High Done, Medium Done, Low Done,
    #          Top Performer, Top Performer Tasks, Team Members Active,
    #          Avg Days to Complete, Overdue Tasks, On-Time Rate,
    #          Key Highlights, Blockers & Issues

    @with_google_api_retry
    async def generate_weekly_report(self, week_start: datetime = None) -> Dict[str, Any]:
        """
        Generate and save a weekly report.
        
        Q2 2026: Added retry logic with exponential backoff.
        """
        if not await self.initialize():
            return {}

        try:
            # Default to current week
            if week_start is None:
                today = datetime.now()
                week_start = today - timedelta(days=today.weekday())

            week_end = week_start + timedelta(days=6)
            week_num = week_start.isocalendar()[1]
            year = week_start.year

            # Get all tasks
            all_tasks = await self.get_all_tasks()

            # Filter tasks created/completed this week
            week_tasks = []
            completed_this_week = []

            for task in all_tasks:
                created_str = task.get('Created', '')
                if created_str:
                    try:
                        created = datetime.strptime(created_str.split()[0], '%Y-%m-%d')
                        if week_start.date() <= created.date() <= week_end.date():
                            week_tasks.append(task)
                    except (ValueError, AttributeError, IndexError) as e:
                        logger.debug(f"Skipping task with invalid created date: {created_str}")

                updated_str = task.get('Updated', '')
                status = task.get('Status', '')
                if status == 'completed' and updated_str:
                    try:
                        updated = datetime.strptime(updated_str.split()[0], '%Y-%m-%d')
                        if week_start.date() <= updated.date() <= week_end.date():
                            completed_this_week.append(task)
                    except (ValueError, AttributeError, IndexError) as e:
                        logger.debug(f"Skipping task with invalid date: {e}")

            # Calculate metrics
            tasks_created = len(week_tasks)
            tasks_completed = len(completed_this_week)
            tasks_pending = len([t for t in all_tasks if t.get('Status') == 'pending'])
            tasks_blocked = len([t for t in all_tasks if t.get('Status') == 'blocked'])

            completion_rate = round((tasks_completed / tasks_created * 100) if tasks_created > 0 else 0, 1)

            # Priority breakdown (completed this week)
            urgent_done = len([t for t in completed_this_week if t.get('Priority') == 'urgent'])
            high_done = len([t for t in completed_this_week if t.get('Priority') == 'high'])
            medium_done = len([t for t in completed_this_week if t.get('Priority') == 'medium'])
            low_done = len([t for t in completed_this_week if t.get('Priority') == 'low'])

            # Top performer
            assignee_counts = Counter(t.get('Assignee', 'Unassigned') for t in completed_this_week if t.get('Assignee'))
            top_performer = assignee_counts.most_common(1)[0] if assignee_counts else ('N/A', 0)

            # Team members active
            active_members = len(set(t.get('Assignee') for t in all_tasks if t.get('Assignee') and t.get('Status') != 'completed'))

            # Overdue tasks
            overdue_count = 0
            now = datetime.now()
            for task in all_tasks:
                if task.get('Status') not in ['completed', 'cancelled']:
                    deadline_str = task.get('Deadline', '')
                    if deadline_str:
                        try:
                            deadline = datetime.strptime(deadline_str.split()[0], '%Y-%m-%d')
                            if deadline.date() < now.date():
                                overdue_count += 1
                        except (ValueError, AttributeError, IndexError) as e:
                            logger.debug(f"Skipping task with invalid date: {e}")

            # On-time rate
            on_time_count = tasks_completed - overdue_count if tasks_completed > overdue_count else tasks_completed
            on_time_rate = round((on_time_count / tasks_completed * 100) if tasks_completed > 0 else 100, 1)

            # Build report row
            report_row = [
                str(week_num),
                str(year),
                week_start.strftime('%Y-%m-%d'),
                week_end.strftime('%Y-%m-%d'),
                datetime.now().strftime('%Y-%m-%d %H:%M'),
                str(tasks_created),
                str(tasks_completed),
                str(tasks_pending),
                str(tasks_blocked),
                f"{completion_rate}%",
                str(urgent_done),
                str(high_done),
                str(medium_done),
                str(low_done),
                top_performer[0],
                str(top_performer[1]),
                str(active_members),
                '',  # Avg days to complete (would need more complex calculation)
                str(overdue_count),
                f"{on_time_rate}%",
                '',  # Key Highlights (to be filled manually or by AI)
                ''   # Blockers & Issues (to be filled manually or by AI)
            ]

            # Write to sheet
            worksheet = self.spreadsheet.worksheet(SHEET_WEEKLY)
            worksheet.append_row(report_row, value_input_option='USER_ENTERED')

            logger.info(f"Generated weekly report for Week {week_num}, {year}")

            return {
                'week_num': week_num,
                'year': year,
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': week_end.strftime('%Y-%m-%d'),
                'tasks_created': tasks_created,
                'tasks_completed': tasks_completed,
                'completion_rate': completion_rate,
                'top_performer': top_performer[0],
                'overdue_count': overdue_count
            }

        except Exception as e:
            logger.error(f"Error generating weekly report: {e}")
            return {}

    # ============================================
    # MONTHLY REPORTS
    # ============================================
    # Columns: Month, Year, Generated,
    #          Tasks Created, Tasks Completed, Tasks Cancelled, Completion Rate,
    #          Urgent Created, Urgent Done, High Created, High Done, Medium Created, Medium Done, Low Created, Low Done,
    #          Pending EOM, In Progress EOM, Blocked EOM,
    #          Top Performer, Top Tasks Done, Most Improved, Team Size, Avg Tasks/Person,
    #          Avg Days to Complete, Fastest Completion, Overdue Count, On-Time Rate,
    #          Monthly Summary

    async def generate_monthly_report(self, month: int = None, year: int = None) -> Dict[str, Any]:
        """Generate and save a monthly report."""
        if not await self.initialize():
            return {}

        try:
            # Default to current month
            if month is None or year is None:
                now = datetime.now()
                month = now.month
                year = now.year

            month_start = datetime(year, month, 1)
            if month == 12:
                month_end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = datetime(year, month + 1, 1) - timedelta(days=1)

            month_name = month_start.strftime('%B')

            # Get all tasks
            all_tasks = await self.get_all_tasks()

            # Filter tasks for this month
            month_created = []
            month_completed = []

            for task in all_tasks:
                created_str = task.get('Created', '')
                if created_str:
                    try:
                        created = datetime.strptime(created_str.split()[0], '%Y-%m-%d')
                        if month_start.date() <= created.date() <= month_end.date():
                            month_created.append(task)
                    except (ValueError, AttributeError, IndexError) as e:
                        logger.debug(f"Skipping task with invalid date: {e}")

                updated_str = task.get('Updated', '')
                status = task.get('Status', '')
                if status == 'completed' and updated_str:
                    try:
                        updated = datetime.strptime(updated_str.split()[0], '%Y-%m-%d')
                        if month_start.date() <= updated.date() <= month_end.date():
                            month_completed.append(task)
                    except (ValueError, AttributeError, IndexError) as e:
                        logger.debug(f"Skipping task with invalid date: {e}")

            # Calculate metrics
            tasks_created = len(month_created)
            tasks_completed = len(month_completed)
            tasks_cancelled = len([t for t in month_created if t.get('Status') == 'cancelled'])
            completion_rate = round((tasks_completed / tasks_created * 100) if tasks_created > 0 else 0, 1)

            # Priority breakdown - created
            urgent_created = len([t for t in month_created if t.get('Priority') == 'urgent'])
            high_created = len([t for t in month_created if t.get('Priority') == 'high'])
            medium_created = len([t for t in month_created if t.get('Priority') == 'medium'])
            low_created = len([t for t in month_created if t.get('Priority') == 'low'])

            # Priority breakdown - completed
            urgent_done = len([t for t in month_completed if t.get('Priority') == 'urgent'])
            high_done = len([t for t in month_completed if t.get('Priority') == 'high'])
            medium_done = len([t for t in month_completed if t.get('Priority') == 'medium'])
            low_done = len([t for t in month_completed if t.get('Priority') == 'low'])

            # End of month status
            pending_eom = len([t for t in all_tasks if t.get('Status') == 'pending'])
            in_progress_eom = len([t for t in all_tasks if t.get('Status') == 'in_progress'])
            blocked_eom = len([t for t in all_tasks if t.get('Status') == 'blocked'])

            # Top performer
            assignee_counts = Counter(t.get('Assignee', 'Unassigned') for t in month_completed if t.get('Assignee'))
            top_performer = assignee_counts.most_common(1)[0] if assignee_counts else ('N/A', 0)

            # Team size
            all_assignees = set(t.get('Assignee') for t in all_tasks if t.get('Assignee'))
            team_size = len(all_assignees)
            avg_tasks_person = round(tasks_completed / team_size, 1) if team_size > 0 else 0

            # Overdue
            overdue_count = 0
            now = datetime.now()
            for task in all_tasks:
                if task.get('Status') not in ['completed', 'cancelled']:
                    deadline_str = task.get('Deadline', '')
                    if deadline_str:
                        try:
                            deadline = datetime.strptime(deadline_str.split()[0], '%Y-%m-%d')
                            if deadline.date() < now.date():
                                overdue_count += 1
                        except (ValueError, AttributeError, IndexError) as e:
                            logger.debug(f"Skipping task with invalid date: {e}")

            on_time_rate = round(((tasks_completed - overdue_count) / tasks_completed * 100) if tasks_completed > 0 else 100, 1)

            # Build report row
            report_row = [
                month_name,
                str(year),
                datetime.now().strftime('%Y-%m-%d'),
                str(tasks_created),
                str(tasks_completed),
                str(tasks_cancelled),
                f"{completion_rate}%",
                str(urgent_created),
                str(urgent_done),
                str(high_created),
                str(high_done),
                str(medium_created),
                str(medium_done),
                str(low_created),
                str(low_done),
                str(pending_eom),
                str(in_progress_eom),
                str(blocked_eom),
                top_performer[0],
                str(top_performer[1]),
                '',  # Most improved (would need historical comparison)
                str(team_size),
                str(avg_tasks_person),
                '',  # Avg days to complete
                '',  # Fastest completion
                str(overdue_count),
                f"{on_time_rate}%",
                ''   # Monthly summary (to be filled by AI or manually)
            ]

            # Write to sheet
            worksheet = self.spreadsheet.worksheet(SHEET_MONTHLY)
            worksheet.append_row(report_row, value_input_option='USER_ENTERED')

            logger.info(f"Generated monthly report for {month_name} {year}")

            return {
                'month': month_name,
                'year': year,
                'tasks_created': tasks_created,
                'tasks_completed': tasks_completed,
                'completion_rate': completion_rate,
                'top_performer': top_performer[0],
                'team_size': team_size
            }

        except Exception as e:
            logger.error(f"Error generating monthly report: {e}")
            return {}

    # ============================================
    # TEAM OPERATIONS (v1.5 structure)
    # ============================================
    # Columns: Name, Discord ID, Email, Role, Status, Active Tasks
    # - Name: For Telegram mentions
    # - Discord ID: Numeric ID for Discord @mentions
    # - Email: Google email for Calendar/Tasks
    # - Role: Developer, Marketing, Admin (channel routing)
    # - Status: Active, On Leave, Inactive
    # - Active Tasks: Count of non-completed tasks

    async def update_team_member(
        self,
        name: str,
        discord_id: str,
        email: str,
        role: str,
        status: str = 'Active',
        calendar_id: str = ''
    ) -> bool:
        """
        Add or update a team member in the Team sheet.

        Column structure (v1.5.1):
        - Name: Used for Telegram mentions
        - Discord ID: Numeric ID for Discord @mentions
        - Email: Google email for Calendar/Tasks
        - Role: Developer, Marketing, Admin (for channel routing)
        - Status: Active, On Leave, Inactive
        - Active Tasks: Count (formula-driven)
        - Calendar ID: Google Calendar ID for direct event creation

        Args:
            name: Team member name (used for Telegram mentions)
            discord_id: Numeric Discord user ID for @mentions
            email: Google email address
            role: One of Developer, Marketing, Admin
            status: Active, On Leave, or Inactive
            calendar_id: Google Calendar ID (usually same as email, or custom calendar ID)
        """
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TEAM)

            # Try to find existing member by name
            try:
                cell = worksheet.find(name, in_column=1)
                row_num = cell.row
                # Preserve existing calendar_id if not provided
                if not calendar_id:
                    existing = worksheet.row_values(row_num)
                    if len(existing) >= 7:
                        calendar_id = existing[6]  # Column G
            except (ValueError, AttributeError, IndexError) as e:
                logger.debug(f"Skipping task with invalid date: {e}")
                row_num = len(worksheet.get_all_values()) + 1

            # Calculate active tasks for this person
            all_tasks = await self.get_all_tasks()
            person_tasks = [t for t in all_tasks if t.get('Assignee', '').lower() == name.lower()]
            active_tasks = len([t for t in person_tasks if t.get('Status') not in ['completed', 'cancelled']])

            # Column structure: Name, Discord ID, Email, Role, Status, Active Tasks, Calendar ID
            row_data = [
                name,
                discord_id,
                email,
                role,
                status,
                str(active_tasks),
                calendar_id or email  # Default to email if no calendar_id
            ]

            worksheet.update(f'A{row_num}:G{row_num}', [row_data], value_input_option='USER_ENTERED')
            logger.info(f"Updated team member: {name} (Discord: {discord_id}, Role: {role}, Calendar: {calendar_id or email})")
            return True

        except Exception as e:
            logger.error(f"Error updating team member: {e}")
            return False

    async def get_all_team_members(self) -> List[Dict[str, Any]]:
        """Get all team members from the Team sheet."""
        if not await self.initialize():
            return []

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TEAM)
            # Use numericise_ignore to keep Discord/Telegram IDs as strings
            # These columns contain large numeric IDs that should stay as strings
            return worksheet.get_all_records(numericise_ignore=['all'])
        except Exception as e:
            logger.error(f"Error getting team members: {e}")
            return []

    async def clear_team_sheet(self, keep_header: bool = True) -> bool:
        """
        Clear all data from the Team sheet (remove mock data).

        Args:
            keep_header: If True, keeps the header row

        Returns:
            True if successful
        """
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TEAM)
            all_values = worksheet.get_all_values()

            if len(all_values) <= 1:
                logger.info("Team sheet already empty")
                return True

            # Clear all rows except header
            if keep_header and len(all_values) > 1:
                # Delete rows from bottom up
                for row_num in range(len(all_values), 1, -1):
                    worksheet.delete_rows(row_num)
                logger.info(f"Cleared {len(all_values) - 1} rows from Team sheet")
            else:
                worksheet.clear()
                logger.info("Cleared entire Team sheet")

            return True

        except Exception as e:
            logger.error(f"Error clearing Team sheet: {e}")
            return False

    @with_google_api_retry
    async def sync_team_from_config(self) -> Tuple[int, int]:
        """
        Sync team members from config/team.py to the Team sheet.

        Uses new column structure (v1.5):
        - Name, Discord ID, Email, Role, Status, Active Tasks

        Returns:
            Tuple of (synced_count, failed_count)
            
        Q2 2026: Added retry logic with exponential backoff.
        """
        if not await self.initialize():
            return (0, 0)

        try:
            from config.team import get_default_team

            team_members = get_default_team()

            if not team_members:
                logger.warning("No team members in config/team.py")
                return (0, 0)

            synced = 0
            failed = 0

            for member in team_members:
                try:
                    success = await self.update_team_member(
                        name=member.get("name", ""),
                        discord_id=member.get("discord_id", ""),
                        email=member.get("email", ""),
                        role=member.get("role", "Developer"),
                        status="Active"
                    )
                    if success:
                        synced += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Error syncing team member {member.get('name')}: {e}")
                    failed += 1

            logger.info(f"Team sync complete: {synced} synced, {failed} failed")
            return (synced, failed)

        except Exception as e:
            logger.error(f"Error syncing team from config: {e}")
            return (0, len(team_members) if 'team_members' in dir() else 0)

    async def delete_team_member(self, name: str) -> bool:
        """Delete a team member from the Team sheet."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TEAM)
            cell = worksheet.find(name, in_column=1)

            if not cell or cell.row <= 1:
                logger.warning(f"Team member {name} not found")
                return False

            worksheet.delete_rows(cell.row)
            logger.info(f"Deleted team member: {name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting team member {name}: {e}")
            return False

    # ============================================
    # ARCHIVE OPERATIONS
    # ============================================
    # Columns: ID, Title, Description, Assignee, Priority, Final Status, Type,
    #          Deadline, Created, Completed, Days to Complete, Notes Count, Archived On

    async def archive_task(self, task_id: str) -> bool:
        """Move a completed task to the archive."""
        if not await self.initialize():
            return False

        try:
            # Get task from daily tasks
            task = await self.get_task(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found for archiving")
                return False

            # Calculate days to complete
            created_str = task.get('Created', '')
            updated_str = task.get('Updated', '')
            days_to_complete = ''
            if created_str and updated_str:
                try:
                    created = datetime.strptime(created_str.split()[0], '%Y-%m-%d')
                    completed = datetime.strptime(updated_str.split()[0], '%Y-%m-%d')
                    days_to_complete = str((completed - created).days)
                except (ValueError, AttributeError, IndexError) as e:
                    logger.debug(f"Skipping task with invalid date: {e}")

            archive_row = [
                task.get('ID', ''),
                task.get('Title', ''),
                task.get('Description', ''),
                task.get('Assignee', ''),
                task.get('Priority', ''),
                task.get('Status', ''),
                task.get('Type', ''),
                task.get('Deadline', ''),
                task.get('Created', ''),
                task.get('Updated', ''),  # Completed date
                days_to_complete,
                task.get('Notes', '0'),
                datetime.now().strftime('%Y-%m-%d')
            ]

            # Add to archive
            archive_sheet = self.spreadsheet.worksheet(SHEET_ARCHIVE)
            archive_sheet.append_row(archive_row, value_input_option='USER_ENTERED')

            # Delete from daily tasks
            daily_sheet = self.spreadsheet.worksheet(SHEET_DAILY_TASKS)
            cell = daily_sheet.find(task_id, in_column=1)
            if cell:
                daily_sheet.delete_rows(cell.row)

            logger.info(f"Archived task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Error archiving task: {e}")
            return False

    async def archive_old_completed(self, days_old: int = 7) -> int:
        """Archive all completed tasks older than X days."""
        if not await self.initialize():
            return 0

        try:
            all_tasks = await self.get_all_tasks()
            cutoff = datetime.now() - timedelta(days=days_old)
            archived_count = 0

            for task in all_tasks:
                if task.get('Status') == 'completed':
                    updated_str = task.get('Updated', '')
                    if updated_str:
                        try:
                            updated = datetime.strptime(updated_str.split()[0], '%Y-%m-%d')
                            if updated.date() < cutoff.date():
                                if await self.archive_task(task.get('ID', '')):
                                    archived_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to archive task: {e}", extra={'task_id': task.get('ID', '')})

            logger.info(f"Archived {archived_count} old completed tasks")
            return archived_count

        except Exception as e:
            logger.error(f"Error archiving old tasks: {e}")
            return 0

    # ============================================
    # DASHBOARD OPERATIONS
    # ============================================

    async def refresh_dashboard_timestamp(self) -> bool:
        """Update the dashboard timestamp."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_DASHBOARD)
            worksheet.update('B3', f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            return True
        except Exception as e:
            logger.error(f"Error refreshing dashboard: {e}")
            return False

    # ============================================
    # UTILITY METHODS
    # ============================================

    async def get_overdue_tasks(self) -> List[Dict[str, Any]]:
        """Get all overdue tasks."""
        all_tasks = await self.get_all_tasks()
        now = datetime.now()
        overdue = []

        for task in all_tasks:
            if task.get('Status') not in ['completed', 'cancelled']:
                deadline_str = task.get('Deadline', '')
                if deadline_str:
                    try:
                        deadline = datetime.strptime(deadline_str.split()[0], '%Y-%m-%d')
                        if deadline.date() < now.date():
                            overdue.append(task)
                    except (ValueError, AttributeError, IndexError) as e:
                        logger.debug(f"Skipping task with invalid date: {e}")

        return overdue

    async def get_tasks_due_soon(self, days: int = 2) -> List[Dict[str, Any]]:
        """Get tasks due within X days."""
        all_tasks = await self.get_all_tasks()
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        due_soon = []

        for task in all_tasks:
            if task.get('Status') not in ['completed', 'cancelled']:
                deadline_str = task.get('Deadline', '')
                if deadline_str:
                    try:
                        deadline = datetime.strptime(deadline_str.split()[0], '%Y-%m-%d')
                        if now.date() <= deadline.date() <= cutoff.date():
                            due_soon.append(task)
                    except (ValueError, AttributeError, IndexError) as e:
                        logger.debug(f"Skipping task with invalid date: {e}")

        return due_soon

    # ============================================
    # SEARCH OPERATIONS
    # ============================================

    async def search_tasks(
        self,
        query: str = None,
        assignee: str = None,
        status: str = None,
        priority: str = None,
        due: str = None,
        created: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search tasks with various filters.

        Args:
            query: Text search in title/description
            assignee: Filter by assignee name (supports @mention format)
            status: Filter by status
            priority: Filter by priority (supports #priority format)
            due: Filter by deadline ("today", "week", "overdue")
            created: Filter by creation date ("today", "week", "month")
            limit: Max results to return

        Returns:
            List of matching tasks
        """
        all_tasks = await self.get_all_tasks()
        results = all_tasks

        # Clean up assignee (remove @ if present)
        if assignee:
            assignee = assignee.lstrip('@').strip()

        # Clean up priority (remove # if present)
        if priority:
            priority = priority.lstrip('#').strip()

        # Text search
        if query:
            query_lower = query.lower()
            results = [
                t for t in results
                if query_lower in t.get('Title', '').lower() or
                   query_lower in t.get('Description', '').lower() or
                   query_lower in t.get('Tags', '').lower()
            ]

        # Assignee filter
        if assignee:
            results = [
                t for t in results
                if assignee.lower() in t.get('Assignee', '').lower()
            ]

        # Status filter
        if status:
            results = [
                t for t in results
                if t.get('Status', '').lower() == status.lower()
            ]

        # Priority filter
        if priority:
            results = [
                t for t in results
                if t.get('Priority', '').lower() == priority.lower()
            ]

        # Due date filter
        if due:
            now = datetime.now()
            filtered = []
            for task in results:
                deadline_str = task.get('Deadline', '')
                if not deadline_str:
                    continue
                try:
                    deadline = datetime.strptime(deadline_str.split()[0], '%Y-%m-%d')
                    if due == "today" and deadline.date() == now.date():
                        filtered.append(task)
                    elif due == "week" and now.date() <= deadline.date() <= (now + timedelta(days=7)).date():
                        filtered.append(task)
                    elif due == "overdue" and deadline.date() < now.date():
                        filtered.append(task)
                except (ValueError, AttributeError, IndexError) as e:
                    logger.debug(f"Skipping task with invalid date: {e}")
            results = filtered

        # Created date filter
        if created:
            now = datetime.now()
            filtered = []
            for task in results:
                created_str = task.get('Created', '')
                if not created_str:
                    continue
                try:
                    created_date = datetime.strptime(created_str.split()[0], '%Y-%m-%d')
                    if created == "today" and created_date.date() == now.date():
                        filtered.append(task)
                    elif created == "week" and (now - timedelta(days=7)).date() <= created_date.date():
                        filtered.append(task)
                    elif created == "month" and (now - timedelta(days=30)).date() <= created_date.date():
                        filtered.append(task)
                except (ValueError, AttributeError, IndexError) as e:
                    logger.debug(f"Skipping task with invalid date: {e}")
            results = filtered

        return results[:limit]

    async def bulk_update_status(
        self,
        task_ids: List[str],
        new_status: str,
        note: str = None
    ) -> Tuple[int, List[str]]:
        """
        Update status for multiple tasks at once.

        Args:
            task_ids: List of task IDs to update
            new_status: New status to set
            note: Optional note to add

        Returns:
            Tuple of (success_count, failed_ids)
        """
        success_count = 0
        failed_ids = []

        for task_id in task_ids:
            try:
                result = await self.update_task(task_id, {'status': new_status})
                if result:
                    success_count += 1
                    if note:
                        task = await self.get_task(task_id)
                        await self.add_note(
                            task_id=task_id,
                            task_title=task.get('Title', 'Task') if task else 'Task',
                            author='System',
                            note_type='update',
                            content=f"Status changed to {new_status}. {note}"
                        )
                else:
                    failed_ids.append(task_id)
            except Exception as e:
                logger.error(f"Error updating task {task_id}: {e}")
                failed_ids.append(task_id)

        logger.info(f"Bulk update: {success_count} succeeded, {len(failed_ids)} failed")
        return success_count, failed_ids

    async def bulk_assign(
        self,
        task_ids: List[str],
        assignee: str
    ) -> Tuple[int, List[str]]:
        """
        Assign multiple tasks to a person.

        Returns:
            Tuple of (success_count, failed_ids)
        """
        success_count = 0
        failed_ids = []

        for task_id in task_ids:
            try:
                result = await self.update_task(task_id, {'assignee': assignee})
                if result:
                    success_count += 1
                else:
                    failed_ids.append(task_id)
            except Exception as e:
                logger.error(f"Error assigning task {task_id}: {e}")
                failed_ids.append(task_id)

        logger.info(f"Bulk assign to {assignee}: {success_count} succeeded, {len(failed_ids)} failed")
        return success_count, failed_ids

    # ============================================
    # ATTENDANCE / TIME CLOCK OPERATIONS
    # ============================================
    # Time Logs columns: Record ID, Date, Time, Name, Event, Late, Late Min, Channel
    # Time Reports columns: Week, Year, Name, Days Worked, Total Hours, Avg Start, Avg End, Late Days, Total Late, Break Time, Notes

    async def add_attendance_log(self, record: Dict[str, Any]) -> bool:
        """
        Add a single attendance record to the Time Logs sheet.

        Args:
            record: Dict containing:
                - record_id: ATT-YYYYMMDD-XXX
                - date: YYYY-MM-DD
                - time: HH:MM
                - name: Staff name
                - event: in/out/break in/break out (or [BR] prefixed for boss-reported)
                - late: Yes/No/-
                - late_min: Minutes late (0 if not late)
                - channel: dev/admin/boss
                - notes: Optional notes (for boss-reported entries)
        """
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TIME_LOGS)

            row_data = [
                record.get('record_id', ''),
                record.get('date', ''),
                record.get('time', ''),
                record.get('name', ''),
                record.get('event', ''),
                record.get('late', '-'),
                str(record.get('late_min', 0)),
                record.get('channel', ''),
                record.get('notes', ''),  # Notes column for boss-reported context
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            logger.info(f"Added attendance log: {record.get('record_id')} - {record.get('name')} {record.get('event')}")
            return True

        except Exception as e:
            logger.error(f"Error adding attendance log: {e}")
            return False

    async def add_attendance_logs_batch(self, records: List[Dict[str, Any]]) -> int:
        """
        Batch add attendance records to Time Logs sheet.

        Args:
            records: List of record dicts (same format as add_attendance_log)

        Returns:
            Number of records successfully added
        """
        if not await self.initialize():
            return 0

        if not records:
            return 0

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TIME_LOGS)

            rows = []
            for record in records:
                rows.append([
                    record.get('record_id', ''),
                    record.get('date', ''),
                    record.get('time', ''),
                    record.get('name', ''),
                    record.get('event', ''),
                    record.get('late', '-'),
                    str(record.get('late_min', 0)),
                    record.get('channel', ''),
                ])

            # Get current last row
            current_values = worksheet.get_all_values()
            start_row = len(current_values) + 1

            # Batch update
            worksheet.update(
                f'A{start_row}:H{start_row + len(rows) - 1}',
                rows,
                value_input_option='USER_ENTERED'
            )

            logger.info(f"Batch added {len(rows)} attendance records")
            return len(rows)

        except Exception as e:
            logger.error(f"Error batch adding attendance logs: {e}")
            return 0

    async def update_time_report(
        self,
        week: int,
        year: int,
        summaries: List[Dict[str, Any]]
    ) -> bool:
        """
        Update or add weekly time report summaries.

        Args:
            week: Week number
            year: Year (e.g., 2026)
            summaries: List of user summaries, each containing:
                - name: Staff name
                - days_worked: Number of days
                - total_hours: Total work hours
                - avg_start: Average clock-in time (HH:MM)
                - avg_end: Average clock-out time (HH:MM)
                - late_days: Count of late days
                - total_late_minutes: Total minutes late
                - break_minutes: Total break time in minutes
                - notes: Optional notes

        Returns:
            True if successful
        """
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TIME_REPORTS)

            for summary in summaries:
                # Check if row exists for this week/year/name
                all_records = worksheet.get_all_records()
                existing_row = None

                for idx, record in enumerate(all_records):
                    if (str(record.get('Week', '')) == str(week) and
                        str(record.get('Year', '')) == str(year) and
                        record.get('Name', '').lower() == summary.get('name', '').lower()):
                        existing_row = idx + 2  # +1 for 0-index, +1 for header
                        break

                # Format break time
                break_minutes = summary.get('break_minutes', 0)
                break_hours = break_minutes / 60
                break_str = f"{break_hours:.1f}h"

                row_data = [
                    str(week),
                    str(year),
                    summary.get('name', ''),
                    str(summary.get('days_worked', 0)),
                    str(summary.get('total_hours', 0)),
                    summary.get('avg_start', ''),
                    summary.get('avg_end', ''),
                    str(summary.get('late_days', 0)),
                    str(summary.get('total_late_minutes', 0)),
                    break_str,
                    summary.get('notes', ''),
                ]

                if existing_row:
                    # Update existing row
                    worksheet.update(
                        f'A{existing_row}:K{existing_row}',
                        [row_data],
                        value_input_option='USER_ENTERED'
                    )
                    logger.info(f"Updated time report for {summary.get('name')} week {week}/{year}")
                else:
                    # Append new row
                    worksheet.append_row(row_data, value_input_option='USER_ENTERED')
                    logger.info(f"Added time report for {summary.get('name')} week {week}/{year}")

            return True

        except Exception as e:
            logger.error(f"Error updating time report: {e}")
            return False

    async def get_time_logs(self, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """Get time logs, optionally filtered by date range."""
        if not await self.initialize():
            return []

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TIME_LOGS)
            records = worksheet.get_all_records()

            if not start_date and not end_date:
                return records

            # Filter by date range
            filtered = []
            for record in records:
                record_date = record.get('Date', '')
                if start_date and record_date < start_date:
                    continue
                if end_date and record_date > end_date:
                    continue
                filtered.append(record)

            return filtered

        except Exception as e:
            logger.error(f"Error getting time logs: {e}")
            return []


# Singleton instance
sheets_integration = GoogleSheetsIntegration()


def get_sheets_integration() -> GoogleSheetsIntegration:
    """Get the Google Sheets integration instance."""
    return sheets_integration
