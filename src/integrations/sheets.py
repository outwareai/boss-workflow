"""
Google Sheets integration for task tracking and reporting.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

from config import settings
from ..models.task import Task, TaskStatus

logger = logging.getLogger(__name__)


class GoogleSheetsIntegration:
    """
    Handles Google Sheets integration for task tracking.

    Manages multiple sheets:
    - Daily Tasks: Current day's tasks
    - Weekly Overview: Week-at-a-glance
    - Monthly Report: Metrics and trends
    - Team Performance: Per-person stats
    - Task Archive: Historical data
    - Notes Log: All notes across tasks
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
            # Parse credentials from environment
            creds_json = settings.google_credentials_json
            if not creds_json:
                logger.error("No Google credentials configured")
                return False

            creds_data = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_data,
                scopes=self.SCOPES
            )

            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(settings.google_sheet_id)
            self._initialized = True
            logger.info("Google Sheets integration initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            return False

    def _get_or_create_sheet(self, name: str, headers: List[str]) -> gspread.Worksheet:
        """Get a worksheet by name or create it with headers."""
        try:
            worksheet = self.spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title=name,
                rows=1000,
                cols=len(headers)
            )
            worksheet.update('A1', [headers])
            # Format header row
            worksheet.format('A1:Z1', {
                "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.3},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
            })

        return worksheet

    async def add_task(self, task: Task) -> Optional[int]:
        """
        Add a task to the Daily Tasks sheet.

        Returns the row number where the task was added.
        """
        if not await self.initialize():
            return None

        try:
            # Get extended headers
            headers = Task.sheets_headers()
            worksheet = self._get_or_create_sheet("Daily Tasks", headers)

            # Add the task
            row_data = task.to_sheets_row()
            worksheet.append_row(row_data, value_input_option='USER_ENTERED')

            # Get the row number (last row)
            row_num = len(worksheet.get_all_values())
            logger.info(f"Added task {task.id} to Google Sheets at row {row_num}")

            return row_num

        except Exception as e:
            logger.error(f"Error adding task to Sheets: {e}")
            return None

    async def update_task(self, task: Task, row_id: Optional[int] = None) -> bool:
        """Update a task in the sheet."""
        if not await self.initialize():
            return False

        try:
            worksheet = self._get_or_create_sheet("Daily Tasks", Task.sheets_headers())

            # Find the task row by ID if row_id not provided
            if not row_id:
                cell = worksheet.find(task.id)
                if not cell:
                    logger.warning(f"Task {task.id} not found in sheet")
                    return False
                row_id = cell.row

            # Update the row
            row_data = task.to_sheets_row()
            col_count = len(row_data)
            end_col = chr(ord('A') + col_count - 1)

            worksheet.update(f'A{row_id}:{end_col}{row_id}', [row_data])
            logger.info(f"Updated task {task.id} in row {row_id}")

            return True

        except Exception as e:
            logger.error(f"Error updating task in Sheets: {e}")
            return False

    async def add_note_log(self, task_id: str, note_content: str, author: str, note_type: str) -> bool:
        """Add a note to the Notes Log sheet."""
        if not await self.initialize():
            return False

        try:
            headers = ["Timestamp", "Task ID", "Author", "Note Type", "Content"]
            worksheet = self._get_or_create_sheet("Notes Log", headers)

            row_data = [
                datetime.now().isoformat(),
                task_id,
                author,
                note_type,
                note_content
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error adding note to log: {e}")
            return False

    async def get_daily_tasks(self, date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get all tasks for a specific date."""
        if not await self.initialize():
            return []

        try:
            worksheet = self._get_or_create_sheet("Daily Tasks", Task.sheets_headers())
            all_rows = worksheet.get_all_records()

            if date is None:
                date = datetime.now()

            date_str = date.strftime('%Y-%m-%d')

            # Filter tasks created on the specified date
            daily_tasks = [
                row for row in all_rows
                if row.get('Created At', '').startswith(date_str)
            ]

            return daily_tasks

        except Exception as e:
            logger.error(f"Error getting daily tasks: {e}")
            return []

    async def get_tasks_by_status(self, status: TaskStatus) -> List[Dict[str, Any]]:
        """Get all tasks with a specific status."""
        if not await self.initialize():
            return []

        try:
            worksheet = self._get_or_create_sheet("Daily Tasks", Task.sheets_headers())
            all_rows = worksheet.get_all_records()

            return [row for row in all_rows if row.get('Status') == status.value]

        except Exception as e:
            logger.error(f"Error getting tasks by status: {e}")
            return []

    async def get_team_tasks(self, assignee: str) -> List[Dict[str, Any]]:
        """Get all tasks assigned to a specific team member."""
        if not await self.initialize():
            return []

        try:
            worksheet = self._get_or_create_sheet("Daily Tasks", Task.sheets_headers())
            all_rows = worksheet.get_all_records()

            return [
                row for row in all_rows
                if row.get('Assignee', '').lower() == assignee.lower()
            ]

        except Exception as e:
            logger.error(f"Error getting team tasks: {e}")
            return []

    async def get_overdue_tasks(self) -> List[Dict[str, Any]]:
        """Get all overdue tasks."""
        if not await self.initialize():
            return []

        try:
            worksheet = self._get_or_create_sheet("Daily Tasks", Task.sheets_headers())
            all_rows = worksheet.get_all_records()

            now = datetime.now()
            overdue = []

            for row in all_rows:
                deadline_str = row.get('Deadline', '')
                status = row.get('Status', '')

                if deadline_str and status not in ['completed', 'cancelled']:
                    try:
                        deadline = datetime.fromisoformat(deadline_str)
                        if deadline < now:
                            overdue.append(row)
                    except ValueError:
                        pass

            return overdue

        except Exception as e:
            logger.error(f"Error getting overdue tasks: {e}")
            return []

    async def generate_weekly_overview(self) -> Dict[str, Any]:
        """Generate weekly overview statistics."""
        if not await self.initialize():
            return {}

        try:
            worksheet = self._get_or_create_sheet("Daily Tasks", Task.sheets_headers())
            all_rows = worksheet.get_all_records()

            # Get this week's date range
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)

            # Filter to this week
            weekly_tasks = []
            for row in all_rows:
                created_str = row.get('Created At', '')
                if created_str:
                    try:
                        created = datetime.fromisoformat(created_str)
                        if week_start <= created <= week_end:
                            weekly_tasks.append(row)
                    except ValueError:
                        pass

            # Calculate stats
            total = len(weekly_tasks)
            completed = sum(1 for t in weekly_tasks if t.get('Status') == 'completed')
            in_progress = sum(1 for t in weekly_tasks if t.get('Status') == 'in_progress')
            delayed = sum(1 for t in weekly_tasks if t.get('Status') == 'delayed')
            overdue_count = sum(1 for t in weekly_tasks if t.get('Status') == 'overdue')

            # By assignee
            by_assignee = {}
            for task in weekly_tasks:
                assignee = task.get('Assignee', 'Unassigned')
                if assignee not in by_assignee:
                    by_assignee[assignee] = {'total': 0, 'completed': 0}
                by_assignee[assignee]['total'] += 1
                if task.get('Status') == 'completed':
                    by_assignee[assignee]['completed'] += 1

            return {
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': week_end.strftime('%Y-%m-%d'),
                'total_tasks': total,
                'completed': completed,
                'in_progress': in_progress,
                'delayed': delayed,
                'overdue': overdue_count,
                'completion_rate': round((completed / total * 100) if total > 0 else 0, 1),
                'by_assignee': by_assignee
            }

        except Exception as e:
            logger.error(f"Error generating weekly overview: {e}")
            return {}

    async def archive_completed_tasks(self, days_old: int = 7) -> int:
        """Move completed tasks older than X days to archive."""
        if not await self.initialize():
            return 0

        try:
            daily_sheet = self._get_or_create_sheet("Daily Tasks", Task.sheets_headers())
            archive_sheet = self._get_or_create_sheet("Task Archive", Task.sheets_headers())

            all_rows = daily_sheet.get_all_records()
            cutoff = datetime.now() - timedelta(days=days_old)

            rows_to_archive = []
            rows_to_delete = []

            for i, row in enumerate(all_rows, start=2):  # Start from 2 (after header)
                if row.get('Status') == 'completed':
                    completed_str = row.get('Updated At', '')
                    if completed_str:
                        try:
                            completed = datetime.fromisoformat(completed_str)
                            if completed < cutoff:
                                rows_to_archive.append(list(row.values()))
                                rows_to_delete.append(i)
                        except ValueError:
                            pass

            # Add to archive
            if rows_to_archive:
                archive_sheet.append_rows(rows_to_archive)

            # Delete from daily (in reverse order to maintain row numbers)
            for row_num in reversed(rows_to_delete):
                daily_sheet.delete_rows(row_num)

            logger.info(f"Archived {len(rows_to_archive)} completed tasks")
            return len(rows_to_archive)

        except Exception as e:
            logger.error(f"Error archiving tasks: {e}")
            return 0

    async def update_weekly_sheet(self, overview: Dict[str, Any]) -> bool:
        """Update the Weekly Overview sheet with current stats."""
        if not await self.initialize():
            return False

        try:
            headers = [
                "Week Start", "Week End", "Total Tasks", "Completed",
                "In Progress", "Delayed", "Overdue", "Completion Rate %"
            ]
            worksheet = self._get_or_create_sheet("Weekly Overview", headers)

            row_data = [
                overview.get('week_start', ''),
                overview.get('week_end', ''),
                overview.get('total_tasks', 0),
                overview.get('completed', 0),
                overview.get('in_progress', 0),
                overview.get('delayed', 0),
                overview.get('overdue', 0),
                overview.get('completion_rate', 0)
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error updating weekly sheet: {e}")
            return False


# Singleton instance
sheets_integration = GoogleSheetsIntegration()


def get_sheets_integration() -> GoogleSheetsIntegration:
    """Get the Google Sheets integration instance."""
    return sheets_integration
