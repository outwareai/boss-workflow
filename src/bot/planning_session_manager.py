"""
Enhanced session management for planning sessions with context preservation.

GROUP 3 Phase 7: Enhanced Multi-Turn Planning Sessions

Features:
- Auto-save sessions on timeout (30 minutes)
- Resume capability with AI context summary
- Stale session detection (>24 hours)
- Session recovery on errors
- Multiple saved sessions per user
"""

import logging
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta

from src.database.connection import get_session
from src.database.repositories import get_planning_repository, get_task_draft_repository
from src.database.models import PlanningStateEnum
from src.ai.deepseek import DeepSeekClient

logger = logging.getLogger(__name__)


class PlanningSessionManager:
    """Manage planning session lifecycle with enhanced resume."""

    def __init__(self, ai_client: DeepSeekClient):
        """
        Initialize planning session manager.

        Args:
            ai_client: DeepSeek AI client for context generation
        """
        self.ai = ai_client

    async def get_or_create_session(
        self,
        user_id: str,
        project_description: str
    ) -> Dict[str, Any]:
        """
        Get active session or create new one with stale detection.

        Args:
            user_id: User ID
            project_description: Description of the project

        Returns:
            Dict with session info and status
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)

                # Check for active session
                active_session = await planning_repo.get_active_for_user(user_id)

                if active_session:
                    # Check if session is stale (>24 hours)
                    hours_inactive = (
                        datetime.utcnow() - active_session.last_activity_at
                    ).total_seconds() / 3600

                    if hours_inactive > 24:
                        logger.info(
                            f"Auto-saving stale session {active_session.session_id} "
                            f"({hours_inactive:.1f}h inactive)"
                        )

                        # Auto-save the stale session
                        await self.save_session_snapshot(active_session.session_id)

                        # Create new session
                        return {
                            "status": "created",
                            "previous_session_saved": active_session.session_id,
                            "message": (
                                f"Previous session was inactive for {hours_inactive:.0f} hours. "
                                f"I've saved it and started a new one."
                            )
                        }

                    # Session is still active and fresh
                    return {
                        "status": "active",
                        "session_id": active_session.session_id,
                        "session": active_session,
                        "message": f"Continuing your active planning session"
                    }

                # No active session - check for saved sessions
                saved_sessions = await self._get_saved_sessions(user_id, limit=3)

                if saved_sessions:
                    return {
                        "status": "has_saved",
                        "saved_sessions": saved_sessions,
                        "message": (
                            f"You have {len(saved_sessions)} saved planning session(s). "
                            f"Use /resume to continue, or I'll create a new session."
                        )
                    }

                # No sessions at all - ready to create new
                return {
                    "status": "ready",
                    "message": "Ready to start a new planning session"
                }

        except Exception as e:
            logger.error(f"Failed to get/create session: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }

    async def resume_session_with_context(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Resume session and generate AI context summary.

        Args:
            session_id: Planning session ID to resume

        Returns:
            Dict with session data and AI-generated context summary
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)
                draft_repo = get_task_draft_repository(db)

                # Get session with drafts
                session = await planning_repo.get_by_id_or_fail(
                    session_id,
                    with_drafts=True
                )

                # Can only resume saved sessions
                if session.state != PlanningStateEnum.SAVED.value:
                    return {
                        "success": False,
                        "error": f"Session is not saved (current state: {session.state})"
                    }

                # Get task drafts
                drafts = session.task_drafts or []

                # Generate AI context summary
                context_summary = await self._generate_context_summary(
                    session,
                    drafts
                )

                # Restore session to previous active state
                # Determine which state to restore to based on what was completed
                restore_state = PlanningStateEnum.REVIEWING_BREAKDOWN

                if session.ai_breakdown:
                    restore_state = PlanningStateEnum.REVIEWING_BREAKDOWN
                elif session.clarifying_questions:
                    restore_state = PlanningStateEnum.GATHERING_INFO
                else:
                    restore_state = PlanningStateEnum.INITIATED

                await planning_repo.update_state(
                    session_id,
                    restore_state,
                    last_activity_at=datetime.utcnow()
                )

                logger.info(
                    f"Resumed session {session_id} from SAVED to {restore_state.value}"
                )

                return {
                    "success": True,
                    "session_id": session_id,
                    "session": session,
                    "context_summary": context_summary,
                    "state": restore_state.value,
                    "task_count": len(drafts)
                }

        except Exception as e:
            logger.error(f"Failed to resume session: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def save_session_snapshot(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Save session snapshot for later recovery.

        Args:
            session_id: Planning session ID to save

        Returns:
            Dict with save status
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)

                # Get session
                session = await planning_repo.get_by_id_or_fail(session_id)

                # Only save active sessions
                active_states = [
                    PlanningStateEnum.INITIATED.value,
                    PlanningStateEnum.GATHERING_INFO.value,
                    PlanningStateEnum.AI_ANALYZING.value,
                    PlanningStateEnum.REVIEWING_BREAKDOWN.value,
                    PlanningStateEnum.REFINING.value,
                    PlanningStateEnum.FINALIZING.value
                ]

                if session.state not in active_states:
                    return {
                        "success": False,
                        "error": f"Cannot save session in state: {session.state}"
                    }

                # Update to SAVED state
                await planning_repo.update_state(
                    session_id,
                    PlanningStateEnum.SAVED
                )

                logger.info(f"Saved planning session snapshot: {session_id}")

                return {
                    "success": True,
                    "session_id": session_id,
                    "saved_at": datetime.utcnow().isoformat()
                }

        except Exception as e:
            logger.error(f"Failed to save session snapshot: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def recover_session(
        self,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Recover most recent saved session (last 7 days).

        Args:
            user_id: User ID

        Returns:
            Session data or None if no saved sessions
        """
        try:
            saved_sessions = await self._get_saved_sessions(user_id, limit=1)

            if not saved_sessions:
                return None

            most_recent = saved_sessions[0]

            return {
                "session_id": most_recent["session_id"],
                "project_name": most_recent["project_name"],
                "saved_at": most_recent["updated_at"],
                "task_count": most_recent.get("task_count", 0)
            }

        except Exception as e:
            logger.error(f"Failed to recover session: {e}", exc_info=True)
            return None

    async def _get_saved_sessions(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get user's saved planning sessions (last 7 days).

        Args:
            user_id: User ID
            limit: Max sessions to return

        Returns:
            List of saved session summaries
        """
        try:
            async with get_session() as db:
                planning_repo = get_planning_repository(db)

                # Query for saved sessions
                from sqlalchemy import select, and_, desc
                from src.database.models import PlanningSessionDB

                cutoff_date = datetime.utcnow() - timedelta(days=7)

                query = (
                    select(PlanningSessionDB)
                    .where(
                        and_(
                            PlanningSessionDB.user_id == user_id,
                            PlanningSessionDB.state == PlanningStateEnum.SAVED.value,
                            PlanningSessionDB.updated_at >= cutoff_date
                        )
                    )
                    .order_by(desc(PlanningSessionDB.updated_at))
                    .limit(limit)
                )

                result = await db.execute(query)
                sessions = result.scalars().all()

                # Convert to summary dicts
                summaries = []
                for session in sessions:
                    # Count drafts
                    draft_repo = get_task_draft_repository(db)
                    drafts = await draft_repo.get_by_session(session.session_id)

                    summaries.append({
                        "session_id": session.session_id,
                        "project_name": session.project_name or "Unnamed Project",
                        "raw_input": session.raw_input[:100] + "..." if len(session.raw_input) > 100 else session.raw_input,
                        "task_count": len(drafts),
                        "updated_at": session.updated_at.isoformat(),
                        "complexity": session.complexity
                    })

                return summaries

        except Exception as e:
            logger.error(f"Failed to get saved sessions: {e}", exc_info=True)
            return []

    async def _generate_context_summary(
        self,
        session,
        drafts: List
    ) -> str:
        """
        Generate AI context summary for resuming session.

        Args:
            session: PlanningSessionDB instance
            drafts: List of TaskDraftDB instances

        Returns:
            Formatted context summary
        """
        try:
            # Build context for AI
            context_parts = [
                f"Project: {session.project_name or 'Unnamed'}",
                f"Original Request: {session.raw_input}",
                f"Current State: {session.state}",
                f"Last Activity: {session.last_activity_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ]

            if session.clarifying_questions:
                context_parts.append(
                    f"Questions Asked: {len(session.clarifying_questions)}"
                )

            if drafts:
                context_parts.append(f"Tasks Drafted: {len(drafts)}")
                task_list = "\n".join([
                    f"{i+1}. {d.title} ({d.category}, {d.estimated_hours}h)"
                    for i, d in enumerate(drafts[:5])
                ])
                context_parts.append(f"Task Preview:\n{task_list}")

            if session.user_edits:
                context_parts.append(
                    f"User Edits Made: {len(session.user_edits)}"
                )

            context = "\n".join(context_parts)

            # Generate AI summary
            prompt = f"""You're helping a user resume a planning session they started earlier.

SESSION DETAILS:
{context}

Generate a brief, friendly summary (3-4 sentences) covering:
1. What was being planned
2. What progress was made
3. What needs to be decided next

Keep it conversational and helpful. Use "you" to address the user."""

            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            return response.strip()

        except Exception as e:
            logger.error(f"Failed to generate context summary: {e}", exc_info=True)
            # Fallback summary
            task_count = len(drafts)
            return (
                f"📋 **Resuming Planning Session**\n\n"
                f"You were planning: {session.project_name or 'a new project'}\n\n"
                f"Progress: {task_count} task(s) drafted\n\n"
                f"Let's continue where you left off!"
            )

    async def list_saved_sessions(
        self,
        user_id: str
    ) -> str:
        """
        List user's saved sessions with formatted output.

        Args:
            user_id: User ID

        Returns:
            Formatted list of saved sessions
        """
        try:
            saved_sessions = await self._get_saved_sessions(user_id, limit=10)

            if not saved_sessions:
                return "📭 No saved planning sessions found (last 7 days)."

            lines = [f"📂 **Your Saved Planning Sessions** ({len(saved_sessions)})\n"]

            for idx, session in enumerate(saved_sessions, 1):
                lines.append(
                    f"{idx}. **{session['project_name']}**\n"
                    f"   • ID: `{session['session_id']}`\n"
                    f"   • Tasks: {session['task_count']}\n"
                    f"   • Saved: {session['updated_at'][:10]}\n"
                )

            lines.append("\nUse `/resume <session-id>` to continue a session.")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Failed to list saved sessions: {e}", exc_info=True)
            return f"❌ Error listing saved sessions: {str(e)}"


# Global instance
_planning_session_manager: Optional[PlanningSessionManager] = None


def get_planning_session_manager(ai_client: DeepSeekClient) -> PlanningSessionManager:
    """
    Get or create planning session manager singleton.

    Args:
        ai_client: DeepSeek AI client

    Returns:
        PlanningSessionManager instance
    """
    global _planning_session_manager
    if _planning_session_manager is None:
        _planning_session_manager = PlanningSessionManager(ai_client)
    return _planning_session_manager
