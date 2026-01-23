# Implementation Plan: Comprehensive Task Operations via Natural Language

## Goal
Extend bot natural language understanding to handle comprehensive task management operations without requiring slash commands.

## Current State Analysis

### Existing Intents (src/ai/intent.py)
- ✅ CREATE_TASK - Create new tasks
- ✅ TASK_DONE - Mark task complete
- ✅ SUBMIT_PROOF - Submit work proof
- ✅ APPROVE_TASK / REJECT_TASK - Boss validation
- ✅ CHECK_STATUS - View task status
- ✅ SEARCH_TASKS - Search tasks
- ✅ DELAY_TASK - Postpone tasks
- ✅ ADD_NOTE - Add task notes
- ✅ CANCEL_TASK - Cancel tasks
- ✅ BULK_COMPLETE - Mark multiple done
- ✅ CLEAR_TASKS - Delete tasks
- ✅ ARCHIVE_TASKS - Archive completed

### New Intents Needed
- 🆕 MODIFY_TASK - Change title/description
- 🆕 REASSIGN_TASK - Change assignee
- 🆕 CHANGE_PRIORITY - Update priority
- 🆕 CHANGE_DEADLINE - Update deadline
- 🆕 ADD_TAGS - Add tags to task
- 🆕 REMOVE_TAGS - Remove tags from task
- 🆕 ADD_SUBTASK - Add subtask
- 🆕 COMPLETE_SUBTASK - Mark subtask done
- 🆕 ADD_DEPENDENCY - Add task dependency
- 🆕 REMOVE_DEPENDENCY - Remove dependency
- 🆕 CHANGE_STATUS - Update task status directly
- 🆕 DUPLICATE_TASK - Clone existing task
- 🆕 SPLIT_TASK - Break task into multiple

## Implementation Steps

### Step 1: Update Intent System (src/ai/intent.py)

#### 1.1 Add New Intent Enums
Add to `class UserIntent(str, Enum)`:

```python
# Task modification operations (NEW)
MODIFY_TASK = "modify_task"              # "change the title", "update description"
REASSIGN_TASK = "reassign_task"          # "reassign to Sarah", "give TASK-001 to John"
CHANGE_PRIORITY = "change_priority"      # "make this urgent", "lower priority"
CHANGE_DEADLINE = "change_deadline"      # "extend deadline to tomorrow"
CHANGE_STATUS = "change_status"          # "move to in_progress", "mark as blocked"
ADD_TAGS = "add_tags"                    # "tag this as frontend"
REMOVE_TAGS = "remove_tags"              # "remove urgent tag"
ADD_SUBTASK = "add_subtask"              # "add subtask to design mockup"
COMPLETE_SUBTASK = "complete_subtask"    # "mark subtask 1 done"
ADD_DEPENDENCY = "add_dependency"        # "TASK-001 depends on TASK-002"
REMOVE_DEPENDENCY = "remove_dependency"  # "remove dependency"
DUPLICATE_TASK = "duplicate_task"        # "duplicate this task for Sarah"
SPLIT_TASK = "split_task"                # "split this into 2 tasks"
```

#### 1.2 Update AI Classification Prompt
In `async def _ai_classify()`, update the prompt to include:

```python
**TASK MODIFICATION:**
- modify_task: Change task title or description. Keywords: "change title", "update description", "rename", "edit task".
- reassign_task: Change who's assigned. Keywords: "reassign", "give to [name]", "assign to", "transfer to".
- change_priority: Update priority level. Keywords: "make urgent", "high priority", "lower priority", "priority to medium".
- change_deadline: Update deadline. Keywords: "extend deadline", "push deadline", "due tomorrow", "deadline Friday".
- change_status: Directly update status. Keywords: "move to in_progress", "mark as blocked", "status to review".
- add_tags: Add tags/labels. Keywords: "tag as", "label", "add tag".
- remove_tags: Remove tags. Keywords: "remove tag", "untag", "delete tag".

**TASK STRUCTURE:**
- add_subtask: Add subtask to task. Keywords: "add subtask", "break down into", "add step".
- complete_subtask: Mark subtask done. Keywords: "subtask done", "finish subtask #1".
- add_dependency: Link tasks as dependencies. Keywords: "depends on", "blocked by", "after TASK-X".
- remove_dependency: Remove dependency link. Keywords: "remove dependency", "unblock".
- duplicate_task: Clone a task. Keywords: "duplicate", "copy task", "create similar".
- split_task: Break into multiple tasks. Keywords: "split into", "break into 2 tasks".

**CRITICAL: Task ID Required**
For modification operations, user must reference a task either by:
- Task ID: "TASK-001"
- Context: "this task" (if in conversation about a task)
- Implicit: "the login bug" (AI should extract from recent context)

If no task reference found, confidence should be LOW (<0.5) and suggest asking for task ID.
```

#### 1.3 Update Extracted Data Processing
In `_post_process_data()`, add:

```python
# For modification operations, ensure task_id is present
modification_intents = [
    UserIntent.MODIFY_TASK,
    UserIntent.REASSIGN_TASK,
    UserIntent.CHANGE_PRIORITY,
    UserIntent.CHANGE_DEADLINE,
    UserIntent.CHANGE_STATUS,
    UserIntent.ADD_TAGS,
    UserIntent.REMOVE_TAGS,
    UserIntent.ADD_SUBTASK,
    UserIntent.COMPLETE_SUBTASK,
    UserIntent.ADD_DEPENDENCY,
    UserIntent.REMOVE_DEPENDENCY,
    UserIntent.DUPLICATE_TASK,
    UserIntent.SPLIT_TASK,
]

if intent in modification_intents:
    # Extract task IDs
    task_ids = re.findall(r'TASK-[\w\-]+', message, re.IGNORECASE)
    if task_ids:
        data["task_id"] = task_ids[0].upper()
        data["task_ids"] = [t.upper() for t in task_ids]

    # Extract values based on intent type
    if intent == UserIntent.REASSIGN_TASK:
        # Extract target person name
        for name in TEAM_NAMES:
            if name.lower() in message.lower():
                data["new_assignee"] = name.capitalize()
                break

    elif intent == UserIntent.CHANGE_PRIORITY:
        # Extract priority level
        priority_map = {
            "urgent": "urgent",
            "high": "high",
            "medium": "medium",
            "low": "low",
            "normal": "medium",
        }
        for key, value in priority_map.items():
            if key in message.lower():
                data["new_priority"] = value
                break

    elif intent == UserIntent.ADD_TAGS or intent == UserIntent.REMOVE_TAGS:
        # Extract tags
        tags = re.findall(r'tag(?:ged)? (?:as |with )?(\w+)', message.lower())
        if tags:
            data["tags"] = tags

    data["message"] = message
```

### Step 2: Update Handler (src/bot/handler.py)

#### 2.1 Add Handler Mappings
In `async def handle_message()`, add to intent_handlers dict:

```python
# Task modification operations (NEW)
UserIntent.MODIFY_TASK: self._handle_modify_task,
UserIntent.REASSIGN_TASK: self._handle_reassign_task,
UserIntent.CHANGE_PRIORITY: self._handle_change_priority,
UserIntent.CHANGE_DEADLINE: self._handle_change_deadline,
UserIntent.CHANGE_STATUS: self._handle_change_status,
UserIntent.ADD_TAGS: self._handle_add_tags,
UserIntent.REMOVE_TAGS: self._handle_remove_tags,
UserIntent.ADD_SUBTASK: self._handle_add_subtask_intent,
UserIntent.COMPLETE_SUBTASK: self._handle_complete_subtask_intent,
UserIntent.ADD_DEPENDENCY: self._handle_add_dependency,
UserIntent.REMOVE_DEPENDENCY: self._handle_remove_dependency,
UserIntent.DUPLICATE_TASK: self._handle_duplicate_task,
UserIntent.SPLIT_TASK: self._handle_split_task,
```

#### 2.2 Implement Handler Methods
Add new handler methods (after existing handlers, around line 2100):

```python
async def _handle_modify_task(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle task modification (title/description)."""
    task_id = data.get("task_id")

    if not task_id:
        return "Which task would you like to modify? Please provide the task ID (e.g., TASK-001).", None

    # Get task
    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    # AI extracts what to change
    from .ai.clarifier import get_clarifier
    clarifier = get_clarifier()

    modification = await clarifier.extract_modification_details(
        message=message,
        current_task=task
    )

    updates = {}
    if modification.get("new_title"):
        updates["title"] = modification["new_title"]
    if modification.get("new_description"):
        updates["description"] = modification["new_description"]

    if not updates:
        return f"What would you like to change about {task_id}? (title or description)", None

    # Update task
    success = await self.task_repo.update(task_id, updates)
    if success:
        # Sync to sheets
        await self.sheets.update_task(task_id, updates)

        # Post to Discord
        changes_text = ", ".join([f"{k} updated" for k in updates.keys()])
        await self.discord.post_task_update(
            task_id=task_id,
            updates=updates,
            updated_by=user_name,
            update_type="modification"
        )

        return f"✅ Updated {task_id}: {changes_text}", None

    return f"Failed to update {task_id}.", None


async def _handle_reassign_task(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle task reassignment."""
    task_id = data.get("task_id")
    new_assignee = data.get("new_assignee")

    if not task_id:
        return "Which task would you like to reassign? Please provide the task ID.", None

    if not new_assignee:
        return f"Who should {task_id} be reassigned to?", None

    # Get task
    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    old_assignee = task.get("assignee", "unassigned")

    # Get team member info
    from config.team import TEAM_MEMBERS
    team_member = TEAM_MEMBERS.get(new_assignee.lower())

    updates = {
        "assignee": new_assignee,
        "assignee_telegram_id": team_member.get("telegram_id") if team_member else None,
        "assignee_discord_id": team_member.get("discord_id") if team_member else None,
        "assignee_email": team_member.get("email") if team_member else None,
    }

    # Update
    success = await self.task_repo.update(task_id, updates)
    if success:
        await self.sheets.update_task(task_id, updates)

        # Notify on Discord
        await self.discord.post_task_update(
            task_id=task_id,
            updates={"assignee": f"{old_assignee} → {new_assignee}"},
            updated_by=user_name,
            update_type="reassignment"
        )

        return f"✅ Reassigned {task_id} from {old_assignee} to {new_assignee}", None

    return f"Failed to reassign {task_id}.", None


async def _handle_change_priority(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle priority change."""
    task_id = data.get("task_id")
    new_priority = data.get("new_priority")

    if not task_id:
        return "Which task's priority would you like to change?", None

    if not new_priority:
        return f"What priority level for {task_id}? (urgent/high/medium/low)", None

    # Get task
    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    old_priority = task.get("priority", "medium")

    updates = {"priority": new_priority}
    success = await self.task_repo.update(task_id, updates)

    if success:
        await self.sheets.update_task(task_id, updates)

        # Map priority to Discord tags
        priority_emoji = {
            "urgent": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }

        await self.discord.post_task_update(
            task_id=task_id,
            updates={"priority": f"{priority_emoji.get(old_priority, '')} {old_priority} → {priority_emoji.get(new_priority, '')} {new_priority}"},
            updated_by=user_name,
            update_type="priority_change"
        )

        return f"✅ Changed {task_id} priority: {old_priority} → {new_priority}", None

    return f"Failed to update priority for {task_id}.", None


async def _handle_change_deadline(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle deadline change."""
    from .ai.clarifier import get_clarifier

    task_id = data.get("task_id")
    if not task_id:
        return "Which task's deadline would you like to change?", None

    # Get task
    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    # Extract new deadline using AI
    clarifier = get_clarifier()
    new_deadline = await clarifier.parse_deadline(message)

    if not new_deadline:
        return f"What's the new deadline for {task_id}?", None

    old_deadline = task.get("deadline", "not set")

    updates = {"deadline": new_deadline}
    success = await self.task_repo.update(task_id, updates)

    if success:
        await self.sheets.update_task(task_id, updates)

        await self.discord.post_task_update(
            task_id=task_id,
            updates={"deadline": f"{old_deadline} → {new_deadline}"},
            updated_by=user_name,
            update_type="deadline_change"
        )

        return f"✅ Updated {task_id} deadline: {new_deadline}", None

    return f"Failed to update deadline for {task_id}.", None


async def _handle_change_status(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle status change."""
    task_id = data.get("task_id")
    new_status = data.get("new_status")

    if not task_id:
        return "Which task's status would you like to change?", None

    # Valid statuses
    valid_statuses = [
        "pending", "in_progress", "in_review", "awaiting_validation",
        "needs_revision", "completed", "cancelled", "blocked",
        "delayed", "undone", "on_hold", "waiting", "needs_info", "overdue"
    ]

    if not new_status:
        # Try to extract from message
        for status in valid_statuses:
            if status.replace("_", " ") in message.lower():
                new_status = status
                break

    if not new_status:
        status_list = ", ".join(valid_statuses[:7]) + "..."
        return f"What status for {task_id}? Options: {status_list}", None

    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    old_status = task.get("status", "pending")

    updates = {"status": new_status}
    success = await self.task_repo.update(task_id, updates)

    if success:
        await self.sheets.update_task(task_id, updates)

        await self.discord.post_task_update(
            task_id=task_id,
            updates={"status": f"{old_status} → {new_status}"},
            updated_by=user_name,
            update_type="status_change"
        )

        return f"✅ Changed {task_id} status: {old_status} → {new_status}", None

    return f"Failed to update status for {task_id}.", None


async def _handle_add_tags(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle adding tags."""
    task_id = data.get("task_id")
    new_tags = data.get("tags", [])

    if not task_id:
        return "Which task would you like to tag?", None

    if not new_tags:
        return f"What tags should be added to {task_id}?", None

    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    current_tags = task.get("tags", [])
    if isinstance(current_tags, str):
        current_tags = [t.strip() for t in current_tags.split(",") if t.strip()]

    # Add new tags (avoid duplicates)
    updated_tags = list(set(current_tags + new_tags))

    updates = {"tags": updated_tags}
    success = await self.task_repo.update(task_id, updates)

    if success:
        await self.sheets.update_task(task_id, updates)

        await self.discord.post_task_update(
            task_id=task_id,
            updates={"tags": f"Added: {', '.join(new_tags)}"},
            updated_by=user_name,
            update_type="tags_added"
        )

        return f"✅ Added tags to {task_id}: {', '.join(new_tags)}", None

    return f"Failed to add tags to {task_id}.", None


async def _handle_remove_tags(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle removing tags."""
    task_id = data.get("task_id")
    tags_to_remove = data.get("tags", [])

    if not task_id:
        return "Which task would you like to remove tags from?", None

    if not tags_to_remove:
        return f"Which tags should be removed from {task_id}?", None

    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    current_tags = task.get("tags", [])
    if isinstance(current_tags, str):
        current_tags = [t.strip() for t in current_tags.split(",") if t.strip()]

    # Remove specified tags
    updated_tags = [t for t in current_tags if t.lower() not in [r.lower() for r in tags_to_remove]]

    updates = {"tags": updated_tags}
    success = await self.task_repo.update(task_id, updates)

    if success:
        await self.sheets.update_task(task_id, updates)

        await self.discord.post_task_update(
            task_id=task_id,
            updates={"tags": f"Removed: {', '.join(tags_to_remove)}"},
            updated_by=user_name,
            update_type="tags_removed"
        )

        return f"✅ Removed tags from {task_id}: {', '.join(tags_to_remove)}", None

    return f"Failed to remove tags from {task_id}.", None


async def _handle_add_subtask_intent(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle adding subtask via natural language."""
    task_id = data.get("task_id")
    subtask_title = data.get("subtask_title")

    if not task_id:
        return "Which task should this subtask be added to?", None

    if not subtask_title:
        # Try to extract from message
        patterns = [
            r'add subtask[:\s]+"([^"]+)"',
            r'subtask[:\s]+(.+?)(?:\.|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                subtask_title = match.group(1).strip()
                break

    if not subtask_title:
        return f"What should the subtask for {task_id} be?", None

    # Add subtask
    subtask = await self.task_repo.add_subtask(
        task_id=task_id,
        title=subtask_title,
        description=""
    )

    if subtask:
        # Sync to sheets
        await self.sheets.sync_subtasks(task_id)

        await self.discord.post_task_update(
            task_id=task_id,
            updates={"subtask": f"Added: {subtask_title}"},
            updated_by=user_name,
            update_type="subtask_added"
        )

        return f"✅ Added subtask to {task_id}: {subtask_title}", None

    return f"Failed to add subtask to {task_id}.", None


async def _handle_complete_subtask_intent(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle completing subtask via natural language."""
    task_id = data.get("task_id")
    subtask_number = data.get("subtask_number")

    if not task_id:
        return "Which task's subtask would you like to complete?", None

    if not subtask_number:
        # Try to extract subtask number
        match = re.search(r'subtask\s+#?(\d+)', message, re.IGNORECASE)
        if match:
            subtask_number = int(match.group(1))

    if not subtask_number:
        return f"Which subtask number for {task_id}?", None

    # Mark subtask complete
    success = await self.task_repo.complete_subtask(task_id, subtask_number)

    if success:
        await self.sheets.sync_subtasks(task_id)

        await self.discord.post_task_update(
            task_id=task_id,
            updates={"subtask": f"Completed subtask #{subtask_number}"},
            updated_by=user_name,
            update_type="subtask_completed"
        )

        return f"✅ Marked subtask #{subtask_number} complete on {task_id}", None

    return f"Failed to complete subtask for {task_id}.", None


async def _handle_add_dependency(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle adding task dependency."""
    task_ids = data.get("task_ids", [])

    if len(task_ids) < 2:
        return "Please specify two tasks (e.g., 'TASK-001 depends on TASK-002')", None

    dependent_task = task_ids[0]
    dependency_task = task_ids[1]

    # Add dependency
    success = await self.task_repo.add_dependency(dependent_task, dependency_task)

    if success:
        await self.discord.post_task_update(
            task_id=dependent_task,
            updates={"dependency": f"Now depends on {dependency_task}"},
            updated_by=user_name,
            update_type="dependency_added"
        )

        return f"✅ {dependent_task} now depends on {dependency_task}", None

    return f"Failed to add dependency.", None


async def _handle_remove_dependency(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle removing task dependency."""
    task_ids = data.get("task_ids", [])

    if len(task_ids) < 2:
        return "Please specify two tasks to unlink", None

    dependent_task = task_ids[0]
    dependency_task = task_ids[1]

    # Remove dependency
    success = await self.task_repo.remove_dependency(dependent_task, dependency_task)

    if success:
        await self.discord.post_task_update(
            task_id=dependent_task,
            updates={"dependency": f"Removed dependency on {dependency_task}"},
            updated_by=user_name,
            update_type="dependency_removed"
        )

        return f"✅ Removed dependency: {dependent_task} no longer depends on {dependency_task}", None

    return f"Failed to remove dependency.", None


async def _handle_duplicate_task(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle duplicating a task."""
    task_id = data.get("task_id")
    new_assignee = data.get("new_assignee")

    if not task_id:
        return "Which task would you like to duplicate?", None

    # Get original task
    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    # Create new task with same details
    new_task_data = {
        "title": f"{task.get('title')} (copy)",
        "description": task.get("description"),
        "priority": task.get("priority"),
        "task_type": task.get("task_type"),
        "assignee": new_assignee or task.get("assignee"),
        "deadline": task.get("deadline"),
        "estimated_effort": task.get("estimated_effort"),
        "tags": task.get("tags"),
        "acceptance_criteria": task.get("acceptance_criteria"),
        "created_by": user_name,
    }

    new_task = await self.task_processor.create_task(new_task_data)

    if new_task:
        return f"✅ Duplicated {task_id} as {new_task.get('task_id')}", None

    return f"Failed to duplicate {task_id}.", None


async def _handle_split_task(
    self, user_id: str, message: str, data: Dict, context: Dict, user_name: str
) -> Tuple[str, Optional[Dict]]:
    """Handle splitting a task into multiple tasks."""
    task_id = data.get("task_id")

    if not task_id:
        return "Which task would you like to split?", None

    # Get task
    task = await self.sheets.get_task_by_id(task_id)
    if not task:
        return f"Task {task_id} not found.", None

    # Use AI to suggest split
    from .ai.deepseek import get_deepseek_client
    deepseek = get_deepseek_client()

    breakdown = await deepseek.breakdown_task(
        title=task.get("title"),
        description=task.get("description"),
        priority=task.get("priority"),
    )

    if not breakdown.get("subtasks"):
        return f"Unable to determine how to split {task_id}. Please provide more details.", None

    # Show suggested split
    suggestions = "\n".join([
        f"{i+1}. {sub.get('title')}"
        for i, sub in enumerate(breakdown.get("subtasks", []))
    ])

    response = f"💡 Suggested split for {task_id}:\n\n{suggestions}\n\nCreate these as separate tasks? Reply 'yes' to proceed."

    # Store in context for confirmation
    return response, {
        "awaiting_split_confirm": True,
        "original_task_id": task_id,
        "split_tasks": breakdown.get("subtasks")
    }
```

### Step 3: Add Helper Methods to Clarifier (src/ai/clarifier.py)

Create new file or extend existing clarifier:

```python
async def extract_modification_details(
    self,
    message: str,
    current_task: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract what should be modified in a task."""

    prompt = f"""Extract modification details from this message:

    MESSAGE: "{message}"

    CURRENT TASK:
    Title: {current_task.get('title')}
    Description: {current_task.get('description')}

    What should be changed? Return JSON:
    {{
        "new_title": "new title if changing",
        "new_description": "new description if changing",
        "change_type": "title/description/both"
    }}
    """

    response = await self.deepseek.chat(
        messages=[
            {"role": "system", "content": "Extract task modification details."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return json.loads(response.choices[0].message.content)


async def parse_deadline(self, message: str) -> Optional[str]:
    """Parse deadline from natural language."""

    prompt = f"""Extract deadline from: "{message}"

    Return deadline in YYYY-MM-DD format or null if not found.
    Examples:
    - "tomorrow" → {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}
    - "next Friday" → next Friday's date
    - "in 3 days" → 3 days from now

    Return ONLY the date in YYYY-MM-DD format or null.
    """

    response = await self.deepseek.chat(
        messages=[
            {"role": "system", "content": "Parse dates from natural language."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    result = response.choices[0].message.content.strip()
    if result.lower() == "null":
        return None
    return result
```

### Step 4: Add Repository Methods (src/database/repositories/tasks.py)

Add methods if they don't exist:

```python
async def add_subtask(
    self,
    task_id: str,
    title: str,
    description: str = ""
) -> Optional[SubtaskDB]:
    """Add subtask to a task."""
    async with self.db.session() as session:
        # Get task
        task = await self.get_by_id(task_id)
        if not task:
            return None

        # Get next order number
        existing_subtasks = await session.execute(
            select(SubtaskDB)
            .where(SubtaskDB.task_id == task.id)
            .order_by(SubtaskDB.order.desc())
        )
        last_subtask = existing_subtasks.first()
        next_order = (last_subtask[0].order + 1) if last_subtask else 1

        # Create subtask
        subtask = SubtaskDB(
            task_id=task.id,
            title=title,
            description=description,
            order=next_order,
            completed=False
        )

        session.add(subtask)
        await session.flush()

        # Mark task for sync
        await session.execute(
            update(TaskDB)
            .where(TaskDB.id == task.id)
            .values(needs_sheet_sync=True)
        )

        return subtask


async def complete_subtask(
    self,
    task_id: str,
    subtask_number: int
) -> bool:
    """Mark a subtask as complete."""
    async with self.db.session() as session:
        task = await self.get_by_id(task_id)
        if not task:
            return False

        # Get subtask by order number
        result = await session.execute(
            select(SubtaskDB)
            .where(
                SubtaskDB.task_id == task.id,
                SubtaskDB.order == subtask_number
            )
        )
        subtask = result.scalar_one_or_none()

        if not subtask:
            return False

        subtask.completed = True
        subtask.completed_at = datetime.now()

        # Mark task for sync
        await session.execute(
            update(TaskDB)
            .where(TaskDB.id == task.id)
            .values(needs_sheet_sync=True)
        )

        return True


async def add_dependency(
    self,
    dependent_task_id: str,
    dependency_task_id: str
) -> bool:
    """Add dependency: dependent_task depends on dependency_task."""
    async with self.db.session() as session:
        dependent = await self.get_by_id(dependent_task_id)
        dependency = await self.get_by_id(dependency_task_id)

        if not dependent or not dependency:
            return False

        # Check if dependency already exists
        existing = await session.execute(
            select(TaskDependencyDB)
            .where(
                TaskDependencyDB.task_id == dependent.id,
                TaskDependencyDB.depends_on_task_id == dependency.id
            )
        )

        if existing.scalar_one_or_none():
            return True  # Already exists

        # Create dependency
        dep = TaskDependencyDB(
            task_id=dependent.id,
            depends_on_task_id=dependency.id
        )

        session.add(dep)
        return True


async def remove_dependency(
    self,
    dependent_task_id: str,
    dependency_task_id: str
) -> bool:
    """Remove dependency."""
    async with self.db.session() as session:
        dependent = await self.get_by_id(dependent_task_id)
        dependency = await self.get_by_id(dependency_task_id)

        if not dependent or not dependency:
            return False

        await session.execute(
            delete(TaskDependencyDB)
            .where(
                TaskDependencyDB.task_id == dependent.id,
                TaskDependencyDB.depends_on_task_id == dependency.id
            )
        )

        return True
```

### Step 5: Update Discord Integration (src/integrations/discord.py)

Add method for task update notifications:

```python
async def post_task_update(
    self,
    task_id: str,
    updates: Dict[str, str],
    updated_by: str,
    update_type: str
) -> bool:
    """Post task update notification to Discord."""

    update_emoji = {
        "modification": "✏️",
        "reassignment": "👤",
        "priority_change": "⚡",
        "deadline_change": "📅",
        "status_change": "🔄",
        "tags_added": "🏷️",
        "tags_removed": "🏷️",
        "subtask_added": "➕",
        "subtask_completed": "✅",
        "dependency_added": "🔗",
        "dependency_removed": "🔓",
    }

    emoji = update_emoji.get(update_type, "📝")

    changes_text = "\n".join([f"**{k}:** {v}" for k, v in updates.items()])

    embed = {
        "title": f"{emoji} Task Updated: {task_id}",
        "description": changes_text,
        "color": 3447003,  # Blue
        "footer": {
            "text": f"Updated by {updated_by}"
        },
        "timestamp": datetime.now().isoformat()
    }

    # Post to appropriate channel
    return await self.post_to_tasks_channel(embeds=[embed])
```

### Step 6: Update FEATURES.md

Add comprehensive documentation section:

```markdown
## 🔧 Comprehensive Task Operations (v2.2+)

**Status:** ✅ Production

The bot now supports comprehensive task management operations through natural language - no slash commands required.

### Task Modification

| Operation | Natural Language Examples | What Happens |
|-----------|--------------------------|--------------|
| **Modify Title** | "change the title of TASK-001 to 'Fix login bug'" | Updates task title |
| **Modify Description** | "update TASK-001 description: needs API integration" | Updates description |
| **Reassign Task** | "reassign TASK-001 to Sarah", "give the login task to John" | Changes assignee |
| **Change Priority** | "make TASK-001 urgent", "lower priority of TASK-002" | Updates priority level |
| **Change Deadline** | "extend TASK-001 deadline to Friday", "push deadline to next week" | Updates due date |
| **Change Status** | "move TASK-001 to in_progress", "mark TASK-002 as blocked" | Updates status |

### Tags & Labels

| Operation | Examples |
|-----------|----------|
| **Add Tags** | "tag TASK-001 as frontend", "label this as urgent" |
| **Remove Tags** | "remove urgent tag from TASK-001", "untag frontend" |

### Subtasks

| Operation | Examples |
|-----------|----------|
| **Add Subtask** | "add subtask to TASK-001: design mockup" |
| **Complete Subtask** | "mark subtask 1 done on TASK-001", "subtask #2 complete" |

### Dependencies

| Operation | Examples |
|-----------|----------|
| **Add Dependency** | "TASK-001 depends on TASK-002", "TASK-003 is blocked by TASK-001" |
| **Remove Dependency** | "remove dependency between TASK-001 and TASK-002" |

### Advanced Operations

| Operation | Examples |
|-----------|----------|
| **Duplicate Task** | "duplicate TASK-001 for Sarah" |
| **Split Task** | "split TASK-001 into 2 tasks" (AI suggests breakdown) |

### Implementation Details

- **AI-Powered:** All operations use DeepSeek AI for intent detection
- **Context-Aware:** Can reference "this task" in ongoing conversations
- **Flexible Phrasing:** Natural language works for all operations
- **Auto-Sync:** Changes sync to PostgreSQL, Google Sheets, and Discord
- **Audit Trail:** All changes logged with user and timestamp

**Files:**
- Intent detection: `src/ai/intent.py`
- Handlers: `src/bot/handler.py`
- Repository: `src/database/repositories/tasks.py`
- Discord notifications: `src/integrations/discord.py`
```

### Step 7: Testing Plan

Use `test_full_loop.py` for validation:

```bash
# Test 1: Modify task
python test_full_loop.py full-test "change the title of TASK-001 to 'Updated title'"

# Test 2: Reassign task
python test_full_loop.py full-test "reassign TASK-001 to Mayank"

# Test 3: Change priority
python test_full_loop.py full-test "make TASK-001 urgent"

# Test 4: Change deadline
python test_full_loop.py full-test "extend TASK-001 deadline to Friday"

# Test 5: Add tags
python test_full_loop.py full-test "tag TASK-001 as frontend"

# Test 6: Add subtask
python test_full_loop.py full-test "add subtask to TASK-001: write tests"

# Verify in Discord
python test_full_loop.py read-discord

# Verify in database
python test_full_loop.py read-tasks
```

## Deployment Workflow

1. **Implement changes locally**
2. **Test with test_full_loop.py**
3. **Deploy to Railway:**
   ```bash
   railway redeploy -s boss-workflow --yes
   ```
4. **Wait for deployment:**
   ```bash
   railway logs -s boss-workflow | tail -30
   ```
5. **Test live:**
   ```bash
   python test_full_loop.py full-test "test message"
   ```
6. **Iterate until perfect**

## Success Criteria

- ✅ All new intents detected correctly by AI
- ✅ All handler methods implemented
- ✅ Changes sync to database, Sheets, and Discord
- ✅ Natural language examples work as expected
- ✅ test_full_loop.py validates all operations
- ✅ No errors in Railway logs
- ✅ FEATURES.md updated with documentation

## Estimated Implementation Time

- Step 1 (Intent System): 30 minutes
- Step 2 (Handlers): 90 minutes
- Step 3 (Clarifier): 20 minutes
- Step 4 (Repository): 30 minutes
- Step 5 (Discord): 15 minutes
- Step 6 (Documentation): 15 minutes
- Step 7 (Testing): 30 minutes

**Total:** ~3.5 hours of focused work

## Notes

- Follow existing code patterns in handler.py
- Use existing deepseek methods where possible
- Ensure all changes trigger sheets/discord sync
- Test incrementally after each step
- Use test_full_loop.py for validation throughout
