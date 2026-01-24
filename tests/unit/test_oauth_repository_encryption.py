"""
Unit tests for OAuth repository encryption integration.

Q1 2026: Verify tokens are encrypted/decrypted correctly.
"""
import os
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
from cryptography.fernet import Fernet


# Set encryption key before imports
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()


from src.database.repositories.oauth import OAuthTokenRepository
from src.utils.encryption import get_token_encryption


@pytest.fixture
def mock_database():
    """Mock database connection."""
    db = Mock()
    session = MagicMock()

    # Mock async context manager properly
    async def mock_enter(self):
        return session

    async def mock_exit(self, *args):
        return None

    session.__aenter__ = mock_enter
    session.__aexit__ = mock_exit

    # Mock execute method
    execute_result = MagicMock()

    async def mock_execute(*args, **kwargs):
        return execute_result

    session.execute = mock_execute
    session.add = Mock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()

    db.session = Mock(return_value=session)

    return db, session, execute_result


@pytest.fixture
def repository(mock_database):
    """Create repository with mocked database."""
    db, session, execute_result = mock_database
    repo = OAuthTokenRepository()
    repo.db = db
    return repo, session, execute_result


@pytest.mark.asyncio
async def test_store_token_encrypts_data(repository):
    """Test that store_token encrypts tokens before storage."""
    repo, session, execute_result = repository

    # Mock execute to return no existing token
    execute_result.scalar_one_or_none = Mock(return_value=None)

    # Store token
    success = await repo.store_token(
        email="test@example.com",
        service="calendar",
        refresh_token="plaintext_refresh_token",
        access_token="plaintext_access_token"
    )

    assert success == True

    # Verify session.add was called
    session.add.assert_called_once()

    # Get the token object that was added
    added_token = session.add.call_args[0][0]

    # Verify tokens are encrypted (start with "gAAAAA" for Fernet)
    assert added_token.refresh_token.startswith("gAAAAA")
    assert added_token.access_token.startswith("gAAAAA")

    # Verify they're NOT plaintext
    assert added_token.refresh_token != "plaintext_refresh_token"
    assert added_token.access_token != "plaintext_access_token"


@pytest.mark.asyncio
async def test_get_token_decrypts_data(repository):
    """Test that get_token decrypts tokens after retrieval."""
    repo, session, execute_result = repository

    # Create encrypted token
    encryption = get_token_encryption()
    encrypted_refresh = encryption.encrypt("plaintext_refresh")
    encrypted_access = encryption.encrypt("plaintext_access")

    # Mock database token
    mock_token = Mock()
    mock_token.email = "test@example.com"
    mock_token.service = "calendar"
    mock_token.refresh_token = encrypted_refresh
    mock_token.access_token = encrypted_access
    mock_token.expires_at = None
    mock_token.scopes = None

    execute_result.scalar_one_or_none = Mock(return_value=mock_token)

    # Mock audit logging module
    with patch("src.utils.audit_logger.log_audit_event", new=AsyncMock()):
        # Get token
        result = await repo.get_token("test@example.com", "calendar")

    assert result is not None
    assert result["refresh_token"] == "plaintext_refresh"
    assert result["access_token"] == "plaintext_access"


@pytest.mark.asyncio
async def test_backward_compatibility_plaintext_tokens(repository):
    """Test that plaintext tokens (pre-encryption) still work."""
    repo, session, execute_result = repository

    # Mock database with plaintext token (old format)
    mock_token = Mock()
    mock_token.email = "test@example.com"
    mock_token.service = "calendar"
    mock_token.refresh_token = "plaintext_refresh_token"  # NOT encrypted
    mock_token.access_token = "plaintext_access_token"  # NOT encrypted
    mock_token.expires_at = None
    mock_token.scopes = None

    execute_result.scalar_one_or_none = Mock(return_value=mock_token)

    # Mock audit logging module
    with patch("src.utils.audit_logger.log_audit_event", new=AsyncMock()):
        # Get token - should fall back to plaintext on decrypt failure
        result = await repo.get_token("test@example.com", "calendar")

    assert result is not None
    assert result["refresh_token"] == "plaintext_refresh_token"
    assert result["access_token"] == "plaintext_access_token"


@pytest.mark.asyncio
async def test_update_access_token_encrypts(repository):
    """Test that update_access_token encrypts the new token."""
    repo, session, execute_result = repository

    # Mock existing token
    mock_token = Mock()
    mock_token.access_token = "old_encrypted_token"
    mock_token.expires_at = None
    mock_token.updated_at = datetime.now()

    execute_result.scalar_one_or_none = Mock(return_value=mock_token)

    # Mock audit logging module
    with patch("src.utils.audit_logger.log_audit_event", new=AsyncMock()):
        # Update access token
        success = await repo.update_access_token(
            email="test@example.com",
            service="calendar",
            access_token="new_plaintext_token"
        )

    assert success == True

    # Verify token was encrypted
    assert mock_token.access_token.startswith("gAAAAA")
    assert mock_token.access_token != "new_plaintext_token"


@pytest.mark.asyncio
async def test_round_trip_encryption(repository):
    """Test full encrypt → store → load → decrypt cycle."""
    repo, session, execute_result = repository

    original_refresh = "my_refresh_token_12345"
    original_access = "my_access_token_67890"

    # Store token (should encrypt)
    execute_result.scalar_one_or_none = Mock(return_value=None)
    await repo.store_token(
        email="user@example.com",
        service="gmail",
        refresh_token=original_refresh,
        access_token=original_access
    )

    # Get the stored token
    stored_token = session.add.call_args[0][0]

    # Mock get_token to return the stored token
    execute_result.scalar_one_or_none = Mock(return_value=stored_token)

    # Mock audit logging module
    with patch("src.utils.audit_logger.log_audit_event", new=AsyncMock()):
        # Retrieve token (should decrypt)
        result = await repo.get_token("user@example.com", "gmail")

    # Verify round trip worked
    assert result["refresh_token"] == original_refresh
    assert result["access_token"] == original_access


@pytest.mark.asyncio
async def test_store_token_updates_existing_encrypted(repository):
    """Test that updating an existing token encrypts the new values."""
    repo, session, execute_result = repository

    # Mock existing token
    existing_token = Mock()
    existing_token.email = "test@example.com"
    existing_token.service = "calendar"
    existing_token.refresh_token = "old_encrypted_refresh"
    existing_token.access_token = "old_encrypted_access"
    existing_token.expires_at = None
    existing_token.scopes = None
    existing_token.updated_at = datetime.now()

    execute_result.scalar_one_or_none = Mock(return_value=existing_token)

    # Update token with new values
    success = await repo.store_token(
        email="test@example.com",
        service="calendar",
        refresh_token="new_plaintext_refresh",
        access_token="new_plaintext_access"
    )

    assert success == True

    # Verify tokens were encrypted
    assert existing_token.refresh_token.startswith("gAAAAA")
    assert existing_token.access_token.startswith("gAAAAA")

    # Verify they're NOT plaintext
    assert existing_token.refresh_token != "new_plaintext_refresh"
    assert existing_token.access_token != "new_plaintext_access"
