"""
Google Sheets integration for task tracking and reporting.

Uses native gspread API for compatibility with gspread 6.x.
Sheet names match setup_sheets.py with emoji prefixes.
"""

import json
import logging
from typing import Dict, Any, Optional, List
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

            creds_data = json.loads(creds_json)
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

    async def add_task(self, task_data: Dict[str, Any]) -> Optional[int]:
        """
        Add a task to the Daily Tasks sheet.

        task_data should contain: id, title, description, assignee, priority,
        status, task_type, deadline, created_at, updated_at, effort, tags, created_by
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

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Update a task by ID."""
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

    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks from Daily Tasks sheet."""
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

    async def generate_weekly_report(self, week_start: datetime = None) -> Dict[str, Any]:
        """Generate and save a weekly report."""
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
                    except:
                        pass

                updated_str = task.get('Updated', '')
                status = task.get('Status', '')
                if status == 'completed' and updated_str:
                    try:
                        updated = datetime.strptime(updated_str.split()[0], '%Y-%m-%d')
                        if week_start.date() <= updated.date() <= week_end.date():
                            completed_this_week.append(task)
                    except:
                        pass

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
                        except:
                            pass

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
                    except:
                        pass

                updated_str = task.get('Updated', '')
                status = task.get('Status', '')
                if status == 'completed' and updated_str:
                    try:
                        updated = datetime.strptime(updated_str.split()[0], '%Y-%m-%d')
                        if month_start.date() <= updated.date() <= month_end.date():
                            month_completed.append(task)
                    except:
                        pass

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
                        except:
                            pass

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
    # TEAM OPERATIONS
    # ============================================
    # Columns: Name, Telegram ID, Role, Email, Active Tasks, Completed (Week),
    #          Completed (Month), Completion Rate, Avg Days, Status

    async def update_team_member(self, name: str, telegram_id: str, role: str,
                                  email: str = '', status: str = 'Active') -> bool:
        """Add or update a team member."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet(SHEET_TEAM)

            # Try to find existing member
            try:
                cell = worksheet.find(name, in_column=1)
                row_num = cell.row
            except:
                row_num = len(worksheet.get_all_values()) + 1

            # Get task stats for this person
            all_tasks = await self.get_all_tasks()
            person_tasks = [t for t in all_tasks if t.get('Assignee', '').lower() == name.lower()]

            active_tasks = len([t for t in person_tasks if t.get('Status') not in ['completed', 'cancelled']])
            completed_week = 0  # Would need date filtering
            completed_month = len([t for t in person_tasks if t.get('Status') == 'completed'])
            total_assigned = len(person_tasks)
            completion_rate = round((completed_month / total_assigned * 100) if total_assigned > 0 else 0, 1)

            row_data = [
                name,
                telegram_id,
                role,
                email,
                str(active_tasks),
                str(completed_week),
                str(completed_month),
                f"{completion_rate}%",
                '',  # Avg days
                status
            ]

            worksheet.update(f'A{row_num}:J{row_num}', [row_data], value_input_option='USER_ENTERED')
            logger.info(f"Updated team member: {name}")
            return True

        except Exception as e:
            logger.error(f"Error updating team member: {e}")
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
                except:
                    pass

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
                        except:
                            pass

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
                    except:
                        pass

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
                    except:
                        pass

        return due_soon


# Singleton instance
sheets_integration = GoogleSheetsIntegration()


def get_sheets_integration() -> GoogleSheetsIntegration:
    """Get the Google Sheets integration instance."""
    return sheets_integration
