"""
Unit tests for Voice Transcriber using OpenAI Whisper API.

Tests:
- transcribe_voice() - Voice transcription
- save_audio_file() - Audio file handling
- detect_language() - Language detection
- Error handling (unsupported formats, API failures)
- Context-aware transcription
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import httpx
from pathlib import Path

from src.ai.transcriber import VoiceTranscriber, get_transcriber, transcribe_voice_message


@pytest.fixture
def transcriber():
    """Create VoiceTranscriber instance with API key."""
    with patch('src.ai.transcriber.settings') as mock_settings:
        mock_settings.openai_api_key = "test_api_key"
        return VoiceTranscriber()


@pytest.fixture
def transcriber_no_key():
    """Create VoiceTranscriber without API key."""
    with patch('src.ai.transcriber.settings') as mock_settings:
        mock_settings.openai_api_key = None
        return VoiceTranscriber()


@pytest.fixture
def audio_data():
    """Sample audio data bytes."""
    return b"fake audio data"


class TestTranscriberAvailability:
    """Test transcriber availability checks."""

    def test_is_available_with_key(self, transcriber):
        """Test transcriber is available with API key."""
        assert transcriber.is_available() is True

    def test_is_not_available_without_key(self, transcriber_no_key):
        """Test transcriber is not available without API key."""
        assert transcriber_no_key.is_available() is False


class TestBasicTranscription:
    """Test basic voice transcription."""

    @pytest.mark.asyncio
    async def test_successful_transcription(self, transcriber, audio_data):
        """Test successful voice transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "This is the transcribed text"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data)

                        assert result == "This is the transcribed text"

    @pytest.mark.asyncio
    async def test_transcription_not_available(self, transcriber_no_key, audio_data):
        """Test transcription returns None when API key not available."""
        result = await transcriber_no_key.transcribe(audio_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_transcription_api_error(self, transcriber, audio_data):
        """Test handling API error response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data)

                        assert result is None

    @pytest.mark.asyncio
    async def test_transcription_network_error(self, transcriber, audio_data):
        """Test handling network error."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data)

                        assert result is None


class TestAudioFormats:
    """Test different audio format handling."""

    @pytest.mark.asyncio
    async def test_ogg_format(self, transcriber, audio_data):
        """Test transcribing OGG audio."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed from OGG"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data, filename="audio.ogg")

                        assert result == "Transcribed from OGG"

    @pytest.mark.asyncio
    async def test_mp3_format(self, transcriber, audio_data):
        """Test transcribing MP3 audio."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed from MP3"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data, filename="audio.mp3")

                        assert result == "Transcribed from MP3"

    @pytest.mark.asyncio
    async def test_default_format_when_no_extension(self, transcriber, audio_data):
        """Test default OGG format when no extension."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data, filename="audio")

                        assert result == "Transcribed"


class TestLanguageDetection:
    """Test language-specific transcription."""

    @pytest.mark.asyncio
    async def test_english_language(self, transcriber, audio_data):
        """Test English language transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "English transcription"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data, language="en")

                        assert result == "English transcription"
                        # Verify language was passed to API
                        call_args = mock_client.post.call_args
                        assert call_args[1]['data']['language'] == "en"

    @pytest.mark.asyncio
    async def test_spanish_language(self, transcriber, audio_data):
        """Test Spanish language transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcripción en español"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe(audio_data, language="es")

                        assert result == "Transcripción en español"


class TestContextAwareTranscription:
    """Test transcription with context prompts."""

    @pytest.mark.asyncio
    async def test_transcribe_with_context_prompt(self, transcriber, audio_data):
        """Test transcription with context for better accuracy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Fix the login bug"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe_with_context(
                            audio_data,
                            prompt="task management, bug fixes"
                        )

                        assert result == "Fix the login bug"
                        # Verify prompt was passed
                        call_args = mock_client.post.call_args
                        assert call_args[1]['data']['prompt'] == "task management, bug fixes"

    @pytest.mark.asyncio
    async def test_transcribe_with_context_no_key(self, transcriber_no_key, audio_data):
        """Test context transcription returns None without API key."""
        result = await transcriber_no_key.transcribe_with_context(audio_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_with_context_api_error(self, transcriber, audio_data):
        """Test context transcription handles API error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        result = await transcriber.transcribe_with_context(audio_data)

                        assert result is None


class TestFileHandling:
    """Test audio file handling."""

    @pytest.mark.asyncio
    async def test_temp_file_cleanup(self, transcriber, audio_data):
        """Test temporary file is cleaned up after transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed"

        unlink_mock = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch.object(Path, 'unlink', unlink_mock):
                        await transcriber.transcribe(audio_data)

                        # Verify temp file was deleted
                        assert unlink_mock.called

    @pytest.mark.asyncio
    async def test_temp_file_cleanup_on_error(self, transcriber, audio_data):
        """Test temporary file cleanup even on error."""
        unlink_mock = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("API error"))
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch.object(Path, 'unlink', unlink_mock):
                        await transcriber.transcribe(audio_data)

                        # Verify cleanup still happened
                        assert unlink_mock.called


class TestSingletonAndHelpers:
    """Test singleton and helper functions."""

    def test_get_transcriber_singleton(self):
        """Test get_transcriber returns singleton."""
        with patch('src.ai.transcriber.settings') as mock_settings:
            mock_settings.openai_api_key = "test_key"

            transcriber1 = get_transcriber()
            transcriber2 = get_transcriber()

            assert transcriber1 is transcriber2

    @pytest.mark.asyncio
    async def test_transcribe_voice_message_convenience(self, audio_data):
        """Test convenience function for voice message transcription."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Create task for Mayank"

        with patch('src.ai.transcriber.settings') as mock_settings:
            mock_settings.openai_api_key = "test_key"

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                with patch('aiofiles.open', mock_open(read_data=audio_data)):
                    with patch('tempfile.NamedTemporaryFile'):
                        with patch('pathlib.Path.unlink'):
                            result = await transcribe_voice_message(audio_data)

                            assert result == "Create task for Mayank"
                            # Verify task management context was used
                            call_args = mock_client.post.call_args
                            assert 'prompt' in call_args[1]['data']
                            assert 'task' in call_args[1]['data']['prompt'].lower()


class TestWhisperAPIIntegration:
    """Test Whisper API integration details."""

    @pytest.mark.asyncio
    async def test_correct_api_endpoint(self, transcriber, audio_data):
        """Test correct Whisper API endpoint is used."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        await transcriber.transcribe(audio_data)

                        # Verify correct endpoint
                        call_args = mock_client.post.call_args
                        assert call_args[0][0].endswith('/audio/transcriptions')

    @pytest.mark.asyncio
    async def test_correct_model_used(self, transcriber, audio_data):
        """Test whisper-1 model is used."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        await transcriber.transcribe(audio_data)

                        # Verify model
                        call_args = mock_client.post.call_args
                        assert call_args[1]['data']['model'] == 'whisper-1'

    @pytest.mark.asyncio
    async def test_authorization_header(self, transcriber, audio_data):
        """Test API key is sent in authorization header."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        await transcriber.transcribe(audio_data)

                        # Verify authorization
                        call_args = mock_client.post.call_args
                        assert 'Authorization' in call_args[1]['headers']
                        assert call_args[1]['headers']['Authorization'].startswith('Bearer ')

    @pytest.mark.asyncio
    async def test_response_format_text(self, transcriber, audio_data):
        """Test response format is set to text."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Transcribed"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('aiofiles.open', mock_open(read_data=audio_data)):
                with patch('tempfile.NamedTemporaryFile'):
                    with patch('pathlib.Path.unlink'):
                        await transcriber.transcribe(audio_data)

                        # Verify response format
                        call_args = mock_client.post.call_args
                        assert call_args[1]['data']['response_format'] == 'text'
