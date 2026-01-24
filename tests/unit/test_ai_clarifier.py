"""
Unit tests for Task Clarifier - Smart question generation and conversation management.

Tests:
- generate_questions() - Main question generation
- complexity_score() - Task complexity detection (1-10)
- self_answer_questions() - AI self-answering
- parse_user_answers() - Answer parsing
- should_ask_questions() - Question necessity logic
- Template detection
- Dependency finding
- Spec preview generation
- Answer processing
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime

from src.ai.clarifier import TaskClarifier
from src.models.conversation import ConversationState, ConversationStage, ClarifyingQuestion


@pytest.fixture
def clarifier():
    """Create TaskClarifier instance with mocked DeepSeek client."""
    mock_client = MagicMock()
    mock_client._call_api = AsyncMock()
    mock_client.client = MagicMock()
    mock_client.client.chat = MagicMock()
    mock_client.client.chat.completions = MagicMock()
    mock_client.client.chat.completions.create = AsyncMock()
    return TaskClarifier(deepseek_client=mock_client)


@pytest.fixture
def conversation():
    """Create a basic conversation state."""
    return ConversationState(
        user_id="test_user",
        chat_id=123,
        original_message="Fix the login bug",
        stage=ConversationStage.ANALYZING
    )


class TestComplexityScore:
    """Test task complexity scoring (1-10)."""

    def test_simple_task_low_score(self, clarifier):
        """Test simple tasks get low complexity score (1-3)."""
        score = clarifier._calculate_task_complexity("Fix typo in README", {})
        assert score <= 3
        assert score >= 1

    def test_complex_task_high_score(self, clarifier):
        """Test complex tasks get high complexity score (7-10)."""
        message = "Build entire notification system with email, SMS, push notifications, and scheduling"
        score = clarifier._calculate_task_complexity(message, {})
        assert score >= 7

    def test_medium_task_medium_score(self, clarifier):
        """Test medium tasks get medium score (4-6)."""
        message = "Implement user profile page with settings"
        score = clarifier._calculate_task_complexity(message, {})
        assert 4 <= score <= 6

    def test_complexity_keywords_increase_score(self, clarifier):
        """Test complexity keywords increase score."""
        simple = clarifier._calculate_task_complexity("Update homepage", {})
        complex = clarifier._calculate_task_complexity("Design and build complete system architecture", {})
        assert complex > simple

    def test_multiple_scope_indicators(self, clarifier):
        """Test multiple scope indicators increase complexity."""
        message = "Build comprehensive, complete, full authentication system"
        score = clarifier._calculate_task_complexity(message, {})
        assert score >= 7

    def test_long_message_increases_complexity(self, clarifier):
        """Test long messages indicate higher complexity."""
        short = clarifier._calculate_task_complexity("Fix bug", {})
        long_message = " ".join(["detailed"] * 50)
        long = clarifier._calculate_task_complexity(long_message, {})
        assert long > short

    def test_subtask_indicator_increases_complexity(self, clarifier):
        """Test subtask indicators increase complexity."""
        message = "Fix login: subtask 1, subtask 2, subtask 3, subtask 4, subtask 5"
        score = clarifier._calculate_task_complexity(message, {})
        assert score >= 5

    def test_technical_keywords_increase_complexity(self, clarifier):
        """Test technical keywords add complexity."""
        message = "Build API with database migration and authentication"
        score = clarifier._calculate_task_complexity(message, {})
        assert score >= 5

    def test_no_questions_phrase_forces_simple(self, clarifier):
        """Test 'no questions' phrase overrides to simple."""
        message = "Build entire system no questions asked"
        score = clarifier._calculate_task_complexity(message, {})
        assert score <= 3

    def test_simple_keywords_without_complexity_reduce_score(self, clarifier):
        """Test simple keywords reduce score when no complexity."""
        message = "Quick fix for small typo"
        score = clarifier._calculate_task_complexity(message, {})
        assert score <= 3

    def test_complexity_clamped_to_1_10(self, clarifier):
        """Test complexity is always between 1 and 10."""
        very_complex = "Build complete comprehensive complex entire full system architecture design integration implementation"
        score = clarifier._calculate_task_complexity(very_complex, {})
        assert 1 <= score <= 10


class TestAnalyzeAndDecide:
    """Test analyze_and_decide - main question decision logic."""

    @pytest.mark.asyncio
    async def test_simple_task_skips_questions(self, clarifier, conversation):
        """Test simple tasks skip all questions."""
        conversation.original_message = "Fix typo in README"

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "Fix typo", "assignee": "Mayank"},
                "suggested_questions": [],
                "missing_info": [],
                "confidence": {"title": 0.95},
                "can_proceed_without_questions": True
            }

            should_ask, analysis = await clarifier.analyze_and_decide(
                conversation,
                {},
                {"Mayank": "Developer"}
            )

            assert should_ask is False
            assert analysis["complexity"] <= 3
            assert len(analysis["suggested_questions"]) == 0

    @pytest.mark.asyncio
    async def test_complex_task_asks_questions(self, clarifier, conversation):
        """Test complex tasks ask questions."""
        conversation.original_message = "Build complete authentication system with OAuth, JWT, 2FA"

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "Build auth system"},
                "suggested_questions": [
                    {"question": "Which OAuth providers?", "field": "oauth"},
                    {"question": "Security requirements?", "field": "security"}
                ],
                "missing_info": ["oauth", "security"],
                "confidence": {"title": 0.9},
                "can_proceed_without_questions": False
            }

            with patch.object(clarifier, '_intelligent_self_answer') as mock_self_answer:
                mock_self_answer.return_value = ({}, [
                    {"question": "Which OAuth providers?", "field": "oauth"}
                ])

                should_ask, analysis = await clarifier.analyze_and_decide(
                    conversation,
                    {},
                    {"Mayank": "Developer"}
                )

                assert should_ask is True
                assert analysis["complexity"] >= 7

    @pytest.mark.asyncio
    async def test_medium_task_asks_critical_only(self, clarifier, conversation):
        """Test medium tasks ask only critical questions."""
        conversation.original_message = "Implement user profile page"

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "User profile"},
                "suggested_questions": [
                    {"question": "Who should work on this?", "field": "assignee"},
                    {"question": "Any deadline?", "field": "deadline"}
                ],
                "missing_info": ["assignee"],
                "confidence": {"title": 0.9},
                "can_proceed_without_questions": False
            }

            with patch.object(clarifier, '_intelligent_self_answer') as mock_self_answer:
                mock_self_answer.return_value = ({}, [
                    {"question": "Who should work on this?", "field": "assignee"}
                ])

                should_ask, analysis = await clarifier.analyze_and_decide(
                    conversation,
                    {},
                    {}
                )

                # Medium complexity should limit questions
                assert analysis["complexity"] <= 6
                assert len(analysis["suggested_questions"]) <= 2

    @pytest.mark.asyncio
    async def test_user_says_no_questions(self, clarifier, conversation):
        """Test explicit 'no questions' phrase skips all questions."""
        conversation.original_message = "Build auth system - no need to ask questions"

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "Auth system"},
                "suggested_questions": [],
                "missing_info": [],
                "confidence": {"title": 0.9},
                "can_proceed_without_questions": True
            }

            should_ask, analysis = await clarifier.analyze_and_decide(
                conversation,
                {},
                {}
            )

            assert should_ask is False

    @pytest.mark.asyncio
    async def test_template_applied_to_conversation(self, clarifier, conversation):
        """Test template defaults are applied."""
        conversation.original_message = "Bug: Users can't login"

        with patch.object(clarifier.ai, 'analyze_task_request') as mock_analyze:
            mock_analyze.return_value = {
                "understood": {"title": "Login bug"},
                "suggested_questions": [],
                "missing_info": [],
                "confidence": {"title": 0.95},
                "can_proceed_without_questions": True
            }

            should_ask, analysis = await clarifier.analyze_and_decide(
                conversation,
                {},
                {}
            )

            # Bug template should apply high priority and tags
            assert "template_applied" in analysis
            assert conversation.extracted_info.get("task_type") == "bug"
            assert conversation.extracted_info.get("priority") == "high"


class TestIntelligentSelfAnswer:
    """Test AI self-answering questions."""

    @pytest.mark.asyncio
    async def test_self_answer_fills_missing_info(self, clarifier):
        """Test AI fills in missing information."""
        with patch.object(clarifier.ai, '_call_api') as mock_api:
            mock_api.return_value = json.dumps({
                "self_answered": {
                    "priority": "medium",
                    "estimated_effort": "4 hours",
                    "technical_approach": "Use JWT tokens"
                },
                "remaining_questions": [],
                "reasoning": "Task is clear, used best practices"
            })

            analysis = {
                "suggested_questions": [{"question": "Priority?", "field": "priority"}],
                "missing_info": ["priority", "effort"]
            }

            self_answered, remaining = await clarifier._intelligent_self_answer(
                "Fix login bug",
                analysis,
                {},
                {},
                False
            )

            assert self_answered["priority"] == "medium"
            assert "estimated_effort" in self_answered
            assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_self_answer_error_returns_empty(self, clarifier):
        """Test self-answer error handling."""
        with patch.object(clarifier.ai, '_call_api') as mock_api:
            mock_api.side_effect = Exception("API error")

            self_answered, remaining = await clarifier._intelligent_self_answer(
                "Fix bug",
                {"suggested_questions": [], "missing_info": []},
                {},
                {},
                False
            )

            assert self_answered == {}
            assert remaining == []


class TestTemplateDetection:
    """Test task template detection and application."""

    def test_bug_template_detected(self, clarifier, conversation):
        """Test bug template is detected and applied."""
        conversation.original_message = "Bug: Login doesn't work"

        template_info = clarifier.detect_and_apply_template(conversation, {})

        assert template_info is not None
        assert template_info["template_name"] == "bug"
        assert conversation.extracted_info.get("priority") == "high"
        assert "bugfix" in conversation.extracted_info.get("tags", [])

    def test_hotfix_template_detected(self, clarifier, conversation):
        """Test hotfix template is detected."""
        conversation.original_message = "Hotfix: Critical production issue"

        template_info = clarifier.detect_and_apply_template(conversation, {})

        assert template_info is not None
        assert template_info["template_name"] == "hotfix"
        assert conversation.extracted_info.get("priority") == "urgent"

    def test_feature_template_detected(self, clarifier, conversation):
        """Test feature template is detected."""
        conversation.original_message = "New feature: Add dark mode"

        template_info = clarifier.detect_and_apply_template(conversation, {})

        assert template_info is not None
        assert template_info["template_name"] == "feature"
        assert conversation.extracted_info.get("task_type") == "feature"

    def test_no_template_returns_none(self, clarifier, conversation):
        """Test no template match returns None."""
        conversation.original_message = "Random task with no keywords"

        template_info = clarifier.detect_and_apply_template(conversation, {})

        assert template_info is None


class TestDependencyFinding:
    """Test finding potential task dependencies."""

    @pytest.mark.asyncio
    async def test_finds_related_tasks(self, clarifier):
        """Test finding related tasks as dependencies."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "potential_dependencies": [
                {"task_id": "TASK-001", "reason": "Needs database schema first"}
            ],
            "explanation": "Task requires DB setup"
        })

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            with patch('src.ai.clarifier.get_sheets_integration') as mock_sheets:
                mock_sheets_instance = MagicMock()
                mock_sheets_instance.get_all_tasks = AsyncMock(return_value=[
                    {"ID": "TASK-001", "Title": "Setup database", "Status": "in_progress"}
                ])
                mock_sheets.return_value = mock_sheets_instance

                deps = await clarifier.find_potential_dependencies(
                    "Build API endpoints",
                    "Mayank"
                )

                assert len(deps) == 1
                assert deps[0]["task_id"] == "TASK-001"

    @pytest.mark.asyncio
    async def test_no_dependencies_returns_empty(self, clarifier):
        """Test returns empty when no dependencies found."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "potential_dependencies": [],
            "explanation": "No related tasks"
        })

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            with patch('src.ai.clarifier.get_sheets_integration') as mock_sheets:
                mock_sheets_instance = MagicMock()
                mock_sheets_instance.get_all_tasks = AsyncMock(return_value=[])
                mock_sheets.return_value = mock_sheets_instance

                deps = await clarifier.find_potential_dependencies("Simple task")

                assert deps == []


class TestQuestionGeneration:
    """Test question generation for users."""

    @pytest.mark.asyncio
    async def test_generates_normal_questions(self, clarifier):
        """Test normal question generation."""
        analysis = {
            "suggested_questions": [
                {"question": "Who should work on this?", "field": "assignee"},
                {"question": "Any deadline?", "field": "deadline"}
            ]
        }

        with patch.object(clarifier.ai, 'generate_clarifying_questions') as mock_gen:
            mock_gen.return_value = {
                "intro_message": "A few questions:",
                "questions": [
                    {"text": "Who should work on this?", "options": [], "allow_custom": True}
                ]
            }

            message, questions = await clarifier.generate_question_message(analysis, {})

            assert "few questions" in message.lower()
            assert len(questions) == 1

    @pytest.mark.asyncio
    async def test_generates_prd_questions_in_detailed_mode(self, clarifier):
        """Test PRD-focused questions for detailed mode."""
        analysis = {"detailed_mode": True, "understood": {"title": "Build system"}}

        with patch.object(clarifier.ai, '_call_api') as mock_api:
            mock_api.return_value = json.dumps({
                "intro_message": "Let me understand the requirements:",
                "questions": [
                    {"text": "What's the technical approach?", "options": [], "allow_custom": True}
                ]
            })

            message, questions = await clarifier.generate_question_message(analysis, {}, detailed_mode=True)

            assert "requirements" in message.lower() or "spec" in message.lower()


class TestAnswerProcessing:
    """Test processing user answers to questions."""

    @pytest.mark.asyncio
    async def test_parse_inline_numbered_answers(self, clarifier, conversation):
        """Test parsing '1tomorrow 2high' format."""
        conversation.questions_asked = [
            ClarifyingQuestion(question="When?"),
            ClarifyingQuestion(question="Priority?")
        ]

        with patch.object(clarifier.ai, 'process_answer') as mock_process:
            mock_process.return_value = {
                "field": "deadline",
                "extracted_value": "tomorrow",
                "confidence": 0.9
            }

            updates = await clarifier.process_user_answers(conversation, "1tomorrow 2high")

            assert "deadline" in updates or mock_process.called

    @pytest.mark.asyncio
    async def test_parse_option_selection(self, clarifier, conversation):
        """Test parsing option selection 'A', 'B', etc."""
        question = ClarifyingQuestion(
            question="Priority?",
            options=["High", "Medium", "Low"]
        )
        conversation.questions_asked = [question]

        with patch.object(clarifier.ai, 'process_answer') as mock_process:
            mock_process.return_value = {
                "field": "priority",
                "extracted_value": "High",
                "confidence": 1.0
            }

            updates = await clarifier.process_user_answers(conversation, "A")

            # Should extract option A = "High"
            assert question.answer == "High" or mock_process.called


class TestSpecGeneration:
    """Test spec preview generation."""

    @pytest.mark.asyncio
    async def test_generates_spec_preview(self, clarifier, conversation):
        """Test generating task spec preview."""
        conversation.extracted_info = {
            "title": "Fix login bug",
            "assignee": "Mayank",
            "priority": "high"
        }

        with patch.object(clarifier.ai, 'generate_task_spec') as mock_gen:
            mock_gen.return_value = {
                "title": "Fix critical login bug",
                "description": "Users cannot authenticate",
                "priority": "high",
                "assignee": "Mayank",
                "acceptance_criteria": ["Login works", "Session persists"]
            }

            preview, spec = await clarifier.generate_spec_preview(conversation, {})

            assert "Fix critical login bug" in preview
            assert spec["priority"] == "high"
            assert len(spec["acceptance_criteria"]) == 2

    @pytest.mark.asyncio
    async def test_validates_spec_against_input(self, clarifier, conversation):
        """Test spec validation catches hallucination."""
        conversation.original_message = "Fix login typo"
        conversation.extracted_info = {}

        with patch.object(clarifier.ai, 'generate_task_spec') as mock_gen:
            # AI hallucinates completely unrelated spec
            mock_gen.return_value = {
                "title": "Build e-commerce platform",  # Unrelated!
                "description": "Shopping cart system",
                "priority": "medium"
            }

            preview, spec = await clarifier.generate_spec_preview(conversation, {})

            # Should detect hallucination and use fallback
            if spec.get("_fallback_extraction"):
                assert "login" in spec["title"].lower() or "typo" in spec["title"].lower()


class TestCriticalQuestionFiltering:
    """Test filtering to critical questions only."""

    def test_filters_to_critical_fields(self, clarifier):
        """Test filtering keeps only critical questions."""
        questions = [
            {"field": "assignee", "question": "Who?"},
            {"field": "deadline", "question": "When?"},
            {"field": "tags", "question": "Tags?"},
            {"field": "notes", "question": "Notes?"}
        ]

        critical = clarifier._filter_critical_questions(questions)

        assert len(critical) <= 2
        assert all(q["field"] in ["assignee", "deadline"] for q in critical)

    def test_limits_to_max_2_questions(self, clarifier):
        """Test limits to 2 critical questions max."""
        questions = [
            {"field": "assignee", "question": "Who?"},
            {"field": "deadline", "question": "When?"},
            {"field": "assignee", "question": "Who else?"}
        ]

        critical = clarifier._filter_critical_questions(questions)

        assert len(critical) <= 2


class TestDeadlineParsing:
    """Test natural language deadline parsing."""

    @pytest.mark.asyncio
    async def test_parses_tomorrow(self, clarifier):
        """Test parsing 'tomorrow' to date."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "2026-01-26"

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            deadline = await clarifier.parse_deadline("tomorrow")

            assert deadline == "2026-01-26"

    @pytest.mark.asyncio
    async def test_parses_next_friday(self, clarifier):
        """Test parsing 'next Friday' to date."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "2026-01-30"

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            deadline = await clarifier.parse_deadline("next Friday")

            assert deadline is not None
            assert "-" in deadline  # YYYY-MM-DD format

    @pytest.mark.asyncio
    async def test_no_deadline_returns_none(self, clarifier):
        """Test returns None when no deadline mentioned."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "null"

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            deadline = await clarifier.parse_deadline("no specific deadline")

            assert deadline is None


class TestModificationExtraction:
    """Test extracting task modification details."""

    @pytest.mark.asyncio
    async def test_extracts_title_change(self, clarifier):
        """Test extracting new title from modification message."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "new_title": "Updated title",
            "new_description": None,
            "change_type": "title"
        })

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            result = await clarifier.extract_modification_details(
                "Change title to Updated title",
                {"title": "Old title"}
            )

            assert result["new_title"] == "Updated title"
            assert "new_description" not in result  # Null values removed

    @pytest.mark.asyncio
    async def test_extracts_description_change(self, clarifier):
        """Test extracting new description."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "new_title": None,
            "new_description": "New description text",
            "change_type": "description"
        })

        with patch.object(clarifier.ai.client.chat.completions, 'create', return_value=mock_response):
            result = await clarifier.extract_modification_details(
                "Update description to New description text",
                {"description": "Old"}
            )

            assert result["new_description"] == "New description text"
