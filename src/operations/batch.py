"""
Enterprise batch task operations with dry-run, transactions, and progress tracking.

Q1 2026: Full-featured batch system supporting:
- Dry-run mode (preview changes)
- Transaction support (rollback on failure)
- Progress tracking in Redis
- Audit logging
- Discord notifications
- Cancellation support
"""
import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.repositories import get_task_repository, get_audit_repository
from ..cache.redis_client import cache
from ..integrations.discord import get_discord_integration

logger = logging.getLogger(__name__)


class BatchOperationResult:
    """Result of a batch operation."""

    def __init__(self):
        self.succeeded: List[str] = []
        self.failed: List[Dict] = []
        self.skipped: List[Dict] = []
        self.total = 0
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None

    def add_success(self, item_id: str):
        """Add a successful operation."""
        self.succeeded.append(item_id)

    def add_failure(self, item_id: str, error: str):
        """Add a failed operation."""
        self.failed.append({"id": item_id, "error": error})

    def add_skip(self, item_id: str, reason: str):
        """Add a skipped operation."""
        self.skipped.append({"id": item_id, "reason": reason})

    def finalize(self):
        """Finalize the result with end time."""
        self.end_time = datetime.utcnow()
        self.total = len(self.succeeded) + len(self.failed) + len(self.skipped)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
            "success_count": len(self.succeeded),
            "failure_count": len(self.failed),
            "skip_count": len(self.skipped),
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        }


class BatchOperations:
    """Enterprise batch task operations."""

    def __init__(self):
        self.max_batch_size = 100
        self.progress_cache_ttl = 3600  # 1 hour
        self.discord = get_discord_integration()

    async def execute_batch(
        self,
        session: AsyncSession,
        operation_name: str,
        items: List[str],
        operation_func: Callable,
        dry_run: bool = False,
        user_id: Optional[str] = None,
        notify_discord: bool = True
    ) -> BatchOperationResult:
        """
        Execute a batch operation with progress tracking.

        Args:
            session: Database session
            operation_name: Name of operation (for logging/audit)
            items: List of item IDs to process
            operation_func: Async function to apply to each item
            dry_run: If True, preview without executing
            user_id: User initiating the batch
            notify_discord: Send completion notification

        Returns:
            BatchOperationResult with success/failure details
        """
        result = BatchOperationResult()

        # Validate batch size
        if len(items) > self.max_batch_size:
            raise ValueError(f"Batch size {len(items)} exceeds max {self.max_batch_size}")

        # Generate batch ID for progress tracking
        batch_id = f"batch:{operation_name}:{datetime.utcnow().timestamp()}"

        try:
            for idx, item_id in enumerate(items):
                # Check for cancellation
                cancel_flag = await cache.get(f"{batch_id}:cancel")
                if cancel_flag:
                    logger.warning(f"Batch operation {batch_id} cancelled by user")
                    result.add_skip(item_id, "Batch cancelled by user")
                    continue

                # Update progress
                await self._update_progress(batch_id, idx + 1, len(items))

                try:
                    if dry_run:
                        # Preview mode - validate but don't execute
                        validation = await self._validate_operation(session, item_id, operation_func)
                        if validation["valid"]:
                            result.add_success(item_id)
                        else:
                            result.add_skip(item_id, validation["reason"])
                    else:
                        # Execute operation
                        await operation_func(session, item_id)
                        result.add_success(item_id)

                except Exception as e:
                    logger.error(f"Batch operation failed for {item_id}: {e}")
                    result.add_failure(item_id, str(e))

            result.finalize()

            # Log to audit
            if not dry_run and user_id:
                await self._audit_batch(session, operation_name, result, user_id)

            # Commit transaction (or rollback if dry-run)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()

            # Notify Discord
            if notify_discord and not dry_run and result.succeeded:
                await self._notify_completion(operation_name, result)

        except Exception as e:
            logger.error(f"Batch operation catastrophic failure: {e}")
            await session.rollback()
            raise

        finally:
            # Clear progress
            await cache.delete(batch_id)
            await cache.delete(f"{batch_id}:cancel")

        return result

    async def complete_all_for_assignee(
        self,
        session: AsyncSession,
        assignee: str,
        dry_run: bool = False,
        user_id: Optional[str] = None
    ) -> Dict:
        """Mark all pending/in-progress tasks for assignee as completed."""
        repo = get_task_repository()

        # Get all pending tasks
        tasks = await repo.get_by_assignee(assignee)
        pending_tasks = [
            t["task_id"] for t in tasks
            if t["status"] in ["pending", "in_progress"]
        ]

        if not pending_tasks:
            return {
                "success": True,
                "message": f"No tasks to complete for {assignee}",
                "result": BatchOperationResult().to_dict()
            }

        # Execute batch
        async def complete_task(sess, task_id):
            await repo.update(task_id, {"status": "completed"})

        result = await self.execute_batch(
            session=session,
            operation_name=f"complete_all_{assignee}",
            items=pending_tasks,
            operation_func=complete_task,
            dry_run=dry_run,
            user_id=user_id
        )

        return {
            "success": True,
            "assignee": assignee,
            "dry_run": dry_run,
            "result": result.to_dict()
        }

    async def reassign_all(
        self,
        session: AsyncSession,
        from_assignee: str,
        to_assignee: str,
        status_filter: Optional[List[str]] = None,
        dry_run: bool = False,
        user_id: Optional[str] = None
    ) -> Dict:
        """Reassign all tasks from one person to another."""
        repo = get_task_repository()

        tasks = await repo.get_by_assignee(from_assignee)

        if status_filter:
            tasks = [t for t in tasks if t["status"] in status_filter]

        task_ids = [t["task_id"] for t in tasks]

        if not task_ids:
            return {
                "success": True,
                "message": f"No tasks to reassign from {from_assignee}",
                "result": BatchOperationResult().to_dict()
            }

        async def reassign_task(sess, task_id):
            await repo.update(task_id, {"assignee": to_assignee})

        result = await self.execute_batch(
            session=session,
            operation_name=f"reassign_{from_assignee}_to_{to_assignee}",
            items=task_ids,
            operation_func=reassign_task,
            dry_run=dry_run,
            user_id=user_id
        )

        return {
            "success": True,
            "from_assignee": from_assignee,
            "to_assignee": to_assignee,
            "dry_run": dry_run,
            "result": result.to_dict()
        }

    async def bulk_status_change(
        self,
        session: AsyncSession,
        task_ids: List[str],
        new_status: str,
        dry_run: bool = False,
        user_id: Optional[str] = None
    ) -> Dict:
        """Change status for multiple tasks."""
        repo = get_task_repository()

        async def change_status(sess, task_id):
            await repo.update(task_id, {"status": new_status})

        result = await self.execute_batch(
            session=session,
            operation_name=f"bulk_status_to_{new_status}",
            items=task_ids,
            operation_func=change_status,
            dry_run=dry_run,
            user_id=user_id
        )

        return {
            "success": True,
            "status": new_status,
            "dry_run": dry_run,
            "result": result.to_dict()
        }

    async def bulk_delete(
        self,
        session: AsyncSession,
        task_ids: List[str],
        dry_run: bool = False,
        user_id: Optional[str] = None
    ) -> Dict:
        """Delete multiple tasks."""
        repo = get_task_repository()

        async def delete_task(sess, task_id):
            await repo.delete(task_id)

        result = await self.execute_batch(
            session=session,
            operation_name="bulk_delete",
            items=task_ids,
            operation_func=delete_task,
            dry_run=dry_run,
            user_id=user_id
        )

        return {
            "success": True,
            "dry_run": dry_run,
            "result": result.to_dict()
        }

    async def bulk_add_tags(
        self,
        session: AsyncSession,
        task_ids: List[str],
        tags: List[str],
        dry_run: bool = False,
        user_id: Optional[str] = None
    ) -> Dict:
        """Add tags to multiple tasks."""
        repo = get_task_repository()

        async def add_tags(sess, task_id):
            task = await repo.get_by_id(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            existing_tags = task.get("tags", []) or []
            new_tags = list(set(existing_tags + tags))
            await repo.update(task_id, {"tags": new_tags})

        result = await self.execute_batch(
            session=session,
            operation_name=f"bulk_add_tags_{','.join(tags)}",
            items=task_ids,
            operation_func=add_tags,
            dry_run=dry_run,
            user_id=user_id
        )

        return {
            "success": True,
            "tags": tags,
            "dry_run": dry_run,
            "result": result.to_dict()
        }

    async def get_batch_progress(self, batch_id: str) -> Optional[Dict]:
        """Get progress of a running batch operation."""
        return await cache.get(batch_id)

    async def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a running batch operation."""
        # Set cancellation flag
        await cache.set(f"{batch_id}:cancel", True, ttl=60)
        return True

    async def _update_progress(self, batch_id: str, current: int, total: int):
        """Update batch operation progress."""
        progress = {
            "current": current,
            "total": total,
            "percent": round((current / total) * 100, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        await cache.set(batch_id, progress, ttl=self.progress_cache_ttl)

    async def _validate_operation(
        self,
        session: AsyncSession,
        item_id: str,
        operation_func: Callable
    ) -> Dict:
        """Validate if operation can be performed (dry-run check)."""
        try:
            # Check if item exists
            repo = get_task_repository()
            task = await repo.get_by_id(item_id)
            if not task:
                return {"valid": False, "reason": "Task not found"}

            return {"valid": True, "reason": ""}
        except Exception as e:
            return {"valid": False, "reason": str(e)}

    async def _audit_batch(
        self,
        session: AsyncSession,
        operation_name: str,
        result: BatchOperationResult,
        user_id: str
    ):
        """Log batch operation to audit trail."""
        try:
            audit_repo = get_audit_repository()

            await audit_repo.log(
                action="execute",
                changed_by=user_id,
                entity_type="batch_operation",
                entity_id=operation_name,
                source="api",
                snapshot={
                    "operation": operation_name,
                    "succeeded": result.succeeded,
                    "failed": result.failed,
                    "skipped": result.skipped,
                    "duration": result.to_dict()["duration_seconds"]
                }
            )
            logger.info(f"Logged batch operation {operation_name} to audit trail")
        except Exception as e:
            logger.error(f"Failed to log batch operation to audit: {e}")

    async def _notify_completion(
        self,
        operation_name: str,
        result: BatchOperationResult
    ):
        """Send Discord notification about batch completion."""
        try:
            message = f"""
**Batch Operation Complete: {operation_name}**

✅ Succeeded: {len(result.succeeded)}
❌ Failed: {len(result.failed)}
⏭️ Skipped: {len(result.skipped)}

Duration: {result.to_dict()['duration_seconds']:.2f}s
            """

            # Route to TASKS channel instead of spamming general
            await self.discord.post_alert(
                title="Batch Operation Complete",
                message=message.strip(),
                alert_type="info"
            )
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")


# Global instance
batch_ops = BatchOperations()
