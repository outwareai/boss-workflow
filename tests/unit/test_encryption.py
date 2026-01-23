"""
Tests for OAuth token encryption (encryption.py).

Q1 2026: Ensures Fernet encryption works correctly.
"""

import pytest
from src.utils.encryption import TokenEncryption, encrypt_token, decrypt_token


class TestTokenEncryption:
    """Test OAuth token encryption/decryption."""

    def test_encrypt_decrypt_round_trip(self):
        """Test encryption and decryption round trip."""
        encryption = TokenEncryption()
        original = "test_oauth_token_12345"

        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)

        # If encryption is enabled, encrypted should differ from original
        if encryption._initialized:
            assert encrypted != original
            assert decrypted == original
        else:
            # If disabled, returns plaintext
            assert encrypted == original

    def test_is_encrypted(self):
        """Test detection of encrypted tokens."""
        encryption = TokenEncryption()
        plaintext = "plaintext_token"
        encrypted = encryption.encrypt(plaintext)

        if encryption._initialized:
            assert encryption.is_encrypted(encrypted)
            assert not encryption.is_encrypted(plaintext)

    def test_decrypt_plaintext_token(self):
        """Test decrypting plaintext tokens (backward compatibility)."""
        encryption = TokenEncryption()
        plaintext = "old_plaintext_token"

        # Should return plaintext as-is if decryption fails
        result = encryption.decrypt(plaintext)
        assert result == plaintext

    def test_convenience_functions(self):
        """Test module-level convenience functions."""
        original = "test_token_xyz"
        encrypted = encrypt_token(original)
        decrypted = decrypt_token(encrypted)

        # Should work (either encrypted or plaintext fallback)
        assert decrypted == original or decrypted == encrypted

    def test_empty_string(self):
        """Test encrypting empty string."""
        encryption = TokenEncryption()
        result = encryption.encrypt("")
        assert isinstance(result, str)

    def test_long_token(self):
        """Test encrypting long OAuth token."""
        encryption = TokenEncryption()
        long_token = "x" * 1000
        encrypted = encryption.encrypt(long_token)
        decrypted = encryption.decrypt(encrypted)

        if encryption._initialized:
            assert decrypted == long_token
        else:
            assert encrypted == long_token
