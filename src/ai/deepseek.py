"""DeepSeek AI client for task analysis and generation."""

import json
import logging
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from .prompts import PromptTemplates

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Client for interacting with DeepSeek API."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        self.model = settings.deepseek_model
        self.prompts = PromptTemplates()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_api(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[Dict] = None
    ) -> str:
        """Make an API call to DeepSeek."""
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # DeepSeek supports JSON mode
            if response_format:
                kwargs["response_format"] = response_format

            response = await self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise

    async def analyze_task_request(
        self,
        user_message: str,
        preferences: Dict[str, Any],
        team_info: Dict[str, str],
        conversation_history: str = ""
    ) -> Dict[str, Any]:
        """
        Analyze a task request to identify missing information.

        Returns analysis including understood info, missing fields,
        confidence scores, and suggested questions.
        """
        prompt = self.prompts.analyze_task_prompt(
            user_message=user_message,
            preferences=preferences,
            team_info=team_info,
            conversation_history=conversation_history
        )

        messages = [
            {"role": "system", "content": self.prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await self._call_api(
            messages=messages,
            temperature=0.3,  # Lower temp for analysis
            response_format={"type": "json_object"}
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse analysis response: {response}")
            return {
                "understood": {"title": user_message[:100], "description": user_message},
                "missing_info": ["priority", "assignee", "deadline"],
                "confidence": {},
                "can_proceed_without_questions": False,
                "suggested_questions": []
            }

    async def generate_clarifying_questions(
        self,
        analysis: Dict[str, Any],
        preferences: Dict[str, Any],
        max_questions: int = 3
    ) -> Dict[str, Any]:
        """
        Generate natural clarifying questions based on analysis.

        Returns formatted questions with options.
        """
        prompt = self.prompts.generate_questions_prompt(
            analysis=analysis,
            preferences=preferences,
            max_questions=max_questions
        )

        messages = [
            {"role": "system", "content": self.prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await self._call_api(
            messages=messages,
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse questions response: {response}")
            return {
                "questions": [],
                "intro_message": "I need a bit more information to create this task."
            }

    async def generate_task_spec(
        self,
        original_message: str,
        qa_pairs: Dict[str, str],
        preferences: Dict[str, Any],
        extracted_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate the final task specification.

        Returns complete task spec ready for creation.
        """
        prompt = self.prompts.generate_spec_prompt(
            original_message=original_message,
            qa_pairs=qa_pairs,
            preferences=preferences,
            extracted_info=extracted_info
        )

        messages = [
            {"role": "system", "content": self.prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await self._call_api(
            messages=messages,
            temperature=0.5,
            response_format={"type": "json_object"}
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse spec response: {response}")
            # Return minimal spec based on extracted info
            return {
                "title": extracted_info.get("title", original_message[:100]),
                "description": original_message,
                "priority": "medium",
                "acceptance_criteria": []
            }

    async def format_preview(self, spec: Dict[str, Any]) -> str:
        """Format task spec as a preview message for Telegram."""
        prompt = self.prompts.format_preview_prompt(spec)

        messages = [
            {"role": "system", "content": "You are a helpful assistant that formats messages."},
            {"role": "user", "content": prompt}
        ]

        return await self._call_api(
            messages=messages,
            temperature=0.3,
            max_tokens=1000
        )

    async def process_answer(
        self,
        question: str,
        answer: str,
        current_info: Dict[str, Any],
        field: str
    ) -> Dict[str, Any]:
        """Process a user's answer to extract relevant information."""
        prompt = self.prompts.process_answer_prompt(
            question=question,
            answer=answer,
            current_info=current_info,
            field=field
        )

        messages = [
            {"role": "system", "content": self.prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await self._call_api(
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {
                "field": field,
                "extracted_value": answer,
                "confidence": 0.8,
                "needs_followup": False
            }

    async def generate_daily_standup(
        self,
        tasks: List[Dict[str, Any]],
        completed_yesterday: List[Dict[str, Any]]
    ) -> str:
        """Generate daily standup summary."""
        prompt = self.prompts.daily_standup_prompt(tasks, completed_yesterday)

        messages = [
            {"role": "system", "content": "You are a helpful team assistant."},
            {"role": "user", "content": prompt}
        ]

        return await self._call_api(
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )

    async def generate_weekly_summary(
        self,
        weekly_stats: Dict[str, Any],
        tasks_by_status: Dict[str, List],
        team_performance: Dict[str, Any]
    ) -> str:
        """Generate weekly summary report."""
        prompt = self.prompts.weekly_summary_prompt(
            weekly_stats, tasks_by_status, team_performance
        )

        messages = [
            {"role": "system", "content": "You are a helpful team assistant."},
            {"role": "user", "content": prompt}
        ]

        return await self._call_api(
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )

    async def transcribe_voice(self, audio_file_path: str) -> str:
        """
        Transcribe a voice message.

        Note: DeepSeek doesn't have native transcription.
        This would use Whisper API or similar.
        """
        # Placeholder - would integrate with Whisper or similar
        logger.warning("Voice transcription not implemented - using placeholder")
        return "[Voice message - transcription not available]"


# Singleton instance
deepseek_client = DeepSeekClient()


def get_deepseek_client() -> DeepSeekClient:
    """Get the DeepSeek client instance."""
    return deepseek_client
