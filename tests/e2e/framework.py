"""
End-to-end test framework for conversation flows.

Simulates multi-turn conversations and validates complete workflows.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta, UTC
from dataclasses import dataclass, field

from src.bot.handler import UnifiedHandler
from src.database.repositories import get_task_repository, get_conversation_repository
from src.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""
    user_message: str
    bot_response: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationAssertion:
    """Assertion about conversation state."""
    type: str  # "contains", "task_created", "status_changed", "not_contains"
    value: Any
    description: str = ""


class ConversationSimulator:
    """
    Simulate multi-turn conversations with the bot.

    Features:
    - Track conversation history
    - Make assertions about responses
    - Validate database state
    - Support async workflows
    """

    def __init__(self, user_id: str = "TEST_BOSS", user_name: str = "Test Boss", is_boss: bool = True):
        """
        Initialize conversation simulator.

        Args:
            user_id: User ID for the conversation
            user_name: User display name
            is_boss: Whether user is boss (for permission testing)
        """
        self.handler = UnifiedHandler()
        self.task_repo = get_task_repository()
        self.conv_repo = get_conversation_repository()

        self.user_id = user_id
        self.user_name = user_name
        self.is_boss = is_boss

        self.conversation_history: List[ConversationTurn] = []
        self.created_tasks: List[str] = []  # Track task IDs created during test
        self.test_start_time = datetime.now(UTC)

        logger.info(f"Initialized ConversationSimulator for user {user_id} (boss={is_boss})")

    async def send_message(
        self,
        message: str,
        photo_file_id: Optional[str] = None,
        photo_caption: Optional[str] = None,
        wait_seconds: float = 0.5
    ) -> str:
        """
        Send a message and get bot response.

        Args:
            message: User message text
            photo_file_id: Optional photo file ID
            photo_caption: Optional photo caption
            wait_seconds: Time to wait after sending (simulate thinking)

        Returns:
            Bot's response text
        """
        logger.debug(f"USER ({self.user_id}): {message}")

        # Send to handler
        response, action_data = await self.handler.handle_message(
            user_id=self.user_id,
            message=message,
            photo_file_id=photo_file_id,
            photo_caption=photo_caption,
            user_name=self.user_name,
            is_boss=self.is_boss,
            source="telegram"
        )

        logger.debug(f"BOT: {response[:100]}...")

        # Record turn
        turn = ConversationTurn(
            user_message=message,
            bot_response=response,
            metadata={"action_data": action_data}
        )
        self.conversation_history.append(turn)

        # Extract task ID if created
        if "TASK-" in response:
            import re
            task_ids = re.findall(r'TASK-\d{8}-\d{3}', response)
            self.created_tasks.extend(task_ids)
            logger.info(f"Detected task creation: {task_ids}")

        # Simulate processing delay
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

        return response

    async def run_conversation(
        self,
        messages: List[str],
        wait_between: float = 0.5
    ) -> List[str]:
        """
        Run a multi-turn conversation.

        Args:
            messages: List of user messages
            wait_between: Seconds to wait between messages

        Returns:
            List of bot responses
        """
        responses = []

        for msg in messages:
            response = await self.send_message(msg, wait_seconds=wait_between)
            responses.append(response)

        return responses

    def get_last_response(self) -> str:
        """Get the most recent bot response."""
        if not self.conversation_history:
            return ""
        return self.conversation_history[-1].bot_response

    def get_last_turn(self) -> Optional[ConversationTurn]:
        """Get the most recent conversation turn."""
        if not self.conversation_history:
            return None
        return self.conversation_history[-1]

    # ========== Assertions ==========

    def assert_contains(self, text: str, case_sensitive: bool = False):
        """Assert last bot response contains text."""
        response = self.get_last_response()

        if case_sensitive:
            condition = text in response
        else:
            condition = text.lower() in response.lower()

        assert condition, f"Response does not contain '{text}'.\nResponse: {response[:200]}"

    def assert_not_contains(self, text: str, case_sensitive: bool = False):
        """Assert last bot response does NOT contain text."""
        response = self.get_last_response()

        if case_sensitive:
            condition = text not in response
        else:
            condition = text.lower() not in response.lower()

        assert condition, f"Response should not contain '{text}'.\nResponse: {response[:200]}"

    def assert_task_created(self, task_id_pattern: str = "TASK-"):
        """Assert a task was created in the last response."""
        response = self.get_last_response()
        assert task_id_pattern in response, f"No task created (missing '{task_id_pattern}').\nResponse: {response[:200]}"

    async def assert_task_in_database(
        self,
        task_id: Optional[str] = None,
        title_contains: Optional[str] = None,
        assignee: Optional[str] = None,
        status: Optional[TaskStatus] = None
    ) -> Task:
        """
        Assert a task exists in database with given properties.

        Args:
            task_id: Specific task ID (if None, uses last created task)
            title_contains: Check title contains this text
            assignee: Check assignee matches
            status: Check status matches

        Returns:
            The task object
        """
        # Get task
        if task_id is None:
            assert self.created_tasks, "No tasks created in this conversation"
            task_id = self.created_tasks[-1]

        task = await self.task_repo.get_by_id(task_id)
        assert task is not None, f"Task {task_id} not found in database"

        # Validate properties
        if title_contains:
            assert title_contains.lower() in task.title.lower(), \
                f"Task title '{task.title}' does not contain '{title_contains}'"

        if assignee:
            assert task.assignee == assignee, \
                f"Task assignee '{task.assignee}' does not match expected '{assignee}'"

        if status:
            assert task.status == status, \
                f"Task status '{task.status}' does not match expected '{status}'"

        return task

    async def assert_no_task_created(self, since: Optional[datetime] = None):
        """Assert no new tasks were created."""
        if since is None:
            since = self.test_start_time

        # Check created_tasks list
        assert not self.created_tasks, f"Unexpected tasks created: {self.created_tasks}"

        # Double-check database
        recent_tasks = await self.task_repo.list_tasks(limit=5)
        for task in recent_tasks:
            if task.created_at and task.created_at > since:
                raise AssertionError(f"Unexpected task found: {task.id} created at {task.created_at}")

    def assert_question_asked(self):
        """Assert bot asked a question (indicated by '?')."""
        response = self.get_last_response()
        assert '?' in response, f"Bot did not ask a question.\nResponse: {response[:200]}"

    def assert_confirmation_requested(self):
        """Assert bot requested confirmation."""
        response = self.get_last_response().lower()
        confirmation_keywords = ['confirm', 'proceed', 'looks good', 'correct', 'yes/no']

        has_confirmation = any(kw in response for kw in confirmation_keywords)
        assert has_confirmation, f"Bot did not request confirmation.\nResponse: {response[:200]}"

    async def get_conversation_count(self) -> int:
        """Get number of conversation turns in database."""
        # This would query the conversations repository
        # For now, return history length
        return len(self.conversation_history)

    # ========== Helpers ==========

    async def cleanup(self):
        """Clean up test data."""
        # Delete created tasks
        for task_id in self.created_tasks:
            try:
                await self.task_repo.delete(task_id)
                logger.info(f"Cleaned up test task: {task_id}")
            except Exception as e:
                logger.warning(f"Failed to clean up task {task_id}: {e}")

        self.created_tasks.clear()
        self.conversation_history.clear()

    def print_conversation(self):
        """Print the full conversation for debugging."""
        print("\n" + "=" * 60)
        print("CONVERSATION HISTORY")
        print("=" * 60)

        for i, turn in enumerate(self.conversation_history, 1):
            print(f"\nTurn {i} ({turn.timestamp.strftime('%H:%M:%S')})")
            print(f"USER: {turn.user_message}")
            print(f"BOT:  {turn.bot_response[:150]}...")

        print("=" * 60 + "\n")


class TestScenario:
    """
    A complete test scenario with setup, execution, and validation.
    """

    def __init__(
        self,
        name: str,
        messages: List[str],
        assertions: List[ConversationAssertion],
        user_id: str = "TEST_BOSS",
        is_boss: bool = True
    ):
        self.name = name
        self.messages = messages
        self.assertions = assertions
        self.user_id = user_id
        self.is_boss = is_boss

        self.simulator: Optional[ConversationSimulator] = None
        self.success: bool = False
        self.errors: List[str] = []

    async def run(self) -> Tuple[bool, List[str]]:
        """
        Run the test scenario.

        Returns:
            (success, errors)
        """
        self.simulator = ConversationSimulator(
            user_id=self.user_id,
            is_boss=self.is_boss
        )

        try:
            # Run conversation
            await self.simulator.run_conversation(self.messages)

            # Run assertions
            for assertion in self.assertions:
                try:
                    await self._check_assertion(assertion)
                except AssertionError as e:
                    self.errors.append(f"{assertion.description or assertion.type}: {str(e)}")

            self.success = len(self.errors) == 0

        except Exception as e:
            logger.exception(f"Scenario {self.name} failed with exception")
            self.errors.append(f"Exception: {str(e)}")
            self.success = False

        finally:
            # Cleanup
            if self.simulator:
                await self.simulator.cleanup()

        return self.success, self.errors

    async def _check_assertion(self, assertion: ConversationAssertion):
        """Check a single assertion."""
        if assertion.type == "contains":
            self.simulator.assert_contains(assertion.value)

        elif assertion.type == "not_contains":
            self.simulator.assert_not_contains(assertion.value)

        elif assertion.type == "task_created":
            self.simulator.assert_task_created()

        elif assertion.type == "task_in_db":
            await self.simulator.assert_task_in_database(**assertion.value)

        elif assertion.type == "no_task_created":
            await self.simulator.assert_no_task_created()

        elif assertion.type == "question_asked":
            self.simulator.assert_question_asked()

        elif assertion.type == "confirmation_requested":
            self.simulator.assert_confirmation_requested()

        else:
            raise ValueError(f"Unknown assertion type: {assertion.type}")


# ========== Convenience Functions ==========

def create_task_creation_scenario(
    name: str,
    task_message: str,
    expected_title: str,
    expected_assignee: Optional[str] = None,
    confirm: bool = True
) -> TestScenario:
    """
    Create a standard task creation test scenario.

    Args:
        name: Test name
        task_message: Initial task request
        expected_title: Expected task title (substring)
        expected_assignee: Expected assignee name
        confirm: Whether to confirm with 'yes'
    """
    messages = [task_message]
    if confirm:
        messages.append("yes")

    assertions = [
        ConversationAssertion("task_created", None, "Task ID in response"),
        ConversationAssertion(
            "task_in_db",
            {"title_contains": expected_title, "assignee": expected_assignee},
            f"Task in DB with title='{expected_title}', assignee='{expected_assignee}'"
        )
    ]

    return TestScenario(name, messages, assertions)
