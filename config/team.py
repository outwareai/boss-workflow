"""
Team member configuration.

This file defines the team members that will be synced to Google Sheets via /syncteam.

Structure (matches Team sheet columns):
- name: Name used for Telegram mentions (e.g., "Mayank fix the login bug")
- discord_id: Numeric Discord user ID for @mentions (e.g., "392400310108291092")
- email: Google email for Calendar/Tasks integration
- role: One of "Developer", "Marketing", "Admin" - determines Discord channel routing

Role → Discord Channel Routing:
- Developer → Dev category (forum, tasks, report, general)
- Marketing → Marketing category (when configured)
- Admin → Admin category (when configured)
"""

from typing import Dict, Any, List

# Valid roles for Discord channel routing (must match dropdown in Team sheet)
VALID_ROLES = ["Developer", "Marketing", "Admin"]

# Team members
# Add your team members here - each member needs:
# 1. name - How you'll mention them in Telegram
# 2. discord_id - Get this by: Discord Developer Mode → Right-click user → Copy ID
# 3. email - Their Google email for Calendar/Tasks
# 4. role - One of: Developer, Marketing, Admin
DEFAULT_TEAM_MEMBERS: List[Dict[str, Any]] = [
    {
        "name": "Mayank",
        "discord_id": "392400310108291092",
        "email": "coolmayank52@gmail.com",
        "role": "Developer",
    },
    {
        "name": "Minty",
        "discord_id": "834982814910775306",
        "email": "sutima2543@gmail.com",
        "role": "Admin",
    },
    # Add more team members as needed:
    # {
    #     "name": "Sarah",
    #     "discord_id": "123456789012345678",  # Get from Discord: Right-click → Copy ID
    #     "email": "sarah@example.com",
    #     "role": "Marketing",
    # },
]


def get_default_team() -> List[Dict[str, Any]]:
    """Get the default team configuration."""
    return DEFAULT_TEAM_MEMBERS


def get_valid_roles() -> List[str]:
    """Get list of valid roles for channel routing."""
    return VALID_ROLES
