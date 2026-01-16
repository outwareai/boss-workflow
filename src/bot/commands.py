"""
Command handlers for the Telegram bot.

Handles all slash commands and special message types.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from ..memory.preferences import get_preferences_manager
from ..memory.learning import get_learning_manager
from ..integrations.sheets import get_sheets_integration
from ..integrations.discord import get_discord_integration
from ..ai.deepseek import get_deepseek_client
from .conversation import get_conversation_manager
from .validation import get_validation_workflow
from ..models.validation import ProofType, ValidationStatus

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Handles all bot commands.

    Commands:
    - /start - Welcome message
    - /help - Help text
    - /task - Start task creation (or just send a message)
    - /urgent - Flag current task as urgent
    - /skip - Skip current question, use defaults
    - /done - Finalize task immediately
    - /cancel - Cancel current task creation
    - /status - Get current task overview
    - /weekly - Generate weekly summary
    - /preferences - View/edit preferences
    - /teach - Add a new preference/guideline
    - /note - Add note to a task
    - /delay - Delay a task
    - /team - View team members

    VALIDATION (Team Members):
    - /submit [task-id] - Submit task for validation with proof
    - /submitproof - Finish adding proof items
    - /addproof - Add more proof to current submission

    VALIDATION (Boss):
    - /pending - View pending validation requests
    - /approve [task-id] [message] - Approve a task
    - /reject [task-id] [feedback] - Reject with feedback
    """

    def __init__(self):
        self.prefs = get_preferences_manager()
        self.learning = get_learning_manager()
        self.sheets = get_sheets_integration()
        self.discord = get_discord_integration()
        self.ai = get_deepseek_client()
        self.conversation = get_conversation_manager()
        self.validation = get_validation_workflow()

    async def handle_start(self, user_id: str) -> str:
        """Handle /start command."""
        return """👋 **Welcome to Boss Workflow Automation!**

I help you create and manage tasks through natural conversation.

**How it works:**
1. Just tell me about a task (e.g., "John needs to fix the login bug")
2. I'll ask a few clarifying questions if needed
3. Review the task spec I generate
4. Confirm, and it's posted to Discord + Google Sheets + Calendar!

**Quick Commands:**
• `/task` - Start creating a task
• `/urgent` - Flag as high priority
• `/skip` - Skip questions, use defaults
• `/done` - Finalize immediately
• `/status` - See current overview
• `/teach` - Teach me your preferences
• `/help` - Full command list

**For Team Members:**
• `/submit [task-id]` - Submit completed work for review
• Send screenshots as proof!

**For Boss:**
• `/pending` - View tasks awaiting your approval

Just send me a message to get started!"""

    async def handle_help(self, user_id: str) -> str:
        """Handle /help command."""
        return """📖 **Command Reference**

**Task Creation:**
• `/task [description]` - Start task creation
• `/urgent [description]` - Create urgent task
• `/skip` - Skip current question
• `/done` - Finalize with current info
• `/cancel` - Cancel task creation

**Task Management:**
• `/status` - Current task overview
• `/note [task-id] [note]` - Add note to task
• `/delay [task-id] [new-deadline] [reason]` - Delay a task
• `/complete [task-id]` - Mark task complete
• `/undone [task-id] [reason]` - Reopen completed task

**Reports:**
• `/weekly` - Generate weekly summary
• `/daily` - Today's task summary
• `/overdue` - List overdue tasks

**Settings:**
• `/preferences` - View your preferences
• `/teach` - Teach me something new
• `/team` - View team members
• `/addteam [name] [role]` - Add team member

**Tips:**
• You can just send a message without any command
• Voice messages are supported
• React to Discord messages to update status

Need more help? Just ask!"""

    async def handle_task(self, user_id: str, chat_id: str, message: str) -> str:
        """Handle /task command or plain message task creation."""
        response, _ = await self.conversation.start_conversation(
            user_id=user_id,
            chat_id=chat_id,
            message=message,
            is_urgent=False
        )
        return response

    async def handle_urgent(self, user_id: str, chat_id: str, message: str) -> str:
        """Handle /urgent command."""
        response, _ = await self.conversation.start_conversation(
            user_id=user_id,
            chat_id=chat_id,
            message=message,
            is_urgent=True
        )
        return response

    async def handle_skip(self, user_id: str) -> str:
        """Handle /skip command."""
        response, _ = await self.conversation.handle_skip(user_id)
        return response

    async def handle_done(self, user_id: str) -> str:
        """Handle /done command."""
        response, _ = await self.conversation.handle_done(user_id)
        return response

    async def handle_cancel(self, user_id: str) -> str:
        """Handle /cancel command."""
        response, _ = await self.conversation.handle_cancel(user_id)
        return response

    async def handle_status(self, user_id: str) -> str:
        """Handle /status command - show current overview."""
        # Get conversation status
        conv_status = await self.conversation.get_status(user_id)

        # Get today's tasks from sheets
        daily_tasks = await self.sheets.get_daily_tasks()
        overdue_tasks = await self.sheets.get_overdue_tasks()

        status_msg = f"**Current Status:**\n{conv_status}\n\n"

        if daily_tasks:
            status_msg += f"**Today's Tasks:** {len(daily_tasks)}\n"
            completed = sum(1 for t in daily_tasks if t.get('Status') == 'completed')
            status_msg += f"• Completed: {completed}/{len(daily_tasks)}\n"

        if overdue_tasks:
            status_msg += f"\n⚠️ **Overdue:** {len(overdue_tasks)} task(s)\n"
            for task in overdue_tasks[:3]:
                status_msg += f"• {task.get('Task ID')}: {task.get('Title')[:30]}...\n"

        return status_msg

    async def handle_weekly(self, user_id: str) -> str:
        """Handle /weekly command - generate weekly summary."""
        overview = await self.sheets.generate_weekly_overview()

        if not overview:
            return "Could not generate weekly summary. Please try again."

        # Get tasks for AI summary
        daily_tasks = await self.sheets.get_daily_tasks()
        completed = await self.sheets.get_tasks_by_status(
            __import__('..models.task', fromlist=['TaskStatus']).TaskStatus.COMPLETED
        )

        # Generate AI summary
        summary = await self.ai.generate_weekly_summary(
            weekly_stats=overview,
            tasks_by_status={
                "completed": completed[:20],
                "all": daily_tasks[:50]
            },
            team_performance=overview.get('by_assignee', {})
        )

        # Post to Discord
        await self.discord.post_weekly_summary(summary)

        # Update sheets
        await self.sheets.update_weekly_sheet(overview)

        return f"📊 **Weekly Summary**\n\n{summary}\n\n*Also posted to Discord*"

    async def handle_preferences(self, user_id: str) -> str:
        """Handle /preferences command."""
        return await self.learning.get_preferences_summary(user_id)

    async def handle_teach(self, user_id: str, teaching_text: str) -> str:
        """Handle /teach command."""
        success, response = await self.learning.process_teach_command(user_id, teaching_text)
        return response

    async def handle_team(self, user_id: str) -> str:
        """Handle /team command - show team members."""
        prefs = await self.prefs.get_preferences(user_id)

        if not prefs.team_members:
            return """No team members defined yet.

Use `/teach` to add team members:
• "John is our backend developer"
• "Sarah is the frontend expert"
• "Mike handles DevOps"

Or use `/addteam [name] [role]`"""

        lines = ["👥 **Team Members:**", ""]
        for name, member in prefs.team_members.items():
            lines.append(f"• **{member.name}** (@{member.username})")
            if member.role:
                lines.append(f"  Role: {member.role}")
            if member.skills:
                lines.append(f"  Skills: {', '.join(member.skills)}")
            lines.append("")

        return "\n".join(lines)

    async def handle_addteam(self, user_id: str, name: str, role: str = "") -> str:
        """Handle /addteam command."""
        username = name.lower().replace(" ", "_").replace("@", "")

        success = await self.prefs.add_team_member(
            user_id=user_id,
            name=name,
            username=username,
            role=role
        )

        if success:
            return f"✅ Added **{name}** to your team!"
        else:
            return "Failed to add team member. Please try again."

    async def handle_note(self, user_id: str, task_id: str, note_content: str) -> str:
        """Handle /note command - add note to a task."""
        # This would need to update the task in sheets and discord
        # For now, just log to the notes sheet
        success = await self.sheets.add_note_log(
            task_id=task_id,
            note_content=note_content,
            author=user_id,
            note_type="general"
        )

        if success:
            return f"📝 Note added to {task_id}"
        else:
            return "Failed to add note. Please check the task ID."

    async def handle_delay(
        self,
        user_id: str,
        task_id: str,
        new_deadline: str,
        reason: str
    ) -> str:
        """Handle /delay command."""
        # This would update the task in all integrations
        # For now, just add a note
        note = f"DELAYED to {new_deadline}. Reason: {reason}"

        await self.sheets.add_note_log(
            task_id=task_id,
            note_content=note,
            author=user_id,
            note_type="update"
        )

        await self.discord.post_alert(
            title="Task Delayed",
            message=f"**{task_id}** delayed to {new_deadline}\nReason: {reason}",
            alert_type="warning"
        )

        return f"⏰ Task {task_id} delayed to {new_deadline}"

    async def handle_daily(self, user_id: str) -> str:
        """Handle /daily command - show today's summary."""
        daily_tasks = await self.sheets.get_daily_tasks()

        if not daily_tasks:
            return "No tasks found for today."

        # Group by status
        by_status = {}
        for task in daily_tasks:
            status = task.get('Status', 'pending')
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(task)

        lines = ["📅 **Today's Tasks**", ""]

        for status, tasks in by_status.items():
            status_emoji = {
                'pending': '⏳',
                'in_progress': '🔨',
                'completed': '✅',
                'delayed': '⏰',
                'blocked': '🚫',
            }.get(status, '•')

            lines.append(f"**{status_emoji} {status.upper()}** ({len(tasks)})")
            for task in tasks[:5]:  # Limit to 5 per status
                lines.append(f"  • {task.get('Task ID')}: {task.get('Title')[:40]}")
            if len(tasks) > 5:
                lines.append(f"  ... and {len(tasks) - 5} more")
            lines.append("")

        return "\n".join(lines)

    async def handle_overdue(self, user_id: str) -> str:
        """Handle /overdue command - list overdue tasks."""
        overdue = await self.sheets.get_overdue_tasks()

        if not overdue:
            return "✅ No overdue tasks! Great job!"

        lines = ["🚨 **Overdue Tasks**", ""]

        for task in overdue:
            lines.append(f"• **{task.get('Task ID')}**: {task.get('Title')[:40]}")
            lines.append(f"  Assignee: {task.get('Assignee', 'Unassigned')}")
            lines.append(f"  Deadline: {task.get('Deadline')}")
            lines.append("")

        lines.append(f"Total: {len(overdue)} overdue task(s)")

        return "\n".join(lines)

    # ==================== VALIDATION COMMANDS ====================

    async def handle_submit(
        self,
        user_id: str,
        task_id: str,
        task_title: str = "Task",
        assignee_name: str = "Team Member"
    ) -> str:
        """
        Handle /submit command - Start task submission for validation.

        Team member uses this when they've completed a task.
        """
        return await self.validation.start_submission(
            user_id=user_id,
            task_id=task_id,
            task_title=task_title,
            assignee_name=assignee_name
        )

    async def handle_add_proof(
        self,
        user_id: str,
        proof_type: ProofType,
        content: str,
        caption: str = None,
        file_id: str = None
    ) -> str:
        """Handle adding a proof item to current submission."""
        success, message = await self.validation.add_proof_item(
            user_id=user_id,
            proof_type=proof_type,
            content=content,
            caption=caption,
            file_id=file_id
        )
        return message

    async def handle_submit_proof(self, user_id: str) -> str:
        """Handle /submitproof - Finish collecting proof, move to notes."""
        return await self.validation.finish_collecting_proof(user_id)

    async def handle_submission_notes(self, user_id: str, notes: str) -> str:
        """Handle notes for the submission."""
        return await self.validation.add_submission_notes(user_id, notes)

    async def handle_confirm_submission(self, user_id: str) -> tuple:
        """
        Handle confirmation of submission.

        Returns (response_message, validation_request or None)
        """
        success, message, request = await self.validation.confirm_submission(user_id)
        return message, request

    async def handle_cancel_submission(self, user_id: str) -> str:
        """Handle cancellation of submission."""
        return await self.validation.cancel_submission(user_id)

    async def handle_pending_validations(self, user_id: str) -> str:
        """
        Handle /pending command - Show pending validation requests.

        For boss to see what needs approval.
        """
        pending = await self.validation.get_pending_validations()

        if not pending:
            return "✅ No pending validation requests!"

        lines = ["📋 **Pending Validations**", ""]

        for item in pending:
            lines.append(f"• **{item['task_id']}**")
            lines.append(f"  Attempts: {item['attempts']}")
            if item.get('submitted_at'):
                lines.append(f"  Submitted: {item['submitted_at'][:16]}")
            lines.append("")

        lines.extend([
            "─────────────────────",
            "Reply to a validation message with:",
            "• `approve` - Accept the work",
            "• `reject [feedback]` - Request changes"
        ])

        return "\n".join(lines)

    async def handle_approve(
        self,
        boss_id: str,
        task_id: str,
        message: str = "Great work!"
    ) -> tuple:
        """
        Handle /approve command - Approve a task submission.

        Returns (response_for_boss, feedback, assignee_id)
        """
        return await self.validation.process_boss_response(
            boss_id=boss_id,
            message=f"approve {message}",
            reply_to_request_id=task_id  # Using task_id as lookup
        )

    async def handle_reject(
        self,
        boss_id: str,
        task_id: str,
        feedback: str
    ) -> tuple:
        """
        Handle /reject command - Reject a task with feedback.

        Returns (response_for_boss, feedback, assignee_id)
        """
        return await self.validation.process_boss_response(
            boss_id=boss_id,
            message=f"reject {feedback}",
            reply_to_request_id=task_id
        )

    async def build_validation_notification(
        self,
        feedback,
        task_id: str,
        task_title: str
    ) -> str:
        """Build notification message for assignee after validation."""
        return await self.validation.build_assignee_notification(
            feedback=feedback,
            task_id=task_id,
            task_title=task_title
        )


# Singleton instance
command_handler = CommandHandler()


def get_command_handler() -> CommandHandler:
    """Get the command handler instance."""
    return command_handler
