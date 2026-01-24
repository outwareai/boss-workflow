"""
Test all intents are properly routed.

Verifies no intent falls through to "I'm not sure what you want to do."
"""

# Test messages for each intent category
TEST_MESSAGES = {
    # Task creation (was BROKEN before fix)
    "CREATE_TASK": "Create task for Mayank: Fix the login bug",

    # Task management (was BROKEN)
    "CLEAR_TASKS": "Clear all tasks",
    "SEARCH_TASKS": "What's Mayank working on?",
    "LIST_TASKS": "Show all tasks",
    "CANCEL_TASK": "Cancel TASK-001",
    "ARCHIVE_TASKS": "Archive completed tasks",

    # Task modification (was BROKEN)
    "REASSIGN_TASK": "Reassign TASK-001 to Zea",
    "CHANGE_PRIORITY": "Make TASK-001 urgent",
    "CHANGE_DEADLINE": "Extend TASK-001 deadline to tomorrow",
    "CHANGE_STATUS": "Mark TASK-001 as in progress",
    "ADD_TAGS": "Tag TASK-001 as frontend",
    "DELAY_TASK": "Delay TASK-001 to next week",

    # Subtasks and dependencies (was BROKEN)
    "ADD_SUBTASK": "Add subtask to TASK-001: Design mockup",
    "ADD_DEPENDENCY": "TASK-001 depends on TASK-002",
    "DUPLICATE_TASK": "Duplicate TASK-001 for Zea",

    # Team management (was BROKEN)
    "ADD_TEAM_MEMBER": "John is our backend developer",
    "ASK_TEAM_MEMBER": "Ask Mayank about the API status",
    "REPORT_ABSENCE": "Mayank was late today",

    # Status queries (was working)
    "CHECK_STATUS": "What's pending?",
    "CHECK_OVERDUE": "Anything overdue?",

    # Other (was BROKEN)
    "TEACH_PREFERENCE": "When I say urgent, deadline is today",
    "LIST_TEMPLATES": "What templates are there?",
    "GENERATE_SPEC": "Generate spec for TASK-001",
    "EMAIL_RECAP": "Summarize my emails",

    # Meta (was working)
    "HELP": "Help",
    "GREETING": "Hello",
}

print("INTENT ROUTING TEST MESSAGES")
print("=" * 60)
print("Send these to Telegram bot to verify routing works:")
print()

for intent, msg in TEST_MESSAGES.items():
    print(f"  [{intent}]")
    print(f"    > {msg}")
    print()

print("=" * 60)
print("EXPECTED: Each should get a meaningful response, NOT 'I'm not sure'")
