"""
Repository for planning templates.

Manages reusable templates for common project types.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, and_, desc
from sqlalchemy.exc import IntegrityError

from src.database.models import PlanningTemplateDB
from src.database.exceptions import (
    DatabaseConstraintError,
    EntityNotFoundError,
    DatabaseOperationError
)
import logging
import uuid

logger = logging.getLogger(__name__)


class TemplateRepository:
    """Repository for planning templates"""

    def __init__(self, session):
        self.session = session

    def _generate_template_id(self) -> str:
        """Generate unique template ID"""
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"TPL-{timestamp}-{unique_id}"

    async def create(
        self,
        name: str,
        task_template: List[Dict[str, Any]],
        source: str,
        **kwargs
    ) -> PlanningTemplateDB:
        """
        Create new planning template

        Args:
            name: Template name
            task_template: List of template tasks
            source: Template source ('manual', 'ai_generated', 'pattern_extracted')
            **kwargs: Additional fields

        Returns:
            Created template

        Raises:
            DatabaseConstraintError: On constraint violation
            ValidationError: On invalid data
        """
        try:
            # Validate source
            valid_sources = ['manual', 'ai_generated', 'pattern_extracted']
            if source not in valid_sources:
                from src.database.exceptions import ValidationError
                raise ValidationError(f"Invalid source: {source}. Must be one of {valid_sources}")

            template_id = self._generate_template_id()

            template = PlanningTemplateDB(
                template_id=template_id,
                name=name,
                task_template=task_template,
                source=source,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                version="1.0",
                **kwargs
            )

            self.session.add(template)
            await self.session.commit()
            await self.session.refresh(template)

            logger.info(f"Created template {template_id}: {name}")
            return template

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"Constraint violation creating template: {e}", exc_info=True)
            raise DatabaseConstraintError(f"Failed to create template: {e}")
        except Exception as e:
            if isinstance(e, (DatabaseConstraintError, EntityNotFoundError)):
                raise
            await self.session.rollback()
            logger.error(f"CRITICAL: Failed to create template: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to create template: {e}")

    async def get_by_id(self, template_id: str) -> Optional[PlanningTemplateDB]:
        """Get template by ID"""
        try:
            query = select(PlanningTemplateDB).where(
                PlanningTemplateDB.template_id == template_id
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching template {template_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch template: {e}")

    async def get_by_id_or_fail(self, template_id: str) -> PlanningTemplateDB:
        """Get template or raise EntityNotFoundError"""
        template = await self.get_by_id(template_id)
        if not template:
            raise EntityNotFoundError(f"Template {template_id} not found")
        return template

    async def get_by_category(
        self,
        category: str,
        active_only: bool = True
    ) -> List[PlanningTemplateDB]:
        """
        Get templates by category

        Args:
            category: Template category (mobile_dev, web_dev, api_dev, infrastructure)
            active_only: Only return active templates

        Returns:
            List of templates ordered by success rate
        """
        try:
            conditions = [PlanningTemplateDB.category == category]

            if active_only:
                conditions.append(PlanningTemplateDB.active == True)

            query = (
                select(PlanningTemplateDB)
                .where(and_(*conditions))
                .order_by(desc(PlanningTemplateDB.success_rate))
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching templates for category {category}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch templates: {e}")

    async def get_all_active(self) -> List[PlanningTemplateDB]:
        """Get all active templates"""
        try:
            query = (
                select(PlanningTemplateDB)
                .where(PlanningTemplateDB.active == True)
                .order_by(desc(PlanningTemplateDB.usage_count))
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching active templates: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch templates: {e}")

    async def increment_usage(self, template_id: str) -> PlanningTemplateDB:
        """
        Increment template usage counter

        Raises:
            EntityNotFoundError: If template not found
        """
        try:
            template = await self.get_by_id_or_fail(template_id)

            template.usage_count += 1
            template.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(template)

            logger.info(f"Incremented usage for template {template_id} (count: {template.usage_count})")
            return template

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to increment usage for template {template_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to update template: {e}")

    async def update_success_rate(
        self,
        template_id: str,
        success_rate: float
    ) -> PlanningTemplateDB:
        """
        Update template success rate based on outcomes

        Args:
            template_id: Template ID
            success_rate: Success rate (0-1)

        Returns:
            Updated template

        Raises:
            EntityNotFoundError: If template not found
            ValidationError: If success_rate invalid
        """
        try:
            if not 0 <= success_rate <= 1:
                from src.database.exceptions import ValidationError
                raise ValidationError(f"Success rate must be 0-1, got {success_rate}")

            template = await self.get_by_id_or_fail(template_id)

            template.success_rate = success_rate
            template.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(template)

            logger.info(f"Updated success rate for template {template_id}: {success_rate:.2%}")
            return template

        except (EntityNotFoundError, DatabaseConstraintError):
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update success rate for template {template_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to update template: {e}")

    async def deactivate(self, template_id: str) -> PlanningTemplateDB:
        """
        Deactivate a template (soft delete)

        Raises:
            EntityNotFoundError: If template not found
        """
        try:
            template = await self.get_by_id_or_fail(template_id)

            template.active = False
            template.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(template)

            logger.info(f"Deactivated template {template_id}")
            return template

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to deactivate template {template_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to deactivate template: {e}")

    async def activate(self, template_id: str) -> PlanningTemplateDB:
        """
        Activate a previously deactivated template

        Raises:
            EntityNotFoundError: If template not found
        """
        try:
            template = await self.get_by_id_or_fail(template_id)

            template.active = True
            template.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(template)

            logger.info(f"Activated template {template_id}")
            return template

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to activate template {template_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to activate template: {e}")

    async def update(
        self,
        template_id: str,
        updates: Dict[str, Any]
    ) -> PlanningTemplateDB:
        """
        Update template fields

        Args:
            template_id: Template ID
            updates: Dict of field updates

        Returns:
            Updated template

        Raises:
            EntityNotFoundError: If template not found
        """
        try:
            template = await self.get_by_id_or_fail(template_id)

            for key, value in updates.items():
                if hasattr(template, key) and key not in ['template_id', 'id', 'created_at']:
                    setattr(template, key, value)

            template.updated_at = datetime.utcnow()

            await self.session.commit()
            await self.session.refresh(template)

            logger.info(f"Updated template {template_id}")
            return template

        except EntityNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update template {template_id}: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to update template: {e}")

    async def search_by_name(
        self,
        query: str,
        active_only: bool = True
    ) -> List[PlanningTemplateDB]:
        """
        Search templates by name (case-insensitive)

        Args:
            query: Search query
            active_only: Only return active templates

        Returns:
            List of matching templates
        """
        try:
            conditions = [PlanningTemplateDB.name.ilike(f"%{query}%")]

            if active_only:
                conditions.append(PlanningTemplateDB.active == True)

            sql_query = (
                select(PlanningTemplateDB)
                .where(and_(*conditions))
                .order_by(desc(PlanningTemplateDB.usage_count))
            )

            result = await self.session.execute(sql_query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error searching templates: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to search templates: {e}")

    async def get_most_used(self, limit: int = 10) -> List[PlanningTemplateDB]:
        """
        Get most frequently used templates

        Args:
            limit: Max results

        Returns:
            List of templates ordered by usage count
        """
        try:
            query = (
                select(PlanningTemplateDB)
                .where(PlanningTemplateDB.active == True)
                .order_by(desc(PlanningTemplateDB.usage_count))
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching most used templates: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch templates: {e}")

    async def get_highest_success(self, limit: int = 10) -> List[PlanningTemplateDB]:
        """
        Get templates with highest success rates

        Args:
            limit: Max results

        Returns:
            List of templates ordered by success rate
        """
        try:
            query = (
                select(PlanningTemplateDB)
                .where(
                    and_(
                        PlanningTemplateDB.active == True,
                        PlanningTemplateDB.success_rate.is_not(None)
                    )
                )
                .order_by(desc(PlanningTemplateDB.success_rate))
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching highest success templates: {e}", exc_info=True)
            raise DatabaseOperationError(f"Failed to fetch templates: {e}")


# Helper function
def get_template_repository(session) -> TemplateRepository:
    """Factory function for template repository"""
    return TemplateRepository(session)
