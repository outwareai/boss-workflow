"""
QueryHandler - Handles status queries and reporting operations.

Q1 2026: Task #4.6 Part 1 - Extracted from UnifiedHandler.
Manages all read-only query operations.
"""
from typing import Optional, Dict, Any, List, Tuple
import logging
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


class QueryHandler(BaseHandler):
    """
    Handles read-only query and reporting operations.

    Responsibilities:
    - Check task status
    - List tasks by criteria (status, assignee, priority)
    - Generate reports (daily, weekly, monthly)
    - Search tasks by keyword/ID
    - Show overdue tasks
    - Team status overview
    """

    def __init__(self):
        """Initialize query handler."""
        super().__init__()
        self.logger = logging.getLogger("QueryHandler")

    async def can_handle(self, message: str, user_id: str, **kwargs) -> bool:
        """
        Check if this is a query/status request.

        Handles:
        - "status", "check task", "show tasks"
        - "my tasks", "overdue tasks"
        - "report", "standup", "weekly report"
        - Task ID lookups (TASK-XXX)
        """
        message_lower = message.lower().strip()

        query_keywords = [
            "status", "check", "show", "list", "find",
            "my tasks", "overdue", "pending", "completed",
            "report", "standup", "weekly", "monthly",
            "task-", "search", "filter", "what's", "working on"
        ]

        return any(keyword in message_lower for keyword in query_keywords)

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Route query to appropriate handler."""
        message = update.message.text.strip()
        message_lower = message.lower()
        user_info = await self.get_user_info(update)
        user_id = user_info["user_id"]

        try:
            # Detect query type
            if re.search(r'task-\d+', message_lower):
                await self._handle_task_lookup(update, message)
            elif any(word in message_lower for word in ["my tasks", "my task"]):
                await self._handle_my_tasks(update, user_info)
            elif "overdue" in message_lower:
                await self._handle_overdue_tasks(update, user_info)
            elif any(word in message_lower for word in ["daily report", "standup"]):
                await self._handle_daily_report(update, user_info)
            elif "weekly report" in message_lower or "weekly" in message_lower:
                await self._handle_weekly_report(update, user_info)
            elif "monthly report" in message_lower or "monthly" in message_lower:
                await self._handle_monthly_report(update, user_info)
            elif any(word in message_lower for word in ["search", "find", "what's", "working on"]):
                await self._handle_search(update, message, user_info)
            elif "status" in message_lower:
                await self._handle_status_query(update, message, user_info)
            else:
                # Generic task list
                await self._handle_list_tasks(update, user_info)

        except Exception as e:
            self.logger.error(f"Query handling error: {e}", exc_info=True)
            await self.send_error(update, f"Query failed: {str(e)}")

    # ==================== TASK LOOKUP ====================

    async def _handle_task_lookup(self, update: Update, message: str) -> None:
        """Look up specific task by ID."""
        # Extract task ID (TASK-XXX format)
        match = re.search(r'TASK-\d+', message.upper())

        if not match:
            await self.send_error(update, "Invalid task ID format. Use TASK-XXX")
            return

        task_id = match.group(0)

        # Try database first
        try:
            task = await self.task_repo.get_by_id(task_id)

            if task:
                # Format task details from DB
                response = self._format_task_details_from_db(task)
                await self.send_message(update, response)
                return
        except Exception as e:
            self.logger.warning(f"Database lookup failed for {task_id}: {e}")

        # Fall back to Sheets
        try:
            tasks = await self.sheets.get_all_tasks()
            task = next((t for t in tasks if t.get("ID") == task_id), None)

            if task:
                response = self._format_task_details(task)
                await self.send_message(update, response)
            else:
                await self.send_error(update, f"Task {task_id} not found")
        except Exception as e:
            self.logger.error(f"Sheets lookup failed: {e}")
            await self.send_error(update, f"Failed to look up task: {str(e)}")

    # ==================== MY TASKS ====================

    async def _handle_my_tasks(self, update: Update, user_info: Dict) -> None:
        """Show tasks assigned to requesting user."""
        user_name = user_info.get("first_name") or user_info.get("username") or "Unknown"

        try:
            # Get user's tasks from Sheets
            all_tasks = await self.sheets.get_all_tasks()
            my_tasks = [
                task for task in all_tasks
                if task.get("Assignee", "").lower() == user_name.lower()
            ]

            if not my_tasks:
                await self.send_message(update, f"📭 No tasks assigned to {user_name}")
                return

            # Group by status
            grouped = self._group_tasks_by_status_sheets(my_tasks)

            response = f"📋 **Tasks for {user_name}**\n\n"

            for status, task_list in grouped.items():
                if task_list:
                    response += f"**{status.upper()}** ({len(task_list)}):\n"
                    for task in task_list[:5]:  # Limit to 5 per status
                        task_id = task.get("ID", "N/A")
                        title = task.get("Title", "Untitled")[:40]
                        response += f"  • {task_id}: {title}\n"
                    if len(task_list) > 5:
                        response += f"  ... and {len(task_list) - 5} more\n"
                    response += "\n"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"My tasks error: {e}")
            await self.send_error(update, f"Failed to get your tasks: {str(e)}")

    # ==================== OVERDUE TASKS ====================

    async def _handle_overdue_tasks(self, update: Update, user_info: Dict) -> None:
        """Show overdue tasks."""
        try:
            overdue = await self.sheets.get_overdue_tasks()

            if not overdue:
                await self.send_message(update, "✅ No overdue tasks!")
                return

            response = f"⚠️ **{len(overdue)} Overdue Tasks**\n\n"

            for task in overdue[:10]:  # Limit to 10
                task_id = task.get("ID", "N/A")
                title = task.get("Title", "Untitled")[:35]
                assignee = task.get("Assignee", "Unassigned")
                deadline = task.get("Deadline", "")

                response += f"🔴 {task_id}: {title}\n"
                response += f"   Assignee: {assignee}\n"
                if deadline:
                    response += f"   Deadline: {deadline}\n"
                response += "\n"

            if len(overdue) > 10:
                response += f"... and {len(overdue) - 10} more\n"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"Overdue tasks error: {e}")
            await self.send_error(update, f"Failed to get overdue tasks: {str(e)}")

    # ==================== REPORTS ====================

    async def _handle_daily_report(self, update: Update, user_info: Dict) -> None:
        """Generate daily standup report."""
        try:
            daily_tasks = await self.sheets.get_daily_tasks()

            if not daily_tasks:
                await self.send_message(update, "📭 No tasks for today")
                return

            # Group by status
            completed = [t for t in daily_tasks if t.get("Status") == "completed"]
            in_progress = [t for t in daily_tasks if t.get("Status") == "in_progress"]
            pending = [t for t in daily_tasks if t.get("Status") == "pending"]
            blocked = [t for t in daily_tasks if t.get("Status") == "blocked"]

            today = datetime.now().strftime("%Y-%m-%d")

            response = f"📊 **Daily Standup Report - {today}**\n\n"
            response += f"✅ Completed: {len(completed)}\n"
            response += f"🔄 In Progress: {len(in_progress)}\n"
            response += f"🆕 Pending: {len(pending)}\n"
            if blocked:
                response += f"🚫 Blocked: {len(blocked)}\n"

            response += f"\nTotal: {len(daily_tasks)} tasks\n"

            # Completion rate
            if daily_tasks:
                completion_rate = (len(completed) / len(daily_tasks)) * 100
                response += f"Completion Rate: {completion_rate:.1f}%\n"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"Daily report error: {e}")
            await self.send_error(update, f"Failed to generate daily report: {str(e)}")

    async def _handle_weekly_report(self, update: Update, user_info: Dict) -> None:
        """Generate weekly summary report."""
        try:
            # Get all tasks
            all_tasks = await self.sheets.get_all_tasks()

            # Filter to this week
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())

            # Count tasks (this is simplified - in production you'd filter by date)
            completed = len([t for t in all_tasks if t.get("Status") == "completed"])
            total = len(all_tasks)

            response = f"📅 **Weekly Report - Week of {week_start.strftime('%Y-%m-%d')}**\n\n"
            response += f"Total Tasks: {total}\n"
            response += f"Completed: {completed}\n"

            if total > 0:
                completion_rate = (completed / total) * 100
                response += f"Completion Rate: {completion_rate:.1f}%\n"

            # Group by status
            by_status = {}
            for task in all_tasks:
                status = task.get("Status", "pending")
                by_status[status] = by_status.get(status, 0) + 1

            response += "\n**By Status:**\n"
            for status, count in sorted(by_status.items(), key=lambda x: x[1], reverse=True)[:5]:
                response += f"  {status}: {count}\n"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"Weekly report error: {e}")
            await self.send_error(update, f"Failed to generate weekly report: {str(e)}")

    async def _handle_monthly_report(self, update: Update, user_info: Dict) -> None:
        """Generate monthly summary report."""
        try:
            # Get all tasks
            all_tasks = await self.sheets.get_all_tasks()

            today = datetime.now()

            # Calculate stats
            by_status = {}
            for task in all_tasks:
                status = task.get("Status", "pending")
                by_status[status] = by_status.get(status, 0) + 1

            response = f"📆 **Monthly Report - {today.strftime('%B %Y')}**\n\n"
            response += f"Total Tasks: {len(all_tasks)}\n\n"

            response += "**By Status:**\n"
            for status, count in sorted(by_status.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(all_tasks) * 100) if all_tasks else 0
                response += f"  {status}: {count} ({percentage:.1f}%)\n"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"Monthly report error: {e}")
            await self.send_error(update, f"Failed to generate monthly report: {str(e)}")

    # ==================== SEARCH ====================

    async def _handle_search(self, update: Update, message: str, user_info: Dict) -> None:
        """Handle natural language search."""
        message_lower = message.lower()

        # Parse natural language search patterns
        assignee = None
        status = None
        priority = None

        # "What's John working on?" -> search by assignee
        working_on_match = re.search(r"what'?s?\s+(\w+)\s+working\s+on", message, re.IGNORECASE)
        if working_on_match:
            assignee = working_on_match.group(1)

        # "tasks for Sarah" -> search by assignee
        tasks_for_match = re.search(r"tasks?\s+(?:for|assigned\s+to)\s+@?(\w+)", message, re.IGNORECASE)
        if tasks_for_match:
            assignee = tasks_for_match.group(1)

        # Extract @mentions
        mention_match = re.search(r'@(\w+)', message)
        if mention_match:
            assignee = mention_match.group(1)

        # "urgent tasks" or "high priority"
        if any(w in message_lower for w in ["urgent", "critical"]):
            priority = "urgent"
        elif "high priority" in message_lower:
            priority = "high"

        # "blocked tasks"
        if "blocked" in message_lower:
            status = "blocked"
        elif "pending" in message_lower:
            status = "pending"
        elif "in progress" in message_lower or "in_progress" in message_lower:
            status = "in_progress"

        # Text search terms (remove special patterns)
        text_query = message
        for pattern in [r"what'?s?\s+\w+\s+working\s+on", r"tasks?\s+(?:for|assigned\s+to)\s+@?\w+", r"@\w+"]:
            text_query = re.sub(pattern, "", text_query, flags=re.IGNORECASE).strip()

        try:
            results = await self.sheets.search_tasks(
                query=text_query if len(text_query) > 2 else None,
                assignee=assignee,
                status=status,
                priority=priority,
                limit=10
            )

            if not results:
                search_desc = []
                if assignee:
                    search_desc.append(f"assignee: {assignee}")
                if status:
                    search_desc.append(f"status: {status}")
                if priority:
                    search_desc.append(f"priority: {priority}")
                await self.send_message(
                    update,
                    f"No tasks found{' (' + ', '.join(search_desc) + ')' if search_desc else ''}"
                )
                return

            response = f"🔍 **Found {len(results)} task(s)**\n\n"

            for task in results:
                priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    task.get('Priority', '').lower(), "⚪"
                )
                task_id = task.get('ID', 'N/A')
                title = task.get('Title', 'Untitled')[:35]
                assignee_name = task.get('Assignee', 'Unassigned')
                status_val = task.get('Status', 'pending')

                response += f"{priority_emoji} **{task_id}**: {title}\n"
                response += f"   {assignee_name} | {status_val}\n\n"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"Search error: {e}")
            await self.send_error(update, f"Search failed: {str(e)}")

    # ==================== STATUS QUERY ====================

    async def _handle_status_query(self, update: Update, message: str, user_info: Dict) -> None:
        """Handle general status queries."""
        try:
            # Get overview from Sheets
            daily_tasks = await self.sheets.get_daily_tasks()
            overdue = await self.sheets.get_overdue_tasks()

            response = "📊 **Status Overview**\n\n"

            if daily_tasks:
                completed = sum(1 for t in daily_tasks if t.get("Status") == "completed")
                response += f"Today: {completed}/{len(daily_tasks)} tasks done\n"
            else:
                response += "No tasks for today\n"

            if overdue:
                response += f"⚠️ {len(overdue)} overdue\n"

            # Check pending validations from session
            user_id = user_info["user_id"]
            pending_validation = await self.get_session("pending_validation", user_id)
            if pending_validation:
                response += f"📋 Awaiting your review\n"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"Status query error: {e}")
            await self.send_error(update, f"Failed to get status: {str(e)}")

    # ==================== LIST TASKS ====================

    async def _handle_list_tasks(self, update: Update, user_info: Dict) -> None:
        """List all tasks (with pagination)."""
        try:
            all_tasks = await self.sheets.get_all_tasks()

            if not all_tasks:
                await self.send_message(update, "📭 No tasks found")
                return

            # Show first 10
            response = f"📋 **All Tasks** ({len(all_tasks)} total)\n\n"

            for task in all_tasks[:10]:
                task_id = task.get("ID", "N/A")
                title = task.get("Title", "Untitled")[:40]
                status = task.get("Status", "pending")
                assignee = task.get("Assignee", "Unassigned")

                response += f"• {task_id}: {title}\n"
                response += f"  Status: {status} | Assignee: {assignee}\n\n"

            if len(all_tasks) > 10:
                response += f"\n... and {len(all_tasks) - 10} more tasks\n"
                response += "Use search to filter tasks"

            await self.send_message(update, response)

        except Exception as e:
            self.logger.error(f"List tasks error: {e}")
            await self.send_error(update, f"Failed to list tasks: {str(e)}")

    # ==================== HELPERS ====================

    def _format_task_details(self, task: Dict) -> str:
        """Format task details from Sheets for display."""
        response = f"📝 **Task Details**\n\n"
        response += f"ID: {task.get('ID', 'N/A')}\n"
        response += f"Title: {task.get('Title', 'Untitled')}\n"
        response += f"Description: {task.get('Description', 'N/A')}\n"
        response += f"Status: {task.get('Status', 'pending')}\n"
        response += f"Assignee: {task.get('Assignee', 'Unassigned')}\n"
        response += f"Priority: {task.get('Priority', 'medium')}\n"

        if task.get('Deadline'):
            response += f"Deadline: {task['Deadline']}\n"

        if task.get('Created'):
            response += f"Created: {task['Created']}\n"

        return response

    def _format_task_details_from_db(self, task) -> str:
        """Format task details from database for display."""
        response = f"📝 **Task Details**\n\n"
        response += f"ID: {task.task_id}\n"
        response += f"Title: {task.title}\n"
        response += f"Description: {task.description or 'N/A'}\n"
        response += f"Status: {task.status}\n"
        response += f"Assignee: {task.assignee or 'Unassigned'}\n"
        response += f"Priority: {task.priority or 'medium'}\n"

        if task.deadline:
            response += f"Deadline: {task.deadline.strftime('%Y-%m-%d %H:%M')}\n"

        response += f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}\n"

        return response

    def _group_tasks_by_status_sheets(self, tasks: List[Dict]) -> Dict[str, List]:
        """Group tasks from Sheets by status."""
        grouped = {}
        for task in tasks:
            status = task.get("Status", "pending")
            if status not in grouped:
                grouped[status] = []
            grouped[status].append(task)
        return grouped
