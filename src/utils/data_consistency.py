"""
Data consistency checker.

Detects orphaned records across Sheets, DB, and Discord.
Identifies:
- Tasks in DB but not in Sheets
- Tasks in Sheets but not in DB
- Discord threads with no matching task
- Active tasks missing Discord threads
- Status mismatches between DB and Sheets

Q3 2026: Production hardening with automated data consistency checks.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime

from ..database.repositories import get_task_repository
from ..database.repositories.staff_context import get_staff_context_repository
from ..integrations.sheets import get_sheets_integration

logger = logging.getLogger(__name__)


class DataConsistencyChecker:
    """Check data consistency across systems."""

    def __init__(self):
        self.task_repo = get_task_repository()
        self.staff_repo = get_staff_context_repository()
        self.sheets = get_sheets_integration()

    async def check_all(self) -> Dict[str, List]:
        """
        Run all consistency checks.

        Returns dict of issues found:
        {
            "orphaned_db_tasks": ["TASK-001", ...],
            "orphaned_sheet_tasks": ["TASK-002", ...],
            "orphaned_discord_threads": ["TASK-003", ...],
            "missing_discord_threads": ["TASK-004", ...],
            "status_mismatches": [{"task_id": "TASK-005", "db_status": "...", "sheet_status": "..."}]
        }
        """
        logger.info("Starting data consistency check...")

        issues = {
            "orphaned_db_tasks": [],
            "orphaned_sheet_tasks": [],
            "orphaned_discord_threads": [],
            "missing_discord_threads": [],
            "status_mismatches": []
        }

        try:
            # Get all data
            db_tasks = await self._get_db_tasks()
            sheet_tasks = await self._get_sheet_tasks()
            discord_threads = await self._get_discord_threads()

            logger.info(f"Fetched {len(db_tasks)} DB tasks, {len(sheet_tasks)} Sheet tasks, {len(discord_threads)} Discord threads")

            # Check orphans
            issues["orphaned_db_tasks"] = await self._find_orphaned_db_tasks(db_tasks, sheet_tasks)
            issues["orphaned_sheet_tasks"] = await self._find_orphaned_sheet_tasks(sheet_tasks, db_tasks)
            issues["orphaned_discord_threads"] = await self._find_orphaned_discord_threads(discord_threads, db_tasks)
            issues["missing_discord_threads"] = await self._find_missing_discord_threads(db_tasks, discord_threads)
            issues["status_mismatches"] = await self._find_status_mismatches(db_tasks, sheet_tasks)

            total_issues = sum(len(v) if isinstance(v, list) else 0 for v in issues.values())
            logger.info(f"Consistency check complete. Found {total_issues} total issues.")

            return issues

        except Exception as e:
            logger.error(f"Error during consistency check: {e}")
            return issues

    async def _get_db_tasks(self) -> List[dict]:
        """Get all tasks from database."""
        try:
            tasks = await self.task_repo.get_all()
            return [
                {
                    "task_id": task.task_id,
                    "status": task.status,
                    "title": task.title,
                    "assignee": task.assignee
                }
                for task in tasks
            ]
        except Exception as e:
            logger.error(f"Error fetching DB tasks: {e}")
            return []

    async def _get_sheet_tasks(self) -> List[dict]:
        """Get all tasks from Sheets."""
        try:
            # Read Daily Tasks sheet
            tasks = await self.sheets.get_all_tasks()
            return [
                {
                    "task_id": task.get("id", ""),
                    "status": task.get("status", ""),
                    "title": task.get("title", ""),
                    "assignee": task.get("assignee", "")
                }
                for task in tasks
                if task.get("id")  # Only include rows with task IDs
            ]
        except Exception as e:
            logger.error(f"Error fetching Sheet tasks: {e}")
            return []

    async def _get_discord_threads(self) -> List[dict]:
        """Get all Discord thread mappings from database."""
        try:
            from sqlalchemy import select
            from ..database.models import DiscordThreadTaskLinkDB
            from ..database import get_database

            db = get_database()
            async with db.session() as session:
                result = await session.execute(select(DiscordThreadTaskLinkDB))
                links = result.scalars().all()

                return [
                    {
                        "task_id": link.task_id,
                        "thread_id": link.thread_id,
                        "channel_id": link.channel_id,
                        "created_at": link.created_at.isoformat() if link.created_at else None
                    }
                    for link in links
                ]
        except Exception as e:
            logger.error(f"Error fetching Discord threads: {e}")
            return []

    async def _find_orphaned_db_tasks(self, db_tasks: List[dict], sheet_tasks: List[dict]) -> List[str]:
        """Find tasks in DB but not in Sheets."""
        sheet_ids = {t["task_id"] for t in sheet_tasks if t["task_id"]}
        orphaned = [t["task_id"] for t in db_tasks if t["task_id"] not in sheet_ids]

        if orphaned:
            logger.warning(f"Found {len(orphaned)} orphaned DB tasks: {orphaned[:5]}...")

        return orphaned

    async def _find_orphaned_sheet_tasks(self, sheet_tasks: List[dict], db_tasks: List[dict]) -> List[str]:
        """Find tasks in Sheets but not in DB."""
        db_ids = {t["task_id"] for t in db_tasks}
        orphaned = [t["task_id"] for t in sheet_tasks if t["task_id"] and t["task_id"] not in db_ids]

        if orphaned:
            logger.warning(f"Found {len(orphaned)} orphaned Sheet tasks: {orphaned[:5]}...")

        return orphaned

    async def _find_orphaned_discord_threads(self, discord_threads: List[dict], db_tasks: List[dict]) -> List[str]:
        """Find Discord threads with no matching task."""
        db_ids = {t["task_id"] for t in db_tasks}
        orphaned = [t["task_id"] for t in discord_threads if t["task_id"] not in db_ids]

        if orphaned:
            logger.warning(f"Found {len(orphaned)} orphaned Discord threads: {orphaned[:5]}...")

        return orphaned

    async def _find_missing_discord_threads(self, db_tasks: List[dict], discord_threads: List[dict]) -> List[str]:
        """Find tasks that should have Discord threads but don't."""
        thread_ids = {t["task_id"] for t in discord_threads}

        # Only active tasks should have threads
        active_statuses = ["pending", "in_progress", "in_review", "blocked", "needs_revision", "awaiting_validation"]

        missing = [
            t["task_id"] for t in db_tasks
            if t["status"] in active_statuses and t["task_id"] not in thread_ids
        ]

        if missing:
            logger.info(f"Found {len(missing)} active tasks missing Discord threads: {missing[:5]}...")

        return missing

    async def _find_status_mismatches(self, db_tasks: List[dict], sheet_tasks: List[dict]) -> List[dict]:
        """Find tasks with different status in DB vs Sheets."""
        mismatches = []
        sheet_dict = {t["task_id"]: t for t in sheet_tasks if t["task_id"]}

        for db_task in db_tasks:
            task_id = db_task["task_id"]
            if task_id in sheet_dict:
                sheet_task = sheet_dict[task_id]
                # Normalize status comparison (handle case differences)
                db_status = db_task["status"].lower().strip()
                sheet_status = sheet_task["status"].lower().strip()

                if db_status != sheet_status:
                    mismatches.append({
                        "task_id": task_id,
                        "db_status": db_task["status"],
                        "sheet_status": sheet_task["status"],
                        "title": db_task["title"]
                    })

        if mismatches:
            logger.warning(f"Found {len(mismatches)} status mismatches: {[m['task_id'] for m in mismatches[:5]]}...")

        return mismatches


async def run_consistency_check() -> Dict[str, List]:
    """Run consistency check and return results."""
    checker = DataConsistencyChecker()
    return await checker.check_all()


async def fix_orphaned_data(issues: Dict[str, List]):
    """
    Auto-fix orphaned data where safe.

    Safe fixes:
    - Delete orphaned Discord threads (no matching task)
    - Sync status mismatches (DB is source of truth)

    Unsafe fixes (require manual intervention):
    - Orphaned DB tasks (might need to be re-synced to Sheets)
    - Orphaned Sheet tasks (might be legitimate manual entries)
    """
    from ..database import get_database
    from ..database.models import DiscordThreadTaskLinkDB
    from sqlalchemy import delete

    logger.info("Auto-fixing orphaned data...")
    fixed_count = 0

    # Delete orphaned Discord threads
    if issues["orphaned_discord_threads"]:
        logger.info(f"Deleting {len(issues['orphaned_discord_threads'])} orphaned Discord threads...")

        try:
            db = get_database()
            async with db.session() as session:
                result = await session.execute(
                    delete(DiscordThreadTaskLinkDB).where(
                        DiscordThreadTaskLinkDB.task_id.in_(issues["orphaned_discord_threads"])
                    )
                )
                fixed_count += result.rowcount
                logger.info(f"Deleted {result.rowcount} orphaned Discord thread links")
        except Exception as e:
            logger.error(f"Error deleting orphaned Discord threads: {e}")

    # Sync status mismatches (DB is source of truth)
    if issues["status_mismatches"]:
        logger.info(f"Fixing {len(issues['status_mismatches'])} status mismatches...")

        sheets = get_sheets_integration()

        for mismatch in issues["status_mismatches"]:
            try:
                await sheets.update_task_status(
                    mismatch["task_id"],
                    mismatch["db_status"]
                )
                fixed_count += 1
                logger.info(f"Fixed status mismatch for {mismatch['task_id']}: {mismatch['sheet_status']} → {mismatch['db_status']}")
            except Exception as e:
                logger.error(f"Error fixing status mismatch for {mismatch['task_id']}: {e}")

    logger.info(f"Auto-fix complete. Fixed {fixed_count} issues.")
    return fixed_count
