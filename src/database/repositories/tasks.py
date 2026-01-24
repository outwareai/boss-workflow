"""
Task repository with full relationship support.

Handles:
- Task CRUD operations
- Subtasks management
- Dependencies (blocked-by, depends-on)
- Project assignment
- Status tracking
- Sheets sync flagging
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import get_database
from ..models import TaskDB, SubtaskDB, TaskDependencyDB, ProjectDB
from ..exceptions import (
    DatabaseConstraintError,
    DatabaseOperationError,
    EntityNotFoundError,
)
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class TaskRepository:
    """Repository for task operations."""

    def __init__(self):
        self.db = get_database()

    # ==================== TASK CRUD ====================

    async def create(self, task_data: Dict[str, Any]) -> TaskDB:
        """Create a new task."""
        async with self.db.session() as session:
            try:
                task = TaskDB(
                    task_id=task_data.get("task_id") or task_data.get("id"),
                    title=task_data.get("title"),
                    description=task_data.get("description"),
                    priority=task_data.get("priority", "medium"),
                    status=task_data.get("status", "pending"),
                    task_type=task_data.get("task_type", "task"),
                    assignee=task_data.get("assignee"),
                    assignee_telegram_id=task_data.get("assignee_telegram_id"),
                    assignee_discord_id=task_data.get("assignee_discord_id"),
                    assignee_email=task_data.get("assignee_email"),
                    deadline=task_data.get("deadline"),
                    estimated_effort=task_data.get("estimated_effort") or task_data.get("effort"),
                    tags=task_data.get("tags"),
                    acceptance_criteria=task_data.get("acceptance_criteria"),
                    created_by=task_data.get("created_by"),
                    original_message=task_data.get("original_message"),
                    project_id=task_data.get("project_id"),
                    needs_sheet_sync=True,
                )
                session.add(task)
                await session.flush()

                logger.info(f"Created task {task.task_id} in database")
                return task

            except IntegrityError as e:
                logger.error(f"Constraint violation creating task: {e}")
                raise DatabaseConstraintError(
                    f"Cannot create task {task_data.get('task_id') or task_data.get('id')}: duplicate or constraint violation"
                )

            except Exception as e:
                logger.error(f"CRITICAL: Task creation failed: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to create task: {e}")

    async def get_by_id(self, task_id: str) -> Optional[TaskDB]:
        """Get task by task_id (TASK-XXXXXX-XXX format)."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .options(
                    selectinload(TaskDB.subtasks),
                    selectinload(TaskDB.dependencies_out),
                    selectinload(TaskDB.dependencies_in),
                    selectinload(TaskDB.project),
                    selectinload(TaskDB.audit_logs),  # FIX: Prevent N+1 on audit queries
                )
                .where(TaskDB.task_id == task_id)
            )
            return result.scalar_one_or_none()

    async def get_by_db_id(self, db_id: int) -> Optional[TaskDB]:
        """Get task by database primary key."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .options(selectinload(TaskDB.subtasks))
                .where(TaskDB.id == db_id)
            )
            return result.scalar_one_or_none()

    async def update(self, task_id: str, updates: Dict[str, Any]) -> TaskDB:
        """Update a task."""
        async with self.db.session() as session:
            try:
                # Mark for sheet sync
                updates["needs_sheet_sync"] = True
                updates["updated_at"] = datetime.now()

                await session.execute(
                    update(TaskDB)
                    .where(TaskDB.task_id == task_id)
                    .values(**updates)
                )

                # Fetch and return updated task
                result = await session.execute(
                    select(TaskDB).where(TaskDB.task_id == task_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    raise EntityNotFoundError(f"Task {task_id} not found for update")

                return task

            except EntityNotFoundError:
                raise

            except IntegrityError as e:
                logger.error(f"Constraint violation updating task {task_id}: {e}")
                raise DatabaseConstraintError(f"Cannot update task {task_id}: constraint violation")

            except Exception as e:
                logger.error(f"CRITICAL: Task update failed for {task_id}: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to update task {task_id}: {e}")

    async def delete(self, task_id: str) -> bool:
        """
        Delete a task.

        Q2 2026: Added audit logging for task deletion.
        """
        async with self.db.session() as session:
            try:
                # Get task info before deletion
                result = await session.execute(
                    select(TaskDB).where(TaskDB.task_id == task_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    raise EntityNotFoundError(f"Task {task_id} not found for deletion")

                await session.execute(
                    delete(TaskDB).where(TaskDB.task_id == task_id)
                )

                if task:
                    # Q2 2026: Audit log task deletion
                    from ...utils.audit_logger import log_audit_event, AuditAction, AuditLevel
                    await log_audit_event(
                        action=AuditAction.TASK_DELETE,
                        entity_type="task",
                        entity_id=task_id,
                        details={"title": task.title, "assignee": task.assignee},
                        level=AuditLevel.WARNING
                    )

                return True

            except EntityNotFoundError:
                raise

            except Exception as e:
                logger.error(f"CRITICAL: Task deletion failed for {task_id}: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to delete task {task_id}: {e}")

    async def change_status(
        self,
        task_id: str,
        new_status: str,
        changed_by: str,
        reason: Optional[str] = None
    ) -> Optional[TaskDB]:
        """Change task status with proper tracking."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                return None

            old_status = task.status
            task.status = new_status
            task.updated_at = datetime.now()
            task.needs_sheet_sync = True

            # Handle special status transitions
            if new_status == "in_progress" and not task.started_at:
                task.started_at = datetime.now()
            elif new_status == "completed":
                task.completed_at = datetime.now()
            elif new_status == "delayed":
                if task.deadline and not task.original_deadline:
                    task.original_deadline = task.deadline
                task.delayed_count += 1
                task.delay_reason = reason

            await session.flush()
            logger.info(f"Task {task_id} status changed: {old_status} -> {new_status}")
            return task

    # ==================== QUERY METHODS ====================

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[TaskDB]:
        """Get all tasks with pagination support."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .options(selectinload(TaskDB.subtasks))
                .order_by(TaskDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_recent(self, limit: int = 10) -> List[TaskDB]:
        """Get most recent tasks (alias for get_all with smaller default)."""
        return await self.get_all(limit=limit)

    async def get_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[TaskDB]:
        """
        Get tasks by status with pagination support.

        Q2 2026 Optimization: Added eager loading to prevent lazy-load N+1.
        Q3 2026: Added pagination (limit/offset) to prevent unbounded queries.
        """
        from sqlalchemy.orm import selectinload

        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .where(TaskDB.status == status)
                .options(
                    selectinload(TaskDB.subtasks),
                    selectinload(TaskDB.dependencies_in),
                    selectinload(TaskDB.dependencies_out)
                )
                .order_by(TaskDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_by_assignee(self, assignee: str, limit: int = 100, offset: int = 0) -> List[TaskDB]:
        """
        Get tasks by assignee with pagination support.

        Q2 2026 Optimization: Added eager loading to prevent lazy-load N+1.
        Q3 2026: Added pagination (limit/offset) to prevent unbounded queries.
        """
        from sqlalchemy.orm import selectinload

        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .where(TaskDB.assignee.ilike(f"%{assignee}%"))
                .options(
                    selectinload(TaskDB.subtasks),
                    selectinload(TaskDB.dependencies_in),
                    selectinload(TaskDB.dependencies_out)
                )
                .order_by(TaskDB.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_overdue(self) -> List[TaskDB]:
        """Get overdue tasks."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .where(
                    and_(
                        TaskDB.deadline < datetime.now(),
                        TaskDB.status.notin_(["completed", "cancelled"]),
                    )
                )
                .order_by(TaskDB.deadline.asc())
            )
            return list(result.scalars().all())

    async def get_due_soon(self, hours: int = 24) -> List[TaskDB]:
        """Get tasks due within X hours."""
        deadline_threshold = datetime.now() + timedelta(hours=hours)
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .where(
                    and_(
                        TaskDB.deadline <= deadline_threshold,
                        TaskDB.deadline > datetime.now(),
                        TaskDB.status.notin_(["completed", "cancelled"]),
                    )
                )
                .order_by(TaskDB.deadline.asc())
            )
            return list(result.scalars().all())

    async def get_by_project(self, project_id: int) -> List[TaskDB]:
        """Get tasks in a project."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .where(TaskDB.project_id == project_id)
                .order_by(TaskDB.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_pending_sync(self, limit: int = 50) -> List[TaskDB]:
        """Get tasks that need to be synced to Sheets."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB)
                .where(TaskDB.needs_sheet_sync == True)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def mark_synced(self, task_ids: List[str]):
        """Mark tasks as synced to Sheets."""
        async with self.db.session() as session:
            await session.execute(
                update(TaskDB)
                .where(TaskDB.task_id.in_(task_ids))
                .values(needs_sheet_sync=False, last_synced_to_sheets=datetime.now())
            )

    async def get_daily_stats(self) -> Dict[str, int]:
        """Get task statistics for today."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        async with self.db.session() as session:
            # Total created today
            created_result = await session.execute(
                select(func.count(TaskDB.id))
                .where(TaskDB.created_at >= today_start)
            )
            created_count = created_result.scalar() or 0

            # Completed today
            completed_result = await session.execute(
                select(func.count(TaskDB.id))
                .where(
                    and_(
                        TaskDB.completed_at >= today_start,
                        TaskDB.status == "completed"
                    )
                )
            )
            completed_count = completed_result.scalar() or 0

            # Currently pending
            pending_result = await session.execute(
                select(func.count(TaskDB.id))
                .where(TaskDB.status.in_(["pending", "in_progress"]))
            )
            pending_count = pending_result.scalar() or 0

            # Overdue
            overdue_result = await session.execute(
                select(func.count(TaskDB.id))
                .where(
                    and_(
                        TaskDB.deadline < datetime.now(),
                        TaskDB.status.notin_(["completed", "cancelled"])
                    )
                )
            )
            overdue_count = overdue_result.scalar() or 0

            return {
                "created_today": created_count,
                "completed_today": completed_count,
                "pending": pending_count,
                "overdue": overdue_count,
            }

    # ==================== SUBTASKS ====================

    async def add_subtask(
        self,
        task_id: str,
        title: str,
        assignee: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[SubtaskDB]:
        """Add a subtask to a task."""
        async with self.db.session() as session:
            # Get parent task
            result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                return None

            # Get next order number
            order_result = await session.execute(
                select(func.max(SubtaskDB.order)).where(SubtaskDB.task_id == task.id)
            )
            max_order = order_result.scalar() or 0
            next_order = max_order + 1

            subtask = SubtaskDB(
                task_id=task.id,
                title=title,
                description=description,
                order=next_order,
            )
            session.add(subtask)
            await session.flush()

            # Mark parent for sync
            task.needs_sheet_sync = True

            logger.info(f"Added subtask to {task_id}: {title}")
            return subtask

    async def complete_subtask_by_order(
        self,
        task_id: str,
        order: int,
        completed_by: str
    ) -> bool:
        """Mark a subtask as completed by its order number."""
        async with self.db.session() as session:
            # Get parent task first
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            if not task:
                return False

            # Find subtask by order
            subtask_result = await session.execute(
                select(SubtaskDB).where(
                    and_(
                        SubtaskDB.task_id == task.id,
                        SubtaskDB.order == order
                    )
                )
            )
            subtask = subtask_result.scalar_one_or_none()

            if not subtask:
                return False

            subtask.completed = True
            subtask.completed_at = datetime.now()
            subtask.completed_by = completed_by

            # Update parent task progress
            all_subtasks = await session.execute(
                select(SubtaskDB).where(SubtaskDB.task_id == task.id)
            )
            subtasks = list(all_subtasks.scalars().all())
            completed = sum(1 for s in subtasks if s.completed)
            progress = int((completed / len(subtasks)) * 100) if subtasks else 0

            task.progress = progress
            task.needs_sheet_sync = True

            await session.flush()
            logger.info(f"Completed subtask {order} of {task_id}")
            return True

    async def complete_subtask(
        self,
        subtask_id: int,
        completed_by: str
    ) -> Optional[SubtaskDB]:
        """Mark a subtask as completed."""
        async with self.db.session() as session:
            result = await session.execute(
                select(SubtaskDB)
                .options(selectinload(SubtaskDB.task))
                .where(SubtaskDB.id == subtask_id)
            )
            subtask = result.scalar_one_or_none()

            if not subtask:
                return None

            subtask.completed = True
            subtask.completed_at = datetime.now()
            subtask.completed_by = completed_by

            # Update parent task progress
            all_subtasks = await session.execute(
                select(SubtaskDB).where(SubtaskDB.task_id == subtask.task_id)
            )
            subtasks = list(all_subtasks.scalars().all())
            completed = sum(1 for s in subtasks if s.completed)
            progress = int((completed / len(subtasks)) * 100) if subtasks else 0

            await session.execute(
                update(TaskDB)
                .where(TaskDB.id == subtask.task_id)
                .values(progress=progress, needs_sheet_sync=True)
            )

            return subtask

    async def get_subtasks(self, task_id: str) -> List[SubtaskDB]:
        """Get all subtasks for a task."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                return []

            subtasks_result = await session.execute(
                select(SubtaskDB)
                .where(SubtaskDB.task_id == task.id)
                .order_by(SubtaskDB.order)
            )
            return list(subtasks_result.scalars().all())

    # ==================== DEPENDENCIES ====================

    async def add_dependency(
        self,
        task_id: str,
        depends_on_task_id: str,
        dependency_type: str = "depends_on",
        created_by: Optional[str] = None
    ) -> Optional[TaskDependencyDB]:
        """Add a dependency between tasks."""
        async with self.db.session() as session:
            # Get both tasks
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            depends_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == depends_on_task_id)
            )
            depends_on = depends_result.scalar_one_or_none()

            if not task or not depends_on:
                logger.warning(f"Could not find tasks for dependency: {task_id} -> {depends_on_task_id}")
                return None

            # Check for circular dependency
            if await self._would_create_cycle(session, task.id, depends_on.id):
                logger.warning(f"Circular dependency detected: {task_id} -> {depends_on_task_id}")
                return None

            dependency = TaskDependencyDB(
                task_id=task.id,
                depends_on_id=depends_on.id,
                dependency_type=dependency_type,
                created_by=created_by,
            )
            session.add(dependency)

            # If blocked_by, update task status
            if dependency_type in ["blocked_by", "depends_on"]:
                if depends_on.status not in ["completed", "cancelled"]:
                    task.status = "blocked"
                    task.needs_sheet_sync = True

            await session.flush()
            logger.info(f"Added dependency: {task_id} {dependency_type} {depends_on_task_id}")
            return dependency

    async def remove_dependency(self, task_id: str, depends_on_task_id: str) -> bool:
        """Remove a dependency between tasks."""
        async with self.db.session() as session:
            # Get both tasks
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            depends_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == depends_on_task_id)
            )
            depends_on = depends_result.scalar_one_or_none()

            if not task or not depends_on:
                return False

            await session.execute(
                delete(TaskDependencyDB)
                .where(
                    and_(
                        TaskDependencyDB.task_id == task.id,
                        TaskDependencyDB.depends_on_id == depends_on.id
                    )
                )
            )

            # Check if task can be unblocked
            remaining = await session.execute(
                select(func.count(TaskDependencyDB.id))
                .where(TaskDependencyDB.task_id == task.id)
            )
            if remaining.scalar() == 0 and task.status == "blocked":
                task.status = "pending"
                task.needs_sheet_sync = True

            return True

    async def get_blocking_tasks(self, task_id: str) -> List[TaskDB]:
        """Get tasks that are blocking this task."""
        async with self.db.session() as session:
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            if not task:
                return []

            result = await session.execute(
                select(TaskDB)
                .join(TaskDependencyDB, TaskDependencyDB.depends_on_id == TaskDB.id)
                .where(TaskDependencyDB.task_id == task.id)
            )
            return list(result.scalars().all())

    async def get_blocked_tasks(self, task_id: str) -> List[TaskDB]:
        """Get tasks that this task is blocking."""
        async with self.db.session() as session:
            task_result = await session.execute(
                select(TaskDB).where(TaskDB.task_id == task_id)
            )
            task = task_result.scalar_one_or_none()

            if not task:
                return []

            result = await session.execute(
                select(TaskDB)
                .join(TaskDependencyDB, TaskDependencyDB.task_id == TaskDB.id)
                .where(TaskDependencyDB.depends_on_id == task.id)
            )
            return list(result.scalars().all())

    async def _would_create_cycle(
        self,
        session: AsyncSession,
        task_id: int,
        depends_on_id: int
    ) -> bool:
        """Check if adding a dependency would create a cycle."""
        visited = set()
        to_visit = [depends_on_id]

        while to_visit:
            current = to_visit.pop()
            if current == task_id:
                return True  # Cycle detected

            if current in visited:
                continue

            visited.add(current)

            # Get dependencies of current
            result = await session.execute(
                select(TaskDependencyDB.depends_on_id)
                .where(TaskDependencyDB.task_id == current)
            )
            for row in result:
                to_visit.append(row[0])

        return False

    # ==================== PROJECTS ====================

    async def assign_to_project(self, task_id: str, project_id: int) -> Optional[TaskDB]:
        """Assign a task to a project."""
        return await self.update(task_id, {"project_id": project_id})

    async def remove_from_project(self, task_id: str) -> Optional[TaskDB]:
        """Remove a task from its project."""
        return await self.update(task_id, {"project_id": None})


# Singleton
_task_repository: Optional[TaskRepository] = None


def get_task_repository() -> TaskRepository:
    """Get the task repository singleton."""
    global _task_repository
    if _task_repository is None:
        _task_repository = TaskRepository()
    return _task_repository
