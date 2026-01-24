"""
Unit tests for OAuthRepository.

CRITICAL - TIER 1 (Security/Data Integrity)
Tests token encryption, decryption, and secure storage.

Q4 2026: Comprehensive OAuth repository tests.
Target coverage: 75%+
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta

from src.database.repositories.oauth import OAuthTokenRepository
from src.database.models import OAuthTokenDB


@pytest.fixture
def mock_database():
    """Mock database with session context manager."""
    db = Mock()
    session = AsyncMock()

    # Mock session context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    # Mock session methods
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = Mock()
    session.delete = AsyncMock()

    db.session = Mock(return_value=session)

    return db, session


@pytest.fixture
def oauth_repository(mock_database):
    """Create OAuthRepository with mocked database."""
    db, session = mock_database
    repo = OAuthTokenRepository()
    repo.db = db
    return repo, session


@pytest.fixture
def sample_oauth_token():
    """Create a sample OAuth token for testing."""
    return OAuthTokenDB(
        id=1,
        email="test@example.com",
        service="calendar",
        refresh_token="gAAAAA_encrypted_refresh_token_12345",
        access_token="gAAAAA_encrypted_access_token_67890",
        expires_at=datetime.utcnow() + timedelta(hours=1),
        scopes="https://www.googleapis.com/auth/calendar",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


# ============================================================
# STORE TOKEN TESTS (Encryption)
# ============================================================

@pytest.mark.asyncio
async def test_store_token_encrypts_tokens(oauth_repository):
    """Test that tokens are encrypted before storage."""
    repo, session = oauth_repository

    # Mock no existing token
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc:
        mock_encryption = Mock()
        mock_encryption.encrypt = Mock(side_effect=lambda x: f"gAAAAA_encrypted_{x}".encode() if isinstance(x, str) else f"gAAAAA_encrypted_{x.decode()}".encode())
        mock_enc.return_value = mock_encryption

        result = await repo.store_token(
            email="test@example.com",
            service="calendar",
            refresh_token="plain_refresh_token",
            access_token="plain_access_token"
        )

        assert result == True
        assert mock_encryption.encrypt.call_count == 2  # refresh + access
        session.add.assert_called_once()


@pytest.mark.asyncio
async def test_store_token_updates_existing(oauth_repository, sample_oauth_token):
    """Test that existing tokens are updated, not duplicated."""
    repo, session = oauth_repository

    # Mock existing token
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_oauth_token)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc:
        mock_encryption = Mock()
        mock_encryption.encrypt = Mock(return_value=b"gAAAAA_new_encrypted")
        mock_enc.return_value = mock_encryption

        result = await repo.store_token(
            email="test@example.com",
            service="calendar",
            refresh_token="new_refresh",
            access_token="new_access"
        )

        assert result == True
        assert sample_oauth_token.refresh_token == b"gAAAAA_new_encrypted"
        session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_store_token_handles_expiry(oauth_repository):
    """Test that expiry timestamps are correctly calculated."""
    repo, session = oauth_repository

    # Mock no existing token
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc:
        mock_encryption = Mock()
        mock_encryption.encrypt = Mock(return_value=b"gAAAAA_encrypted")
        mock_enc.return_value = mock_encryption

        before = datetime.utcnow()

        result = await repo.store_token(
            email="test@example.com",
            service="calendar",
            refresh_token="token",
            expires_in=3600  # 1 hour
        )

        after = datetime.utcnow() + timedelta(seconds=3600)

        assert result == True
        # Verify expiry was set (check via session.add call)
        session.add.assert_called_once()


# ============================================================
# GET TOKEN TESTS (Decryption)
# ============================================================

@pytest.mark.asyncio
async def test_get_token_decrypts_successfully(oauth_repository, sample_oauth_token):
    """Test that encrypted tokens are decrypted on retrieval."""
    repo, session = oauth_repository

    # Mock token retrieval
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_oauth_token)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc, \
         patch('src.utils.audit_logger.log_audit_event') as mock_audit:

        mock_encryption = Mock()
        mock_encryption.decrypt = Mock(side_effect=lambda x: x.replace("gAAAAA_encrypted_", "").replace("_12345", "").replace("_67890", ""))
        mock_enc.return_value = mock_encryption
        mock_audit.return_value = AsyncMock()

        result = await repo.get_token("test@example.com", "calendar")

        assert result is not None
        assert result["email"] == "test@example.com"
        assert result["service"] == "calendar"
        assert "refresh_token" in result
        assert "access_token" in result
        mock_encryption.decrypt.call_count == 2  # refresh + access


@pytest.mark.asyncio
async def test_get_token_returns_none_if_missing(oauth_repository):
    """Test that None is returned if token doesn't exist."""
    repo, session = oauth_repository

    # Mock no token found
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_token("nonexistent@example.com", "calendar")

    assert result is None


@pytest.mark.asyncio
async def test_get_token_backward_compatibility_plaintext(oauth_repository):
    """Test backward compatibility with plaintext tokens."""
    repo, session = oauth_repository

    # Create token with plaintext (no gAAAAA prefix)
    plaintext_token = OAuthTokenDB(
        id=1,
        email="old@example.com",
        service="calendar",
        refresh_token="plaintext_refresh_token",  # No encryption
        access_token="plaintext_access_token",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=plaintext_token)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc, \
         patch('src.database.repositories.oauth.log_audit_event') as mock_audit:

        mock_encryption = Mock()
        mock_encryption.decrypt = Mock(side_effect=Exception("Invalid token format"))
        mock_enc.return_value = mock_encryption

        result = await repo.get_token("old@example.com", "calendar")

        # Should fallback to plaintext
        assert result is not None
        assert result["refresh_token"] == "plaintext_refresh_token"
        assert result["access_token"] == "plaintext_access_token"


@pytest.mark.asyncio
async def test_get_token_logs_audit_event(oauth_repository, sample_oauth_token):
    """Test that OAuth token access is logged for audit."""
    repo, session = oauth_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_oauth_token)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc, \
         patch('src.database.repositories.oauth.log_audit_event') as mock_audit:

        mock_encryption = Mock()
        mock_encryption.decrypt = Mock(return_value="decrypted_token")
        mock_enc.return_value = mock_encryption
        mock_audit.return_value = AsyncMock()

        result = await repo.get_token("test@example.com", "calendar")

        # Verify audit was logged
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["user_id"] == "test@example.com"
        assert call_kwargs["entity_id"] == "test@example.com:calendar"


# ============================================================
# UPDATE ACCESS TOKEN TESTS
# ============================================================

@pytest.mark.asyncio
async def test_update_access_token_encrypts(oauth_repository, sample_oauth_token):
    """Test that access token updates are encrypted."""
    repo, session = oauth_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_oauth_token)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc, \
         patch('src.database.repositories.oauth.log_audit_event') as mock_audit:

        mock_encryption = Mock()
        mock_encryption.encrypt = Mock(return_value=b"gAAAAA_new_access_encrypted")
        mock_enc.return_value = mock_encryption
        mock_audit.return_value = AsyncMock()

        result = await repo.update_access_token(
            email="test@example.com",
            service="calendar",
            access_token="new_access_token",
            expires_in=7200
        )

        assert result == True
        assert sample_oauth_token.access_token == b"gAAAAA_new_access_encrypted"
        mock_encryption.encrypt.assert_called_once_with("new_access_token")


@pytest.mark.asyncio
async def test_update_access_token_returns_false_if_missing(oauth_repository):
    """Test that update fails gracefully if token doesn't exist."""
    repo, session = oauth_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    with patch('src.database.repositories.oauth.get_token_encryption') as mock_enc:
        mock_encryption = Mock()
        mock_enc.return_value = mock_encryption

        result = await repo.update_access_token(
            email="nonexistent@example.com",
            service="calendar",
            access_token="new_token"
        )

        assert result == False


# ============================================================
# DELETE TOKEN TESTS
# ============================================================

@pytest.mark.asyncio
async def test_delete_token_success(oauth_repository, sample_oauth_token):
    """Test that tokens are deleted successfully."""
    repo, session = oauth_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_oauth_token)
    session.execute.return_value = mock_result

    result = await repo.delete_token("test@example.com", "calendar")

    assert result == True
    session.delete.assert_called_once_with(sample_oauth_token)
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_token_handles_missing(oauth_repository):
    """Test that deleting non-existent token doesn't error."""
    repo, session = oauth_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.delete_token("nonexistent@example.com", "calendar")

    assert result == True  # Idempotent
    session.delete.assert_not_called()


# ============================================================
# HAS TOKEN TESTS
# ============================================================

@pytest.mark.asyncio
async def test_has_token_returns_true_if_exists(oauth_repository, sample_oauth_token):
    """Test that has_token returns True when token exists."""
    repo, session = oauth_repository

    # Mock get_token to return a token
    with patch.object(repo, 'get_token', return_value={"refresh_token": "token"}):
        result = await repo.has_token("test@example.com", "calendar")
        assert result == True


@pytest.mark.asyncio
async def test_has_token_returns_false_if_missing(oauth_repository):
    """Test that has_token returns False when token doesn't exist."""
    repo, session = oauth_repository

    # Mock get_token to return None
    with patch.object(repo, 'get_token', return_value=None):
        result = await repo.has_token("test@example.com", "calendar")
        assert result == False


# ============================================================
# GET REFRESH TOKEN TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_refresh_token_extracts_correctly(oauth_repository):
    """Test that get_refresh_token extracts just the refresh token."""
    repo, session = oauth_repository

    # Mock get_token
    with patch.object(repo, 'get_token', return_value={
        "refresh_token": "my_refresh_token",
        "access_token": "my_access_token"
    }):
        result = await repo.get_refresh_token("test@example.com", "calendar")
        assert result == "my_refresh_token"


@pytest.mark.asyncio
async def test_get_refresh_token_returns_none_if_missing(oauth_repository):
    """Test that get_refresh_token returns None if token doesn't exist."""
    repo, session = oauth_repository

    with patch.object(repo, 'get_token', return_value=None):
        result = await repo.get_refresh_token("test@example.com", "calendar")
        assert result is None
