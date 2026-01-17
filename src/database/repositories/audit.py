"""
Audit log repository for tracking all changes.

Logs every action with:
- What changed (field, old value, new value)
- Who changed it
- When it changed
- Why it changed (optional reason)
- Source (telegram, discord, api, scheduler)
"""

import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import get_database
from ..models import AuditLogDB, TaskDB

logger = logging.getLogger(__name__)


class AuditRepository:
    """Repository for audit log operations."""

    def __init__(self):
        self.db = get_database()

    async def log(
        self,
        action: str,
        changed_by: str,
        entity_type: str = "task",
        entity_id: Optional[str] = None,
        task_id: Optional[int] = None,
        task_ref: Optional[str] = None,
        field_changed: Optional[str] = None,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        reason: Optional[str] = None,
        source: str = "telegram",
        changed_by_id: Optional[str] = None,
        snapshot: Optional[Dict] = None,
    ) -> Optional[AuditLogDB]:
        """Log an action to the audit trail."""
        async with self.db.session() as session:
            try:
                # Convert values to strings if needed
                old_str = json.dumps(old_value) if isinstance(old_value, (dict, list)) else str(old_value) if old_value is not None else None
                new_str = json.dumps(new_value) if isinstance(new_value, (dict, list)) else str(new_value) if new_value is not None else None

                log_entry = AuditLogDB(
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    task_id=task_id,
                    task_ref=task_ref,
                    field_changed=field_changed,
                    old_value=old_str,
                    new_value=new_str,
                    changed_by=changed_by,
                    changed_by_id=changed_by_id,
                    reason=reason,
                    source=source,
                    snapshot=snapshot,
                )
                session.add(log_entry)
                await session.flush()

                logger.debug(f"Audit log: {action} on {entity_type}/{entity_id} by {changed_by}")
                return log_entry

            except Exception as e:
                logger.error(f"Error creating audit log: {e}")
                return None

    async def log_task_created(
        self,
        task: TaskDB,
        created_by: str,
        source: str = "telegram",
        created_by_id: Optional[str] = None,
    ) -> Optional[AuditLogDB]:
        """Log task creation."""
        return await self.log(
            action="created",
            entity_type="task",
            entity_id=task.task_id,
            task_id=task.id,
            task_ref=task.task_id,
            changed_by=created_by,
            changed_by_id=created_by_id,
            source=source,
            new_value={
                "title": task.title,
                "assignee": task.assignee,
                "priority": task.priority,
                "deadline": task.deadline.isoformat() if task.deadline else None,
            },
        )

    async def log_status_change(
        self,
        task_ref: str,
        old_status: str,
        new_status: str,
        changed_by: str,
        reason: Optional[str] = None,
        source: str = "telegram",
        changed_by_id: Optional[str] = None,
    ) -> Optional[AuditLogDB]:
        """Log task status change."""
        return await self.log(
            action="status_changed",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            field_changed="status",
            old_value=old_status,
            new_value=new_status,
            changed_by=changed_by,
            changed_by_id=changed_by_id,
            reason=reason,
            source=source,
        )

    async def log_field_change(
        self,
        task_ref: str,
        field: str,
        old_value: Any,
        new_value: Any,
        changed_by: str,
        source: str = "telegram",
    ) -> Optional[AuditLogDB]:
        """Log a field change on a task."""
        return await self.log(
            action="updated",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            field_changed=field,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            source=source,
        )

    async def log_approval(
        self,
        task_ref: str,
        approved_by: str,
        message: Optional[str] = None,
        source: str = "telegram",
    ) -> Optional[AuditLogDB]:
        """Log task approval."""
        return await self.log(
            action="approved",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            changed_by=approved_by,
            reason=message,
            source=source,
        )

    async def log_rejection(
        self,
        task_ref: str,
        rejected_by: str,
        feedback: str,
        source: str = "telegram",
    ) -> Optional[AuditLogDB]:
        """Log task rejection."""
        return await self.log(
            action="rejected",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            changed_by=rejected_by,
            reason=feedback,
            source=source,
        )

    async def log_proof_submitted(
        self,
        task_ref: str,
        submitted_by: str,
        proof_count: int,
        source: str = "telegram",
    ) -> Optional[AuditLogDB]:
        """Log proof submission."""
        return await self.log(
            action="proof_submitted",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            changed_by=submitted_by,
            new_value={"proof_count": proof_count},
            source=source,
        )

    async def log_dependency_added(
        self,
        task_ref: str,
        depends_on_ref: str,
        dependency_type: str,
        created_by: str,
    ) -> Optional[AuditLogDB]:
        """Log dependency creation."""
        return await self.log(
            action="dependency_added",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            changed_by=created_by,
            new_value={
                "depends_on": depends_on_ref,
                "type": dependency_type,
            },
        )

    async def log_subtask_added(
        self,
        task_ref: str,
        subtask_title: str,
        created_by: str,
    ) -> Optional[AuditLogDB]:
        """Log subtask addition."""
        return await self.log(
            action="subtask_added",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            changed_by=created_by,
            new_value={"subtask": subtask_title},
        )

    async def log_sheets_sync(
        self,
        task_ref: str,
        row_id: Optional[int] = None,
    ) -> Optional[AuditLogDB]:
        """Log sync to Google Sheets."""
        return await self.log(
            action="synced_to_sheets",
            entity_type="task",
            entity_id=task_ref,
            task_ref=task_ref,
            changed_by="system",
            source="scheduler",
            new_value={"sheets_row": row_id},
        )

    # ==================== QUERY METHODS ====================

    async def get_task_history(self, task_ref: str) -> List[AuditLogDB]:
        """Get full audit history for a task."""
        async with self.db.session() as session:
            result = await session.execute(
                select(AuditLogDB)
                .where(AuditLogDB.task_ref == task_ref)
                .order_by(AuditLogDB.timestamp.desc())
            )
            return list(result.scalars().all())

    async def get_user_activity(
        self,
        user_id: str,
        days: int = 7
    ) -> List[AuditLogDB]:
        """Get recent activity by a user."""
        since = datetime.now() - timedelta(days=days)
        async with self.db.session() as session:
            result = await session.execute(
                select(AuditLogDB)
                .where(
                    and_(
                        AuditLogDB.changed_by_id == user_id,
                        AuditLogDB.timestamp >= since,
                    )
                )
                .order_by(AuditLogDB.timestamp.desc())
            )
            return list(result.scalars().all())

    async def get_recent_logs(
        self,
        limit: int = 50,
        action_filter: Optional[str] = None
    ) -> List[AuditLogDB]:
        """Get recent audit logs."""
        async with self.db.session() as session:
            query = select(AuditLogDB)

            if action_filter:
                query = query.where(AuditLogDB.action == action_filter)

            query = query.order_by(AuditLogDB.timestamp.desc()).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_activity_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get activity statistics."""
        since = datetime.now() - timedelta(days=days)

        async with self.db.session() as session:
            # Count by action type
            action_counts = await session.execute(
                select(AuditLogDB.action, func.count(AuditLogDB.id))
                .where(AuditLogDB.timestamp >= since)
                .group_by(AuditLogDB.action)
            )
            actions = {row[0]: row[1] for row in action_counts}

            # Count by user
            user_counts = await session.execute(
                select(AuditLogDB.changed_by, func.count(AuditLogDB.id))
                .where(AuditLogDB.timestamp >= since)
                .group_by(AuditLogDB.changed_by)
                .order_by(func.count(AuditLogDB.id).desc())
                .limit(10)
            )
            users = {row[0]: row[1] for row in user_counts}

            # Total events
            total = await session.execute(
                select(func.count(AuditLogDB.id))
                .where(AuditLogDB.timestamp >= since)
            )
            total_count = total.scalar() or 0

            return {
                "total_events": total_count,
                "by_action": actions,
                "by_user": users,
                "period_days": days,
            }

    async def search_logs(
        self,
        query: str,
        limit: int = 50
    ) -> List[AuditLogDB]:
        """Search audit logs by content."""
        async with self.db.session() as session:
            result = await session.execute(
                select(AuditLogDB)
                .where(
                    or_(
                        AuditLogDB.task_ref.ilike(f"%{query}%"),
                        AuditLogDB.changed_by.ilike(f"%{query}%"),
                        AuditLogDB.reason.ilike(f"%{query}%"),
                        AuditLogDB.old_value.ilike(f"%{query}%"),
                        AuditLogDB.new_value.ilike(f"%{query}%"),
                    )
                )
                .order_by(AuditLogDB.timestamp.desc())
                .limit(limit)
            )
            return list(result.scalars().all())


# Import or_ for search
from sqlalchemy import or_

# Singleton
_audit_repository: Optional[AuditRepository] = None


def get_audit_repository() -> AuditRepository:
    """Get the audit repository singleton."""
    global _audit_repository
    if _audit_repository is None:
        _audit_repository = AuditRepository()
    return _audit_repository
