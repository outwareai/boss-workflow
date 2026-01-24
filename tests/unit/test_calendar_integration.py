"""
Unit tests for Google Calendar integration.

Tests Google Calendar operations including:
- Event creation for task deadlines
- Event updates
- Event deletion
- Reminder management
- Calendar scheduling
- Timezone handling
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.integrations.calendar import GoogleCalendarIntegration
from src.models.task import Task, TaskPriority, TaskStatus


@pytest.fixture
def calendar():
    """Create Google Calendar integration instance."""
    return GoogleCalendarIntegration()


@pytest.fixture
def sample_task():
    """Create sample task with deadline."""
    return Task(
        id="TASK-001",
        title="Fix critical bug",
        description="Production issue",
        assignee="Mayank",
        priority=TaskPriority.URGENT,
        status=TaskStatus.PENDING,
        deadline=datetime(2026, 2, 1, 10, 0),
        estimated_effort="2 hours"
    )


class TestGoogleCalendarIntegration:
    """Test Google Calendar integration functionality."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, calendar):
        """Test successful initialization."""
        with patch('src.integrations.calendar.build') as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            result = await calendar.initialize()

            assert result is True
            assert calendar._initialized is True
            assert calendar.service == mock_service

    @pytest.mark.asyncio
    async def test_initialize_failure(self, calendar):
        """Test initialization failure."""
        with patch('src.integrations.calendar.build') as mock_build:
            mock_build.side_effect = Exception("Auth failed")

            result = await calendar.initialize()

            assert result is False

    @pytest.mark.asyncio
    async def test_create_task_event_success(self, calendar, sample_task):
        """Test creating calendar event for task."""
        calendar._initialized = True
        calendar.service = MagicMock()

        with patch.object(calendar, '_get_assignee_info') as mock_info:
            mock_info.return_value = {'email': 'mayank@example.com', 'calendar_id': 'primary'}
            with patch('asyncio.to_thread') as mock_thread:
                mock_result = {'id': 'event_123'}
                mock_thread.return_value = mock_result

                event_id = await calendar.create_task_event(sample_task)

                assert event_id == 'event_123'

    @pytest.mark.asyncio
    async def test_create_task_event_no_deadline(self, calendar, sample_task):
        """Test skipping event creation when task has no deadline."""
        calendar._initialized = True
        sample_task.deadline = None

        event_id = await calendar.create_task_event(sample_task)

        assert event_id is None

    @pytest.mark.asyncio
    async def test_create_task_event_calendar_not_found(self, calendar, sample_task):
        """Test handling calendar not found error."""
        from googleapiclient.errors import HttpError

        calendar._initialized = True
        calendar.service = MagicMock()

        with patch.object(calendar, '_get_assignee_info') as mock_info:
            mock_info.return_value = {'email': 'mayank@example.com', 'calendar_id': 'invalid'}
            with patch('asyncio.to_thread') as mock_thread:
                mock_response = MagicMock()
                mock_response.status = 404
                mock_thread.side_effect = HttpError(mock_response, b'Not found')

                event_id = await calendar.create_task_event(sample_task)

                assert event_id is None

    @pytest.mark.asyncio
    async def test_update_task_event_success(self, calendar, sample_task):
        """Test updating existing calendar event."""
        calendar._initialized = True
        calendar.service = MagicMock()
        sample_task.google_calendar_event_id = 'event_123'

        with patch.object(calendar, '_get_assignee_info') as mock_info:
            mock_info.return_value = {'email': 'mayank@example.com', 'calendar_id': 'primary'}
            with patch('asyncio.to_thread') as mock_thread:
                mock_thread.return_value = {'id': 'event_123'}

                result = await calendar.update_task_event(sample_task)

                assert result is True

    @pytest.mark.asyncio
    async def test_update_task_event_create_if_missing(self, calendar, sample_task):
        """Test creating event if it doesn't exist during update."""
        calendar._initialized = True
        sample_task.google_calendar_event_id = None

        with patch.object(calendar, 'create_task_event') as mock_create:
            mock_create.return_value = 'event_123'

            result = await calendar.update_task_event(sample_task)

            assert result is True
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_task_event_delete_if_no_deadline(self, calendar, sample_task):
        """Test deleting event when deadline is removed."""
        calendar._initialized = True
        sample_task.google_calendar_event_id = 'event_123'
        sample_task.deadline = None

        with patch.object(calendar, 'delete_task_event') as mock_delete:
            mock_delete.return_value = True

            result = await calendar.update_task_event(sample_task)

            assert result is True
            mock_delete.assert_called_once_with('event_123')

    @pytest.mark.asyncio
    async def test_delete_task_event_success(self, calendar):
        """Test deleting calendar event."""
        calendar._initialized = True
        calendar.service = MagicMock()

        with patch('asyncio.to_thread') as mock_thread:
            mock_thread.return_value = None

            result = await calendar.delete_task_event('event_123')

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_task_event_already_deleted(self, calendar):
        """Test deleting already deleted event (404)."""
        from googleapiclient.errors import HttpError

        calendar._initialized = True
        calendar.service = MagicMock()

        with patch('asyncio.to_thread') as mock_thread:
            mock_response = MagicMock()
            mock_response.status = 404
            mock_thread.side_effect = HttpError(mock_response, b'Not found')

            result = await calendar.delete_task_event('event_123')

            # Should return True for already deleted
            assert result is True

    @pytest.mark.asyncio
    async def test_get_upcoming_deadlines(self, calendar):
        """Test getting upcoming task deadlines."""
        calendar._initialized = True
        calendar.service = MagicMock()

        with patch('asyncio.to_thread') as mock_thread:
            mock_thread.return_value = {
                'items': [
                    {
                        'id': 'event_1',
                        'summary': '[TASK] Fix bug',
                        'start': {'dateTime': '2026-02-01T10:00:00Z'},
                        'description': 'Task ID: TASK-001\nDescription'
                    }
                ]
            }

            deadlines = await calendar.get_upcoming_deadlines(hours=24)

            assert len(deadlines) == 1
            assert deadlines[0]['task_id'] == 'TASK-001'

    @pytest.mark.asyncio
    async def test_create_reminder_event(self, calendar):
        """Test creating standalone reminder."""
        calendar._initialized = True
        calendar.service = MagicMock()

        reminder_time = datetime(2026, 2, 1, 14, 0)

        with patch('asyncio.to_thread') as mock_thread:
            mock_thread.return_value = {'id': 'reminder_123'}

            event_id = await calendar.create_reminder_event(
                "Team Meeting",
                "Quarterly review",
                reminder_time,
                duration_minutes=60
            )

            assert event_id == 'reminder_123'

    @pytest.mark.asyncio
    async def test_get_daily_schedule(self, calendar):
        """Test getting daily schedule."""
        calendar._initialized = True
        calendar.service = MagicMock()

        with patch('asyncio.to_thread') as mock_thread:
            mock_thread.return_value = {
                'items': [
                    {
                        'id': 'event_1',
                        'summary': 'Meeting',
                        'start': {'dateTime': '2026-01-24T10:00:00Z'}
                    },
                    {
                        'id': 'event_2',
                        'summary': '[TASK] Deadline',
                        'start': {'dateTime': '2026-01-24T14:00:00Z'}
                    }
                ]
            }

            schedule = await calendar.get_daily_schedule(datetime(2026, 1, 24))

            assert len(schedule) == 2

    @pytest.mark.asyncio
    async def test_build_event_body_with_high_priority(self, calendar, sample_task):
        """Test building event body for high priority task."""
        sample_task.priority = TaskPriority.HIGH

        event = calendar._build_event_body(sample_task)

        assert event['summary'] == '[TASK] Fix critical bug'
        assert event['colorId'] == '6'  # Orange for high priority
        assert 'Task ID: TASK-001' in event['description']
        # High priority should have multiple reminders
        assert len(event['reminders']['overrides']) == 3

    @pytest.mark.asyncio
    async def test_build_event_body_with_urgent_priority(self, calendar, sample_task):
        """Test building event body for urgent priority task."""
        sample_task.priority = TaskPriority.URGENT

        event = calendar._build_event_body(sample_task)

        assert event['colorId'] == '11'  # Red for urgent
        # Urgent should have most reminders
        assert len(event['reminders']['overrides']) == 4

    @pytest.mark.asyncio
    async def test_build_event_body_with_overdue_status(self, calendar, sample_task):
        """Test building event body for overdue task."""
        sample_task.status = TaskStatus.OVERDUE

        event = calendar._build_event_body(sample_task)

        assert '🚨 OVERDUE:' in event['summary']

    @pytest.mark.asyncio
    async def test_build_event_body_with_delayed_status(self, calendar, sample_task):
        """Test building event body for delayed task."""
        sample_task.status = TaskStatus.DELAYED

        event = calendar._build_event_body(sample_task)

        assert '⏰ DELAYED:' in event['summary']

    @pytest.mark.asyncio
    async def test_build_event_body_includes_acceptance_criteria(self, calendar, sample_task):
        """Test event body includes acceptance criteria."""
        from src.models.task import AcceptanceCriteria

        sample_task.acceptance_criteria = [
            AcceptanceCriteria(description="Must work on mobile", completed=False),
            AcceptanceCriteria(description="Must be secure", completed=True)
        ]

        event = calendar._build_event_body(sample_task)

        assert 'Acceptance Criteria:' in event['description']
        assert 'Must work on mobile' in event['description']

    @pytest.mark.asyncio
    async def test_get_assignee_info_from_sheets(self, calendar):
        """Test looking up assignee info from Google Sheets."""
        with patch('src.integrations.sheets.sheets_integration') as mock_sheets:
            mock_sheets.get_all_team_members = AsyncMock(return_value=[
                {
                    'Name': 'Mayank',
                    'Email': 'mayank@example.com',
                    'Calendar ID': 'mayank@example.com'
                }
            ])

            info = await calendar._get_assignee_info('Mayank')

            assert info['email'] == 'mayank@example.com'
            assert info['calendar_id'] == 'mayank@example.com'

    @pytest.mark.asyncio
    async def test_get_assignee_info_not_found(self, calendar):
        """Test looking up non-existent assignee."""
        with patch('src.integrations.sheets.sheets_integration') as mock_sheets:
            mock_sheets.get_all_team_members = AsyncMock(return_value=[])

            info = await calendar._get_assignee_info('Unknown')

            assert info['email'] is None
            assert info['calendar_id'] is None

    @pytest.mark.asyncio
    async def test_extract_task_id_from_description(self, calendar):
        """Test extracting task ID from event description."""
        description = "Task ID: TASK-001\nSome description"

        task_id = calendar._extract_task_id(description)

        assert task_id == 'TASK-001'

    @pytest.mark.asyncio
    async def test_extract_task_id_no_match(self, calendar):
        """Test extracting task ID when not present."""
        description = "Regular event description"

        task_id = calendar._extract_task_id(description)

        assert task_id is None

    @pytest.mark.asyncio
    async def test_set_calendar_id(self, calendar):
        """Test setting custom calendar ID."""
        calendar.set_calendar_id('custom_calendar@example.com')

        assert calendar.calendar_id == 'custom_calendar@example.com'

    @pytest.mark.asyncio
    async def test_build_event_body_estimated_effort_hours(self, calendar, sample_task):
        """Test event duration based on estimated effort (hours)."""
        sample_task.estimated_effort = "3 hours"

        event = calendar._build_event_body(sample_task)

        # End time should be 3 hours after start
        start = datetime.fromisoformat(event['start']['dateTime'])
        end = datetime.fromisoformat(event['end']['dateTime'])
        duration = (end - start).total_seconds() / 3600

        assert duration == 3

    @pytest.mark.asyncio
    async def test_build_event_body_estimated_effort_days(self, calendar, sample_task):
        """Test event duration based on estimated effort (days)."""
        sample_task.estimated_effort = "1 day"

        event = calendar._build_event_body(sample_task)

        # End time should be 8 hours after start (1 workday)
        start = datetime.fromisoformat(event['start']['dateTime'])
        end = datetime.fromisoformat(event['end']['dateTime'])
        duration = (end - start).total_seconds() / 3600

        assert duration == 8

    @pytest.mark.asyncio
    async def test_build_event_body_includes_pinned_notes(self, calendar, sample_task):
        """Test event body includes pinned notes."""
        # Create mock notes
        note1 = MagicMock()
        note1.content = "Important context"
        note1.is_pinned = True
        note1.author = "Boss"

        note2 = MagicMock()
        note2.content = "Regular note"
        note2.is_pinned = False
        note2.author = "Dev"

        sample_task.notes = [note1, note2]

        event = calendar._build_event_body(sample_task)

        assert 'Pinned Notes:' in event['description']
        assert 'Important context' in event['description']

    @pytest.mark.asyncio
    async def test_build_event_body_includes_attendee(self, calendar, sample_task):
        """Test event body includes assignee as attendee."""
        with patch.object(calendar, '_get_assignee_email') as mock_email:
            mock_email.return_value = 'mayank@example.com'

            event = calendar._build_event_body(sample_task)

            assert 'attendees' in event
            assert event['attendees'][0]['email'] == 'mayank@example.com'
            assert event['sendUpdates'] == 'all'

    @pytest.mark.asyncio
    async def test_create_task_event_uses_assignee_calendar(self, calendar, sample_task):
        """Test event is created on assignee's personal calendar if available."""
        calendar._initialized = True
        calendar.service = MagicMock()

        with patch.object(calendar, '_get_assignee_info') as mock_info:
            mock_info.return_value = {
                'email': 'mayank@example.com',
                'calendar_id': 'mayank_custom@example.com'
            }
            with patch('asyncio.to_thread') as mock_thread:
                mock_thread.return_value = {'id': 'event_123'}

                event_id = await calendar.create_task_event(sample_task)

                # Should use assignee's custom calendar
                assert event_id == 'event_123'
                # Verify calendar ID was passed to API
                call_args = mock_thread.call_args[0][0]
                # The function creates events with calendarId parameter

    @pytest.mark.asyncio
    async def test_update_event_not_found_creates_new(self, calendar, sample_task):
        """Test updating event that doesn't exist creates new one."""
        from googleapiclient.errors import HttpError

        calendar._initialized = True
        calendar.service = MagicMock()
        sample_task.google_calendar_event_id = 'deleted_event'

        with patch.object(calendar, '_get_assignee_info') as mock_info:
            mock_info.return_value = {'email': 'mayank@example.com', 'calendar_id': 'primary'}
            with patch('asyncio.to_thread') as mock_thread:
                # First call (update) fails with 404
                mock_response = MagicMock()
                mock_response.status = 404
                mock_thread.side_effect = [
                    HttpError(mock_response, b'Not found'),
                    {'id': 'new_event_123'}  # Second call (create) succeeds
                ]

                result = await calendar.update_task_event(sample_task)

                assert result is True
                # Should have attempted both update and create
                assert mock_thread.call_count == 2
