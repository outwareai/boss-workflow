"""
Team member lookup utilities.

Centralized functions for finding team member information including
Discord IDs, emails, and roles. This ensures consistent lookup across
the application.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TeamMemberInfo:
    """Team member information for task assignment."""
    name: str
    discord_id: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[str] = None
    role: Optional[str] = None
    calendar_id: Optional[str] = None


async def lookup_team_member(name: str) -> Optional[TeamMemberInfo]:
    """
    Look up team member by name from all sources.

    Search order:
    1. PostgreSQL database (fastest)
    2. Google Sheets Team tab (source of truth)
    3. config/team.py (local config)

    Args:
        name: Team member name (case-insensitive partial match)

    Returns:
        TeamMemberInfo if found, None otherwise
    """
    if not name:
        return None

    name_lower = name.strip().lower()

    # 1. Try database first (fastest)
    try:
        from ..database.repositories import get_team_repository
        team_repo = get_team_repository()
        member = await team_repo.find_member(name)
        if member:
            logger.debug(f"Found {name} in database")
            return TeamMemberInfo(
                name=member.name,
                discord_id=member.discord_id,
                email=member.email,
                telegram_id=member.telegram_id,
                role=member.role,
                calendar_id=getattr(member, 'calendar_id', None),
            )
    except Exception as e:
        logger.debug(f"Database lookup failed for {name}: {e}")

    # 2. Try Google Sheets (source of truth)
    try:
        from ..integrations.sheets import get_sheets_integration
        sheets = get_sheets_integration()
        team_members = await sheets.get_all_team_members()

        for member in team_members:
            # Handle various column name formats (some sheets have ' Name' with leading space)
            member_name = None
            for key in ["Name", " Name", "name", "Nickname", ""]:
                if key in member and member[key]:
                    member_name = str(member[key]).strip().lower()
                    break
            # Fallback to first column value
            if not member_name and member:
                first_key = list(member.keys())[0]
                if member[first_key]:
                    member_name = str(member[first_key]).strip().lower()

            if member_name and (member_name == name_lower or name_lower in member_name):
                logger.info(f"Found {name} in Sheets (matched: {member_name})")
                # Get values with flexible key matching
                discord_id = member.get("Discord ID") or member.get("discord_id") or member.get("Discord")
                return TeamMemberInfo(
                    name=member.get("Name") or member.get(" Name") or name,
                    discord_id=str(discord_id) if discord_id else None,
                    email=member.get("Email") or member.get("email"),
                    telegram_id=member.get("Telegram ID") or member.get("telegram_id"),
                    role=member.get("Role") or member.get("role"),
                    calendar_id=member.get("Calendar ID") or member.get("calendar_id"),
                )
    except Exception as e:
        logger.debug(f"Sheets lookup failed for {name}: {e}")

    # 3. Fallback to local config
    try:
        from config.team import get_default_team
        for member in get_default_team():
            member_name = member.get("name", "").lower()
            if member_name == name_lower or name_lower in member_name:
                logger.debug(f"Found {name} in config/team.py")
                return TeamMemberInfo(
                    name=member.get("name", name),
                    discord_id=member.get("discord_id"),
                    email=member.get("email"),
                    telegram_id=member.get("telegram_id"),
                    role=member.get("role"),
                    calendar_id=member.get("calendar_id"),
                )
    except Exception as e:
        logger.debug(f"Config lookup failed for {name}: {e}")

    logger.warning(f"Team member '{name}' not found in any source")
    return None


async def get_assignee_info(assignee_name: str) -> Dict[str, Any]:
    """
    Get all relevant assignee info for task creation.

    This is the main function to call when creating a task - it returns
    all the IDs needed for notifications across platforms.

    Args:
        assignee_name: Name of the assignee

    Returns:
        Dict with keys: discord_id, email, telegram_id, role, calendar_id
        All values may be None if not found
    """
    result = {
        "discord_id": None,
        "email": None,
        "telegram_id": None,
        "role": None,
        "calendar_id": None,
    }

    if not assignee_name:
        return result

    member = await lookup_team_member(assignee_name)
    if member:
        # Ensure IDs are strings (they may come as int from sheets)
        result["discord_id"] = str(member.discord_id) if member.discord_id else None
        result["email"] = member.email
        result["telegram_id"] = str(member.telegram_id) if member.telegram_id else None
        result["role"] = member.role
        result["calendar_id"] = member.calendar_id

    return result


async def get_role_for_assignee(assignee_name: str) -> Optional[str]:
    """
    Get the role for an assignee (used for Discord channel routing).

    Args:
        assignee_name: Name of the assignee

    Returns:
        Role string (e.g., "Developer", "Admin") or None
    """
    member = await lookup_team_member(assignee_name)
    return member.role if member else None


def validate_discord_id(discord_id) -> bool:
    """
    Validate that a Discord ID is a numeric user ID.

    Discord user IDs are 17-19 digit snowflakes.

    Args:
        discord_id: The ID to validate (can be str or int)

    Returns:
        True if valid numeric Discord ID
    """
    if not discord_id:
        return False

    # Convert to string if int
    discord_id_str = str(discord_id)

    # Remove any @ prefix
    clean_id = discord_id_str.lstrip('@')

    # Should be all digits and reasonable length
    return clean_id.isdigit() and 17 <= len(clean_id) <= 19
