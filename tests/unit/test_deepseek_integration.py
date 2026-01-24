"""
Unit tests for DeepSeek AI integration.

Tests AI client operations including:
- Intent classification
- Task generation
- Entity extraction
- Question generation
- Report generation
- Attendance analysis
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.ai.deepseek import DeepSeekClient


@pytest.fixture
def deepseek():
    """Create DeepSeek client instance."""
    return DeepSeekClient()


@pytest.fixture
def mock_ai_response():
    """Create mock AI response."""
    def _response(content):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = content
        return response
    return _response


class TestDeepSeekIntegration:
    """Test DeepSeek AI integration functionality."""

    @pytest.mark.asyncio
    async def test_analyze_task_request_success(self, deepseek, mock_ai_response):
        """Test analyzing task request."""
        response_data = {
            "understood": {
                "title": "Fix login bug",
                "description": "Users cannot log in"
            },
            "missing_info": ["priority", "deadline"],
            "confidence": {"title": 0.95, "description": 0.9},
            "can_proceed_without_questions": False,
            "suggested_questions": [
                "What is the priority?",
                "When should this be done?"
            ]
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(response_data)

            result = await deepseek.analyze_task_request(
                "Fix the login bug, users cannot log in",
                {},
                {"Mayank": "Developer"}
            )

            assert result['understood']['title'] == "Fix login bug"
            assert "priority" in result['missing_info']
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_task_request_parse_error(self, deepseek):
        """Test handling JSON parse error in analysis."""
        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = "Invalid JSON"

            result = await deepseek.analyze_task_request(
                "Fix bug",
                {},
                {}
            )

            # Should return default structure
            assert 'understood' in result
            assert 'missing_info' in result
            assert result['can_proceed_without_questions'] is False

    @pytest.mark.asyncio
    async def test_generate_clarifying_questions(self, deepseek):
        """Test generating clarifying questions."""
        analysis = {
            "missing_info": ["priority", "assignee"],
            "understood": {"title": "Fix bug"}
        }
        response_data = {
            "questions": [
                {"field": "priority", "text": "How urgent is this?"},
                {"field": "assignee", "text": "Who should work on this?"}
            ],
            "intro_message": "I need more information."
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(response_data)

            result = await deepseek.generate_clarifying_questions(
                analysis,
                {},
                max_questions=2
            )

            assert len(result['questions']) == 2
            assert result['questions'][0]['field'] == 'priority'

    @pytest.mark.asyncio
    async def test_generate_task_spec_success(self, deepseek):
        """Test generating task specification."""
        spec_data = {
            "title": "Fix critical login bug",
            "description": "Users cannot authenticate",
            "priority": "urgent",
            "assignee": "Mayank",
            "deadline": "2026-02-01",
            "acceptance_criteria": [
                "Login works on all browsers",
                "Session persists correctly"
            ]
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(spec_data)

            result = await deepseek.generate_task_spec(
                "Fix the login bug",
                {"priority": "urgent", "assignee": "Mayank"},
                {},
                {"title": "Fix login bug"}
            )

            assert result['title'] == "Fix critical login bug"
            assert result['priority'] == "urgent"
            assert len(result['acceptance_criteria']) == 2

    @pytest.mark.asyncio
    async def test_generate_task_spec_detailed_mode(self, deepseek):
        """Test generating detailed spec with SPECSHEETS mode."""
        spec_data = {
            "title": "Build authentication system",
            "description": "Comprehensive auth system",
            "priority": "high",
            "subtasks": [
                {"title": "Design database schema", "description": "Create tables"},
                {"title": "Implement API endpoints", "description": "Build REST API"}
            ],
            "technical_details": "Use JWT tokens",
            "acceptance_criteria": ["Security audit passed"]
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(spec_data)

            result = await deepseek.generate_task_spec(
                "Build auth system",
                {},
                {},
                {},
                detailed_mode=True
            )

            assert 'subtasks' in result
            assert len(result['subtasks']) == 2
            assert 'technical_details' in result

    @pytest.mark.asyncio
    async def test_process_answer(self, deepseek):
        """Test processing user answer to question."""
        answer_data = {
            "field": "priority",
            "extracted_value": "urgent",
            "confidence": 0.95,
            "needs_followup": False
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(answer_data)

            result = await deepseek.process_answer(
                "What is the priority?",
                "This is very urgent!",
                {},
                "priority"
            )

            assert result['field'] == 'priority'
            assert result['extracted_value'] == 'urgent'
            assert result['confidence'] > 0.9

    @pytest.mark.asyncio
    async def test_generate_daily_standup(self, deepseek):
        """Test generating daily standup summary."""
        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = "**Daily Standup**\n\n3 tasks in progress\n2 completed yesterday"

            result = await deepseek.generate_daily_standup(
                [{'id': 'TASK-001', 'status': 'in_progress'}],
                [{'id': 'TASK-002', 'status': 'completed'}]
            )

            assert "Daily Standup" in result
            assert "tasks in progress" in result

    @pytest.mark.asyncio
    async def test_generate_weekly_summary(self, deepseek):
        """Test generating weekly summary report."""
        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = "**Weekly Summary**\n\nCompleted: 10 tasks\nPending: 5 tasks"

            result = await deepseek.generate_weekly_summary(
                {'completed': 10, 'pending': 5},
                {},
                {}
            )

            assert "Weekly Summary" in result
            assert "Completed" in result

    @pytest.mark.asyncio
    async def test_breakdown_task_success(self, deepseek):
        """Test breaking down complex task into subtasks."""
        breakdown_data = {
            "analysis": "This is a complex feature requiring multiple steps",
            "is_complex_enough": True,
            "recommended": True,
            "subtasks": [
                {
                    "title": "Design database schema",
                    "description": "Create tables for users and sessions",
                    "estimated_effort": "2 hours"
                },
                {
                    "title": "Build API endpoints",
                    "description": "Implement login and logout endpoints",
                    "estimated_effort": "4 hours"
                }
            ],
            "reason": "Task involves backend and frontend work"
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(breakdown_data)

            result = await deepseek.breakdown_task(
                "Build authentication system",
                "Complete user authentication with sessions",
                "feature",
                "high"
            )

            assert result['is_complex_enough'] is True
            assert len(result['subtasks']) == 2
            assert result['subtasks'][0]['title'] == "Design database schema"

    @pytest.mark.asyncio
    async def test_breakdown_task_not_complex(self, deepseek):
        """Test breakdown when task is too simple."""
        breakdown_data = {
            "analysis": "Task is straightforward",
            "is_complex_enough": False,
            "recommended": False,
            "subtasks": [],
            "reason": "Can be completed as single task"
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(breakdown_data)

            result = await deepseek.breakdown_task(
                "Fix typo",
                "Correct spelling in header",
                "bug",
                "low"
            )

            assert result['is_complex_enough'] is False
            assert result['recommended'] is False

    @pytest.mark.asyncio
    async def test_analyze_attendance_report(self, deepseek):
        """Test analyzing attendance report from boss."""
        attendance_data = {
            "affected_person": "Mayank",
            "status_type": "absence_reported",
            "affected_date": "2026-01-25",
            "reason": "Sick leave",
            "duration_minutes": None,
            "event_time": None,
            "confidence": 0.95,
            "multiple_people": False
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(attendance_data)

            result = await deepseek.analyze_attendance_report(
                "Mayank will be absent tomorrow due to sick leave",
                {"Mayank": "Developer"}
            )

            assert result['affected_person'] == "Mayank"
            assert result['status_type'] == "absence_reported"
            assert result['affected_date'] == "2026-01-25"
            assert result['confidence'] > 0.9

    @pytest.mark.asyncio
    async def test_analyze_attendance_late_arrival(self, deepseek):
        """Test analyzing late arrival report."""
        attendance_data = {
            "affected_person": "Mayank",
            "status_type": "late_reported",
            "affected_date": "2026-01-24",
            "reason": "Traffic",
            "duration_minutes": 30,
            "event_time": None,
            "confidence": 0.9,
            "multiple_people": False
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(attendance_data)

            result = await deepseek.analyze_attendance_report(
                "Mayank arrived 30 minutes late today due to traffic",
                {"Mayank": "Developer"}
            )

            assert result['status_type'] == "late_reported"
            assert result['duration_minutes'] == 30

    @pytest.mark.asyncio
    async def test_chat_method(self, deepseek, mock_ai_response):
        """Test direct chat method."""
        with patch.object(deepseek.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_ai_response("Hello! How can I help?")

            response = await deepseek.chat(
                [{"role": "user", "content": "Hello"}],
                temperature=0.7
            )

            assert response.choices[0].message.content == "Hello! How can I help?"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_api_with_json_mode(self, deepseek):
        """Test API call with JSON response format."""
        with patch.object(deepseek.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"result": "success"}'
            mock_create.return_value = mock_response

            result = await deepseek._call_api(
                [{"role": "user", "content": "Test"}],
                response_format={"type": "json_object"}
            )

            assert '{"result": "success"}' in result
            # Verify JSON mode was passed
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs['response_format'] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_call_api_retry_on_error(self, deepseek):
        """Test API retry logic on failure."""
        with patch.object(deepseek.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            # First call fails, second succeeds
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Success"

            mock_create.side_effect = [
                Exception("API error"),
                mock_response
            ]

            result = await deepseek._call_api(
                [{"role": "user", "content": "Test"}]
            )

            assert result == "Success"
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_format_preview(self, deepseek):
        """Test formatting task preview message."""
        spec = {
            "title": "Fix login bug",
            "description": "Users cannot log in",
            "priority": "urgent",
            "assignee": "Mayank"
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = "**Task Preview**\n\n📋 Fix login bug\n⚡ Urgent"

            result = await deepseek.format_preview(spec)

            assert "Fix login bug" in result
            assert "Urgent" in result

    @pytest.mark.asyncio
    async def test_transcribe_voice_placeholder(self, deepseek):
        """Test voice transcription placeholder."""
        result = await deepseek.transcribe_voice("/path/to/audio.ogg")

        # Should return placeholder message
        assert "Voice message" in result
        assert "not available" in result

    @pytest.mark.asyncio
    async def test_breakdown_task_with_acceptance_criteria(self, deepseek):
        """Test breakdown with acceptance criteria."""
        breakdown_data = {
            "analysis": "Complex feature with clear requirements",
            "is_complex_enough": True,
            "recommended": True,
            "subtasks": [
                {"title": "Implement feature A", "description": "..."},
                {"title": "Implement feature B", "description": "..."}
            ]
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(breakdown_data)

            result = await deepseek.breakdown_task(
                "Build feature",
                "Complex feature",
                "feature",
                "high",
                estimated_effort="1 week",
                acceptance_criteria=["Must work on mobile", "Must be secure"]
            )

            assert result['is_complex_enough'] is True
            # Verify the method was called
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_task_with_conversation_history(self, deepseek):
        """Test analysis with conversation context."""
        response_data = {
            "understood": {"title": "Continue previous work"},
            "missing_info": [],
            "confidence": {"title": 0.9},
            "can_proceed_without_questions": True,
            "suggested_questions": []
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(response_data)

            result = await deepseek.analyze_task_request(
                "Continue working on it",
                {},
                {},
                conversation_history="Previously discussed: Build login system"
            )

            assert result['understood']['title'] == "Continue previous work"
            # Verify the method was called with conversation history
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_spec_parse_error_fallback(self, deepseek):
        """Test spec generation with parse error returns minimal spec."""
        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = "Invalid JSON response"

            result = await deepseek.generate_task_spec(
                "Fix bug",
                {},
                {},
                {"title": "Fix bug", "description": "Critical issue"}
            )

            # Should return minimal spec from extracted info
            assert 'title' in result
            assert result['title'] == "Fix bug"
            assert result['priority'] == "medium"  # Default

    @pytest.mark.asyncio
    async def test_process_answer_parse_error_fallback(self, deepseek):
        """Test answer processing with parse error returns basic extraction."""
        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = "Invalid JSON"

            result = await deepseek.process_answer(
                "What priority?",
                "urgent",
                {},
                "priority"
            )

            # Should return basic extraction
            assert result['field'] == 'priority'
            assert result['extracted_value'] == 'urgent'
            assert result['confidence'] == 0.8

    @pytest.mark.asyncio
    async def test_analyze_attendance_multiple_people(self, deepseek):
        """Test analyzing attendance report for multiple people."""
        attendance_data = {
            "affected_person": "Mayank, Zea",
            "status_type": "absence_reported",
            "affected_date": "2026-01-25",
            "reason": "Team offsite",
            "duration_minutes": None,
            "event_time": None,
            "confidence": 0.85,
            "multiple_people": True
        }

        with patch.object(deepseek, '_call_api') as mock_api:
            mock_api.return_value = json.dumps(attendance_data)

            result = await deepseek.analyze_attendance_report(
                "Mayank and Zea will be at team offsite tomorrow",
                {"Mayank": "Developer", "Zea": "Admin"}
            )

            assert result['multiple_people'] is True
            assert "Mayank" in result['affected_person']
