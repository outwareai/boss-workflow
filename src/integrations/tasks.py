"""
Google Tasks integration for two-way sync.

Syncs tasks with Google Tasks for mobile access.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings
from ..models.task import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


class GoogleTasksIntegration:
    """
    Google Tasks integration for syncing tasks.

    Features:
    - Create tasks in Google Tasks
    - Sync status between systems
    - Mobile access via Google Tasks app
    - Due date sync
    """

    SCOPES = [
        'https://www.googleapis.com/auth/tasks'
    ]

    def __init__(self):
        self.service = None
        self._initialized = False
        self.tasklist_id = None  # Will store our tasklist ID

    async def initialize(self) -> bool:
        """Initialize Google Tasks API connection."""
        if not settings.google_credentials_json:
            logger.warning("Google credentials not configured for Tasks")
            return False

        try:
            # Parse credentials
            if settings.google_credentials_json.startswith('{'):
                creds_dict = json.loads(settings.google_credentials_json)
            else:
                with open(settings.google_credentials_json, 'r') as f:
                    creds_dict = json.load(f)

            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=self.SCOPES
            )

            self.service = build('tasks', 'v1', credentials=credentials)
            self._initialized = True

            # Get or create our tasklist
            self.tasklist_id = await self._get_or_create_tasklist("Boss Workflow")

            logger.info("Google Tasks integration initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Tasks: {e}")
            return False

    async def _get_or_create_tasklist(self, name: str) -> Optional[str]:
        """Get existing tasklist or create new one."""
        try:
            # List all tasklists
            results = self.service.tasklists().list().execute()
            tasklists = results.get('items', [])

            # Find existing
            for tl in tasklists:
                if tl.get('title') == name:
                    return tl.get('id')

            # Create new
            new_list = self.service.tasklists().insert(
                body={'title': name}
            ).execute()

            logger.info(f"Created tasklist: {name}")
            return new_list.get('id')

        except Exception as e:
            logger.error(f"Error getting/creating tasklist: {e}")
            return None

    async def create_task(self, task: Task) -> Optional[str]:
        """
        Create a task in Google Tasks.

        Returns:
            Google Task ID if successful
        """
        if not self._initialized:
            await self.initialize()

        if not self.service or not self.tasklist_id:
            return None

        try:
            # Build task body
            task_body = {
                'title': f"[{task.priority.value.upper()}] {task.title}",
                'notes': self._build_notes(task),
                'status': 'needsAction'
            }

            # Add due date if exists
            if task.deadline:
                task_body['due'] = task.deadline.strftime('%Y-%m-%dT%H:%M:%S.000Z')

            # Create task
            result = self.service.tasks().insert(
                tasklist=self.tasklist_id,
                body=task_body
            ).execute()

            google_task_id = result.get('id')
            logger.info(f"Created Google Task: {task.id} -> {google_task_id}")

            return google_task_id

        except Exception as e:
            logger.error(f"Error creating Google Task: {e}")
            return None

    def _build_notes(self, task: Task) -> str:
        """Build notes field for Google Task."""
        lines = [
            f"Task ID: {task.id}",
            f"Assignee: {task.assignee or 'Unassigned'}",
            "",
            task.description or "",
            ""
        ]

        if task.acceptance_criteria:
            lines.append("Acceptance Criteria:")
            for i, ac in enumerate(task.acceptance_criteria, 1):
                lines.append(f"  {i}. {ac.description}")

        return "\n".join(lines)

    async def update_task_status(
        self,
        google_task_id: str,
        completed: bool
    ) -> bool:
        """Update task completion status in Google Tasks."""
        if not self.service or not self.tasklist_id:
            return False

        try:
            status = 'completed' if completed else 'needsAction'

            self.service.tasks().patch(
                tasklist=self.tasklist_id,
                task=google_task_id,
                body={'status': status}
            ).execute()

            logger.info(f"Updated Google Task {google_task_id} status: {status}")
            return True

        except Exception as e:
            logger.error(f"Error updating Google Task status: {e}")
            return False

    async def delete_task(self, google_task_id: str) -> bool:
        """Delete a task from Google Tasks."""
        if not self.service or not self.tasklist_id:
            return False

        try:
            self.service.tasks().delete(
                tasklist=self.tasklist_id,
                task=google_task_id
            ).execute()

            logger.info(f"Deleted Google Task: {google_task_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting Google Task: {e}")
            return False

    async def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending tasks from Google Tasks."""
        if not self.service or not self.tasklist_id:
            return []

        try:
            results = self.service.tasks().list(
                tasklist=self.tasklist_id,
                showCompleted=False
            ).execute()

            return results.get('items', [])

        except Exception as e:
            logger.error(f"Error listing Google Tasks: {e}")
            return []

    async def get_completed_tasks(
        self,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get completed tasks from Google Tasks."""
        if not self.service or not self.tasklist_id:
            return []

        try:
            params = {
                'tasklist': self.tasklist_id,
                'showCompleted': True,
                'showHidden': True
            }

            if since:
                params['completedMin'] = since.strftime('%Y-%m-%dT%H:%M:%S.000Z')

            results = self.service.tasks().list(**params).execute()

            # Filter to only completed
            return [
                t for t in results.get('items', [])
                if t.get('status') == 'completed'
            ]

        except Exception as e:
            logger.error(f"Error listing completed Google Tasks: {e}")
            return []

    async def sync_from_google_tasks(self) -> List[Dict[str, Any]]:
        """
        Check for tasks completed in Google Tasks.

        Returns list of completed tasks that need status update.
        """
        if not self.service or not self.tasklist_id:
            return []

        try:
            # Get tasks completed in last 24 hours
            since = datetime.now() - timedelta(hours=24)
            completed = await self.get_completed_tasks(since)

            # Parse task IDs from notes
            updates = []
            for task in completed:
                notes = task.get('notes', '')
                # Extract our task ID from notes
                if 'Task ID:' in notes:
                    for line in notes.split('\n'):
                        if line.startswith('Task ID:'):
                            task_id = line.replace('Task ID:', '').strip()
                            updates.append({
                                'google_task_id': task.get('id'),
                                'task_id': task_id,
                                'completed_at': task.get('completed')
                            })
                            break

            return updates

        except Exception as e:
            logger.error(f"Error syncing from Google Tasks: {e}")
            return []


# Singleton
tasks_integration = GoogleTasksIntegration()


def get_tasks_integration() -> GoogleTasksIntegration:
    return tasks_integration
