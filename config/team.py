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
# 5. timezone - For attendance tracking (e.g., Asia/Kolkata, Asia/Bangkok)
# 6. work_start/work_end - Expected work hours (e.g., 09:00, 21:00)
# 7. hours_per_day/hours_per_week - Working hours
# 8. max_break - Max break time in minutes
# 9. grace_period - Late grace period in minutes
DEFAULT_TEAM_MEMBERS: List[Dict[str, Any]] = [
    {
        "name": "Mayank",
        "discord_id": "392400310108291092",
        "email": "coolmayank52@gmail.com",
        "role": "Developer",
        "timezone": "Asia/Kolkata",
        "work_start": "09:00",
        "work_end": "21:00",
        "hours_per_day": 12,
        "hours_per_week": 60,
        "max_break": 60,
        "grace_period": 15,
    },
    {
        "name": "Minty",
        "discord_id": "834982814910775306",
        "email": "sutima2543@gmail.com",
        "role": "Admin",
        "timezone": "Asia/Bangkok",
        "work_start": "09:00",
        "work_end": "21:00",
        "hours_per_day": 12,
        "hours_per_week": 60,
        "max_break": 60,
        "grace_period": 15,
    },
    {
        "name": "Zea",
        "discord_id": "222222222",
        "email": "zea@example.com",
        "role": "Admin",
        "timezone": "Asia/Bangkok",
        "work_start": "09:00",
        "work_end": "18:00",
        "hours_per_day": 8,
        "hours_per_week": 40,
        "max_break": 60,
        "grace_period": 15,
    },
    # Add more team members as needed:
    # {
    #     "name": "Sarah",
    #     "discord_id": "123456789012345678",  # Get from Discord: Right-click → Copy ID
    #     "email": "sarah@example.com",
    #     "role": "Marketing",
    #     "timezone": "Asia/Bangkok",
    #     "work_start": "09:00",
    #     "work_end": "18:00",
    #     "hours_per_day": 8,
    #     "hours_per_week": 40,
    #     "max_break": 60,
    #     "grace_period": 15,
    # },
]


def get_default_team() -> List[Dict[str, Any]]:
    """Get the default team configuration."""
    return DEFAULT_TEAM_MEMBERS


def get_valid_roles() -> List[str]:
    """Get list of valid roles for channel routing."""
    return VALID_ROLES
