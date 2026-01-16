"""
Email summarizer using DeepSeek AI.

Analyzes emails and generates:
- Overall summary of inbox activity
- Action items requiring attention
- Priority categorization
- Key highlights
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from openai import AsyncOpenAI
import json

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailSummaryResult:
    """Result of email summarization."""
    summary: str
    action_items: List[str]
    priority_subjects: List[Dict[str, str]]  # {"subject": ..., "reason": ..., "from": ...}
    categories: Dict[str, int]  # {"work": 5, "personal": 2, ...}
    highlights: List[str]
    needs_urgent_attention: bool = False
    urgent_reason: Optional[str] = None


class EmailSummarizer:
    """
    Summarizes emails using DeepSeek AI.

    Provides:
    - Concise digest of email content
    - Extracted action items
    - Priority categorization
    - Smart grouping by topic/sender
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        self.model = settings.deepseek_model

    async def summarize_emails(
        self,
        emails: List[Dict[str, Any]],
        period: str = "today",
        user_context: Optional[str] = None
    ) -> EmailSummaryResult:
        """
        Summarize a batch of emails.

        Args:
            emails: List of email dicts with subject, from, body, etc.
            period: Time period description ("morning", "evening", "today")
            user_context: Optional context about user preferences

        Returns:
            EmailSummaryResult with summary and action items
        """
        if not emails:
            return EmailSummaryResult(
                summary="No new emails to summarize.",
                action_items=[],
                priority_subjects=[],
                categories={},
                highlights=[]
            )

        # Prepare emails for prompt
        email_text = self._format_emails_for_prompt(emails)

        prompt = f"""Analyze these emails and provide a concise summary.

EMAILS ({len(emails)} total):
{email_text}

TIME PERIOD: {period}
{f"USER CONTEXT: {user_context}" if user_context else ""}

Provide your analysis as JSON:
{{
    "summary": "2-3 sentence overview of inbox activity",
    "action_items": [
        "specific action required from email 1",
        "action from email 2",
        ...
    ],
    "priority_subjects": [
        {{"subject": "...", "from": "...", "reason": "why this is priority"}},
        ...
    ],
    "categories": {{
        "work": 5,
        "personal": 2,
        "newsletters": 3,
        "automated": 1
    }},
    "highlights": [
        "Key point 1",
        "Important update 2",
        ...
    ],
    "needs_urgent_attention": true/false,
    "urgent_reason": "why it's urgent (or null)"
}}

Guidelines:
- Be concise but informative
- Extract SPECIFIC action items (not vague)
- Prioritize by business importance
- Flag anything time-sensitive
- Group newsletters/automated emails separately
- Highlight any deadlines mentioned"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an executive assistant summarizing emails. Be concise, actionable, and prioritize what matters. Respond only with JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )

            content = response.choices[0].message.content

            # Handle markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            result = json.loads(content.strip())

            return EmailSummaryResult(
                summary=result.get("summary", ""),
                action_items=result.get("action_items", []),
                priority_subjects=result.get("priority_subjects", []),
                categories=result.get("categories", {}),
                highlights=result.get("highlights", []),
                needs_urgent_attention=result.get("needs_urgent_attention", False),
                urgent_reason=result.get("urgent_reason")
            )

        except Exception as e:
            logger.error(f"Email summarization failed: {e}")
            # Fallback to basic summary
            return self._basic_summary(emails)

    def _format_emails_for_prompt(self, emails: List[Dict], max_emails: int = 20) -> str:
        """Format emails for the AI prompt."""
        lines = []

        for i, email in enumerate(emails[:max_emails], 1):
            subject = email.get("subject", "(No subject)")
            sender = email.get("from", "Unknown")
            date = email.get("date", "")
            body = email.get("body", email.get("snippet", ""))[:500]
            important = "⭐" if email.get("is_important") else ""
            attachments = email.get("attachments", [])

            lines.append(f"--- Email {i} {important}---")
            lines.append(f"From: {sender}")
            lines.append(f"Subject: {subject}")
            lines.append(f"Date: {date}")
            if attachments:
                lines.append(f"Attachments: {', '.join(attachments[:3])}")
            lines.append(f"Content: {body}")
            lines.append("")

        if len(emails) > max_emails:
            lines.append(f"... and {len(emails) - max_emails} more emails")

        return "\n".join(lines)

    def _basic_summary(self, emails: List[Dict]) -> EmailSummaryResult:
        """Fallback basic summary without AI."""
        subjects = [e.get("subject", "")[:50] for e in emails[:5]]
        senders = list(set(e.get("from", "")[:30] for e in emails[:10]))

        summary = f"You have {len(emails)} emails. "
        if senders:
            summary += f"From: {', '.join(senders[:3])}{'...' if len(senders) > 3 else ''}."

        return EmailSummaryResult(
            summary=summary,
            action_items=[],
            priority_subjects=[
                {"subject": s, "from": "", "reason": "Recent"} for s in subjects
            ],
            categories={"uncategorized": len(emails)},
            highlights=subjects[:3]
        )

    async def summarize_single_email(
        self,
        email: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Summarize a single email in detail.

        Returns:
            Dict with summary, action_items, key_points, sentiment
        """
        prompt = f"""Summarize this email concisely:

From: {email.get('from', 'Unknown')}
Subject: {email.get('subject', 'No subject')}
Date: {email.get('date', '')}

Content:
{email.get('body', '')[:3000]}

Respond with JSON:
{{
    "one_line_summary": "Single sentence summary",
    "key_points": ["point 1", "point 2"],
    "action_required": "What you need to do (or null)",
    "deadline_mentioned": "Any deadline (or null)",
    "sentiment": "positive/neutral/negative/urgent",
    "suggested_reply": "Brief reply suggestion (or null)"
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You summarize emails concisely. Respond only with JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=500
            )

            content = response.choices[0].message.content
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            return json.loads(content.strip())

        except Exception as e:
            logger.error(f"Single email summary failed: {e}")
            return {
                "one_line_summary": email.get("snippet", "")[:100],
                "key_points": [],
                "action_required": None,
                "deadline_mentioned": None,
                "sentiment": "neutral",
                "suggested_reply": None
            }

    async def generate_digest_message(
        self,
        summary_result: EmailSummaryResult,
        period: str,
        total_emails: int,
        unread_count: int
    ) -> str:
        """
        Generate a formatted digest message for Telegram.

        Args:
            summary_result: The summarization result
            period: "morning" or "evening"
            total_emails: Total email count
            unread_count: Unread email count
        """
        emoji = "☀️" if period == "morning" else "🌙"

        lines = [
            f"{emoji} **{period.title()} Email Digest**",
            "",
            f"📬 **{total_emails}** emails | **{unread_count}** unread",
            "",
        ]

        # Urgent flag
        if summary_result.needs_urgent_attention:
            lines.append(f"🚨 **URGENT:** {summary_result.urgent_reason}")
            lines.append("")

        # Summary
        if summary_result.summary:
            lines.append(f"**Summary:**")
            lines.append(summary_result.summary)
            lines.append("")

        # Action items
        if summary_result.action_items:
            lines.append("**Action Items:**")
            for item in summary_result.action_items[:5]:
                lines.append(f"  ☐ {item}")
            lines.append("")

        # Priority emails
        if summary_result.priority_subjects:
            lines.append("**Priority:**")
            for p in summary_result.priority_subjects[:4]:
                subj = p.get("subject", "")[:35]
                sender = p.get("from", "")[:15]
                lines.append(f"  📧 {subj}...")
                lines.append(f"     _{sender}_")
            lines.append("")

        # Categories breakdown
        if summary_result.categories:
            cats = [f"{k}: {v}" for k, v in summary_result.categories.items() if v > 0]
            if cats:
                lines.append(f"**Breakdown:** {' | '.join(cats[:4])}")
                lines.append("")

        # Highlights
        if summary_result.highlights:
            lines.append("**Highlights:**")
            for h in summary_result.highlights[:3]:
                lines.append(f"  • {h}")

        lines.append("")
        lines.append("─────────────────")

        return "\n".join(lines)


# Singleton
email_summarizer = EmailSummarizer()


def get_email_summarizer() -> EmailSummarizer:
    return email_summarizer
