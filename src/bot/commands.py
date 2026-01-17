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
• `/templates` - View available task templates

**Task Management:**
• `/status` - Current task overview
• `/note [task-id] [note]` - Add note to task
• `/delay [task-id] [deadline] [reason]` - Delay a task

**Subtasks:**
• `/subtask TASK-001 "Title"` - Add subtask
• `/subtasks TASK-001` - List subtasks
• `/subdone TASK-001 1,2,3` - Complete subtasks
• `/breakdown TASK-001` - AI-powered task breakdown

**Time Tracking:**
• `/start TASK-001` - Start timer
• `/stop` - Stop current timer
• `/log TASK-001 2h30m` - Log time manually
• `/time TASK-001` - Show time on task
• `/timesheet` - Your weekly timesheet
• `/timesheet team` - Team timesheet

**Recurring Tasks:**
• `/recurring "Title" every:monday 9am` - Create
• `/recurring list` - View all
• `/recurring pause/resume/delete REC-001`

**Search & Filter:**
• `/search [query]` - Search tasks by keyword
• `/search @John` - Tasks assigned to John
• `/search #urgent` - Urgent priority tasks
• `/search status:blocked` - Blocked tasks

**Bulk Operations:**
• `/complete ID ID ID` - Mark multiple done
• `/block ID ID [reason]` - Block tasks
• `/assign @Person ID ID` - Assign tasks

**Reports:**
• `/weekly` - Generate weekly summary
• `/daily` - Today's task summary
• `/overdue` - List overdue tasks

**Team & Settings:**
• `/team` - View team members
• `/addteam [name] [role]` - Add team member
• `/preferences` - View preferences
• `/teach` - Teach me preferences

**Validation:**
• `/pending` - View pending validations
• `/approve [task-id]` - Approve work
• `/reject [task-id] [feedback]` - Reject

**Voice Messages:**
• Send a voice message and I'll transcribe it!

**Tips:**
• Natural language works!
• Templates: "bug: login crashes"
• Discord reactions: ✅🚧🚫⏸️🔄

Need help? Just ask!"""

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

    # ==================== SEARCH & BULK COMMANDS ====================

    async def handle_search(self, user_id: str, query: str) -> str:
        """Handle /search command - search tasks with filters."""
        import re

        # Parse special operators
        assignee = None
        status = None
        priority = None
        due = None
        text_query = query

        # Extract @mention for assignee
        assignee_match = re.search(r'@(\w+)', query)
        if assignee_match:
            assignee = assignee_match.group(1)
            text_query = text_query.replace(assignee_match.group(0), '').strip()

        # Extract #priority
        priority_match = re.search(r'#(urgent|high|medium|low)', query, re.IGNORECASE)
        if priority_match:
            priority = priority_match.group(1)
            text_query = text_query.replace(priority_match.group(0), '').strip()

        # Extract status:value
        status_match = re.search(r'status:(\w+)', query, re.IGNORECASE)
        if status_match:
            status = status_match.group(1)
            text_query = text_query.replace(status_match.group(0), '').strip()

        # Extract due:value
        due_match = re.search(r'due:(today|week|overdue)', query, re.IGNORECASE)
        if due_match:
            due = due_match.group(1)
            text_query = text_query.replace(due_match.group(0), '').strip()

        # Search
        results = await self.sheets.search_tasks(
            query=text_query if text_query else None,
            assignee=assignee,
            status=status,
            priority=priority,
            due=due,
            limit=10
        )

        if not results:
            return f"No tasks found matching: {query}"

        lines = [f"🔍 **Search Results** ({len(results)} found)", ""]

        for task in results:
            priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.get('Priority', '').lower(), "⚪"
            )
            lines.append(f"{priority_emoji} **{task.get('ID', 'N/A')}**: {task.get('Title', 'Untitled')[:40]}")
            lines.append(f"   {task.get('Assignee', 'Unassigned')} | {task.get('Status', 'pending')}")
            lines.append("")

        return "\n".join(lines)

    async def handle_complete(self, user_id: str, task_ids: list) -> str:
        """Handle /complete command - mark multiple tasks as completed."""
        if not task_ids:
            return "Please provide task IDs: `/complete TASK-001 TASK-002`"

        success_count, failed = await self.sheets.bulk_update_status(
            task_ids=task_ids,
            new_status="completed"
        )

        # Post to Discord
        if success_count > 0:
            await self.discord.post_alert(
                title="Tasks Completed",
                message=f"{success_count} task(s) marked as completed",
                alert_type="success"
            )

        if failed:
            return f"✅ Completed {success_count} task(s)\n❌ Failed: {', '.join(failed)}"
        return f"✅ Completed {success_count} task(s)!"

    async def handle_block(self, user_id: str, task_ids: list, reason: str = "") -> str:
        """Handle /block command - mark multiple tasks as blocked."""
        if not task_ids:
            return "Please provide task IDs: `/block TASK-001 TASK-002 [reason]`"

        success_count, failed = await self.sheets.bulk_update_status(
            task_ids=task_ids,
            new_status="blocked",
            note=reason if reason else "Blocked by boss"
        )

        # Post to Discord
        if success_count > 0:
            await self.discord.post_alert(
                title="Tasks Blocked",
                message=f"{success_count} task(s) blocked. {reason}",
                alert_type="warning"
            )

        if failed:
            return f"🚫 Blocked {success_count} task(s)\n❌ Failed: {', '.join(failed)}"
        return f"🚫 Blocked {success_count} task(s)"

    async def handle_assign(self, user_id: str, assignee: str, task_ids: list) -> str:
        """Handle /assign command - assign multiple tasks to a person."""
        if not task_ids:
            return "Please provide task IDs: `/assign @John TASK-001 TASK-002`"

        # Clean assignee
        assignee = assignee.lstrip('@').strip()

        success_count, failed = await self.sheets.bulk_assign(
            task_ids=task_ids,
            assignee=assignee
        )

        if failed:
            return f"📋 Assigned {success_count} task(s) to {assignee}\n❌ Failed: {', '.join(failed)}"
        return f"📋 Assigned {success_count} task(s) to {assignee}"

    async def handle_templates(self, user_id: str) -> str:
        """Handle /templates command - list available task templates."""
        from ..memory.preferences import DEFAULT_TEMPLATES

        lines = ["📝 **Task Templates**", ""]
        lines.append("Templates auto-apply defaults when detected in your message:")
        lines.append("")

        for template in DEFAULT_TEMPLATES:
            name = template["name"]
            defaults = template["defaults"]
            keywords = template["keywords"][:3]  # Show first 3 keywords

            priority = defaults.get("priority", "medium")
            priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")

            lines.append(f"**{name.upper()}** {priority_emoji}")
            lines.append(f"  Keywords: {', '.join(keywords)}")
            lines.append(f"  Sets: type={defaults.get('task_type', 'task')}, priority={priority}")
            if defaults.get("deadline_hours"):
                lines.append(f"  Deadline: {defaults['deadline_hours']} hours")
            lines.append("")

        lines.append("─────────────────")
        lines.append("**Usage examples:**")
        lines.append("• \"bug: login page crashes\" → Bug template")
        lines.append("• \"hotfix: payment failing\" → Hotfix template")
        lines.append("• \"feature: add dark mode\" → Feature template")

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

    # ==================== RECURRING TASKS ====================

    async def handle_recurring(self, user_id: str, args: str) -> str:
        """
        Handle /recurring command - manage recurring tasks.

        Usage:
        - /recurring "Task title" every:monday 9am assign:@John
        - /recurring list
        - /recurring pause REC-001
        - /recurring resume REC-001
        - /recurring delete REC-001
        """
        from ..database.repositories.recurring import get_recurring_repository, RecurrenceCalculator
        import re

        repo = get_recurring_repository()
        args = args.strip()

        if not args:
            return await self._recurring_help()

        # Handle subcommands
        if args.lower() == "list":
            return await self._list_recurring()

        if args.lower().startswith("pause "):
            recurring_id = args[6:].strip().upper()
            success = await repo.pause(recurring_id)
            if success:
                return f"⏸️ Paused recurring task {recurring_id}"
            return f"❌ Recurring task {recurring_id} not found"

        if args.lower().startswith("resume "):
            recurring_id = args[7:].strip().upper()
            success = await repo.resume(recurring_id)
            if success:
                recurring = await repo.get_by_id(recurring_id)
                next_run = recurring.next_run.strftime("%A, %b %d at %H:%M") if recurring else "soon"
                return f"▶️ Resumed recurring task {recurring_id}\nNext run: {next_run}"
            return f"❌ Recurring task {recurring_id} not found"

        if args.lower().startswith("delete "):
            recurring_id = args[7:].strip().upper()
            success = await repo.delete(recurring_id)
            if success:
                return f"🗑️ Deleted recurring task {recurring_id}"
            return f"❌ Recurring task {recurring_id} not found"

        # Parse new recurring task
        # Format: "Task title" every:pattern time [assign:@name] [priority:level]
        title_match = re.search(r'"([^"]+)"', args)
        if not title_match:
            return "Please wrap the task title in quotes: `/recurring \"Weekly standup\" every:monday 9am`"

        title = title_match.group(1)
        rest = args.replace(title_match.group(0), '').strip()

        # Extract pattern
        pattern_match = re.search(r'every:(\S+)', rest, re.IGNORECASE)
        if not pattern_match:
            return "Please specify a pattern: `every:monday`, `every:day`, `every:1st`, etc."

        pattern = f"every:{pattern_match.group(1)}"
        if not RecurrenceCalculator.is_valid_pattern(pattern):
            return f"Invalid pattern: {pattern}\n\nValid patterns: `every:day`, `every:weekday`, `every:monday`, `every:1st`, `every:last`, `every:2weeks`"

        # Extract time
        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', rest, re.IGNORECASE)
        time_str = time_match.group(1) if time_match else "09:00"

        # Extract assignee
        assignee_match = re.search(r'assign:@?(\w+)', rest, re.IGNORECASE)
        assignee = assignee_match.group(1) if assignee_match else None

        # Extract priority
        priority_match = re.search(r'priority:(\w+)', rest, re.IGNORECASE)
        priority = priority_match.group(1).lower() if priority_match else "medium"

        # Create recurring task
        recurring = await repo.create({
            "title": title,
            "pattern": pattern,
            "time": time_str,
            "assignee": assignee,
            "priority": priority,
            "created_by": user_id,
        })

        if not recurring:
            return "❌ Failed to create recurring task"

        next_run = recurring.next_run.strftime("%A, %b %d at %H:%M") if recurring.next_run else "calculating..."

        return f"""✅ **Recurring Task Created!**

**ID:** {recurring.recurring_id}
**Title:** {recurring.title}
**Schedule:** {recurring.pattern} at {recurring.time}
**Assignee:** {recurring.assignee or 'Unassigned'}
**Priority:** {recurring.priority}

**Next run:** {next_run}

Use `/recurring list` to see all recurring tasks."""

    async def _recurring_help(self) -> str:
        """Show recurring tasks help."""
        return """🔄 **Recurring Tasks**

**Create:**
`/recurring "Task title" every:pattern time [assign:@name]`

**Examples:**
• `/recurring "Daily standup" every:day 9am`
• `/recurring "Weekly report" every:monday 10am assign:@Sarah`
• `/recurring "Monthly review" every:1st 2pm priority:high`

**Patterns:**
• `every:day` - Daily
• `every:weekday` - Monday-Friday
• `every:monday` - Weekly on Monday
• `every:monday,wednesday,friday` - Multiple days
• `every:1st` - 1st of each month
• `every:15th` - 15th of each month
• `every:last` - Last day of month
• `every:2weeks` - Every 2 weeks
• `every:3days` - Every 3 days

**Manage:**
• `/recurring list` - View all recurring tasks
• `/recurring pause REC-001` - Pause a recurring task
• `/recurring resume REC-001` - Resume a paused task
• `/recurring delete REC-001` - Delete a recurring task"""

    async def _list_recurring(self) -> str:
        """List all recurring tasks."""
        from ..database.repositories.recurring import get_recurring_repository

        repo = get_recurring_repository()
        tasks = await repo.get_all()

        if not tasks:
            return "No recurring tasks found. Use `/recurring \"Task\" every:monday 9am` to create one."

        lines = ["🔄 **Recurring Tasks**", ""]

        for task in tasks:
            status = "▶️" if task.is_active else "⏸️"
            next_run = task.next_run.strftime("%b %d, %H:%M") if task.next_run else "N/A"
            lines.append(f"{status} **{task.recurring_id}**: {task.title[:40]}")
            lines.append(f"   {task.pattern} at {task.time} | Next: {next_run}")
            lines.append(f"   Instances: {task.instances_created}")
            lines.append("")

        return "\n".join(lines)

    # ==================== TIME TRACKING ====================

    async def handle_start_timer(self, user_id: str, user_name: str, task_id: str) -> str:
        """Handle /start command - start timer for a task."""
        from ..database.repositories.time_tracking import get_time_tracking_repository

        if not task_id:
            return "Please specify a task: `/start TASK-001`"

        repo = get_time_tracking_repository()
        result = await repo.start_timer(user_id, user_name, task_id.upper())

        if not result:
            return "❌ Failed to start timer"

        if result.get("error") == "timer_running":
            return f"⚠️ Timer already running for {result['task_ref']}\nUse `/stop` first."

        if result.get("error") == "task_not_found":
            return f"❌ Task {task_id} not found"

        return f"""⏱️ **Timer Started!**

**Task:** {result['task_id']}
**Title:** {result['task_title'][:50]}
**Started:** {result['started_at'].strftime('%H:%M')}

Use `/stop` when you're done."""

    async def handle_stop_timer(self, user_id: str) -> str:
        """Handle /stop command - stop the active timer."""
        from ..database.repositories.time_tracking import get_time_tracking_repository

        repo = get_time_tracking_repository()
        result = await repo.stop_timer(user_id)

        if not result:
            return "No timer running. Use `/start TASK-001` to start one."

        return f"""⏱️ **Timer Stopped!**

**Task:** {result['task_id']}
**Title:** {result['task_title'][:50]}
**Duration:** {result['duration_formatted']}

**Total on task:** {result['total_formatted']}"""

    async def handle_log_time(self, user_id: str, user_name: str, task_id: str, duration: str, description: str = None) -> str:
        """Handle /log command - log time manually."""
        from ..database.repositories.time_tracking import get_time_tracking_repository

        if not task_id or not duration:
            return "Usage: `/log TASK-001 2h30m [description]`"

        repo = get_time_tracking_repository()
        result = await repo.log_manual(user_id, user_name, task_id.upper(), duration, description)

        if not result:
            return "❌ Failed to log time"

        if result.get("error") == "task_not_found":
            return f"❌ Task {task_id} not found"

        if result.get("error") == "invalid_duration":
            return "❌ Invalid duration. Examples: `2h30m`, `1.5h`, `45m`, `1d`"

        return f"""📝 **Time Logged!**

**Task:** {result['task_id']}
**Logged:** {result['duration_formatted']}
**Total on task:** {result['total_formatted']}"""

    async def handle_time(self, user_id: str, task_id: str) -> str:
        """Handle /time command - show time spent on a task."""
        from ..database.repositories.time_tracking import get_time_tracking_repository

        if not task_id:
            # Check for active timer
            repo = get_time_tracking_repository()
            active = await repo.get_active_timer(user_id)

            if active:
                return f"""⏱️ **Active Timer**

**Task:** {active['task_ref']}
**Running:** {active['duration_formatted']}
**Started:** {active['started_at'].strftime('%H:%M')}

Use `/stop` to stop the timer."""
            return "Usage: `/time TASK-001`"

        repo = get_time_tracking_repository()
        result = await repo.get_task_time(task_id.upper())

        if result.get("error") == "task_not_found":
            return f"❌ Task {task_id} not found"

        lines = [f"⏱️ **Time on {result['task_id']}**", ""]
        lines.append(f"**{result['task_title'][:50]}**")
        lines.append(f"**Total:** {result['total_formatted']}")
        lines.append(f"**Entries:** {result['entry_count']}")

        if result['is_running']:
            lines.append(f"🔴 Timer running: +{result['running_duration']}m")

        if result.get('entries'):
            lines.append("")
            lines.append("**Recent entries:**")
            for entry in result['entries'][:5]:
                lines.append(f"• {entry['duration']} by {entry['user_name']} ({entry['date']})")

        return "\n".join(lines)

    async def handle_timesheet(self, user_id: str, user_name: str, args: str) -> str:
        """Handle /timesheet command - show time summary."""
        from ..database.repositories.time_tracking import get_time_tracking_repository
        from datetime import date, timedelta

        repo = get_time_tracking_repository()

        # Parse arguments
        args = args.strip().lower() if args else ""

        # Determine date range
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        if args == "month":
            start = today.replace(day=1)
            if today.month == 12:
                end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif args.startswith("@"):
            # Get specific user's timesheet (for boss)
            target_user = args[1:]
            result = await repo.get_team_timesheet(start_of_week, end_of_week)
            # Filter for specific user
            for member in result.get("members", []):
                if member["user_name"].lower() == target_user.lower():
                    return self._format_user_timesheet(member, start_of_week, end_of_week)
            return f"No time entries found for @{target_user}"
        elif args == "team" or args == "week":
            # Full team timesheet
            result = await repo.get_team_timesheet(start_of_week, end_of_week)
            return self._format_team_timesheet(result)
        else:
            # Current user's timesheet
            start = start_of_week
            end = end_of_week
            result = await repo.get_user_timesheet(user_id, start, end)
            return self._format_personal_timesheet(result, user_name)

    def _format_personal_timesheet(self, result: dict, user_name: str) -> str:
        """Format personal timesheet."""
        lines = [f"📊 **Timesheet: {user_name}**"]
        lines.append(f"_{result['start_date']} to {result['end_date']}_")
        lines.append("")

        if not result.get('tasks'):
            lines.append("No time entries for this period.")
            return "\n".join(lines)

        for task in result['tasks']:
            lines.append(f"• **{task['task_id']}**: {task['title'][:35]}")
            lines.append(f"   {task['duration']}")

        lines.append("")
        lines.append(f"**Total:** {result['total_formatted']}")

        return "\n".join(lines)

    def _format_user_timesheet(self, member: dict, start: date, end: date) -> str:
        """Format a specific user's timesheet."""
        lines = [f"📊 **Timesheet: {member['user_name']}**"]
        lines.append(f"_{start.isoformat()} to {end.isoformat()}_")
        lines.append("")

        for task in member.get('tasks', []):
            lines.append(f"• **{task['task_id']}**: {task['title'][:35]}")
            lines.append(f"   {task['duration']}")

        lines.append("")
        lines.append(f"**Total:** {member['total_formatted']}")

        return "\n".join(lines)

    def _format_team_timesheet(self, result: dict) -> str:
        """Format team timesheet."""
        lines = ["📊 **Team Timesheet**"]
        lines.append(f"_{result['start_date']} to {result['end_date']}_")
        lines.append("")

        if not result.get('members'):
            lines.append("No time entries for this period.")
            return "\n".join(lines)

        for member in result['members']:
            lines.append(f"👤 **{member['user_name']}** - {member['total_formatted']}")
            for task in member['tasks'][:3]:
                lines.append(f"   • {task['task_id']}: {task['duration']}")
            if len(member['tasks']) > 3:
                lines.append(f"   ... and {len(member['tasks']) - 3} more tasks")
            lines.append("")

        lines.append("═══════════════════")
        lines.append(f"**Team Total:** {result['team_total_formatted']}")

        return "\n".join(lines)

    # ==================== SUBTASKS ====================

    async def handle_subtask(self, user_id: str, task_id: str, subtask_title: str, assignee: str = None) -> str:
        """Handle /subtask command - add a subtask to a task."""
        from ..database.repositories.tasks import get_task_repository

        if not task_id or not subtask_title:
            return "Usage: `/subtask TASK-001 \"Subtask title\" [@assignee]`"

        repo = get_task_repository()
        subtask = await repo.add_subtask(task_id.upper(), subtask_title, assignee)

        if not subtask:
            return f"❌ Task {task_id} not found"

        # Get updated task for progress
        task = await repo.get_by_id(task_id.upper())

        # Calculate progress
        subtasks = await repo.get_subtasks(task_id.upper())
        total = len(subtasks)
        completed = sum(1 for s in subtasks if s.completed)
        progress = int((completed / total) * 100) if total > 0 else 0

        return f"""✅ **Subtask Added!**

**Task:** {task_id.upper()}
**#{subtask.order}:** {subtask_title}
{f'**Assignee:** {assignee}' if assignee else ''}

**Progress:** {progress}% ({completed}/{total} subtasks)"""

    async def handle_subtasks(self, user_id: str, task_id: str) -> str:
        """Handle /subtasks command - list subtasks for a task."""
        from ..database.repositories.tasks import get_task_repository

        if not task_id:
            return "Usage: `/subtasks TASK-001`"

        repo = get_task_repository()
        task = await repo.get_by_id(task_id.upper())

        if not task:
            return f"❌ Task {task_id} not found"

        subtasks = await repo.get_subtasks(task_id.upper())

        if not subtasks:
            return f"No subtasks for {task_id}. Use `/subtask {task_id} \"Title\"` to add one."

        total = len(subtasks)
        completed = sum(1 for s in subtasks if s.completed)
        progress = int((completed / total) * 100) if total > 0 else 0

        lines = [f"📋 **Subtasks for {task_id.upper()}**"]
        lines.append(f"_{task.title[:50]}_")
        lines.append("")

        for st in subtasks:
            status = "✅" if st.completed else "⬜"
            assignee = f" @{st.completed_by}" if st.completed and st.completed_by else ""
            lines.append(f"{status} {st.order}. {st.title}{assignee}")

        lines.append("")
        lines.append(f"**Progress:** {progress}% ({completed}/{total})")
        lines.append("")
        lines.append(f"Mark complete: `/subdone {task_id} 1` or `/subdone {task_id} 1,2,3`")

        return "\n".join(lines)

    async def handle_subdone(self, user_id: str, user_name: str, task_id: str, subtask_nums: str) -> str:
        """Handle /subdone command - mark subtasks as complete."""
        from ..database.repositories.tasks import get_task_repository

        if not task_id or not subtask_nums:
            return "Usage: `/subdone TASK-001 1` or `/subdone TASK-001 1,2,3`"

        repo = get_task_repository()
        task = await repo.get_by_id(task_id.upper())

        if not task:
            return f"❌ Task {task_id} not found"

        # Parse subtask numbers
        try:
            nums = [int(n.strip()) for n in subtask_nums.split(",")]
        except ValueError:
            return "Invalid subtask numbers. Use: `/subdone TASK-001 1,2,3`"

        completed = []
        for num in nums:
            success = await repo.complete_subtask_by_order(task_id.upper(), num, user_name)
            if success:
                completed.append(num)

        if not completed:
            return "❌ No subtasks were completed. Check the numbers."

        # Get updated progress
        subtasks = await repo.get_subtasks(task_id.upper())
        total = len(subtasks)
        done = sum(1 for s in subtasks if s.completed)
        progress = int((done / total) * 100) if total > 0 else 0

        result = f"✅ Completed subtask(s): {', '.join(map(str, completed))}\n"
        result += f"**Progress:** {progress}% ({done}/{total})"

        # Check if all subtasks done
        if done == total and total > 0:
            result += f"\n\n🎉 All subtasks complete! Consider marking {task_id} as done."

        return result

    # ==================== AI TASK BREAKDOWN ====================

    async def handle_breakdown(self, user_id: str, task_id: str, auto_create: bool = False) -> Tuple[str, Optional[Dict]]:
        """
        Handle /breakdown command - AI-powered task breakdown into subtasks.

        Args:
            user_id: User requesting the breakdown
            task_id: Task ID to break down
            auto_create: If True, automatically create subtasks without confirmation

        Returns:
            Tuple of (response message, action dict if confirmation needed)
        """
        from ..database.repositories.tasks import get_task_repository

        if not task_id:
            return "Usage: `/breakdown TASK-001`\n\nI'll analyze the task and suggest subtasks.", None

        repo = get_task_repository()
        task = await repo.get_by_id(task_id.upper())

        if not task:
            return f"❌ Task {task_id} not found", None

        # Check if task already has subtasks
        existing_subtasks = await repo.get_subtasks(task_id.upper())
        if existing_subtasks:
            return f"⚠️ Task {task_id} already has {len(existing_subtasks)} subtasks.\n\nUse `/subtasks {task_id}` to view them.", None

        # Get task details
        title = task.title
        description = task.description or ""
        task_type = task.task_type or "task"
        priority = task.priority or "medium"
        effort = task.estimated_effort

        # Get acceptance criteria if available
        criteria = []
        if hasattr(task, 'acceptance_criteria') and task.acceptance_criteria:
            criteria = task.acceptance_criteria

        # Call AI to break down the task
        result = await self.ai.breakdown_task(
            title=title,
            description=description,
            task_type=task_type,
            priority=priority,
            estimated_effort=effort,
            acceptance_criteria=criteria
        )

        # Check if task is complex enough
        if not result.get("is_complex_enough", True):
            return f"""📋 **Task Analysis: {task_id}**

This task appears simple enough to complete without breaking it down.

**Reason:** {result.get('reason', 'Task is straightforward')}

If you still want to add subtasks manually:
`/subtask {task_id} "Subtask title"`""", None

        # Check if breakdown is recommended
        if not result.get("recommended", True):
            return f"""📋 **Task Analysis: {task_id}**

**Not Recommended:** {result.get('reason', 'See analysis')}

**Analysis:** {result.get('analysis', 'N/A')}

If you still want to add subtasks manually:
`/subtask {task_id} "Subtask title"`""", None

        # Build the response
        subtasks = result.get("subtasks", [])

        if not subtasks:
            return "❌ Could not generate subtasks for this task. Try adding them manually.", None

        lines = [f"🔍 **AI Task Breakdown: {task_id}**"]
        lines.append(f"_{title[:60]}_")
        lines.append("")
        lines.append(f"**Analysis:** {result.get('analysis', 'N/A')}")
        lines.append("")
        lines.append("**Suggested Subtasks:**")

        for i, st in enumerate(subtasks, 1):
            dep = f" (after #{st.get('depends_on')})" if st.get('depends_on') else ""
            effort_str = f" ~{st.get('estimated_effort')}" if st.get('estimated_effort') else ""
            lines.append(f"{i}. {st.get('title')}{effort_str}{dep}")

        lines.append("")
        lines.append(f"**Total Estimated Effort:** {result.get('total_estimated_effort', 'N/A')}")
        lines.append("")

        if auto_create:
            # Automatically create subtasks
            created = 0
            for st in subtasks:
                subtask = await repo.add_subtask(task_id.upper(), st.get('title'))
                if subtask:
                    created += 1

            lines.append(f"✅ **Created {created} subtasks!**")
            lines.append(f"\nUse `/subtasks {task_id}` to view them.")
            return "\n".join(lines), None
        else:
            # Ask for confirmation
            lines.append("**Create these subtasks?**")
            lines.append("Reply `yes` or `create` to add them all.")
            lines.append("Reply `no` to cancel.")

            # Return action for handler to process confirmation
            action = {
                "type": "breakdown_confirm",
                "task_id": task_id.upper(),
                "subtasks": subtasks
            }
            return "\n".join(lines), action

    async def handle_breakdown_confirm(self, user_id: str, task_id: str, subtasks: list) -> str:
        """Create subtasks after user confirms breakdown."""
        from ..database.repositories.tasks import get_task_repository

        repo = get_task_repository()
        created = 0

        for st in subtasks:
            subtask = await repo.add_subtask(task_id, st.get('title'))
            if subtask:
                created += 1

        if created == 0:
            return "❌ Failed to create subtasks. Please try again."

        return f"""✅ **Created {created} subtasks for {task_id}!**

Use `/subtasks {task_id}` to view them.
Use `/subdone {task_id} 1` to mark them complete."""


# Singleton instance
command_handler = CommandHandler()


def get_command_handler() -> CommandHandler:
    """Get the command handler instance."""
    return command_handler
