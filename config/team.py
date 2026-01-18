"""
Team member configuration.

This file defines the default team members that will be loaded into the preferences system.
Update this file to add, remove, or modify team members.

Roles determine which Discord channel tasks are sent to:
- developer, dev, backend, frontend, engineer → Dev channel
- admin, administrator, manager, lead → Admin channel
- marketing, content, social, growth → Marketing channel
- design, designer, ui, ux, graphic → Design channel
"""

from typing import Dict, Any, List

# Valid roles for Discord channel routing
VALID_ROLES = [
    "developer",      # → Dev channel
    "backend",        # → Dev channel
    "frontend",       # → Dev channel
    "admin",          # → Admin channel
    "manager",        # → Admin channel
    "marketing",      # → Marketing channel
    "content",        # → Marketing channel (Graphic & Content)
    "designer",       # → Design channel
    "qa",             # → Dev channel
    "devops",         # → Dev channel
]

# Default team members
# Add your team members here with their contact information
DEFAULT_TEAM_MEMBERS: List[Dict[str, Any]] = [
    {
        "name": "Mayank",
        "username": "mayank",
        "role": "developer",  # Routes to Dev > #tasks
        "email": "colmayank52@gmail.com",
        "discord_username": "@MAYANK",
        "discord_id": "392400310108291092",  # Numeric Discord user ID for @mentions
        "telegram_id": "",  # Fill in if known
        "skills": ["development", "general"],
    },
    # Add more team members as needed:
    # {
    #     "name": "Sarah",
    #     "username": "sarah",
    #     "role": "designer",  # Routes to Graphic & Content channel
    #     "email": "sarah@example.com",
    #     "discord_username": "@sarah",
    #     "discord_id": "",  # Get from Discord: Right-click user > Copy ID
    #     "telegram_id": "",
    #     "skills": ["ui", "ux", "figma"],
    # },
    # {
    #     "name": "Mike",
    #     "username": "mike",
    #     "role": "admin",  # Routes to Admin > #tasks-admin
    #     "email": "mike@example.com",
    #     "discord_username": "@mike",
    #     "discord_id": "",
    #     "telegram_id": "",
    #     "skills": ["management", "operations"],
    # },
    # {
    #     "name": "Lisa",
    #     "username": "lisa",
    #     "role": "marketing",  # Routes to Marketing channel
    #     "email": "lisa@example.com",
    #     "discord_username": "@lisa",
    #     "discord_id": "",
    #     "telegram_id": "",
    #     "skills": ["social media", "content", "analytics"],
    # },
]


def get_default_team() -> List[Dict[str, Any]]:
    """Get the default team configuration."""
    return DEFAULT_TEAM_MEMBERS


def get_valid_roles() -> List[str]:
    """Get list of valid roles for channel routing."""
    return VALID_ROLES
