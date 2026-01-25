"""
Repositories for project memory, decisions, and discussions.

Handles AI-extracted patterns, key decisions, and important discussions.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, and_, desc
from sqlalchemy.exc import IntegrityError

from src.database.models import (
    ProjectMemoryDB,
    ProjectDecisionDB,
    KeyDiscussionDB
)
from src.database.exceptions import (
    DatabaseConstraintError,
    EntityNotFoundError,
    DatabaseOperationError
)
import logging
import uuid

logger = logging.getLogger(__name__)


class MemoryRepository:
    """Repository for project memory and AI-extracted patterns"""

    def __init__(self, session):
        self.session = session

    def _generate_memory_id(self) -> str:
        """Generate unique memory ID"""
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"MEM-{timestamp}-{unique_id}"

    async def get_or_create_for_project(
        self,
        project_id: str
    ) -> ProjectMemoryDB:
        """
        Get existing memory for project or create new one

        Args:
            project_id: Project ID

        Returns:
            Project memory record
        """
        try:
            # Try to find existing
            query = select(ProjectMemoryDB).where(
                ProjectMemoryDB.project_id == project_id
            )

            result = await self.session.execute(query)
            memory = result.scalar_one_or_none()

            if memory:
                return memory

            # Create new
            memory_id = self._generate_memory_id()
            memory = ProjectMemoryDB(
                memory_id=memory_id,
                project_id=project_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            self.session.add(memory)
            await self.session.commit()
            await self.session.refresh(memory)

            logger.info(f"Created project memory {memory_id} for project {project_id}")
            return memory

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"Constraint violation creating memory: {e}", exc_info=True)
            raise DatabaseConstraintError(f"Failed to create project memory: {e}")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"CRITICAL: Failed to get/create project memory: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to get/create project memory: {e}")

    async def update_patterns(
        self,
        project_id: str,
        patterns: Dict[str, Any],
        confidence: float
    ) -> ProjectMemoryDB:
        """
        Update AI-extracted patterns for project

        Args:
            project_id: Project ID
            patterns: Dict with challenges, successes, team_insights, etc.
            confidence: Pattern confidence score (0-1)

        Returns:
            Updated memory record
        """
        try:
            memory = await self.get_or_create_for_project(project_id)

            memory.common_challenges = patterns.get("challenges")
            memory.success_patterns = patterns.get("successes")
            memory.team_insights = patterns.get("team")
            memory.estimated_vs_actual = patterns.get("time_analysis")
            memory.bottleneck_patterns = patterns.get("bottlenecks")
            memory.recommended_templates = patterns.get("templates")
            memory.pattern_confidence = confidence
            memory.last_analyzed_at = datetime.utcnow()
            memory.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(memory)

            logger.info(f"Updated patterns for project {project_id} (confidence: {confidence:.2f})")
            return memory

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update patterns for project {project_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to update patterns: {e}")

    async def get_similar_projects(
        self,
        category: Optional[str] = None,
        min_confidence: float = 0.7,
        limit: int = 5
    ) -> List[ProjectMemoryDB]:
        """
        Find similar projects for pattern matching

        Args:
            category: Optional project category filter
            min_confidence: Minimum pattern confidence
            limit: Max results

        Returns:
            List of project memories with high-confidence patterns
        """
        try:
            conditions = [ProjectMemoryDB.pattern_confidence >= min_confidence]

            # TODO: Add category filtering when project.category is added
            # if category:
            #     conditions.append(Project.category == category)

            query = (
                select(ProjectMemoryDB)
                .where(and_(*conditions))
                .order_by(desc(ProjectMemoryDB.pattern_confidence))
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching similar projects: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch similar projects: {e}")


class DecisionRepository:
    """Repository for project decisions"""

    def __init__(self, session):
        self.session = session

    def _generate_decision_id(self) -> str:
        """Generate unique decision ID"""
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"DEC-{timestamp}-{unique_id}"

    async def create(
        self,
        project_id: str,
        decision_type: str,
        decision_text: str,
        made_by: str,
        **kwargs
    ) -> ProjectDecisionDB:
        """
        Record a project decision

        Args:
            project_id: Project ID
            decision_type: Type of decision (tech_choice, scope_change, etc.)
            decision_text: The decision made
            made_by: Who made the decision
            **kwargs: Additional fields (reasoning, alternatives_considered, etc.)

        Returns:
            Created decision record

        Raises:
            DatabaseConstraintError: On constraint violation
            DatabaseOperationError: On general failure
        """
        try:
            decision_id = self._generate_decision_id()

            decision = ProjectDecisionDB(
                decision_id=decision_id,
                project_id=project_id,
                decision_type=decision_type,
                decision_text=decision_text,
                made_by=made_by,
                decided_at=datetime.utcnow(),
                **kwargs
            )

            self.session.add(decision)
            await self.session.commit()
            await self.session.refresh(decision)

            logger.info(f"Recorded decision {decision_id} for project {project_id}")
            return decision

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"Constraint violation creating decision: {e}", exc_info=True)
            raise DatabaseConstraintError(f"Failed to create decision: {e}")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"CRITICAL: Failed to create decision: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to create decision: {e}")

    async def get_by_project(
        self,
        project_id: str,
        decision_type: Optional[str] = None
    ) -> List[ProjectDecisionDB]:
        """
        Get all decisions for a project

        Args:
            project_id: Project ID
            decision_type: Optional filter by type

        Returns:
            List of decisions, ordered by date (most recent first)
        """
        try:
            conditions = [ProjectDecisionDB.project_id == project_id]

            if decision_type:
                conditions.append(ProjectDecisionDB.decision_type == decision_type)

            query = (
                select(ProjectDecisionDB)
                .where(and_(*conditions))
                .order_by(desc(ProjectDecisionDB.decided_at))
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching decisions for project {project_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch decisions: {e}")

    async def update_outcome(
        self,
        decision_id: str,
        outcome: str,
        impact_assessment: Optional[str] = None
    ) -> ProjectDecisionDB:
        """
        Update decision outcome after implementation

        Args:
            decision_id: Decision ID
            outcome: Outcome description
            impact_assessment: Optional impact assessment

        Returns:
            Updated decision

        Raises:
            EntityNotFoundError: If decision not found
        """
        try:
            query = select(ProjectDecisionDB).where(
                ProjectDecisionDB.decision_id == decision_id
            )
            result = await self.session.execute(query)
            decision = result.scalar_one_or_none()

            if not decision:
                raise EntityNotFoundError(f"Decision {decision_id} not found")

            decision.outcome = outcome
            if impact_assessment:
                decision.impact_assessment = impact_assessment
            decision.reviewed_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(decision)

            logger.info(f"Updated outcome for decision {decision_id}")
            return decision

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update decision outcome: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to update decision: {e}")


class DiscussionRepository:
    """Repository for key discussions"""

    def __init__(self, session):
        self.session = session

    def _generate_discussion_id(self) -> str:
        """Generate unique discussion ID"""
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"DISC-{timestamp}-{unique_id}"

    async def create(
        self,
        project_id: str,
        topic: str,
        summary: str,
        **kwargs
    ) -> KeyDiscussionDB:
        """
        Create discussion record

        Args:
            project_id: Project ID
            topic: Discussion topic
            summary: AI-generated summary
            **kwargs: Additional fields

        Returns:
            Created discussion

        Raises:
            DatabaseConstraintError: On constraint violation
        """
        try:
            discussion_id = self._generate_discussion_id()

            discussion = KeyDiscussionDB(
                discussion_id=discussion_id,
                project_id=project_id,
                topic=topic,
                summary=summary,
                occurred_at=datetime.utcnow(),
                **kwargs
            )

            self.session.add(discussion)
            await self.session.commit()
            await self.session.refresh(discussion)

            logger.info(f"Recorded discussion {discussion_id} for project {project_id}")
            return discussion

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"Constraint violation creating discussion: {e}", exc_info=True)
            raise DatabaseConstraintError(f"Failed to create discussion: {e}")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"CRITICAL: Failed to create discussion: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to create discussion: {e}")

    async def get_important_for_project(
        self,
        project_id: str,
        min_importance: float = 0.7,
        limit: int = 10
    ) -> List[KeyDiscussionDB]:
        """
        Get important discussions for context

        Args:
            project_id: Project ID
            min_importance: Minimum importance score
            limit: Max results

        Returns:
            List of important discussions
        """
        try:
            query = (
                select(KeyDiscussionDB)
                .where(
                    and_(
                        KeyDiscussionDB.project_id == project_id,
                        KeyDiscussionDB.importance_score >= min_importance
                    )
                )
                .order_by(desc(KeyDiscussionDB.importance_score))
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching discussions for project {project_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch discussions: {e}")

    async def summarize_conversation(
        self,
        project_id: str,
        planning_session_id: str,
        messages: List[Dict[str, Any]],
        ai_summary: str,
        importance_score: float,
        **kwargs
    ) -> KeyDiscussionDB:
        """
        Create discussion summary from conversation

        Args:
            project_id: Project ID
            planning_session_id: Planning session ID
            messages: Conversation messages
            ai_summary: AI-generated summary
            importance_score: Importance (0-1)
            **kwargs: Additional fields

        Returns:
            Created discussion
        """
        message_ids = [msg.get("message_id") for msg in messages if msg.get("message_id")]
        participant_ids = list(set(msg.get("user_id") for msg in messages if msg.get("user_id")))

        return await self.create(
            project_id=project_id,
            planning_session_id=planning_session_id,
            topic=f"Planning discussion for {project_id}",
            summary=ai_summary,
            message_ids=message_ids,
            participant_ids=participant_ids,
            importance_score=importance_score,
            summarized_at=datetime.utcnow(),
            **kwargs
        )


# Helper functions
def get_memory_repository(session) -> MemoryRepository:
    """Factory function for memory repository"""
    return MemoryRepository(session)


def get_decision_repository(session) -> DecisionRepository:
    """Factory function for decision repository"""
    return DecisionRepository(session)


def get_discussion_repository(session) -> DiscussionRepository:
    """Factory function for discussion repository"""
    return DiscussionRepository(session)
