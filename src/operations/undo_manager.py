"""
Enterprise undo/redo system with multi-level support.

Provides:
- Multi-level undo/redo (up to 10 actions)
- Full audit trail integration
- Redis caching for fast access
- Automatic cleanup of old history
- Support for various action types
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import UndoHistoryDB, TaskDB
from ..database.connection import get_database
from ..cache.redis_client import cache

logger = logging.getLogger(__name__)


class UndoManager:
    """Enterprise undo/redo manager."""

    def __init__(self):
        self.db = get_database()
        self.max_history_days = 7  # Keep undo history for 7 days
        self.max_undo_depth = 10  # Support up to 10 undos
        self.cache_ttl = 3600  # 1 hour cache

    async def record_action(
        self,
        user_id: str,
        action_type: str,
        action_data: Dict,
        undo_function: str,
        undo_data: Dict,
        description: str,
        metadata: Optional[Dict] = None,
        session: Optional[AsyncSession] = None
    ) -> int:
        """
        Record an undoable action in database and cache.

        Args:
            user_id: User who performed the action (Telegram/Discord ID)
            action_type: Type of action (delete_task, change_status, etc.)
            action_data: Original action parameters (for redo)
            undo_function: Function name to call for undo
            undo_data: Data needed to undo the action
            description: Human-readable description
            metadata: Additional context

        Returns:
            ID of the recorded undo action
        """
        # Use provided session or create a new one
        use_existing_session = session is not None

        if not use_existing_session:
            session = self.db.session()
            await session.__aenter__()

        try:
            # Create database record
            undo_record = UndoHistoryDB(
                user_id=user_id,
                action_type=action_type,
                action_data=action_data,
                undo_function=undo_function,
                undo_data=undo_data,
                description=description,
                metadata=metadata or {}
            )

            session.add(undo_record)
            await session.flush()

            record_id = undo_record.id

            # Cache last N actions for fast access
            cache_key = f"undo:history:{user_id}"
            history = await cache.get(cache_key) or []
            history.insert(0, {
                "id": record_id,
                "action_type": action_type,
                "description": description,
                "timestamp": undo_record.timestamp.isoformat()
            })

            # Keep only recent actions in cache
            history = history[:self.max_undo_depth]
            await cache.set(cache_key, history, ttl=self.cache_ttl)

            logger.info(f"Recorded undoable action: {action_type} for user {user_id}")

            # Only commit if we created the session
            if not use_existing_session:
                await session.commit()

            return record_id

        except Exception as e:
            logger.error(f"Failed to record undo action: {e}")
            if not use_existing_session:
                await session.rollback()
            raise
        finally:
            # Only close if we created the session
            if not use_existing_session:
                await session.__aexit__(None, None, None)

    async def get_undo_history(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get undo history for user.

        Args:
            user_id: User ID to get history for
            limit: Maximum number of records to return

        Returns:
            List of undo history entries
        """
        # Try cache first
        cache_key = f"undo:history:{user_id}"
        cached = await cache.get(cache_key)
        if cached:
            return cached[:limit]

        # Query database
        async with self.db.session() as session:
            stmt = (
                select(UndoHistoryDB)
                .where(UndoHistoryDB.user_id == user_id)
                .where(UndoHistoryDB.is_undone == False)
                .order_by(UndoHistoryDB.timestamp.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            records = result.scalars().all()

            history = [
                {
                    "id": r.id,
                    "action_type": r.action_type,
                    "description": r.description,
                    "timestamp": r.timestamp.isoformat(),
                    "metadata": r.metadata
                }
                for r in records
            ]

            # Update cache
            await cache.set(cache_key, history, ttl=self.cache_ttl)

            return history

    async def undo_action(
        self,
        user_id: str,
        action_id: Optional[int] = None
    ) -> Dict:
        """
        Undo an action (most recent if action_id not provided).

        Args:
            user_id: User performing the undo
            action_id: Specific action to undo (or None for most recent)

        Returns:
            Dict with success status and result details
        """
        async with self.db.session() as session:
            try:
                # Get action to undo
                if action_id:
                    stmt = select(UndoHistoryDB).where(UndoHistoryDB.id == action_id)
                else:
                    # Get most recent undoable action
                    stmt = (
                        select(UndoHistoryDB)
                        .where(UndoHistoryDB.user_id == user_id)
                        .where(UndoHistoryDB.is_undone == False)
                        .order_by(UndoHistoryDB.timestamp.desc())
                        .limit(1)
                    )

                result = await session.execute(stmt)
                undo_record = result.scalar_one_or_none()

                if not undo_record:
                    return {
                        "success": False,
                        "message": "No action to undo"
                    }

                if undo_record.is_undone:
                    return {
                        "success": False,
                        "message": "Action already undone"
                    }

                # Execute undo
                undo_result = await self._execute_undo(
                    session,
                    undo_record.undo_function,
                    undo_record.undo_data
                )

                # Mark as undone
                undo_record.is_undone = True
                undo_record.undo_timestamp = datetime.utcnow()

                # Clear cache
                cache_key = f"undo:history:{user_id}"
                await cache.delete(cache_key)

                logger.info(f"Undone action {undo_record.id}: {undo_record.action_type}")

                return {
                    "success": True,
                    "action_type": undo_record.action_type,
                    "description": undo_record.description,
                    "result": undo_result
                }

            except Exception as e:
                logger.error(f"Undo failed: {e}")
                await session.rollback()
                return {
                    "success": False,
                    "message": f"Undo failed: {str(e)}"
                }

    async def redo_action(
        self,
        user_id: str,
        action_id: int
    ) -> Dict:
        """
        Redo a previously undone action.

        Args:
            user_id: User performing the redo
            action_id: ID of action to redo

        Returns:
            Dict with success status and result details
        """
        async with self.db.session() as session:
            try:
                stmt = select(UndoHistoryDB).where(UndoHistoryDB.id == action_id)
                result = await session.execute(stmt)
                undo_record = result.scalar_one_or_none()

                if not undo_record or not undo_record.is_undone:
                    return {
                        "success": False,
                        "message": "Action cannot be redone"
                    }

                # Re-execute original action
                redo_result = await self._execute_action(
                    session,
                    undo_record.action_type,
                    undo_record.action_data
                )

                # Mark as not undone
                undo_record.is_undone = False
                undo_record.undo_timestamp = None

                # Clear cache
                cache_key = f"undo:history:{user_id}"
                await cache.delete(cache_key)

                logger.info(f"Redone action {action_id}: {undo_record.action_type}")

                return {
                    "success": True,
                    "action_type": undo_record.action_type,
                    "description": undo_record.description,
                    "result": redo_result
                }

            except Exception as e:
                logger.error(f"Redo failed: {e}")
                await session.rollback()
                return {
                    "success": False,
                    "message": f"Redo failed: {str(e)}"
                }

    async def _execute_undo(
        self,
        session: AsyncSession,
        function_name: str,
        data: Dict
    ) -> Dict:
        """Execute the undo function based on function name."""
        if function_name == "restore_task":
            return await self._undo_delete_task(session, data)
        elif function_name == "restore_status":
            return await self._undo_status_change(session, data)
        elif function_name == "restore_assignee":
            return await self._undo_reassign(session, data)
        elif function_name == "restore_priority":
            return await self._undo_priority_change(session, data)
        elif function_name == "restore_deadline":
            return await self._undo_deadline_change(session, data)
        else:
            raise ValueError(f"Unknown undo function: {function_name}")

    async def _execute_action(
        self,
        session: AsyncSession,
        action_type: str,
        data: Dict
    ) -> Dict:
        """Re-execute original action (for redo)."""
        from ..database.repositories import get_task_repository

        repo = get_task_repository()

        if action_type == "delete_task":
            # Re-delete the task
            await repo.delete(data["task_id"])
            return {"task_id": data["task_id"], "deleted": True}

        elif action_type == "change_status":
            await repo.update(data["task_id"], {"status": data["new_status"]})
            return {"task_id": data["task_id"], "status": data["new_status"]}

        elif action_type == "reassign":
            await repo.update(data["task_id"], {"assignee": data["new_assignee"]})
            return {"task_id": data["task_id"], "assignee": data["new_assignee"]}

        elif action_type == "change_priority":
            await repo.update(data["task_id"], {"priority": data["new_priority"]})
            return {"task_id": data["task_id"], "priority": data["new_priority"]}

        elif action_type == "change_deadline":
            await repo.update(data["task_id"], {"deadline": data["new_deadline"]})
            return {"task_id": data["task_id"], "deadline": data["new_deadline"]}

        else:
            raise ValueError(f"Unknown action type: {action_type}")

    async def _undo_delete_task(self, session: AsyncSession, data: Dict) -> Dict:
        """Restore deleted task."""
        from ..database.repositories import get_task_repository

        repo = get_task_repository()
        task = await repo.create(data["task_data"])

        logger.info(f"Restored deleted task: {task.task_id}")

        return {"task_id": task.task_id, "restored": True}

    async def _undo_status_change(self, session: AsyncSession, data: Dict) -> Dict:
        """Restore previous status."""
        from ..database.repositories import get_task_repository

        repo = get_task_repository()
        await repo.update(data["task_id"], {"status": data["old_status"]})

        logger.info(f"Restored status for {data['task_id']}: {data['old_status']}")

        return {"task_id": data["task_id"], "status": data["old_status"]}

    async def _undo_reassign(self, session: AsyncSession, data: Dict) -> Dict:
        """Restore previous assignee."""
        from ..database.repositories import get_task_repository

        repo = get_task_repository()
        await repo.update(data["task_id"], {"assignee": data["old_assignee"]})

        logger.info(f"Restored assignee for {data['task_id']}: {data['old_assignee']}")

        return {"task_id": data["task_id"], "assignee": data["old_assignee"]}

    async def _undo_priority_change(self, session: AsyncSession, data: Dict) -> Dict:
        """Restore previous priority."""
        from ..database.repositories import get_task_repository

        repo = get_task_repository()
        await repo.update(data["task_id"], {"priority": data["old_priority"]})

        logger.info(f"Restored priority for {data['task_id']}: {data['old_priority']}")

        return {"task_id": data["task_id"], "priority": data["old_priority"]}

    async def _undo_deadline_change(self, session: AsyncSession, data: Dict) -> Dict:
        """Restore previous deadline."""
        from ..database.repositories import get_task_repository

        repo = get_task_repository()
        await repo.update(data["task_id"], {"deadline": data["old_deadline"]})

        logger.info(f"Restored deadline for {data['task_id']}: {data['old_deadline']}")

        return {"task_id": data["task_id"], "deadline": data["old_deadline"]}

    async def cleanup_old_history(self) -> int:
        """
        Remove undo history older than max_history_days.

        Returns:
            Number of records cleaned up
        """
        cutoff = datetime.utcnow() - timedelta(days=self.max_history_days)

        async with self.db.session() as session:
            try:
                stmt = delete(UndoHistoryDB).where(UndoHistoryDB.timestamp < cutoff)
                result = await session.execute(stmt)

                count = result.rowcount
                logger.info(f"Cleaned up {count} old undo records")

                return count

            except Exception as e:
                logger.error(f"Failed to cleanup old undo history: {e}")
                await session.rollback()
                return 0


# Global singleton instance
_undo_manager: Optional[UndoManager] = None


def get_undo_manager() -> UndoManager:
    """Get the global undo manager instance."""
    global _undo_manager
    if _undo_manager is None:
        _undo_manager = UndoManager()
    return _undo_manager
