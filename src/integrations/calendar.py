"""
Google Calendar integration for task deadlines and reminders.

Creates calendar events for tasks with deadlines and sends reminders.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings
from ..models.task import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


class GoogleCalendarIntegration:
    """
    Handles Google Calendar integration for task deadlines.

    Features:
    - Create calendar events for task deadlines
    - Update events when deadlines change
    - Delete events when tasks are cancelled/completed
    - Color-code by priority
    - Add reminders before deadlines
    """

    SCOPES = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events"
    ]

    # Google Calendar color IDs (1-11)
    PRIORITY_COLORS = {
        TaskPriority.LOW: "2",      # Green
        TaskPriority.MEDIUM: "5",   # Yellow
        TaskPriority.HIGH: "6",     # Orange
        TaskPriority.URGENT: "11",  # Red
    }

    def __init__(self):
        self.service = None
        self.calendar_id: str = "primary"  # Can be set to a specific calendar
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the Google Calendar client."""
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

            self.service = build('calendar', 'v3', credentials=credentials)
            self._initialized = True
            logger.info("Google Calendar integration initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar: {e}")
            return False

    def set_calendar_id(self, calendar_id: str) -> None:
        """Set the calendar ID to use (default is 'primary')."""
        self.calendar_id = calendar_id

    async def create_task_event(self, task: Task) -> Optional[str]:
        """
        Create a calendar event for a task deadline.

        Creates event on assignee's personal calendar if they have shared it,
        otherwise falls back to the default calendar.

        Returns the event ID if successful.
        """
        if not await self.initialize():
            return None

        if not task.deadline:
            logger.info(f"Task {task.id} has no deadline, skipping calendar event")
            return None

        try:
            # Get assignee's calendar ID (their personal calendar if shared)
            target_calendar = self.calendar_id  # Default
            if task.assignee:
                assignee_info = await self._get_assignee_info(task.assignee)
                if assignee_info.get('calendar_id'):
                    target_calendar = assignee_info['calendar_id']
                    logger.info(f"Using {task.assignee}'s calendar: {target_calendar}")

            # Build event body
            event = self._build_event_body(task)

            # Create the event on assignee's calendar
            result = await asyncio.wait_for(
                asyncio.to_thread(self.service.events().insert(
                    calendarId=target_calendar,
                    body=event
                ).execute),
                timeout=30.0
            )

            event_id = result.get('id')
            logger.info(f"Created calendar event {event_id} for task {task.id} on calendar {target_calendar}")

            return event_id

        except HttpError as e:
            if e.resp.status == 404:
                logger.error(f"Calendar not found or not shared: {target_calendar}. "
                            f"Assignee needs to share their calendar with the service account.")
            else:
                logger.error(f"Google Calendar API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return None

    async def update_task_event(self, task: Task) -> bool:
        """Update an existing calendar event for a task."""
        if not await self.initialize():
            return False

        if not task.google_calendar_event_id:
            # No existing event, create one if there's a deadline
            if task.deadline:
                event_id = await self.create_task_event(task)
                return event_id is not None
            return True

        if not task.deadline:
            # Deadline removed, delete the event
            return await self.delete_task_event(task.google_calendar_event_id)

        try:
            # Get assignee's calendar ID (their personal calendar if shared)
            target_calendar = self.calendar_id  # Default
            if task.assignee:
                assignee_info = await self._get_assignee_info(task.assignee)
                if assignee_info.get('calendar_id'):
                    target_calendar = assignee_info['calendar_id']
                    logger.info(f"Updating event on {task.assignee}'s calendar: {target_calendar}")

            event = self._build_event_body(task)

            await asyncio.wait_for(
                asyncio.to_thread(self.service.events().update(
                    calendarId=target_calendar,
                    eventId=task.google_calendar_event_id,
                    body=event
                ).execute),
                timeout=30.0
            )

            logger.info(f"Updated calendar event for task {task.id}")
            return True

        except HttpError as e:
            if e.resp.status == 404:
                # Event was deleted, create a new one
                event_id = await self.create_task_event(task)
                return event_id is not None
            logger.error(f"Google Calendar API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating calendar event: {e}")
            return False

    async def delete_task_event(self, event_id: str) -> bool:
        """Delete a calendar event."""
        if not await self.initialize():
            return False

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self.service.events().delete(
                    calendarId=self.calendar_id,
                    eventId=event_id
                ).execute),
                timeout=30.0
            )

            logger.info(f"Deleted calendar event {event_id}")
            return True

        except HttpError as e:
            if e.resp.status == 404:
                # Already deleted
                return True
            logger.error(f"Google Calendar API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting calendar event: {e}")
            return False

    async def get_upcoming_deadlines(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get all task events with deadlines in the next X hours."""
        if not await self.initialize():
            return []

        try:
            now = datetime.utcnow()
            time_max = now + timedelta(hours=hours)

            events_result = await asyncio.wait_for(
                asyncio.to_thread(self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=now.isoformat() + 'Z',
                    timeMax=time_max.isoformat() + 'Z',
                    singleEvents=True,
                    orderBy='startTime',
                    q='[TASK]'  # Filter by task events
                ).execute),
                timeout=30.0
            )

            events = events_result.get('items', [])

            return [
                {
                    'event_id': e.get('id'),
                    'summary': e.get('summary'),
                    'start': e.get('start', {}).get('dateTime'),
                    'description': e.get('description'),
                    'task_id': self._extract_task_id(e.get('description', ''))
                }
                for e in events
            ]

        except Exception as e:
            logger.error(f"Error getting upcoming deadlines: {e}")
            return []

    async def create_reminder_event(
        self,
        title: str,
        description: str,
        reminder_time: datetime,
        duration_minutes: int = 30
    ) -> Optional[str]:
        """Create a standalone reminder event (not tied to a task)."""
        if not await self.initialize():
            return None

        try:
            end_time = reminder_time + timedelta(minutes=duration_minutes)

            event = {
                'summary': f"🔔 Reminder: {title}",
                'description': description,
                'start': {
                    'dateTime': reminder_time.isoformat(),
                    'timeZone': settings.timezone,
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': settings.timezone,
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 10},
                    ],
                },
            }

            result = await asyncio.wait_for(
                asyncio.to_thread(self.service.events().insert(
                    calendarId=self.calendar_id,
                    body=event
                ).execute),
                timeout=30.0
            )

            return result.get('id')

        except Exception as e:
            logger.error(f"Error creating reminder event: {e}")
            return None

    async def get_daily_schedule(self, date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get all events for a specific day."""
        if not await self.initialize():
            return []

        try:
            if date is None:
                date = datetime.now()

            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            events_result = await asyncio.wait_for(
                asyncio.to_thread(self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=day_start.isoformat() + 'Z',
                    timeMax=day_end.isoformat() + 'Z',
                    singleEvents=True,
                    orderBy='startTime'
                ).execute),
                timeout=30.0
            )

            return events_result.get('items', [])

        except Exception as e:
            logger.error(f"Error getting daily schedule: {e}")
            return []

    def _build_event_body(self, task: Task) -> Dict[str, Any]:
        """Build the calendar event body from a task."""
        # Determine event duration based on estimated effort
        duration_hours = 1  # Default 1 hour
        if task.estimated_effort:
            effort_lower = task.estimated_effort.lower()
            if 'hour' in effort_lower:
                try:
                    duration_hours = int(effort_lower.split()[0])
                except (ValueError, IndexError):
                    pass
            elif 'day' in effort_lower:
                duration_hours = 8  # Full day

        end_time = task.deadline + timedelta(hours=duration_hours)

        # Build description
        description_parts = [
            f"Task ID: {task.id}",
            f"Assignee: {task.assignee or 'Unassigned'}",
            f"Priority: {task.priority.value.upper()}",
            "",
            task.description,
        ]

        if task.acceptance_criteria:
            description_parts.append("\nAcceptance Criteria:")
            for criteria in task.acceptance_criteria:
                check = "☑" if criteria.completed else "☐"
                description_parts.append(f"{check} {criteria.description}")

        if task.notes:
            pinned = [n for n in task.notes if n.is_pinned]
            if pinned:
                description_parts.append("\nPinned Notes:")
                for note in pinned[:3]:
                    description_parts.append(f"• {note.content[:100]}")

        description = "\n".join(description_parts)

        # Status indicator in title
        status_prefix = ""
        if task.status == TaskStatus.DELAYED:
            status_prefix = "⏰ DELAYED: "
        elif task.status == TaskStatus.OVERDUE:
            status_prefix = "🚨 OVERDUE: "

        # Build reminders based on priority
        reminder_minutes = {
            TaskPriority.LOW: [60],           # 1 hour before
            TaskPriority.MEDIUM: [60, 30],    # 1 hour and 30 min before
            TaskPriority.HIGH: [120, 60, 30], # 2 hours, 1 hour, 30 min before
            TaskPriority.URGENT: [240, 120, 60, 30],  # 4 hours, 2 hours, 1 hour, 30 min
        }

        overrides = [
            {'method': 'popup', 'minutes': m}
            for m in reminder_minutes.get(task.priority, [60])
        ]

        event = {
            'summary': f"[TASK] {status_prefix}{task.title}",
            'description': description,
            'start': {
                'dateTime': task.deadline.isoformat(),
                'timeZone': settings.timezone,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': settings.timezone,
            },
            'colorId': self.PRIORITY_COLORS.get(task.priority, "5"),
            'reminders': {
                'useDefault': False,
                'overrides': overrides,
            },
        }

        # Add assignee as attendee if they have an email
        if task.assignee:
            assignee_email = self._get_assignee_email(task.assignee)
            if assignee_email:
                event['attendees'] = [
                    {'email': assignee_email, 'displayName': task.assignee}
                ]
                # Send notifications to attendees
                event['sendUpdates'] = 'all'

        return event

    async def _get_assignee_info(self, assignee_name: str) -> Dict[str, Optional[str]]:
        """
        Look up assignee's email and calendar ID from Google Sheets.

        Returns:
            Dict with 'email' and 'calendar_id' keys
        """
        result = {'email': None, 'calendar_id': None}

        if not assignee_name:
            return result

        assignee_lower = assignee_name.lower()

        # Try Google Sheets first (source of truth)
        try:
            from .sheets import sheets_integration
            team_members = await sheets_integration.get_all_team_members()
            for member in team_members:
                member_name = member.get("Name", "").strip().lower()
                if member_name == assignee_lower or assignee_lower in member_name:
                    result['email'] = member.get("Email", "")
                    result['calendar_id'] = member.get("Calendar ID", "") or member.get("Email", "")
                    logger.debug(f"Found {assignee_name} in Sheets: email={result['email']}, calendar={result['calendar_id']}")
                    return result
        except Exception as e:
            logger.debug(f"Sheets lookup failed for {assignee_name}: {e}")

        # Fallback to config/team.py
        try:
            from config.team import get_default_team
            team = get_default_team()

            for member in team:
                if member.get('name', '').lower() == assignee_lower:
                    result['email'] = member.get('email')
                    result['calendar_id'] = member.get('calendar_id') or member.get('email')
                    return result
        except Exception as e:
            logger.debug(f"Config lookup failed for {assignee_name}: {e}")

        return result

    def _get_assignee_email(self, assignee_name: str) -> Optional[str]:
        """Sync wrapper for backward compatibility."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context, fallback to config
                from config.team import get_default_team
                team = get_default_team()
                assignee_lower = assignee_name.lower()
                for member in team:
                    if member.get('name', '').lower() == assignee_lower:
                        return member.get('email')
                return None
            else:
                result = loop.run_until_complete(self._get_assignee_info(assignee_name))
                return result.get('email')
        except Exception as e:
            logger.debug(f"Could not look up assignee email: {e}")
            return None

    def _extract_task_id(self, description: str) -> Optional[str]:
        """Extract task ID from event description."""
        if not description:
            return None

        for line in description.split('\n'):
            if line.startswith('Task ID:'):
                return line.replace('Task ID:', '').strip()

        return None


# Singleton instance
calendar_integration = GoogleCalendarIntegration()


def get_calendar_integration() -> GoogleCalendarIntegration:
    """Get the Google Calendar integration instance."""
    return calendar_integration
