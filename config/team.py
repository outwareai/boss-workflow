"""
Team member configuration.

This file defines the default team members that will be loaded into the preferences system.
Update this file to add, remove, or modify team members.
"""

from typing import Dict, Any, List

# Default team members
# Add your team members here with their contact information
DEFAULT_TEAM_MEMBERS: List[Dict[str, Any]] = [
    {
        "name": "Mayank",
        "username": "mayank",
        "role": "developer",
        "email": "colmayank52@gmail.com",
        "discord_username": "@MAYANK",
        "discord_id": "392400310108291092",  # Numeric Discord user ID for @mentions
        "telegram_id": "",  # Fill in if known
        "skills": ["development", "general"],
    },
    # Add more team members as needed:
    # {
    #     "name": "John",
    #     "username": "john",
    #     "role": "backend specialist",
    #     "email": "john@example.com",
    #     "discord_username": "@john",
    #     "discord_id": "",
    #     "telegram_id": "",
    #     "skills": ["backend", "python", "databases"],
    # },
]


def get_default_team() -> List[Dict[str, Any]]:
    """Get the default team configuration."""
    return DEFAULT_TEAM_MEMBERS
