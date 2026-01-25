"""Task template definitions and management system.

Enables quick task creation from predefined templates with
standardized fields, acceptance criteria, and best practices.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TemplateType(str, Enum):
    """Available template types."""
    BUG = "bug"
    FEATURE = "feature"
    HOTFIX = "hotfix"
    RESEARCH = "research"
    MEETING = "meeting"
    DOCUMENTATION = "documentation"
    REVIEW = "review"
    DEPLOYMENT = "deployment"


@dataclass
class Template:
    """A task template with predefined fields and structure."""
    name: str
    title_template: str
    priority: str
    tags: List[str]
    acceptance_criteria: List[str]
    description_template: Optional[str] = None
    estimated_effort: Optional[str] = None
    task_type: str = "task"


# Core task templates
TASK_TEMPLATES: Dict[str, Template] = {
    "bug": Template(
        name="bug",
        title_template="Bug Fix: {description}",
        priority="high",
        tags=["bug", "urgent"],
        acceptance_criteria=[
            "Bug is reproduced and root cause identified",
            "Fix is implemented and tested in development",
            "Testing confirms the fix resolves the issue",
            "No regressions introduced",
            "Verified in production"
        ],
        description_template="**Bug Details:**\n- Steps to reproduce: \n- Expected behavior: \n- Actual behavior: \n- Browser/Environment: ",
        estimated_effort="2-4 hours",
        task_type="bug"
    ),

    "feature": Template(
        name="feature",
        title_template="Feature: {description}",
        priority="medium",
        tags=["feature", "enhancement"],
        acceptance_criteria=[
            "Requirements are clearly defined",
            "Design/mockups approved (if applicable)",
            "Implementation is complete",
            "Code is tested and documented",
            "Ready for review and deployment"
        ],
        description_template="**Feature Requirements:**\n- User story: \n- Acceptance criteria: \n- Mockups/designs: \n- Technical approach: ",
        estimated_effort="1-3 days",
        task_type="feature"
    ),

    "hotfix": Template(
        name="hotfix",
        title_template="HOTFIX: {description}",
        priority="urgent",
        tags=["hotfix", "urgent", "prod", "critical"],
        acceptance_criteria=[
            "Root cause analyzed",
            "Minimal, targeted fix implemented",
            "Issue is fixed in production",
            "Monitoring confirms fix is working",
            "Post-mortem and prevention plan documented"
        ],
        description_template="**Production Issue:**\n- Severity: Critical\n- Impact: \n- Affected users: \n- Temporary workaround: ",
        estimated_effort="< 1 hour",
        task_type="bug"
    ),

    "research": Template(
        name="research",
        title_template="Research: {description}",
        priority="low",
        tags=["research", "investigation", "exploration"],
        acceptance_criteria=[
            "Research scope defined",
            "Key sources identified and reviewed",
            "Findings compiled and organized",
            "Recommendations provided",
            "Report documented"
        ],
        description_template="**Research Scope:**\n- Question to answer: \n- Key areas to explore: \n- Success metrics: \n- Timeline: ",
        estimated_effort="4-8 hours",
        task_type="task"
    ),

    "meeting": Template(
        name="meeting",
        title_template="Meeting: {description}",
        priority="medium",
        tags=["meeting", "discussion", "sync"],
        acceptance_criteria=[
            "Agenda prepared and shared",
            "Required attendees confirmed",
            "Meeting conducted",
            "Notes documented",
            "Action items assigned"
        ],
        description_template="**Meeting Details:**\n- Purpose: \n- Attendees: \n- Agenda items: \n- Expected duration: \n- Preparation needed: ",
        estimated_effort="1-2 hours",
        task_type="task"
    ),

    "documentation": Template(
        name="documentation",
        title_template="Documentation: {description}",
        priority="medium",
        tags=["documentation", "docs", "knowledge"],
        acceptance_criteria=[
            "Content is accurate and complete",
            "Examples are provided",
            "Formatting is consistent",
            "Links and references verified",
            "Documentation is accessible"
        ],
        description_template="**Documentation Scope:**\n- Topic: \n- Target audience: \n- Sections needed: \n- Examples to include: ",
        estimated_effort="2-6 hours",
        task_type="task"
    ),

    "review": Template(
        name="review",
        title_template="Code Review: {description}",
        priority="high",
        tags=["review", "code-review", "qa"],
        acceptance_criteria=[
            "Pull request identified",
            "Code changes reviewed for logic and quality",
            "Tests are adequate",
            "Documentation updated",
            "Feedback provided and resolved"
        ],
        description_template="**Review Details:**\n- PR/Link: \n- Reviewer notes: \n- Areas of concern: ",
        estimated_effort="1-3 hours",
        task_type="task"
    ),

    "deployment": Template(
        name="deployment",
        title_template="Deployment: {description}",
        priority="high",
        tags=["deployment", "release", "prod"],
        acceptance_criteria=[
            "Deployment plan reviewed",
            "Pre-deployment checklist completed",
            "Code deployed to production",
            "Smoke tests passed",
            "Monitoring confirms health",
            "Rollback plan ready if needed"
        ],
        description_template="**Deployment Details:**\n- Version: \n- Environment: \n- Changes: \n- Deployment window: \n- Rollback procedure: ",
        estimated_effort="1-4 hours",
        task_type="task"
    ),
}


def get_template(template_name: str) -> Optional[Template]:
    """Get a template by name.

    Args:
        template_name: Name of the template (case-insensitive)

    Returns:
        Template object or None if not found
    """
    template_name_lower = template_name.lower().strip()
    return TASK_TEMPLATES.get(template_name_lower)


def list_templates() -> Dict[str, str]:
    """List all available templates with descriptions.

    Returns:
        Dictionary mapping template names to their descriptions
    """
    descriptions = {
        "bug": "High priority bug fix with root cause analysis and verification",
        "feature": "New feature implementation with requirements and testing",
        "hotfix": "Critical production hotfix with minimal changes and monitoring",
        "research": "Investigation task with scope, findings, and recommendations",
        "meeting": "Meeting planning with agenda, attendees, and action items",
        "documentation": "Documentation creation with content and examples",
        "review": "Code review task with feedback and approval",
        "deployment": "Deployment with planning, execution, and verification",
    }
    return descriptions


def apply_template(
    template_name: str,
    description: str,
    **overrides
) -> Dict[str, Any]:
    """Apply a template to create task data.

    Takes a template and description, fills in the template fields,
    and applies any overrides.

    Args:
        template_name: Name of the template
        description: Description to fill into the template
        **overrides: Field overrides (e.g., priority="urgent")

    Returns:
        Dictionary with task data ready for creation

    Raises:
        ValueError: If template not found
    """
    template = get_template(template_name)
    if not template:
        available = ", ".join(TASK_TEMPLATES.keys())
        raise ValueError(
            f"Unknown template: {template_name}. "
            f"Available: {available}"
        )

    # Build task data from template
    task_data = {
        "title": template.title_template.format(description=description),
        "description": template.description_template or description,
        "priority": template.priority,
        "tags": template.tags.copy(),
        "acceptance_criteria": template.acceptance_criteria.copy(),
        "task_type": template.task_type,
        "estimated_effort": template.estimated_effort,
        "template_name": template_name,
    }

    # Apply any overrides
    task_data.update(overrides)

    logger.info(
        f"Applied template '{template_name}' for: {description}",
        extra={"template": template_name, "priority": task_data["priority"]}
    )

    return task_data


def validate_template_name(template_name: str) -> bool:
    """Check if a template name is valid.

    Args:
        template_name: Template name to validate

    Returns:
        True if valid, False otherwise
    """
    return template_name.lower().strip() in TASK_TEMPLATES


def get_template_suggestions(text: str) -> List[str]:
    """Suggest templates based on input text.

    Analyzes text for keywords that suggest a particular template.

    Args:
        text: Input text to analyze

    Returns:
        List of suggested template names
    """
    text_lower = text.lower()
    suggestions = []

    # Keyword mapping for templates
    keyword_map = {
        "bug": ["bug", "broken", "crash", "error", "issue", "not working", "fails", "failed"],
        "hotfix": ["hotfix", "critical", "urgent", "prod issue", "production", "emergency"],
        "feature": ["feature", "add", "new", "implement", "build", "create", "develop"],
        "research": ["research", "investigate", "explore", "analyze", "study", "understand"],
        "meeting": ["meeting", "call", "sync", "standup", "discuss", "review call"],
        "documentation": ["documentation", "doc", "write", "guide", "readme", "tutorial"],
        "review": ["review", "code review", "cr", "pr", "pull request"],
        "deployment": ["deploy", "release", "push to prod", "ship", "launch"],
    }

    for template_name, keywords in keyword_map.items():
        if any(keyword in text_lower for keyword in keywords):
            suggestions.append(template_name)

    return suggestions


def format_template_help() -> str:
    """Format help text for available templates.

    Returns:
        Formatted help message
    """
    templates_list = list_templates()
    help_text = "📋 **Available Task Templates:**\n\n"

    for template_name, description in templates_list.items():
        help_text += f"• **/{template_name}** - {description}\n"

    help_text += "\n**Usage:** /template <name> <description>\n"
    help_text += "**Example:** /template bug Login redirects to wrong page\n"

    return help_text
