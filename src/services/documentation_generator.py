"""
Generate comprehensive documentation from planning sessions.

Phase 8: Automated Documentation Generation
- Markdown export with AI-powered sections
- Google Docs integration
- Auto-update Google Sheets
- Decision log tracking
- Timeline visualization
- Risk assessment
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import os
from pathlib import Path

from src.database.connection import get_db
from src.database.repositories import (
    get_planning_repository,
    get_task_draft_repository,
    get_memory_repository,
    get_decision_repository,
    get_task_repository
)
from src.ai.deepseek import get_deepseek_client
from src.integrations.sheets import sheets_client

logger = logging.getLogger(__name__)


class DocumentationGenerator:
    """Generate various documentation formats from planning data."""

    def __init__(self):
        self.ai = get_deepseek_client()

    async def generate_project_plan_markdown(self, session_id: str) -> str:
        """
        Generate comprehensive markdown document from planning session.

        Args:
            session_id: Planning session ID

        Returns:
            Complete markdown document
        """
        async for session in get_db():
            planning_repo = get_planning_repository(session)
            draft_repo = get_task_draft_repository(session)

            # Get session and drafts
            planning_session = await planning_repo.get_by_id(session_id, with_drafts=True)
            if not planning_session:
                return "❌ Session not found"

            task_drafts = await draft_repo.get_by_session(session_id)

            # Convert to dict for easier access
            session_data = {
                "session_id": planning_session.session_id,
                "project_description": planning_session.raw_input,
                "created_at": planning_session.created_at,
                "status": planning_session.state,
                "complexity": planning_session.complexity,
                "estimated_duration_hours": planning_session.estimated_duration_hours,
            }

            drafts_data = []
            for draft in task_drafts:
                drafts_data.append({
                    "task_id": draft.draft_id,
                    "title": draft.title,
                    "description": draft.description,
                    "assignee": draft.assigned_to or "Unassigned",
                    "priority": draft.priority or "medium",
                    "estimated_effort_hours": draft.estimated_hours,
                    "deadline": draft.deadline_date,
                    "dependencies": draft.depends_on or [],
                    "category": draft.category,
                })

            # Build markdown
            md = await self._build_markdown_document(session_data, drafts_data)
            return md

    async def _build_markdown_document(
        self,
        session: Dict[str, Any],
        task_drafts: List[Dict[str, Any]]
    ) -> str:
        """Build the complete markdown document."""
        md = f"# Project Plan: {session.get('project_description')}\n\n"
        md += f"**Created:** {session.get('created_at').strftime('%Y-%m-%d %H:%M')}\n"
        md += f"**Status:** {session.get('status')}\n"
        md += f"**Complexity:** {session.get('complexity', 'medium')}\n"

        if session.get('estimated_duration_hours'):
            md += f"**Estimated Duration:** {session.get('estimated_duration_hours')} hours\n"

        md += f"**Total Tasks:** {len(task_drafts)}\n\n"

        md += "---\n\n"

        # Executive Summary
        md += "## Executive Summary\n\n"
        summary = await self._generate_executive_summary(session, task_drafts)
        md += f"{summary}\n\n"

        # Tasks Breakdown
        md += "## Tasks Breakdown\n\n"
        md += await self._generate_tasks_section(task_drafts)

        # Timeline
        md += "\n## Timeline\n\n"
        md += await self._generate_timeline_section(task_drafts)

        # Risk Assessment
        md += "\n## Risk Assessment\n\n"
        md += await self._generate_risk_section(session, task_drafts)

        # Success Criteria
        md += "\n## Success Criteria\n\n"
        md += await self._generate_success_criteria(session, task_drafts)

        # Decision Log
        md += "\n## Decision Log\n\n"
        md += await self._generate_decision_log(session.get('session_id'))

        # Appendix
        md += "\n## Appendix\n\n"
        md += f"**Session ID:** {session.get('session_id')}\n"
        md += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        return md

    async def _generate_executive_summary(
        self,
        session: Dict[str, Any],
        task_drafts: List[Dict[str, Any]]
    ) -> str:
        """Generate AI-powered executive summary."""
        summary_prompt = f"""
Write a concise 2-3 paragraph executive summary for this project plan:

**Project:** {session.get('project_description')}
**Total Tasks:** {len(task_drafts)}
**Complexity:** {session.get('complexity', 'medium')}
**Estimated Duration:** {session.get('estimated_duration_hours', 'TBD')} hours

**Key Tasks:**
{chr(10).join([f"- {t['title']} ({t.get('assignee', 'Unassigned')})" for t in task_drafts[:5]])}

The summary should cover:
1. Project objective and scope
2. Key deliverables and milestones
3. Resource allocation and timeline overview

Write in professional, business-friendly language.
"""

        messages = [
            {"role": "system", "content": "You are a professional project manager creating executive summaries."},
            {"role": "user", "content": summary_prompt}
        ]

        try:
            response = await self.ai.chat(messages, temperature=0.7, max_tokens=500)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate executive summary: {e}")
            return f"Project to {session.get('project_description')} with {len(task_drafts)} tasks planned."

    async def _generate_tasks_section(self, task_drafts: List[Dict[str, Any]]) -> str:
        """Generate tasks breakdown by assignee."""
        if not task_drafts:
            return "No tasks defined.\n"

        # Group by assignee
        by_assignee = {}
        for task in task_drafts:
            assignee = task.get("assignee", "Unassigned")
            if assignee not in by_assignee:
                by_assignee[assignee] = []
            by_assignee[assignee].append(task)

        md = ""
        for assignee, tasks in by_assignee.items():
            md += f"### {assignee} ({len(tasks)} tasks)\n\n"

            for task in tasks:
                md += f"**{task['task_id']}:** {task['title']}\n"

                if task.get('description'):
                    md += f"- **Description:** {task['description']}\n"

                md += f"- **Priority:** {task.get('priority', 'medium')}\n"
                md += f"- **Category:** {task.get('category', 'general')}\n"

                if task.get('estimated_effort_hours'):
                    md += f"- **Effort:** {task['estimated_effort_hours']} hours\n"

                if task.get('deadline'):
                    md += f"- **Deadline:** {task['deadline'].strftime('%Y-%m-%d')}\n"

                if task.get('dependencies') and len(task['dependencies']) > 0:
                    md += f"- **Depends on:** {', '.join(task['dependencies'])}\n"

                md += "\n"

        return md

    async def _generate_timeline_section(self, task_drafts: List[Dict[str, Any]]) -> str:
        """Generate timeline in markdown format."""
        # Sort by deadline
        tasks_with_deadlines = [t for t in task_drafts if t.get('deadline')]
        tasks_with_deadlines.sort(key=lambda x: x['deadline'])

        if not tasks_with_deadlines:
            return "No deadlines set. Tasks can be scheduled flexibly.\n"

        timeline = "```\n"
        timeline += "Chronological Timeline\n"
        timeline += "=" * 60 + "\n\n"

        for task in tasks_with_deadlines:
            deadline = task['deadline'].strftime('%Y-%m-%d')
            assignee = task.get('assignee', 'Unassigned')[:15].ljust(15)
            title = task['title'][:40]
            timeline += f"{deadline} | {assignee} | {title}\n"

        timeline += "```\n"
        return timeline

    async def _generate_risk_section(
        self,
        session: Dict[str, Any],
        task_drafts: List[Dict[str, Any]]
    ) -> str:
        """Generate AI-powered risk assessment section."""
        risk_prompt = f"""
Analyze potential risks for this project with {len(task_drafts)} tasks:

**Project:** {session.get('project_description')}
**Complexity:** {session.get('complexity', 'medium')}

**Sample Tasks:**
{chr(10).join([f"- {t['title']} (effort: {t.get('estimated_effort_hours', 'TBD')}h, priority: {t.get('priority', 'medium')})" for t in task_drafts[:10]])}

Identify 3-5 key risks with:
1. Risk description
2. Impact level (High/Medium/Low)
3. Mitigation strategy

Format as markdown bullet points:
- **Risk Name** (Impact: Level) - Description. *Mitigation: Strategy*
"""

        messages = [
            {"role": "system", "content": "You are a risk assessment expert analyzing project plans."},
            {"role": "user", "content": risk_prompt}
        ]

        try:
            response = await self.ai.chat(messages, temperature=0.6, max_tokens=800)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate risk assessment: {e}")
            return "- **Scope Creep** (Impact: Medium) - Monitor task additions carefully.\n- **Timeline Delays** (Impact: Medium) - Build in buffer time."

    async def _generate_success_criteria(
        self,
        session: Dict[str, Any],
        task_drafts: List[Dict[str, Any]]
    ) -> str:
        """Generate AI-powered success criteria."""
        criteria_prompt = f"""
Define 3-5 measurable success criteria for this project:

**Project:** {session.get('project_description')}
**Total Tasks:** {len(task_drafts)}

**Categories Involved:**
{chr(10).join(list(set([f"- {t.get('category', 'general')}" for t in task_drafts[:5]])))}

Format as markdown checklist with measurable criteria:
- [ ] Criterion 1 (with specific metric)
- [ ] Criterion 2 (with specific metric)
"""

        messages = [
            {"role": "system", "content": "You are a project manager defining success criteria."},
            {"role": "user", "content": criteria_prompt}
        ]

        try:
            response = await self.ai.chat(messages, temperature=0.5, max_tokens=500)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate success criteria: {e}")
            return f"- [ ] All {len(task_drafts)} tasks completed\n- [ ] Deliverables meet requirements\n- [ ] Project delivered on time"

    async def _generate_decision_log(self, session_id: str) -> str:
        """Generate decision log section."""
        async for session in get_db():
            decision_repo = get_decision_repository(session)

            # Note: We need to get project_id from planning session
            # For now, return placeholder
            logger.warning(f"Decision log not yet linked to planning session {session_id}")
            return "No decisions recorded yet. Decision log will track key project decisions.\n"

    async def export_to_file(self, session_id: str, output_path: Optional[str] = None) -> str:
        """
        Export plan to markdown file.

        Args:
            session_id: Planning session ID
            output_path: Optional custom path. If None, auto-generates in exports/

        Returns:
            Full path to exported file
        """
        markdown = await self.generate_project_plan_markdown(session_id)

        # Generate default path if not provided
        if not output_path:
            exports_dir = Path("exports")
            exports_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"plan_{session_id}_{timestamp}.md"
            output_path = str(exports_dir / filename)

        # Write to file
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown)

            logger.info(f"Exported planning session {session_id} to {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to export to file: {e}")
            raise

    async def auto_update_project_tracker(
        self,
        session_id: str,
        created_tasks: List[Dict[str, Any]]
    ):
        """
        Auto-update Google Sheets with newly created tasks.

        Args:
            session_id: Planning session ID
            created_tasks: List of task dicts that were created
        """
        async for session in get_db():
            planning_repo = get_planning_repository(session)

            planning_session = await planning_repo.get_by_id(session_id)
            if not planning_session:
                logger.error(f"Planning session {session_id} not found")
                return

            try:
                # Prepare data for Sheets
                rows = []
                for task in created_tasks:
                    row = [
                        task.get('task_id', ''),
                        task.get('title', ''),
                        task.get('assignee', ''),
                        task.get('status', 'pending'),
                        task.get('priority', 'medium'),
                        task.get('deadline', '').strftime('%Y-%m-%d') if task.get('deadline') else '',
                        task.get('estimated_effort_hours', ''),
                        planning_session.raw_input[:100],  # Project description
                        datetime.now().strftime('%Y-%m-%d %H:%M')
                    ]
                    rows.append(row)

                # Append to Daily Tasks sheet
                if rows:
                    await sheets_client.append_rows("📋 Daily Tasks", rows)
                    logger.info(f"Appended {len(rows)} tasks to Daily Tasks sheet")

                # Update Dashboard metrics
                await self._update_dashboard_metrics()

                logger.info(f"Auto-updated project tracker with {len(created_tasks)} tasks from session {session_id}")

            except Exception as e:
                logger.error(f"Failed to auto-update project tracker: {e}", exc_info=True)

    async def create_google_doc_spec(self, session_id: str) -> Optional[str]:
        """
        Create Google Doc specification sheet.

        Args:
            session_id: Planning session ID

        Returns:
            Shareable Google Doc URL
        """
        from src.integrations.google_docs import get_google_docs_client

        async for session in get_db():
            planning_repo = get_planning_repository(session)
            draft_repo = get_task_draft_repository(session)

            planning_session = await planning_repo.get_by_id(session_id, with_drafts=True)
            if not planning_session:
                logger.error(f"Planning session {session_id} not found")
                return None

            task_drafts = await draft_repo.get_by_session(session_id)

            # Prepare session data
            session_data = {
                "session_id": planning_session.session_id,
                "project_description": planning_session.raw_input,
                "created_at": planning_session.created_at,
                "status": planning_session.state,
                "complexity": planning_session.complexity,
                "estimated_duration_hours": planning_session.estimated_duration_hours,
            }

            # Prepare drafts data
            drafts_data = []
            for draft in task_drafts:
                drafts_data.append({
                    "task_id": draft.draft_id,
                    "title": draft.title,
                    "description": draft.description,
                    "assignee": draft.assigned_to or "Unassigned",
                    "priority": draft.priority or "medium",
                    "estimated_effort_hours": draft.estimated_hours,
                    "deadline": draft.deadline_date,
                    "dependencies": draft.depends_on or [],
                    "category": draft.category,
                })

            # Create Google Doc
            docs_client = get_google_docs_client()
            doc_title = f"Project Plan: {planning_session.raw_input[:50]}"

            doc_url = await docs_client.create_spec_document(
                doc_title,
                session_data,
                drafts_data
            )

            logger.info(f"Created Google Doc for session {session_id}: {doc_url}")
            return doc_url

    async def _update_dashboard_metrics(self):
        """Update dashboard with latest metrics."""
        async for session in get_db():
            task_repo = get_task_repository(session)

            try:
                # Get counts (using raw query since we don't have count methods)
                from sqlalchemy import select, func
                from src.database.models import TaskDB

                # Total tasks
                total_query = select(func.count(TaskDB.task_id))
                total_result = await session.execute(total_query)
                total = total_result.scalar() or 0

                # By status
                pending_query = select(func.count(TaskDB.task_id)).where(TaskDB.status == "pending")
                pending_result = await session.execute(pending_query)
                pending = pending_result.scalar() or 0

                in_progress_query = select(func.count(TaskDB.task_id)).where(TaskDB.status == "in_progress")
                in_progress_result = await session.execute(in_progress_query)
                in_progress = in_progress_result.scalar() or 0

                completed_query = select(func.count(TaskDB.task_id)).where(TaskDB.status == "completed")
                completed_result = await session.execute(completed_query)
                completed = completed_result.scalar() or 0

                # Update Dashboard sheet
                completion_rate = f"{(completed/total*100):.1f}%" if total > 0 else "0%"

                dashboard_data = [
                    ["Metric", "Value", "Updated"],
                    ["Total Tasks", str(total), datetime.now().strftime('%Y-%m-%d %H:%M')],
                    ["Pending", str(pending), ""],
                    ["In Progress", str(in_progress), ""],
                    ["Completed", str(completed), ""],
                    ["Completion Rate", completion_rate, ""]
                ]

                await sheets_client.update_range("📊 Dashboard", "A1:C6", dashboard_data)
                logger.info(f"Updated dashboard metrics: {total} total, {completed} completed ({completion_rate})")

            except Exception as e:
                logger.error(f"Failed to update dashboard metrics: {e}", exc_info=True)


# Global instance
doc_generator = DocumentationGenerator()


def get_documentation_generator() -> DocumentationGenerator:
    """Get the documentation generator instance."""
    return doc_generator
