"""
Staff Message Handler - Routes staff Discord messages to AI Assistant.

Handles the conversation flow between staff and the AI assistant:
1. Staff sends message in Discord
2. Handler identifies the task context
3. AI Assistant processes and responds
4. If escalation needed, routes to boss via Telegram
"""

import logging
import re
import aiohttp
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from config import settings
from ..ai.staff_assistant import get_staff_assistant
from ..memory.task_context import get_task_context_manager
from ..integrations.sheets import get_sheets_integration
from ..integrations.discord import get_discord_integration

logger = logging.getLogger(__name__)


class StaffMessageHandler:
    """
    Handles messages from staff in Discord channels.

    Flow:
    1. Staff message → Identify task → Get context
    2. Process with AI Assistant
    3. Respond in Discord
    4. Escalate to boss if needed
    """

    def __init__(self):
        self.assistant = get_staff_assistant()
        self.context_manager = get_task_context_manager()
        self.sheets = get_sheets_integration()
        self.discord = get_discord_integration()
        self.telegram_api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    async def handle_staff_message(
        self,
        user_id: str,
        user_name: str,
        message: str,
        channel_id: str,
        channel_name: str,
        message_url: str = None,
        attachments: List[str] = None,
        thread_id: str = None
    ) -> Dict[str, Any]:
        """
        Handle a message from a staff member.

        Args:
            user_id: Discord user ID
            user_name: Display name
            message: Message content
            channel_id: Discord channel ID
            channel_name: Channel name
            message_url: Jump URL to the message
            attachments: List of attachment URLs
            thread_id: Thread ID if in a thread

        Returns:
            Dict with response, action, and any metadata
        """
        try:
            # Step 1: Identify the task
            task_id = await self._identify_task(
                user_id=user_id,
                user_name=user_name,
                message=message,
                channel_id=channel_id,
                thread_id=thread_id
            )

            if not task_id:
                # No task identified - offer help
                return {
                    "success": True,
                    "response": f"Hey {user_name}! I couldn't identify which task you're referring to. Please mention the task ID (e.g., TASK-20260121-001) or reply in a task thread.",
                    "action": "respond"
                }

            # Step 2: Get or create task context
            context = self.context_manager.get_context(task_id)
            if not context:
                # Fetch task details and create context
                task_details = await self._fetch_task_details(task_id)
                if not task_details:
                    return {
                        "success": False,
                        "response": f"I couldn't find task {task_id}. Please check the task ID.",
                        "action": "respond"
                    }

                context = self.context_manager.create_context(
                    task_id=task_id,
                    task_details=task_details,
                    channel_id=channel_id,
                    staff_id=user_id
                )

            # Step 3: Add staff message to history
            self.context_manager.add_message(
                task_id=task_id,
                role="staff",
                content=message,
                metadata={"attachments": attachments, "message_url": message_url}
            )

            # Step 4: Process with AI Assistant
            conversation_history = self.context_manager.get_conversation_history(task_id)
            task_context = context.get("task_details", {})
            task_context["task_id"] = task_id

            result = await self.assistant.process_staff_message(
                staff_name=user_name,
                message=message,
                task_context=task_context,
                conversation_history=conversation_history
            )

            # Step 5: Add AI response to history
            self.context_manager.add_message(
                task_id=task_id,
                role="assistant",
                content=result.get("response", ""),
                metadata={"action": result.get("action")}
            )

            # Step 6: Handle actions
            action = result.get("action", "respond")

            if action == "escalate":
                telegram_msg_id = await self._escalate_to_boss(
                    task_id=task_id,
                    staff_name=user_name,
                    message=message,
                    reason=result.get("escalation_reason", "Staff needs assistance"),
                    message_url=message_url
                )
                # Record escalation with telegram message ID for boss reply routing
                await self.context_manager.record_escalation_async(
                    task_id=task_id,
                    reason=result.get("escalation_reason", ""),
                    staff_message=message,
                    message_url=message_url,
                    telegram_message_id=telegram_msg_id
                )

            elif action == "submit_for_review":
                telegram_msg_id = await self._submit_for_boss_review(
                    task_id=task_id,
                    staff_name=user_name,
                    message=message,
                    validation_result=result.get("validation_result", {}),
                    attachments=attachments,
                    message_url=message_url
                )
                self.context_manager.record_submission(task_id, result.get("validation_result", {}))
                # Also record as escalation for boss reply routing
                if telegram_msg_id:
                    await self.context_manager.record_escalation_async(
                        task_id=task_id,
                        reason="Work submission for review",
                        staff_message=message,
                        message_url=message_url,
                        telegram_message_id=telegram_msg_id
                    )

            return {
                "success": True,
                "response": result.get("response", ""),
                "action": action,
                "task_id": task_id
            }

        except Exception as e:
            logger.error(f"Error handling staff message: {e}", exc_info=True)
            return {
                "success": False,
                "response": f"Sorry {user_name}, I encountered an error. Please try again or contact the boss directly.",
                "action": "error",
                "error": str(e)
            }

    async def _identify_task(
        self,
        user_id: str,
        user_name: str,
        message: str,
        channel_id: str,
        thread_id: str = None
    ) -> Optional[str]:
        """
        Identify which task the staff is referring to.

        Priority:
        1. Task ID mentioned in message
        2. Thread linked to task
        3. Channel linked to task
        4. Staff's active task
        5. Staff's only assigned task
        """
        # 1. Check for task ID in message
        task_pattern = r'TASK-\d{8}-[A-Z0-9]+'
        matches = re.findall(task_pattern, message, re.IGNORECASE)
        if matches:
            return matches[0].upper()

        # 2. Check if thread is linked to a task
        if thread_id:
            task_id = self.context_manager.get_task_by_channel(thread_id)
            if task_id:
                return task_id

        # 3. Check if channel is linked to a task
        task_id = self.context_manager.get_task_by_channel(channel_id)
        if task_id:
            return task_id

        # 4. Check staff's active task
        task_id = self.context_manager.get_task_by_staff(user_id)
        if task_id:
            return task_id

        # 5. Check if staff has only one assigned task
        staff_tasks = await self._get_staff_assigned_tasks(user_name)
        if len(staff_tasks) == 1:
            task_id = staff_tasks[0]
            self.context_manager.set_staff_active_task(user_id, task_id)
            return task_id

        return None

    async def _fetch_task_details(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch task details from sheets/database."""
        try:
            # Try database first
            from ..database.repositories import get_task_repository
            task_repo = get_task_repository()
            task = await task_repo.get_by_id(task_id)

            if task:
                return {
                    "task_id": task.task_id,
                    "title": task.title,
                    "description": task.description,
                    "acceptance_criteria": task.acceptance_criteria or [],
                    "deadline": task.deadline.isoformat() if task.deadline else None,
                    "priority": task.priority,
                    "assignee": task.assignee,
                    "status": task.status,
                    "notes": task.notes
                }

            # Fallback to sheets
            all_tasks = await self.sheets.get_daily_tasks()
            for task in all_tasks:
                if task.get("Task ID", "").upper() == task_id.upper():
                    # Parse acceptance criteria
                    criteria_str = task.get("Acceptance Criteria", "")
                    criteria = []
                    if criteria_str:
                        # Split by newlines or numbered items
                        lines = re.split(r'\n|(?=\d+\.)', criteria_str)
                        criteria = [line.strip() for line in lines if line.strip()]

                    return {
                        "task_id": task.get("Task ID"),
                        "title": task.get("Title", ""),
                        "description": task.get("Description", ""),
                        "acceptance_criteria": criteria,
                        "deadline": task.get("Deadline"),
                        "priority": task.get("Priority", "medium"),
                        "assignee": task.get("Assignee", ""),
                        "status": task.get("Status", "pending"),
                        "notes": task.get("Notes", "")
                    }

            return None

        except Exception as e:
            logger.error(f"Error fetching task details for {task_id}: {e}")
            return None

    async def _get_staff_assigned_tasks(self, user_name: str) -> List[str]:
        """Get list of task IDs assigned to a staff member."""
        try:
            all_tasks = await self.sheets.get_daily_tasks()
            assigned = []
            for task in all_tasks:
                assignee = task.get("Assignee", "").lower()
                status = task.get("Status", "").lower()
                if user_name.lower() in assignee and status not in ["completed", "cancelled", "archived"]:
                    task_id = task.get("Task ID")
                    if task_id:
                        assigned.append(task_id)
            return assigned
        except Exception as e:
            logger.error(f"Error getting assigned tasks for {user_name}: {e}")
            return []

    async def _escalate_to_boss(
        self,
        task_id: str,
        staff_name: str,
        message: str,
        reason: str,
        message_url: str = None
    ) -> Optional[str]:
        """
        Escalate a message to the boss via Telegram.

        Returns the Telegram message ID if successful, for boss reply routing.
        """
        try:
            text = f"""📣 **Staff Escalation**

**From:** {staff_name}
**Task:** {task_id}
**Reason:** {reason}

**Message:**
{message[:500]}{'...' if len(message) > 500 else ''}

{f'[View in Discord]({message_url})' if message_url else ''}

_Reply to this message to respond to {staff_name}._"""

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.telegram_api}/sendMessage",
                    json={
                        "chat_id": settings.telegram_boss_chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                        "reply_markup": {
                            "force_reply": True,
                            "selective": True
                        }
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        telegram_msg_id = str(data.get("result", {}).get("message_id", ""))
                        logger.info(f"Escalation sent to boss, telegram_msg_id={telegram_msg_id}")
                        return telegram_msg_id
                    return None

        except Exception as e:
            logger.error(f"Error escalating to boss: {e}")
            return None

    async def _submit_for_boss_review(
        self,
        task_id: str,
        staff_name: str,
        message: str,
        validation_result: Dict[str, Any],
        attachments: List[str] = None,
        message_url: str = None
    ) -> Optional[str]:
        """
        Submit work for boss review via Telegram.

        Returns the Telegram message ID if successful, for boss reply routing.
        """
        try:
            overall_status = validation_result.get("overall_status", "needs_review")
            status_emoji = {"pass": "✅", "fail": "❌", "needs_review": "⚠️"}.get(overall_status, "⚠️")

            text = f"""📥 **Work Submission**

**From:** {staff_name}
**Task:** {task_id}
**AI Validation:** {status_emoji} {overall_status.replace('_', ' ').title()}

**Submission:**
{message[:500]}{'...' if len(message) > 500 else ''}

{f'**Attachments:** {len(attachments)} file(s)' if attachments else ''}
{f'[View in Discord]({message_url})' if message_url else ''}

_Reply to this message: "approve" or "reject [reason]"_"""

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.telegram_api}/sendMessage",
                    json={
                        "chat_id": settings.telegram_boss_chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                        "reply_markup": {
                            "force_reply": True,
                            "selective": True
                        }
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        telegram_msg_id = str(data.get("result", {}).get("message_id", ""))
                        logger.info(f"Submission sent to boss, telegram_msg_id={telegram_msg_id}")
                        return telegram_msg_id
                    return None

        except Exception as e:
            logger.error(f"Error submitting for boss review: {e}")
            return None

    async def handle_boss_reply(
        self,
        task_id: str,
        boss_message: str,
        staff_id: str = None
    ) -> Dict[str, Any]:
        """
        Handle boss reply to a staff conversation.

        Routes the boss's reply back to the staff via Discord.
        """
        try:
            context = self.context_manager.get_context(task_id)
            if not context:
                return {"success": False, "error": "No context found for task"}

            channel_id = context.get("channel_id")
            staff_id = staff_id or context.get("staff_id")

            if not channel_id:
                return {"success": False, "error": "No Discord channel linked to task"}

            # Format boss reply
            message_content = f"**Response from Boss:**\n{boss_message}"

            # Send to Discord
            message_id = await self.discord.send_message(
                channel_id=int(channel_id),
                content=f"<@{staff_id}>" if staff_id else None,
                embed={
                    "description": message_content,
                    "color": 0xF1C40F,  # Gold for boss replies
                    "timestamp": datetime.now().isoformat()
                }
            )

            if message_id:
                # Add to conversation history
                self.context_manager.add_message(
                    task_id=task_id,
                    role="boss",
                    content=boss_message
                )
                return {"success": True, "message_id": message_id}
            else:
                return {"success": False, "error": "Failed to send message to Discord"}

        except Exception as e:
            logger.error(f"Error handling boss reply: {e}")
            return {"success": False, "error": str(e)}

    async def handle_boss_reply_to_escalation(
        self,
        reply_to_message_id: str,
        boss_message: str
    ) -> Dict[str, Any]:
        """
        Handle boss reply to an escalation via Telegram reply.

        Looks up the escalation by telegram message ID and routes
        the response back to the staff via Discord.

        Args:
            reply_to_message_id: The Telegram message ID being replied to
            boss_message: The boss's reply text

        Returns:
            Dict with success status and details
        """
        try:
            # Look up escalation by telegram message ID
            escalation = await self.context_manager.get_pending_escalation_by_telegram(
                reply_to_message_id
            )

            if not escalation:
                logger.warning(f"No pending escalation found for telegram msg {reply_to_message_id}")
                return {
                    "success": False,
                    "error": "No pending escalation found for this message",
                    "handled": False
                }

            task_id = escalation.get("task_id")
            staff_id = escalation.get("staff_id")
            channel_id = escalation.get("channel_id") or escalation.get("thread_id")

            if not channel_id:
                return {"success": False, "error": "No Discord channel linked to escalation"}

            # Format boss reply with context
            message_content = f"**Response from Boss:**\n{boss_message}"

            # Send to Discord
            message_id = await self.discord.send_message(
                channel_id=int(channel_id),
                content=f"<@{staff_id}>" if staff_id else None,
                embed={
                    "title": f"📨 Boss Reply - {task_id}",
                    "description": message_content,
                    "color": 0xF1C40F,  # Gold for boss replies
                    "timestamp": datetime.now().isoformat(),
                    "footer": {"text": "Reply in this thread to continue the conversation"}
                }
            )

            if message_id:
                # Add to conversation history
                self.context_manager.add_message(
                    task_id=task_id,
                    role="boss",
                    content=boss_message
                )

                # Mark escalation as responded
                await self.context_manager.mark_escalation_responded(
                    escalation_id=escalation.get("id"),
                    boss_response=boss_message
                )

                logger.info(f"Boss reply routed to Discord for task {task_id}")
                return {
                    "success": True,
                    "message_id": message_id,
                    "task_id": task_id,
                    "handled": True
                }
            else:
                return {"success": False, "error": "Failed to send message to Discord"}

        except Exception as e:
            logger.error(f"Error handling boss reply to escalation: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# Singleton
_staff_handler = None


def get_staff_handler() -> StaffMessageHandler:
    global _staff_handler
    if _staff_handler is None:
        _staff_handler = StaffMessageHandler()
    return _staff_handler
