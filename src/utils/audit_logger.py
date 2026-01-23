"""
Audit logging for sensitive operations.

Q2 2026: Comprehensive audit trail for compliance and security monitoring.
Tracks: admin actions, team changes, task deletions, OAuth access, rate limit violations.
"""

import logging
import functools
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Types of auditable actions."""
    # Admin actions
    MIGRATION_RUN = "migration_run"
    TEAM_SEED = "team_seed"
    CONVERSATION_CLEAR = "conversation_clear"

    # Team management
    TEAM_MEMBER_CREATE = "team_member_create"
    TEAM_MEMBER_UPDATE = "team_member_update"
    TEAM_MEMBER_DELETE = "team_member_delete"

    # Task operations
    TASK_DELETE = "task_delete"
    TASK_BULK_UPDATE = "task_bulk_update"
    TASK_ARCHIVE = "task_archive"

    # OAuth/Security
    OAUTH_TOKEN_ACCESS = "oauth_token_access"
    OAUTH_TOKEN_REFRESH = "oauth_token_refresh"
    RATE_LIMIT_VIOLATION = "rate_limit_violation"
    AUTH_FAILURE = "auth_failure"

    # Data operations
    DATABASE_QUERY = "database_query"
    EXPORT_DATA = "export_data"


class AuditLevel(str, Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


async def log_audit_event(
    action: AuditAction,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    level: AuditLevel = AuditLevel.INFO,
    ip_address: Optional[str] = None,
) -> bool:
    """
    Log an audit event to database and system logs.

    Args:
        action: Type of action performed
        user_id: ID of user performing action
        entity_type: Type of entity affected (task, user, project, etc.)
        entity_id: ID of affected entity
        details: Additional context (changes, reasons, etc.)
        level: Severity level
        ip_address: Client IP address

    Returns:
        True if logged successfully
    """
    try:
        from ..database.repositories import get_audit_repository

        audit_repo = get_audit_repository()

        # Create audit log entry
        entry = await audit_repo.create(
            action=action.value,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            level=level.value,
            ip_address=ip_address,
            timestamp=datetime.now(),
        )

        # Also log to system logs for real-time monitoring
        log_message = f"AUDIT: {action.value} by {user_id or 'system'}"
        if entity_type and entity_id:
            log_message += f" on {entity_type}:{entity_id}"

        if level == AuditLevel.CRITICAL:
            logger.critical(log_message, extra={"audit": True, "details": details})
        elif level == AuditLevel.WARNING:
            logger.warning(log_message, extra={"audit": True, "details": details})
        else:
            logger.info(log_message, extra={"audit": True, "details": details})

        return True

    except Exception as e:
        # Never fail the operation due to audit logging failure
        logger.error(f"Failed to log audit event: {e}")
        return False


def audit_log(
    action: AuditAction,
    entity_type: Optional[str] = None,
    level: AuditLevel = AuditLevel.INFO,
    extract_user_from: str = "user_id",
    extract_entity_from: Optional[str] = None,
):
    """
    Decorator to automatically audit function calls.

    Usage:
        @audit_log(AuditAction.TASK_DELETE, entity_type="task", extract_entity_from="task_id")
        async def delete_task(user_id: str, task_id: str):
            ...

    Args:
        action: Type of action to audit
        entity_type: Type of entity being acted upon
        level: Severity level
        extract_user_from: Parameter name containing user_id
        extract_entity_from: Parameter name containing entity_id
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user_id and entity_id from function parameters
            user_id = kwargs.get(extract_user_from)
            entity_id = kwargs.get(extract_entity_from) if extract_entity_from else None

            # Get IP address from request context if available
            ip_address = None
            if "request" in kwargs:
                request = kwargs["request"]
                ip_address = request.client.host if hasattr(request, "client") else None

            # Execute the function
            try:
                result = await func(*args, **kwargs)

                # Log successful audit event
                await log_audit_event(
                    action=action,
                    user_id=user_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    details={
                        "function": func.__name__,
                        "args": str(args)[:200],  # Truncate long args
                        "status": "success",
                    },
                    level=level,
                    ip_address=ip_address,
                )

                return result

            except Exception as e:
                # Log failed audit event
                await log_audit_event(
                    action=action,
                    user_id=user_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    details={
                        "function": func.__name__,
                        "status": "failed",
                        "error": str(e)[:200],
                    },
                    level=AuditLevel.WARNING,
                    ip_address=ip_address,
                )
                raise

        return wrapper
    return decorator


def audit_rate_limit_violation(ip_address: str, path: str, limit: int):
    """
    Log rate limit violation for security monitoring.

    Args:
        ip_address: Client IP that exceeded limit
        path: API path that was rate limited
        limit: Rate limit that was exceeded
    """
    import asyncio

    asyncio.create_task(log_audit_event(
        action=AuditAction.RATE_LIMIT_VIOLATION,
        entity_type="api_endpoint",
        entity_id=path,
        details={
            "limit": limit,
            "path": path,
        },
        level=AuditLevel.WARNING,
        ip_address=ip_address,
    ))


def audit_auth_failure(user_id: Optional[str], reason: str, ip_address: Optional[str]):
    """
    Log authentication failure for security monitoring.

    Args:
        user_id: User who failed authentication
        reason: Reason for failure
        ip_address: Client IP
    """
    import asyncio

    asyncio.create_task(log_audit_event(
        action=AuditAction.AUTH_FAILURE,
        user_id=user_id,
        details={"reason": reason},
        level=AuditLevel.WARNING,
        ip_address=ip_address,
    ))
