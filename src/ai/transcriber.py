"""
Voice transcription using OpenAI Whisper API.

Transcribes voice messages to text for hands-free task creation.
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class VoiceTranscriber:
    """Transcribe voice messages using OpenAI Whisper."""

    def __init__(self):
        from config import settings
        self.api_key = getattr(settings, 'openai_api_key', None)
        self.base_url = "https://api.openai.com/v1"

    def is_available(self) -> bool:
        """Check if transcription is available."""
        return bool(self.api_key)

    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.ogg",
        language: str = "en"
    ) -> Optional[str]:
        """
        Transcribe audio to text using Whisper API.

        Args:
            audio_data: Raw audio bytes
            filename: Original filename (for format detection)
            language: Language code (default: auto-detect)

        Returns:
            Transcribed text or None on error
        """
        if not self.is_available():
            logger.warning("Voice transcription not available - OPENAI_API_KEY not set")
            return None

        try:
            # Save to temp file
            suffix = Path(filename).suffix or ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio_data)
                temp_path = Path(f.name)

            try:
                # Call Whisper API
                async with httpx.AsyncClient(timeout=60.0) as client:
                    with open(temp_path, "rb") as audio_file:
                        response = await client.post(
                            f"{self.base_url}/audio/transcriptions",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                            },
                            files={
                                "file": (filename, audio_file, "audio/ogg"),
                            },
                            data={
                                "model": "whisper-1",
                                "language": language,
                                "response_format": "text",
                            },
                        )

                if response.status_code == 200:
                    text = response.text.strip()
                    logger.info(f"Transcribed audio: {len(text)} chars")
                    return text
                else:
                    logger.error(f"Whisper API error: {response.status_code} - {response.text}")
                    return None

            finally:
                # Cleanup temp file
                try:
                    temp_path.unlink()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None

    async def transcribe_with_context(
        self,
        audio_data: bytes,
        filename: str = "audio.ogg",
        prompt: Optional[str] = None
    ) -> Optional[str]:
        """
        Transcribe with optional context prompt for better accuracy.

        Args:
            audio_data: Raw audio bytes
            filename: Original filename
            prompt: Context prompt to improve accuracy
                   (e.g., "task assignment, team management, deadlines")
        """
        if not self.is_available():
            return None

        try:
            suffix = Path(filename).suffix or ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio_data)
                temp_path = Path(f.name)

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    with open(temp_path, "rb") as audio_file:
                        data = {
                            "model": "whisper-1",
                            "response_format": "text",
                        }
                        if prompt:
                            data["prompt"] = prompt

                        response = await client.post(
                            f"{self.base_url}/audio/transcriptions",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                            },
                            files={
                                "file": (filename, audio_file, "audio/ogg"),
                            },
                            data=data,
                        )

                if response.status_code == 200:
                    return response.text.strip()
                else:
                    logger.error(f"Whisper API error: {response.status_code}")
                    return None

            finally:
                try:
                    temp_path.unlink()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Transcription with context failed: {e}")
            return None


# Singleton
_transcriber: Optional[VoiceTranscriber] = None


def get_transcriber() -> VoiceTranscriber:
    """Get the voice transcriber singleton."""
    global _transcriber
    if _transcriber is None:
        _transcriber = VoiceTranscriber()
    return _transcriber


async def transcribe_voice_message(audio_data: bytes, filename: str = "audio.ogg") -> Optional[str]:
    """Convenience function to transcribe voice message."""
    transcriber = get_transcriber()
    return await transcriber.transcribe_with_context(
        audio_data,
        filename,
        prompt="task management, assignments, deadlines, team members, priorities, urgent tasks"
    )
