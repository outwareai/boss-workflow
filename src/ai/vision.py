"""
DeepSeek Vision integration for image analysis.

Analyzes screenshots, photos, and images sent by users.
"""

import base64
import logging
from typing import Optional, Dict, Any, List
import httpx

from config import settings

logger = logging.getLogger(__name__)


class DeepSeekVision:
    """Analyze images using DeepSeek VL (Vision-Language) model."""

    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = "deepseek-vl"  # DeepSeek's vision model

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str = "Describe this image in detail.",
        context: Optional[str] = None
    ) -> Optional[str]:
        """
        Analyze an image and return a description.

        Args:
            image_data: Raw image bytes
            prompt: What to analyze/look for
            context: Additional context about the image

        Returns:
            Analysis text or None on error
        """
        if not self.api_key:
            logger.warning("DeepSeek API key not configured")
            return None

        try:
            # Encode image to base64
            image_b64 = base64.b64encode(image_data).decode('utf-8')

            # Build the message with image
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": self._build_prompt(prompt, context)
                        }
                    ]
                }
            ]

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": 1000,
                        "temperature": 0.3
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    logger.info(f"Vision analysis completed: {len(content)} chars")
                    return content
                else:
                    logger.error(f"DeepSeek Vision API error: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return None

    async def analyze_screenshot(self, image_data: bytes) -> Optional[Dict[str, Any]]:
        """
        Analyze a screenshot for task-related information.

        Returns structured info about what's shown.
        """
        prompt = """Analyze this screenshot and extract:
1. What application/website is shown
2. Any error messages or issues visible
3. Key information displayed (text, data, status)
4. What action might be needed

Be concise and focus on actionable information."""

        analysis = await self.analyze_image(image_data, prompt)

        if analysis:
            return {
                "description": analysis,
                "type": "screenshot_analysis"
            }
        return None

    async def analyze_proof(self, image_data: bytes, task_title: str) -> Optional[Dict[str, Any]]:
        """
        Analyze an image submitted as proof of task completion.

        Args:
            image_data: The proof image
            task_title: The task this is proof for

        Returns:
            Analysis with relevance assessment
        """
        prompt = f"""This image is submitted as proof of completing the task: "{task_title}"

Analyze the image and determine:
1. What does this image show?
2. Does it appear to be valid proof of task completion?
3. Any concerns or issues visible?
4. Brief summary of what's demonstrated

Be objective and concise."""

        analysis = await self.analyze_image(image_data, prompt)

        if analysis:
            return {
                "description": analysis,
                "task_title": task_title,
                "type": "proof_analysis"
            }
        return None

    async def extract_text(self, image_data: bytes) -> Optional[str]:
        """
        Extract text/OCR from an image.

        Useful for reading error messages, logs, etc.
        """
        prompt = """Extract all readable text from this image.
Return the text exactly as shown, preserving any structure or formatting.
If no text is visible, say "No text found"."""

        return await self.analyze_image(image_data, prompt)

    async def describe_for_task(self, image_data: bytes) -> Optional[str]:
        """
        Analyze image in context of task creation.

        Tries to understand what task might be related to this image.
        """
        prompt = """This image was sent in context of creating or discussing a task.

Analyze it and suggest:
1. What issue or task does this image represent?
2. Who might need to work on this?
3. What priority level seems appropriate?
4. Any specific details to include in a task description?

Be concise and actionable."""

        return await self.analyze_image(image_data, prompt)

    def _build_prompt(self, prompt: str, context: Optional[str] = None) -> str:
        """Build the full prompt with optional context."""
        if context:
            return f"{context}\n\n{prompt}"
        return prompt


# Singleton
_vision: Optional[DeepSeekVision] = None


def get_vision() -> DeepSeekVision:
    """Get the DeepSeek Vision singleton."""
    global _vision
    if _vision is None:
        _vision = DeepSeekVision()
    return _vision


async def analyze_image(image_data: bytes, prompt: str = None) -> Optional[str]:
    """Convenience function to analyze an image."""
    vision = get_vision()
    return await vision.analyze_image(
        image_data,
        prompt or "Describe this image and any relevant details for task management."
    )
