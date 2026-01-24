"""
Team member repository.

Stores team member information for:
- Contact details (Telegram, Discord, Email)
- Role and skills
- Task assignment
- Performance stats
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import select, update, delete, func, or_

from ..connection import get_database
from ..models import TeamMemberDB
from ..exceptions import DatabaseConstraintError, DatabaseOperationError, EntityNotFoundError
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class TeamRepository:
    """Repository for team member operations."""

    def __init__(self):
        self.db = get_database()

    async def create(
        self,
        name: str,
        role: str = "developer",
        telegram_id: Optional[str] = None,
        discord_id: Optional[str] = None,
        discord_username: Optional[str] = None,
        email: Optional[str] = None,
        skills: Optional[List[str]] = None,
    ) -> Optional[TeamMemberDB]:
        """
        Create a new team member.
        
        Q2 2026: Added audit logging for team member creation.
        """
        async with self.db.session() as session:
            try:
                member = TeamMemberDB(
                    name=name,
                    username=name.lower().replace(" ", "_"),
                    role=role,
                    telegram_id=telegram_id,
                    discord_id=discord_id,
                    discord_username=discord_username,
                    email=email,
                    skills=skills or [],
                    is_active=True,
                )
                session.add(member)
                await session.flush()

                logger.info(f"Created team member: {name}")
                
                # Q2 2026: Audit log team member creation
                from ...utils.audit_logger import log_audit_event, AuditAction, AuditLevel
                await log_audit_event(
                    action=AuditAction.TEAM_MEMBER_CREATE,
                    entity_type="team_member",
                    entity_id=str(member.id),
                    details={"name": name, "role": role, "email": email},
                    level=AuditLevel.INFO
                )
                
                return member

            except IntegrityError as e:
                logger.error(f"Constraint violation creating team member {name}: {e}")
                raise DatabaseConstraintError(f"Cannot create team member {name}: duplicate or constraint violation")

            except Exception as e:
                logger.error(f"CRITICAL: Team member creation failed for {name}: {e}", exc_info=True)
                raise DatabaseOperationError(f"Failed to create team member {name}: {e}")

    async def get_by_id(self, member_id: int) -> Optional[TeamMemberDB]:
        """Get team member by database ID."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TeamMemberDB).where(TeamMemberDB.id == member_id)
            )
            return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[TeamMemberDB]:
        """Get team member by name (case-insensitive)."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TeamMemberDB)
                .where(TeamMemberDB.name.ilike(f"%{name}%"))
            )
            return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: str) -> Optional[TeamMemberDB]:
        """Get team member by Telegram ID."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TeamMemberDB)
                .where(TeamMemberDB.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def get_by_discord_id(self, discord_id: str) -> Optional[TeamMemberDB]:
        """Get team member by Discord ID or username."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TeamMemberDB)
                .where(
                    or_(
                        TeamMemberDB.discord_id == discord_id,
                        TeamMemberDB.discord_username == discord_id,
                    )
                )
            )
            return result.scalar_one_or_none()

    async def find_member(self, search: str) -> Optional[TeamMemberDB]:
        """Find a team member by any identifier."""
        async with self.db.session() as session:
            search_lower = search.lower().strip("@")

            result = await session.execute(
                select(TeamMemberDB)
                .where(
                    or_(
                        TeamMemberDB.name.ilike(f"%{search_lower}%"),
                        TeamMemberDB.username.ilike(f"%{search_lower}%"),
                        TeamMemberDB.telegram_id == search,
                        TeamMemberDB.discord_id == search,
                        TeamMemberDB.discord_username.ilike(f"%{search_lower}%"),
                        TeamMemberDB.email.ilike(f"%{search_lower}%"),
                    )
                )
            )
            return result.scalar_one_or_none()

    async def update(
        self,
        member_id: int,
        updates: Dict[str, Any]
    ) -> Optional[TeamMemberDB]:
        """
        Update a team member.
        
        Q2 2026: Added audit logging for team member updates.
        """
        async with self.db.session() as session:
            updates["updated_at"] = datetime.now()

            await session.execute(
                update(TeamMemberDB)
                .where(TeamMemberDB.id == member_id)
                .values(**updates)
            )

            result = await session.execute(
                select(TeamMemberDB).where(TeamMemberDB.id == member_id)
            )
            member = result.scalar_one_or_none()
            
            if member:
                # Q2 2026: Audit log team member update
                from ...utils.audit_logger import log_audit_event, AuditAction, AuditLevel
                await log_audit_event(
                    action=AuditAction.TEAM_MEMBER_UPDATE,
                    entity_type="team_member",
                    entity_id=str(member_id),
                    details={"name": member.name, "updates": list(updates.keys())},
                    level=AuditLevel.INFO
                )
            
            return member

    async def delete(self, member_id: int) -> bool:
        """
        Delete a team member.
        
        Q2 2026: Added audit logging for team member deletion.
        """
        async with self.db.session() as session:
            # Get member info before deletion
            result = await session.execute(
                select(TeamMemberDB).where(TeamMemberDB.id == member_id)
            )
            member = result.scalar_one_or_none()
            
            await session.execute(
                delete(TeamMemberDB).where(TeamMemberDB.id == member_id)
            )
            
            if member:
                # Q2 2026: Audit log team member deletion
                from ...utils.audit_logger import log_audit_event, AuditAction, AuditLevel
                await log_audit_event(
                    action=AuditAction.TEAM_MEMBER_DELETE,
                    entity_type="team_member",
                    entity_id=str(member_id),
                    details={"name": member.name, "role": member.role},
                    level=AuditLevel.WARNING
                )
            
            return True

    async def deactivate(self, member_id: int) -> Optional[TeamMemberDB]:
        """Deactivate a team member (soft delete)."""
        return await self.update(member_id, {"is_active": False})

    async def activate(self, member_id: int) -> Optional[TeamMemberDB]:
        """Reactivate a team member."""
        return await self.update(member_id, {"is_active": True})

    async def get_all(self, active_only: bool = True) -> List[TeamMemberDB]:
        """Get all team members."""
        async with self.db.session() as session:
            query = select(TeamMemberDB)

            if active_only:
                query = query.where(TeamMemberDB.is_active == True)

            query = query.order_by(TeamMemberDB.name)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_by_role(self, role: str) -> List[TeamMemberDB]:
        """Get team members by role."""
        async with self.db.session() as session:
            result = await session.execute(
                select(TeamMemberDB)
                .where(
                    TeamMemberDB.role.ilike(f"%{role}%"),
                    TeamMemberDB.is_active == True,
                )
                .order_by(TeamMemberDB.name)
            )
            return list(result.scalars().all())

    async def get_by_skill(self, skill: str) -> List[TeamMemberDB]:
        """Get team members with a specific skill."""
        async with self.db.session() as session:
            # PostgreSQL JSON contains query
            result = await session.execute(
                select(TeamMemberDB)
                .where(TeamMemberDB.is_active == True)
            )
            members = result.scalars().all()

            # Filter by skill (case-insensitive)
            skill_lower = skill.lower()
            return [
                m for m in members
                if m.skills and any(s.lower() == skill_lower for s in m.skills)
            ]

    # ==================== STATS ====================

    async def increment_assigned(self, member_id: int):
        """Increment tasks assigned count."""
        async with self.db.session() as session:
            await session.execute(
                update(TeamMemberDB)
                .where(TeamMemberDB.id == member_id)
                .values(
                    tasks_assigned=TeamMemberDB.tasks_assigned + 1,
                    updated_at=datetime.now(),
                )
            )

    async def increment_completed(self, member_id: int):
        """Increment tasks completed count."""
        async with self.db.session() as session:
            await session.execute(
                update(TeamMemberDB)
                .where(TeamMemberDB.id == member_id)
                .values(
                    tasks_completed=TeamMemberDB.tasks_completed + 1,
                    updated_at=datetime.now(),
                )
            )

    async def get_performance_stats(self) -> List[Dict[str, Any]]:
        """Get performance stats for all active members."""
        members = await self.get_all(active_only=True)

        stats = []
        for member in members:
            completion_rate = 0
            if member.tasks_assigned > 0:
                completion_rate = (member.tasks_completed / member.tasks_assigned) * 100

            stats.append({
                "id": member.id,
                "name": member.name,
                "role": member.role,
                "tasks_assigned": member.tasks_assigned,
                "tasks_completed": member.tasks_completed,
                "completion_rate": round(completion_rate, 1),
            })

        # Sort by completion rate descending
        stats.sort(key=lambda x: x["completion_rate"], reverse=True)
        return stats

    async def to_dict(self, member: TeamMemberDB) -> Dict[str, Any]:
        """Convert team member to dictionary."""
        return {
            "id": member.id,
            "name": member.name,
            "username": member.username,
            "role": member.role,
            "telegram_id": member.telegram_id,
            "discord_id": member.discord_id,
            "discord_username": member.discord_username,
            "email": member.email,
            "skills": member.skills or [],
            "is_active": member.is_active,
            "tasks_assigned": member.tasks_assigned,
            "tasks_completed": member.tasks_completed,
        }


# Singleton
_team_repository: Optional[TeamRepository] = None


def get_team_repository() -> TeamRepository:
    """Get the team repository singleton."""
    global _team_repository
    if _team_repository is None:
        _team_repository = TeamRepository()
    return _team_repository
