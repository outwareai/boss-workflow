"""
Project repository for task grouping.

Projects allow grouping related tasks together for:
- Better organization
- Project-level reporting
- Milestone tracking
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload

from ..connection import get_database
from ..models import ProjectDB, TaskDB
from ..exceptions import DatabaseConstraintError, DatabaseOperationError, EntityNotFoundError
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class ProjectRepository:
    """Repository for project operations."""

    def __init__(self):
        self.db = get_database()

    async def create(
        self,
        name: str,
        description: Optional[str] = None,
        color: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Optional[ProjectDB]:
        """Create a new project."""
        async with self.db.session() as session:
            try:
                project = ProjectDB(
                    name=name,
                    description=description,
                    color=color,
                    status="active",
                    created_by=created_by,
                )
                session.add(project)
                await session.flush()

                logger.info(f"Created project: {name}")
                return project

            except IntegrityError as e:
                logger.error(f"Constraint violation creating project {name}: {e}")
                raise DatabaseConstraintError(f"Cannot create project {name}: duplicate or constraint violation")

            except Exception as e:
                logger.error(f"CRITICAL: Project creation failed for {name}: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to create project {name}: {e}")

    async def get_by_id(self, project_id: int) -> Optional[ProjectDB]:
        """Get project by ID with tasks."""
        async with self.db.session() as session:
            result = await session.execute(
                select(ProjectDB)
                .options(selectinload(ProjectDB.tasks))
                .where(ProjectDB.id == project_id)
            )
            return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[ProjectDB]:
        """Get project by name (case-insensitive)."""
        async with self.db.session() as session:
            result = await session.execute(
                select(ProjectDB)
                .where(ProjectDB.name.ilike(f"%{name}%"))
            )
            return result.scalar_one_or_none()

    async def update(
        self,
        project_id: int,
        updates: Dict[str, Any]
    ) -> Optional[ProjectDB]:
        """Update a project."""
        async with self.db.session() as session:
            updates["updated_at"] = datetime.now()

            await session.execute(
                update(ProjectDB)
                .where(ProjectDB.id == project_id)
                .values(**updates)
            )

            result = await session.execute(
                select(ProjectDB).where(ProjectDB.id == project_id)
            )
            return result.scalar_one_or_none()

    async def delete(self, project_id: int) -> bool:
        """Delete a project (tasks are kept but unassigned)."""
        async with self.db.session() as session:
            # Unassign tasks from project
            await session.execute(
                update(TaskDB)
                .where(TaskDB.project_id == project_id)
                .values(project_id=None, needs_sheet_sync=True)
            )

            # Delete project
            await session.execute(
                delete(ProjectDB).where(ProjectDB.id == project_id)
            )
            return True

    async def archive(self, project_id: int) -> Optional[ProjectDB]:
        """Archive a project."""
        return await self.update(project_id, {"status": "archived"})

    async def complete(self, project_id: int) -> Optional[ProjectDB]:
        """Mark project as completed."""
        return await self.update(project_id, {"status": "completed"})

    async def get_all(
        self,
        status: Optional[str] = None,
        include_tasks: bool = False
    ) -> List[ProjectDB]:
        """Get all projects."""
        async with self.db.session() as session:
            query = select(ProjectDB)

            if include_tasks:
                query = query.options(selectinload(ProjectDB.tasks))

            if status:
                query = query.where(ProjectDB.status == status)

            query = query.order_by(ProjectDB.created_at.desc())

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_active(self) -> List[ProjectDB]:
        """Get all active projects."""
        return await self.get_all(status="active")

    async def get_project_stats(self, project_id: int) -> Dict[str, Any]:
        """Get statistics for a project."""
        async with self.db.session() as session:
            # Get project
            project = await self.get_by_id(project_id)
            if not project:
                return {}

            # Count tasks by status
            status_counts = await session.execute(
                select(TaskDB.status, func.count(TaskDB.id))
                .where(TaskDB.project_id == project_id)
                .group_by(TaskDB.status)
            )
            statuses = {row[0]: row[1] for row in status_counts}

            # Total tasks
            total = sum(statuses.values())

            # Completed tasks
            completed = statuses.get("completed", 0)

            # Calculate progress
            progress = (completed / total * 100) if total > 0 else 0

            # Overdue tasks
            overdue_count = await session.execute(
                select(func.count(TaskDB.id))
                .where(
                    TaskDB.project_id == project_id,
                    TaskDB.deadline < datetime.now(),
                    TaskDB.status.notin_(["completed", "cancelled"]),
                )
            )
            overdue = overdue_count.scalar() or 0

            return {
                "project_id": project_id,
                "name": project.name,
                "status": project.status,
                "total_tasks": total,
                "completed_tasks": completed,
                "progress_percent": round(progress, 1),
                "overdue_tasks": overdue,
                "tasks_by_status": statuses,
            }

    async def get_all_stats(self) -> List[Dict[str, Any]]:
        """
        Get stats for all active projects.
        
        Q2 2026 Optimization: Fixed N+1 query pattern with bulk aggregation.
        Before: 1 + 3N queries (get_active + 3 queries per project)
        After: 3 queries total (95% reduction for 15 projects: 46 → 3)
        """
        from sqlalchemy import select, func, case
        
        async with self.db.session() as session:
            # Query 1: Get all active projects
            projects = await self.get_active()
            if not projects:
                return []
            
            project_ids = [p.id for p in projects]
            
            # Query 2: Get task counts by status for all projects (GROUP BY project_id, status)
            status_result = await session.execute(
                select(TaskDB.project_id, TaskDB.status, func.count(TaskDB.id))
                .where(TaskDB.project_id.in_(project_ids))
                .group_by(TaskDB.project_id, TaskDB.status)
            )
            
            # Organize status counts by project
            status_by_project: Dict[int, Dict[str, int]] = {}
            for project_id, status, count in status_result:
                if project_id not in status_by_project:
                    status_by_project[project_id] = {}
                status_by_project[project_id][status] = count
            
            # Query 3: Get overdue counts for all projects (GROUP BY project_id)
            overdue_result = await session.execute(
                select(TaskDB.project_id, func.count(TaskDB.id))
                .where(
                    TaskDB.project_id.in_(project_ids),
                    TaskDB.deadline < datetime.now(),
                    TaskDB.status.notin_(["completed", "cancelled"]),
                )
                .group_by(TaskDB.project_id)
            )
            
            overdue_by_project = {row[0]: row[1] for row in overdue_result}
            
            # Build stats for each project (no queries, all data already fetched)
            stats = []
            for project in projects:
                statuses = status_by_project.get(project.id, {})
                total = sum(statuses.values())
                completed = statuses.get("completed", 0)
                progress = (completed / total * 100) if total > 0 else 0
                overdue = overdue_by_project.get(project.id, 0)
                
                stats.append({
                    "project_id": project.id,
                    "name": project.name,
                    "status": project.status,
                    "total_tasks": total,
                    "completed_tasks": completed,
                    "progress_percent": round(progress, 1),
                    "overdue_tasks": overdue,
                    "tasks_by_status": statuses,
                })
            
            # Sort by progress
            stats.sort(key=lambda x: x["progress_percent"], reverse=True)
            return stats

    async def find_or_create(
        self,
        name: str,
        created_by: Optional[str] = None
    ) -> ProjectDB:
        """Find a project by name or create if doesn't exist."""
        project = await self.get_by_name(name)
        if project:
            return project

        return await self.create(name=name, created_by=created_by)


# Singleton
_project_repository: Optional[ProjectRepository] = None


def get_project_repository() -> ProjectRepository:
    """Get the project repository singleton."""
    global _project_repository
    if _project_repository is None:
        _project_repository = ProjectRepository()
    return _project_repository
