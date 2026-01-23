"""
OAuth token encryption utilities.

Q1 2026 Security: Encrypt sensitive OAuth tokens using Fernet (AES-128).
Requires ENCRYPTION_KEY environment variable (generate with: Fernet.generate_key()).
"""

import logging
from typing import Optional
from cryptography.fernet import Fernet
from config.settings import settings

logger = logging.getLogger(__name__)


class TokenEncryption:
    """Handles encryption/decryption of OAuth tokens."""

    def __init__(self):
        """Initialize with encryption key from environment."""
        self._cipher: Optional[Fernet] = None
        self._initialized = False

        # Get encryption key from environment
        key = getattr(settings, 'encryption_key', None)

        if not key:
            logger.warning(
                "ENCRYPTION_KEY not configured - OAuth tokens will be stored in plaintext! "
                "Generate key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
            return

        try:
            # Validate and create cipher
            if isinstance(key, str):
                key = key.encode()

            self._cipher = Fernet(key)
            self._initialized = True
            logger.info("Token encryption initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize token encryption: {e}")

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext OAuth token.

        Args:
            plaintext: The token string to encrypt

        Returns:
            Encrypted token (base64) or original plaintext if encryption disabled
        """
        if not self._initialized or not self._cipher:
            logger.debug("Encryption not initialized, storing token in plaintext")
            return plaintext

        try:
            encrypted = self._cipher.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Failed to encrypt token: {e}")
            return plaintext  # Fallback to plaintext on error

    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt an encrypted OAuth token.

        Args:
            encrypted: The encrypted token string (base64)

        Returns:
            Decrypted plaintext token or original string if decryption fails
        """
        if not self._initialized or not self._cipher:
            logger.debug("Encryption not initialized, returning token as-is")
            return encrypted

        try:
            decrypted = self._cipher.decrypt(encrypted.encode())
            return decrypted.decode()
        except Exception as e:
            # Could be plaintext token from before encryption was enabled
            logger.debug(f"Failed to decrypt token (might be plaintext): {e}")
            return encrypted  # Return as-is, assume it's plaintext

    def is_encrypted(self, token: str) -> bool:
        """
        Check if a token appears to be encrypted (Fernet format).

        Args:
            token: Token string to check

        Returns:
            True if token looks encrypted, False otherwise
        """
        if not self._initialized or not self._cipher:
            return False

        # Fernet tokens start with "gAAAAA" after base64 encoding
        # and are typically 100+ characters
        return token.startswith("gAAAAA") and len(token) > 50


# Global instance
_encryption_instance: Optional[TokenEncryption] = None


def get_token_encryption() -> TokenEncryption:
    """Get singleton token encryption instance."""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = TokenEncryption()
    return _encryption_instance


def encrypt_token(token: str) -> str:
    """
    Convenience function to encrypt a token.

    Usage:
        encrypted = encrypt_token(oauth_token)
    """
    encryption = get_token_encryption()
    return encryption.encrypt(token)


def decrypt_token(encrypted: str) -> str:
    """
    Convenience function to decrypt a token.

    Usage:
        plaintext = decrypt_token(encrypted_token)
    """
    encryption = get_token_encryption()
    return encryption.decrypt(encrypted)
