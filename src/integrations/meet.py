"""
Google Meet integration for quick meeting links.

Creates instant meeting links for task discussions,
blocked task resolution, or team syncs.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, UTC
import json
import uuid

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings

logger = logging.getLogger(__name__)


class GoogleMeetIntegration:
    """
    Google Meet integration for creating meeting links.

    Features:
    - Quick meet links for task discussions
    - Scheduled meetings for reviews
    - Integration with Calendar for reminders
    """

    SCOPES = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events'
    ]

    def __init__(self):
        self.service = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize Google Calendar API for Meet links."""
        if not settings.google_credentials_json:
            logger.warning("Google credentials not configured for Meet")
            return False

        try:
            # Parse credentials (async)
            if settings.google_credentials_json.startswith('{'):
                creds_dict = await asyncio.to_thread(json.loads, settings.google_credentials_json)
            else:
                import aiofiles
                async def _read_creds_file_async(path):
                    async with aiofiles.open(path, 'r') as f:
                        content = await f.read()
                        return await asyncio.to_thread(json.loads, content)
                creds_dict = await _read_creds_file_async(settings.google_credentials_json)

            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=self.SCOPES
            )

            self.service = build('calendar', 'v3', credentials=credentials)
            self._initialized = True

            logger.info("Google Meet integration initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Meet: {e}")
            return False

    async def create_instant_meeting(
        self,
        title: str,
        description: Optional[str] = None,
        duration_minutes: int = 30,
        attendees: Optional[list] = None
    ) -> Optional[Dict[str, str]]:
        """
        Create an instant meeting starting now.

        Args:
            title: Meeting title
            description: Optional description
            duration_minutes: Meeting duration
            attendees: List of email addresses to invite

        Returns:
            Dict with meet_link, event_id, and event_link
        """
        if not self._initialized:
            await self.initialize()

        if not self.service:
            return None

        try:
            now = datetime.now(UTC)
            end = now + timedelta(minutes=duration_minutes)

            event = {
                'summary': title,
                'description': description or f"Quick meeting for: {title}",
                'start': {
                    'dateTime': now.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': settings.timezone
                },
                'end': {
                    'dateTime': end.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': settings.timezone
                },
                'conferenceData': {
                    'createRequest': {
                        'requestId': str(uuid.uuid4()),
                        'conferenceSolutionKey': {
                            'type': 'hangoutsMeet'
                        }
                    }
                }
            }

            # Add attendees if provided
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]

            # Create event with conference
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.service.events().insert(
                        calendarId='primary',
                        body=event,
                        conferenceDataVersion=1,
                        sendUpdates='all' if attendees else 'none'
                    ).execute
                ),
                timeout=30.0
            )

            # Extract Meet link
            meet_link = None
            conference_data = result.get('conferenceData', {})
            entry_points = conference_data.get('entryPoints', [])
            for ep in entry_points:
                if ep.get('entryPointType') == 'video':
                    meet_link = ep.get('uri')
                    break

            logger.info(f"Created instant meeting: {meet_link}")

            return {
                'meet_link': meet_link,
                'event_id': result.get('id'),
                'event_link': result.get('htmlLink')
            }

        except Exception as e:
            logger.error(f"Error creating instant meeting: {e}")
            return None

    async def schedule_meeting(
        self,
        title: str,
        start_time: datetime,
        duration_minutes: int = 60,
        description: Optional[str] = None,
        attendees: Optional[list] = None
    ) -> Optional[Dict[str, str]]:
        """
        Schedule a future meeting with Meet link.

        Args:
            title: Meeting title
            start_time: When the meeting starts
            duration_minutes: Duration
            description: Meeting description
            attendees: List of email addresses

        Returns:
            Dict with meet_link, event_id, and event_link
        """
        if not self._initialized:
            await self.initialize()

        if not self.service:
            return None

        try:
            end_time = start_time + timedelta(minutes=duration_minutes)

            event = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start_time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': settings.timezone
                },
                'end': {
                    'dateTime': end_time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': settings.timezone
                },
                'conferenceData': {
                    'createRequest': {
                        'requestId': str(uuid.uuid4()),
                        'conferenceSolutionKey': {
                            'type': 'hangoutsMeet'
                        }
                    }
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 10},
                        {'method': 'email', 'minutes': 60}
                    ]
                }
            }

            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.service.events().insert(
                        calendarId='primary',
                        body=event,
                        conferenceDataVersion=1,
                        sendUpdates='all' if attendees else 'none'
                    ).execute
                ),
                timeout=30.0
            )

            # Extract Meet link
            meet_link = None
            conference_data = result.get('conferenceData', {})
            entry_points = conference_data.get('entryPoints', [])
            for ep in entry_points:
                if ep.get('entryPointType') == 'video':
                    meet_link = ep.get('uri')
                    break

            logger.info(f"Scheduled meeting for {start_time}: {meet_link}")

            return {
                'meet_link': meet_link,
                'event_id': result.get('id'),
                'event_link': result.get('htmlLink'),
                'start_time': start_time.isoformat()
            }

        except Exception as e:
            logger.error(f"Error scheduling meeting: {e}")
            return None

    async def create_task_discussion(
        self,
        task_id: str,
        task_title: str,
        attendees: Optional[list] = None
    ) -> Optional[Dict[str, str]]:
        """
        Create a quick meeting for discussing a specific task.
        """
        return await self.create_instant_meeting(
            title=f"Task Discussion: {task_title[:50]}",
            description=f"Quick sync to discuss task {task_id}\n\n{task_title}",
            duration_minutes=15,
            attendees=attendees
        )

    async def create_blocked_task_meeting(
        self,
        task_id: str,
        task_title: str,
        blocker_reason: str,
        attendees: Optional[list] = None
    ) -> Optional[Dict[str, str]]:
        """
        Create a meeting to resolve a blocked task.
        """
        return await self.create_instant_meeting(
            title=f"🚫 Blocked: {task_title[:40]}",
            description=(
                f"Meeting to resolve blocker for task {task_id}\n\n"
                f"Task: {task_title}\n"
                f"Blocker: {blocker_reason}"
            ),
            duration_minutes=30,
            attendees=attendees
        )

    async def delete_meeting(self, event_id: str) -> bool:
        """Delete a scheduled meeting."""
        if not self.service:
            return False

        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self.service.events().delete(
                        calendarId='primary',
                        eventId=event_id
                    ).execute
                ),
                timeout=30.0
            )

            logger.info(f"Deleted meeting: {event_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting meeting: {e}")
            return False


# Singleton
meet_integration = GoogleMeetIntegration()


def get_meet_integration() -> GoogleMeetIntegration:
    return meet_integration
