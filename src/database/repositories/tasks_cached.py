"""
Cached wrapper for TaskRepository.

Q3 2026: Redis caching layer to reduce database load.

This module provides a cached version of TaskRepository methods.
Read methods are cached, write methods invalidate relevant caches.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from .tasks import TaskRepository
from ..models import TaskDB
from ...cache.decorators import cached
from ...cache.redis_client import cache

logger = logging.getLogger(__name__)


class CachedTaskRepository(TaskRepository):
    """
    Task repository with Redis caching.

    Inherits from TaskRepository and adds caching decorators to read methods.
    Write methods automatically invalidate relevant caches.
    """

    # ==================== CACHED READ METHODS ====================

    @cached(ttl=300, key_prefix="task")
    async def get_by_id(self, task_id: str) -> Optional[TaskDB]:
        """
        Get task by ID with 5-minute cache.

        Cache key pattern: task:{task_id}
        """
        return await super().get_by_id(task_id)

    @cached(ttl=60, key_prefix="tasks:status")
    async def get_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[TaskDB]:
        """
        Get tasks by status with 1-minute cache.

        Cache key pattern: tasks:status:{status}:{limit}:{offset}
        """
        return await super().get_by_status(status, limit, offset)

    @cached(ttl=60, key_prefix="tasks:assignee")
    async def get_by_assignee(self, assignee: str, limit: int = 100, offset: int = 0) -> List[TaskDB]:
        """
        Get tasks by assignee with 1-minute cache.

        Cache key pattern: tasks:assignee:{assignee}:{limit}:{offset}
        """
        return await super().get_by_assignee(assignee, limit, offset)

    @cached(ttl=120, key_prefix="tasks:overdue")
    async def get_overdue(self) -> List[TaskDB]:
        """
        Get overdue tasks with 2-minute cache.

        Cache key pattern: tasks:overdue
        """
        return await super().get_overdue()

    @cached(ttl=120, key_prefix="tasks:due_soon")
    async def get_due_soon(self, hours: int = 24) -> List[TaskDB]:
        """
        Get tasks due soon with 2-minute cache.

        Cache key pattern: tasks:due_soon:{hours}
        """
        return await super().get_due_soon(hours)

    @cached(ttl=180, key_prefix="tasks:project")
    async def get_by_project(self, project_id: int) -> List[TaskDB]:
        """
        Get tasks by project with 3-minute cache.

        Cache key pattern: tasks:project:{project_id}
        """
        return await super().get_by_project(project_id)

    @cached(ttl=300, key_prefix="tasks:daily_stats")
    async def get_daily_stats(self) -> Dict[str, int]:
        """
        Get daily statistics with 5-minute cache.

        Cache key pattern: tasks:daily_stats
        """
        return await super().get_daily_stats()

    @cached(ttl=180, key_prefix="task:subtasks")
    async def get_subtasks(self, task_id: str) -> List:
        """
        Get subtasks with 3-minute cache.

        Cache key pattern: task:subtasks:{task_id}
        """
        return await super().get_subtasks(task_id)

    @cached(ttl=180, key_prefix="task:blocking")
    async def get_blocking_tasks(self, task_id: str) -> List[TaskDB]:
        """
        Get blocking tasks with 3-minute cache.

        Cache key pattern: task:blocking:{task_id}
        """
        return await super().get_blocking_tasks(task_id)

    @cached(ttl=180, key_prefix="task:blocked")
    async def get_blocked_tasks(self, task_id: str) -> List[TaskDB]:
        """
        Get blocked tasks with 3-minute cache.

        Cache key pattern: task:blocked:{task_id}
        """
        return await super().get_blocked_tasks(task_id)

    # ==================== WRITE METHODS WITH CACHE INVALIDATION ====================

    async def create(self, task_data: Dict[str, Any]) -> TaskDB:
        """Create task and invalidate list caches."""
        task = await super().create(task_data)

        # Invalidate list caches
        await self._invalidate_list_caches()

        return task

    async def update(self, task_id: str, updates: Dict[str, Any]) -> TaskDB:
        """Update task and invalidate relevant caches."""
        task = await super().update(task_id, updates)

        # Invalidate specific task cache
        await cache.delete(f"task:{task_id}")

        # Invalidate list caches
        await self._invalidate_list_caches()

        # Invalidate relationship caches
        await cache.delete(f"task:subtasks:{task_id}")
        await cache.delete(f"task:blocking:{task_id}")
        await cache.delete(f"task:blocked:{task_id}")

        logger.debug(f"Invalidated caches for task {task_id}")

        return task

    async def delete(self, task_id: str) -> bool:
        """Delete task and invalidate caches."""
        result = await super().delete(task_id)

        # Invalidate specific task cache
        await cache.delete(f"task:{task_id}")

        # Invalidate list caches
        await self._invalidate_list_caches()

        # Invalidate relationship caches
        await cache.delete(f"task:subtasks:{task_id}")
        await cache.delete(f"task:blocking:{task_id}")
        await cache.delete(f"task:blocked:{task_id}")

        return result

    async def change_status(self, task_id: str, new_status: str, notes: Optional[str] = None) -> TaskDB:
        """Change task status and invalidate caches."""
        task = await super().change_status(task_id, new_status, notes)

        # Invalidate specific task cache
        await cache.delete(f"task:{task_id}")

        # Invalidate status-based caches
        await cache.invalidate_pattern("tasks:status:*")
        await cache.invalidate_pattern("tasks:overdue*")
        await cache.invalidate_pattern("tasks:due_soon:*")
        await cache.invalidate_pattern("tasks:daily_stats*")

        return task

    async def add_subtask(
        self,
        task_id: str,
        title: str,
        description: Optional[str] = None,
        order: Optional[int] = None
    ):
        """Add subtask and invalidate caches."""
        result = await super().add_subtask(task_id, title, description, order)

        # Invalidate subtasks cache
        await cache.delete(f"task:subtasks:{task_id}")
        await cache.delete(f"task:{task_id}")

        return result

    async def complete_subtask(self, task_id: str, subtask_id: int):
        """Complete subtask and invalidate caches."""
        result = await super().complete_subtask(task_id, subtask_id)

        # Invalidate subtasks cache
        await cache.delete(f"task:subtasks:{task_id}")
        await cache.delete(f"task:{task_id}")

        return result

    async def add_dependency(
        self,
        task_id: str,
        depends_on_task_id: str,
        dependency_type: str = "blocked_by"
    ):
        """Add dependency and invalidate caches."""
        result = await super().add_dependency(task_id, depends_on_task_id, dependency_type)

        # Invalidate dependency caches
        await cache.delete(f"task:blocking:{task_id}")
        await cache.delete(f"task:blocked:{task_id}")
        await cache.delete(f"task:blocking:{depends_on_task_id}")
        await cache.delete(f"task:blocked:{depends_on_task_id}")
        await cache.delete(f"task:{task_id}")
        await cache.delete(f"task:{depends_on_task_id}")

        return result

    async def remove_dependency(self, task_id: str, depends_on_task_id: str) -> bool:
        """Remove dependency and invalidate caches."""
        result = await super().remove_dependency(task_id, depends_on_task_id)

        # Invalidate dependency caches
        await cache.delete(f"task:blocking:{task_id}")
        await cache.delete(f"task:blocked:{task_id}")
        await cache.delete(f"task:blocking:{depends_on_task_id}")
        await cache.delete(f"task:blocked:{depends_on_task_id}")
        await cache.delete(f"task:{task_id}")
        await cache.delete(f"task:{depends_on_task_id}")

        return result

    async def assign_to_project(self, task_id: str, project_id: int) -> Optional[TaskDB]:
        """Assign to project and invalidate caches."""
        result = await super().assign_to_project(task_id, project_id)

        # Invalidate project caches
        await cache.invalidate_pattern(f"tasks:project:*")
        await cache.delete(f"task:{task_id}")

        return result

    async def remove_from_project(self, task_id: str) -> Optional[TaskDB]:
        """Remove from project and invalidate caches."""
        result = await super().remove_from_project(task_id)

        # Invalidate project caches
        await cache.invalidate_pattern(f"tasks:project:*")
        await cache.delete(f"task:{task_id}")

        return result

    # ==================== HELPER METHODS ====================

    async def _invalidate_list_caches(self):
        """Invalidate all list-based caches."""
        patterns = [
            "tasks:status:*",
            "tasks:assignee:*",
            "tasks:overdue*",
            "tasks:due_soon:*",
            "tasks:project:*",
            "tasks:daily_stats*",
        ]

        for pattern in patterns:
            await cache.invalidate_pattern(pattern)


# Factory function to get cached repository
def get_cached_task_repository() -> CachedTaskRepository:
    """Get cached task repository instance."""
    return CachedTaskRepository()
