"""
Repository for OAuth token storage and retrieval.

Handles storing and refreshing Google OAuth tokens for user-level integrations.

Q1 2026: Integrated token encryption using Fernet (AES-128).
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, UTC
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import OAuthTokenDB
from ..connection import get_database
from ...utils.encryption import get_token_encryption

logger = logging.getLogger(__name__)


class OAuthTokenRepository:
    """Repository for OAuth token operations."""

    def __init__(self):
        self.db = get_database()

    async def store_token(
        self,
        email: str,
        service: str,
        refresh_token: str,
        access_token: Optional[str] = None,
        expires_in: Optional[int] = None,
        scopes: Optional[str] = None,
    ) -> bool:
        """
        Store or update an OAuth token for a user/service combination.

        Q1 2026: Encrypts tokens before storage using Fernet (AES-128).

        Args:
            email: User's email address
            service: Service name ('calendar' or 'tasks')
            refresh_token: OAuth refresh token
            access_token: OAuth access token (optional)
            expires_in: Seconds until access token expires
            scopes: Space-separated list of granted scopes
        """
        try:
            # Encrypt tokens before storage
            encryption = get_token_encryption()
            encrypted_refresh = encryption.encrypt(refresh_token)
            encrypted_access = encryption.encrypt(access_token) if access_token else None

            async with self.db.session() as session:
                # Check if token already exists
                stmt = select(OAuthTokenDB).where(
                    and_(
                        OAuthTokenDB.email == email,
                        OAuthTokenDB.service == service
                    )
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                expires_at = None
                if expires_in:
                    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

                if existing:
                    # Update existing token
                    existing.refresh_token = encrypted_refresh
                    if encrypted_access:
                        existing.access_token = encrypted_access
                    if expires_at:
                        existing.expires_at = expires_at
                    if scopes:
                        existing.scopes = scopes
                    existing.updated_at = datetime.now(UTC)
                    logger.info(f"Updated encrypted {service} token for {email}")
                else:
                    # Create new token
                    token = OAuthTokenDB(
                        email=email,
                        service=service,
                        refresh_token=encrypted_refresh,
                        access_token=encrypted_access,
                        expires_at=expires_at,
                        scopes=scopes,
                    )
                    session.add(token)
                    logger.info(f"Stored new encrypted {service} token for {email}")

                await session.commit()
                return True

        except Exception as e:
            logger.error(f"Error storing OAuth token: {e}")
            return False

    async def get_token(self, email: str, service: str) -> Optional[Dict[str, Any]]:
        """
        Get OAuth token for a user/service combination.

        Q1 2026: Decrypts tokens after retrieval. Falls back to plaintext
        for backward compatibility during migration.

        Q2 2026: Added audit logging for OAuth token access.

        Returns dict with refresh_token, access_token, expires_at, scopes.
        """
        try:
            async with self.db.session() as session:
                stmt = select(OAuthTokenDB).where(
                    and_(
                        OAuthTokenDB.email == email,
                        OAuthTokenDB.service == service
                    )
                )
                result = await session.execute(stmt)
                token = result.scalar_one_or_none()

                if not token:
                    return None

                # Decrypt tokens (with backward compatibility)
                encryption = get_token_encryption()
                try:
                    refresh_token = encryption.decrypt(token.refresh_token)
                    access_token = encryption.decrypt(token.access_token) if token.access_token else None
                except Exception as decrypt_error:
                    # Backward compatibility: if decrypt fails, assume plaintext (pre-encryption)
                    logger.warning(f"Decrypt failed for {email}/{service}, assuming plaintext: {decrypt_error}")
                    refresh_token = token.refresh_token
                    access_token = token.access_token

                # Q2 2026: Audit log OAuth token access
                from ...utils.audit_logger import log_audit_event, AuditAction, AuditLevel
                await log_audit_event(
                    action=AuditAction.OAUTH_TOKEN_ACCESS,
                    user_id=email,
                    entity_type="oauth_token",
                    entity_id=f"{email}:{service}",
                    details={"service": service},
                    level=AuditLevel.INFO
                )

                return {
                    "email": token.email,
                    "service": token.service,
                    "refresh_token": refresh_token,
                    "access_token": access_token,
                    "expires_at": token.expires_at,
                    "scopes": token.scopes,
                }

        except Exception as e:
            logger.error(f"Error getting OAuth token: {e}")
            return None

    async def get_refresh_token(self, email: str, service: str) -> Optional[str]:
        """Get just the refresh token for a user/service."""
        token = await self.get_token(email, service)
        return token.get("refresh_token") if token else None

    async def update_access_token(
        self,
        email: str,
        service: str,
        access_token: str,
        expires_in: Optional[int] = None
    ) -> bool:
        """
        Update the access token after a refresh.

        Q1 2026: Encrypts access token before update.
        Q2 2026: Added audit logging for OAuth token refresh.
        """
        try:
            # Encrypt access token before storage
            encryption = get_token_encryption()
            encrypted_access = encryption.encrypt(access_token)

            async with self.db.session() as session:
                stmt = select(OAuthTokenDB).where(
                    and_(
                        OAuthTokenDB.email == email,
                        OAuthTokenDB.service == service
                    )
                )
                result = await session.execute(stmt)
                token = result.scalar_one_or_none()

                if not token:
                    return False

                token.access_token = encrypted_access
                if expires_in:
                    token.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
                token.updated_at = datetime.now(UTC)

                await session.commit()

                # Q2 2026: Audit log OAuth token refresh
                from ...utils.audit_logger import log_audit_event, AuditAction, AuditLevel
                await log_audit_event(
                    action=AuditAction.OAUTH_TOKEN_REFRESH,
                    user_id=email,
                    entity_type="oauth_token",
                    entity_id=f"{email}:{service}",
                    details={"service": service, "expires_in": expires_in},
                    level=AuditLevel.INFO
                )

                return True

        except Exception as e:
            logger.error(f"Error updating access token: {e}")
            return False

    async def delete_token(self, email: str, service: str) -> bool:
        """Delete a token (e.g., when user disconnects)."""
        try:
            async with self.db.session() as session:
                stmt = select(OAuthTokenDB).where(
                    and_(
                        OAuthTokenDB.email == email,
                        OAuthTokenDB.service == service
                    )
                )
                result = await session.execute(stmt)
                token = result.scalar_one_or_none()

                if token:
                    await session.delete(token)
                    await session.commit()
                    logger.info(f"Deleted {service} token for {email}")

                return True

        except Exception as e:
            logger.error(f"Error deleting OAuth token: {e}")
            return False

    async def has_token(self, email: str, service: str) -> bool:
        """Check if a user has a token for a service."""
        token = await self.get_token(email, service)
        return token is not None


# Singleton instance
_oauth_repo: Optional[OAuthTokenRepository] = None


def get_oauth_repository() -> OAuthTokenRepository:
    """Get the OAuth token repository singleton."""
    global _oauth_repo
    if _oauth_repo is None:
        _oauth_repo = OAuthTokenRepository()
    return _oauth_repo
