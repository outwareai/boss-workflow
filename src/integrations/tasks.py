"""
Google Tasks integration for two-way sync.

Syncs tasks with Google Tasks for mobile access.
Supports user-level OAuth for personal task lists.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
import asyncio

import httpx
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceCredentials
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
            # Parse credentials (async)
            if settings.google_credentials_json.startswith('{'):
                creds_dict = await asyncio.to_thread(json.loads, settings.google_credentials_json)
            else:
                def _read_creds_file(path):
                    with open(path, 'r') as f:
                        return json.load(f)
                creds_dict = await asyncio.to_thread(_read_creds_file, settings.google_credentials_json)

            credentials = ServiceCredentials.from_service_account_info(
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
            results = await asyncio.wait_for(
                asyncio.to_thread(self.service.tasklists().list().execute),
                timeout=30.0
            )
            tasklists = results.get('items', [])

            # Find existing
            for tl in tasklists:
                if tl.get('title') == name:
                    return tl.get('id')

            # Create new
            new_list = await asyncio.wait_for(
                asyncio.to_thread(self.service.tasklists().insert(body={'title': name}).execute),
                timeout=30.0
            )

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
            result = await asyncio.wait_for(
                asyncio.to_thread(self.service.tasks().insert(tasklist=self.tasklist_id, body=task_body).execute),
                timeout=30.0
            )

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

            await asyncio.wait_for(
                asyncio.to_thread(self.service.tasks().patch(tasklist=self.tasklist_id, task=google_task_id, body={'status': status}).execute),
                timeout=30.0
            )

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
            await asyncio.wait_for(
                asyncio.to_thread(self.service.tasks().delete(tasklist=self.tasklist_id, task=google_task_id).execute),
                timeout=30.0
            )

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
            results = await asyncio.wait_for(
                asyncio.to_thread(self.service.tasks().list(tasklist=self.tasklist_id, showCompleted=False).execute),
                timeout=30.0
            )

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

            results = await asyncio.wait_for(
                asyncio.to_thread(self.service.tasks().list(**params).execute),
                timeout=30.0
            )

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

    # =========================================================================
    # User-Level OAuth Methods (for personal Google Tasks)
    # =========================================================================

    async def _refresh_user_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Refresh a user's access token using their refresh token.

        Returns dict with access_token, expires_in if successful.
        """
        try:
            client_id = settings.google_oauth_client_id
            client_secret = settings.google_oauth_client_secret

            if not client_id or not client_secret:
                logger.error("OAuth client credentials not configured")
                return None

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token"
                    }
                )

                if response.status_code != 200:
                    logger.error(f"Token refresh failed: {response.text}")
                    return None

                return response.json()

        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return None

    async def _get_user_service(self, email: str):
        """
        Get a Google Tasks service for a specific user.

        Uses their stored OAuth refresh token.
        """
        try:
            from ..database.repositories import get_oauth_repository
            oauth_repo = get_oauth_repository()

            # Get stored token
            token_data = await oauth_repo.get_token(email, "tasks")
            if not token_data:
                logger.warning(f"No Tasks OAuth token for {email}")
                return None

            refresh_token = token_data.get("refresh_token")
            if not refresh_token:
                logger.warning(f"No refresh token for {email}")
                return None

            # Refresh to get valid access token
            new_tokens = await self._refresh_user_token(refresh_token)
            if not new_tokens:
                return None

            access_token = new_tokens.get("access_token")

            # Update stored access token
            await oauth_repo.update_access_token(
                email=email,
                service="tasks",
                access_token=access_token,
                expires_in=new_tokens.get("expires_in")
            )

            # Build credentials and service
            credentials = UserCredentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret
            )

            service = build('tasks', 'v1', credentials=credentials)
            return service

        except Exception as e:
            logger.error(f"Error getting user Tasks service for {email}: {e}")
            return None

    async def _get_user_tasklist(self, service, list_name: str = "Boss Workflow") -> Optional[str]:
        """Get or create a tasklist for the user."""
        try:
            # List all tasklists
            results = await asyncio.wait_for(
                asyncio.to_thread(service.tasklists().list().execute),
                timeout=30.0
            )
            tasklists = results.get('items', [])

            # Find existing
            for tl in tasklists:
                if tl.get('title') == list_name:
                    return tl.get('id')

            # Create new
            new_list = await asyncio.wait_for(
                asyncio.to_thread(service.tasklists().insert(body={'title': list_name}).execute),
                timeout=30.0
            )

            logger.info(f"Created tasklist '{list_name}' for user")
            return new_list.get('id')

        except Exception as e:
            logger.error(f"Error getting/creating user tasklist: {e}")
            return None

    async def create_task_for_user(
        self,
        user_email: str,
        task: Task
    ) -> Optional[str]:
        """
        Create a task in a specific user's personal Google Tasks.

        Args:
            user_email: Email of the user (must have connected Google Tasks)
            task: Task to create

        Returns:
            Google Task ID if successful
        """
        try:
            # Get user's Tasks service
            service = await self._get_user_service(user_email)
            if not service:
                logger.warning(f"Could not get Tasks service for {user_email}")
                return None

            # Get or create tasklist
            tasklist_id = await self._get_user_tasklist(service)
            if not tasklist_id:
                return None

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
            result = await asyncio.wait_for(
                asyncio.to_thread(service.tasks().insert(tasklist=tasklist_id, body=task_body).execute),
                timeout=30.0
            )

            google_task_id = result.get('id')
            logger.info(f"Created Google Task for {user_email}: {task.id} -> {google_task_id}")

            return google_task_id

        except Exception as e:
            logger.error(f"Error creating task for user {user_email}: {e}")
            return None

    async def has_user_connected_tasks(self, email: str) -> bool:
        """Check if a user has connected their Google Tasks."""
        try:
            from ..database.repositories import get_oauth_repository
            oauth_repo = get_oauth_repository()
            return await oauth_repo.has_token(email, "tasks")
        except Exception as e:
            logger.error(f"Error checking Tasks connection for {email}: {e}")
            return False

    async def update_user_task_status(
        self,
        user_email: str,
        google_task_id: str,
        completed: bool
    ) -> bool:
        """Update task completion status in a user's Google Tasks."""
        try:
            service = await self._get_user_service(user_email)
            if not service:
                return False

            tasklist_id = await self._get_user_tasklist(service)
            if not tasklist_id:
                return False

            status = 'completed' if completed else 'needsAction'

            service.tasks().patch(
                tasklist=tasklist_id,
                task=google_task_id,
                body={'status': status}
            ).execute()

            logger.info(f"Updated Google Task {google_task_id} for {user_email}: {status}")
            return True

        except Exception as e:
            logger.error(f"Error updating task for {user_email}: {e}")
            return False


# Singleton
tasks_integration = GoogleTasksIntegration()


def get_tasks_integration() -> GoogleTasksIntegration:
    return tasks_integration
