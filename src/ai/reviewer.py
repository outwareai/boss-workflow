"""
AI-powered submission reviewer.

Automatically reviews task submissions for quality before escalating to boss.
Provides suggestions for improvement and handles the feedback loop.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass, field
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class ReviewResult(str, Enum):
    """Result of the auto-review."""
    APPROVED = "approved"           # Good to send to boss
    NEEDS_IMPROVEMENT = "needs_improvement"  # Has issues, suggest fixes
    MISSING_REQUIRED = "missing_required"    # Missing critical items


@dataclass
class ReviewFeedback:
    """Feedback from the auto-review."""
    result: ReviewResult
    score: int  # 0-100 quality score
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    improved_notes: Optional[str] = None  # AI-suggested better notes
    improved_description: Optional[str] = None  # AI-suggested description
    missing_items: List[str] = field(default_factory=list)

    @property
    def passes_threshold(self) -> bool:
        """Check if submission passes quality threshold."""
        return self.score >= settings.submission_quality_threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "improved_notes": self.improved_notes,
            "improved_description": self.improved_description,
            "missing_items": self.missing_items,
            "passes": self.passes_threshold
        }


class SubmissionReviewer:
    """
    Reviews task submissions for quality before boss sees them.

    Checks for:
    - Missing notes/explanation
    - Vague or incomplete descriptions
    - Insufficient proof
    - Poor formatting

    Provides suggestions and lets developer choose how to proceed.
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        self.model = settings.deepseek_model

        # Quality requirements
        self.min_proof_items = 1
        self.require_notes = True
        self.min_notes_length = 10

    async def review_submission(
        self,
        task_description: str,
        proof_items: List[Dict],
        notes: Optional[str],
        user_name: str
    ) -> ReviewFeedback:
        """
        Review a submission for quality.

        Returns:
            ReviewFeedback with result, issues, and suggestions
        """
        issues = []
        suggestions = []
        missing = []
        score = 100

        # === BASIC CHECKS ===

        # Check proof items
        if len(proof_items) < self.min_proof_items:
            missing.append("proof/screenshots")
            score -= 30

        # Check for screenshots specifically
        has_screenshot = any(p.get("type") == "screenshot" for p in proof_items)
        has_link = any(p.get("type") == "link" for p in proof_items)

        if not has_screenshot and not has_link:
            issues.append("No visual proof (screenshot or link)")
            suggestions.append("Add a screenshot showing the completed work or a link to the live result")
            score -= 15

        # Check notes
        if self.require_notes:
            if not notes or notes.lower() in ["no", "none", "n/a", "-"]:
                missing.append("notes explaining what was done")
                issues.append("No notes provided")
                suggestions.append("Add notes explaining what you did and any issues encountered")
                score -= 25
            elif len(notes) < self.min_notes_length:
                issues.append("Notes are too brief")
                suggestions.append("Expand your notes to explain what was completed")
                score -= 15

        # === AI-POWERED REVIEW ===

        ai_feedback = await self._ai_review(
            task_description=task_description,
            proof_items=proof_items,
            notes=notes,
            user_name=user_name
        )

        if ai_feedback:
            # Merge AI feedback
            issues.extend(ai_feedback.get("issues", []))
            suggestions.extend(ai_feedback.get("suggestions", []))

            # Adjust score based on AI assessment
            ai_score_modifier = ai_feedback.get("score_modifier", 0)
            score += ai_score_modifier

            improved_notes = ai_feedback.get("improved_notes")
            improved_description = ai_feedback.get("improved_description")
        else:
            improved_notes = None
            improved_description = None

        # Clamp score
        score = max(0, min(100, score))

        # Determine result
        if missing:
            result = ReviewResult.MISSING_REQUIRED
        elif score < settings.submission_quality_threshold:
            result = ReviewResult.NEEDS_IMPROVEMENT
        else:
            result = ReviewResult.APPROVED

        return ReviewFeedback(
            result=result,
            score=score,
            issues=issues,
            suggestions=suggestions,
            improved_notes=improved_notes,
            improved_description=improved_description,
            missing_items=missing
        )

    async def _ai_review(
        self,
        task_description: str,
        proof_items: List[Dict],
        notes: Optional[str],
        user_name: str
    ) -> Optional[Dict[str, Any]]:
        """Use AI to review the submission quality."""

        proof_summary = self._summarize_proof(proof_items)

        prompt = f"""Review this task submission for quality.

TASK: {task_description}

SUBMITTED BY: {user_name}

PROOF PROVIDED:
{proof_summary}

NOTES FROM DEVELOPER:
{notes or "(No notes provided)"}

Evaluate this submission. Consider:
1. Does the proof seem sufficient to verify the work is done?
2. Are the notes clear and helpful?
3. Is anything obviously missing?
4. Would the boss have enough context to approve this?

Respond with JSON:
{{
    "quality_assessment": "good/acceptable/poor",
    "issues": ["list of specific issues found"],
    "suggestions": ["actionable suggestions to improve"],
    "score_modifier": -10 to +10 (adjust score based on overall quality),
    "improved_notes": "if notes are poor, suggest better version (or null)",
    "improved_description": "if description is vague, suggest clearer summary (or null)"
}}

Be constructive but honest. Help the developer submit better work."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You review task submissions for quality. Be helpful and constructive. Respond only with JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )

            import json
            content = response.choices[0].message.content
            # Handle potential markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            return json.loads(content.strip())

        except Exception as e:
            logger.error(f"AI review failed: {e}")
            return None

    def _summarize_proof(self, proof_items: List[Dict]) -> str:
        """Summarize proof items for AI review."""
        if not proof_items:
            return "(No proof provided)"

        lines = []
        for i, item in enumerate(proof_items, 1):
            ptype = item.get("type", "unknown")
            if ptype == "screenshot":
                lines.append(f"{i}. Screenshot" + (f": {item.get('caption')}" if item.get('caption') else ""))
            elif ptype == "link":
                lines.append(f"{i}. Link: {item.get('content', 'URL')}")
            else:
                content = item.get("content", "")[:100]
                lines.append(f"{i}. Note: {content}")

        return "\n".join(lines)

    async def generate_improvement_message(
        self,
        feedback: ReviewFeedback,
        user_name: str
    ) -> str:
        """Generate a friendly message explaining what needs improvement."""

        lines = [f"Hey {user_name}! 👋", ""]

        if feedback.result == ReviewResult.MISSING_REQUIRED:
            lines.append("**Your submission is missing some required items:**")
            for item in feedback.missing_items:
                lines.append(f"  ❌ {item}")
            lines.append("")

        if feedback.issues:
            lines.append("**I noticed a few things:**")
            for issue in feedback.issues[:3]:  # Limit to top 3
                lines.append(f"  • {issue}")
            lines.append("")

        if feedback.suggestions:
            lines.append("**Suggestions:**")
            for suggestion in feedback.suggestions[:3]:
                lines.append(f"  💡 {suggestion}")
            lines.append("")

        if feedback.improved_notes:
            lines.append("**Here's a better version of your notes:**")
            lines.append(f"```\n{feedback.improved_notes}\n```")
            lines.append("")

        lines.append(f"📊 Quality Score: **{feedback.score}/100** (need {settings.submission_quality_threshold}+ to auto-approve)")
        lines.append("")
        lines.append("─────────────────")
        lines.append("**What would you like to do?**")

        return "\n".join(lines)


# Singleton
submission_reviewer = SubmissionReviewer()

def get_submission_reviewer() -> SubmissionReviewer:
    return submission_reviewer
