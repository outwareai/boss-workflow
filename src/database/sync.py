"""
Sheets Sync Layer - Keeps Google Sheets in sync with PostgreSQL.

Strategy:
- PostgreSQL is the source of truth
- Sheets is the boss dashboard (read-friendly)
- Tasks are written to both on creation
- Changes are synced periodically or on-demand
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .connection import get_database
from .repositories.tasks import get_task_repository
from .repositories.audit import get_audit_repository
from .models import TaskDB

logger = logging.getLogger(__name__)


class SheetsSync:
    """Synchronizes PostgreSQL tasks with Google Sheets."""

    def __init__(self):
        self.task_repo = get_task_repository()
        self.audit_repo = get_audit_repository()
        self._sheets = None

    @property
    def sheets(self):
        """Lazy load sheets integration."""
        if self._sheets is None:
            from ..integrations.sheets import get_sheets_integration
            self._sheets = get_sheets_integration()
        return self._sheets

    async def sync_task_to_sheets(self, task: TaskDB) -> bool:
        """Sync a single task to Google Sheets."""
        try:
            task_dict = self._task_to_dict(task)

            if task.sheets_row_id:
                # Update existing row
                await self.sheets.update_task(task.task_id, task_dict)
            else:
                # Add new row
                row_id = await self.sheets.add_task(task_dict)
                if row_id:
                    # Update task with row ID
                    await self.task_repo.update(
                        task.task_id,
                        {
                            "sheets_row_id": row_id,
                            "needs_sheet_sync": False,
                            "last_synced_to_sheets": datetime.now(),
                        }
                    )

            # Log sync
            await self.audit_repo.log_sheets_sync(task.task_id, task.sheets_row_id)

            logger.debug(f"Synced task {task.task_id} to Sheets")
            return True

        except Exception as e:
            logger.error(f"Error syncing task {task.task_id} to Sheets: {e}")
            return False

    async def sync_pending_tasks(self, limit: int = 50) -> Dict[str, Any]:
        """Sync all tasks that need syncing."""
        tasks = await self.task_repo.get_pending_sync(limit=limit)

        if not tasks:
            return {"synced": 0, "failed": 0}

        synced = 0
        failed = 0

        for task in tasks:
            success = await self.sync_task_to_sheets(task)
            if success:
                synced += 1
            else:
                failed += 1

        # Mark synced tasks
        if synced > 0:
            synced_ids = [t.task_id for t in tasks[:synced]]
            await self.task_repo.mark_synced(synced_ids)

        logger.info(f"Sheets sync complete: {synced} synced, {failed} failed")
        return {"synced": synced, "failed": failed}

    async def full_sync(self) -> Dict[str, Any]:
        """Perform a full sync of all tasks."""
        tasks = await self.task_repo.get_all(limit=500)

        synced = 0
        failed = 0

        for task in tasks:
            # Force sync flag
            task.needs_sheet_sync = True
            success = await self.sync_task_to_sheets(task)
            if success:
                synced += 1
            else:
                failed += 1

        logger.info(f"Full sync complete: {synced}/{len(tasks)} tasks synced")
        return {"total": len(tasks), "synced": synced, "failed": failed}

    async def sync_from_sheets(self) -> Dict[str, Any]:
        """Import tasks from Sheets to PostgreSQL (for migration)."""
        try:
            sheets_tasks = await self.sheets.get_all_tasks()
            imported = 0
            skipped = 0

            for sheet_task in sheets_tasks:
                task_id = sheet_task.get("Task ID") or sheet_task.get("id")
                if not task_id:
                    skipped += 1
                    continue

                # Check if exists
                existing = await self.task_repo.get_by_id(task_id)
                if existing:
                    skipped += 1
                    continue

                # Import to PostgreSQL
                task_data = self._sheet_row_to_task(sheet_task)
                await self.task_repo.create(task_data)
                imported += 1

            logger.info(f"Imported {imported} tasks from Sheets, skipped {skipped}")
            return {"imported": imported, "skipped": skipped}

        except Exception as e:
            logger.error(f"Error importing from Sheets: {e}")
            return {"error": str(e)}

    def _task_to_dict(self, task: TaskDB) -> Dict[str, Any]:
        """Convert TaskDB to dict for Sheets."""
        return {
            "id": task.task_id,
            "title": task.title,
            "description": task.description or "",
            "assignee": task.assignee or "",
            "priority": task.priority,
            "status": task.status,
            "task_type": task.task_type,
            "deadline": task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "",
            "created_at": task.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M"),
            "effort": task.estimated_effort or "",
            "progress": f"{task.progress}%",
            "tags": task.tags or "",
            "created_by": task.created_by or "",
        }

    def _sheet_row_to_task(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Sheets row to task data."""
        return {
            "task_id": row.get("Task ID") or row.get("id"),
            "title": row.get("Title") or row.get("title"),
            "description": row.get("Description") or row.get("description"),
            "assignee": row.get("Assignee") or row.get("assignee"),
            "priority": (row.get("Priority") or row.get("priority") or "medium").lower(),
            "status": (row.get("Status") or row.get("status") or "pending").lower().replace(" ", "_"),
            "task_type": row.get("Type") or row.get("task_type") or "task",
            "estimated_effort": row.get("Effort") or row.get("estimated_effort"),
            "tags": row.get("Tags") or row.get("tags"),
            "created_by": row.get("Created By") or row.get("created_by"),
        }


# Singleton
_sheets_sync: Optional[SheetsSync] = None


def get_sheets_sync() -> SheetsSync:
    """Get the sheets sync singleton."""
    global _sheets_sync
    if _sheets_sync is None:
        _sheets_sync = SheetsSync()
    return _sheets_sync


async def run_sync_job():
    """Run the sheets sync as a scheduled job."""
    sync = get_sheets_sync()
    return await sync.sync_pending_tasks()
