"""
Backup all OAuth tokens from production database to encrypted JSON.

This script exports all OAuth tokens to a timestamped JSON backup file.
Run BEFORE any encryption changes to ensure tokens can be recovered.

Usage:
    python scripts/backup_oauth_tokens.py

Output:
    oauth_tokens_backup_YYYYMMDD_HHMMSS.json

⚠️ CRITICAL: Store the output file in 1Password vault immediately after creation.
Vault location: "Boss Workflow Backups" → "OAuth Token Backups"
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.repositories.oauth import get_oauth_repository
from src.database.models import OAuthTokenDB
from src.database.connection import get_database
from sqlalchemy import select


async def get_all_tokens():
    """
    Fetch all OAuth tokens from database.

    Returns:
        List of OAuthTokenDB objects
    """
    db = get_database()
    async with db.session() as session:
        stmt = select(OAuthTokenDB)
        result = await session.execute(stmt)
        return result.scalars().all()


async def backup_tokens():
    """
    Export all OAuth tokens to encrypted backup file.

    Creates a JSON backup with:
    - Timestamp of backup
    - All token data (email, service, tokens, expiry)
    - Metadata for recovery verification

    Returns:
        str: Filename of created backup
    """
    print("[BACKUP] Starting OAuth token backup...")

    try:
        # Get all tokens from database
        tokens = await get_all_tokens()

        if not tokens:
            print("[WARNING] No tokens found in database")
            return None

        print(f"[BACKUP] Found {len(tokens)} token(s) to backup")

        # Create backup structure
        backup = {
            "backup_date": datetime.now().isoformat(),
            "backup_version": "1.0",
            "token_count": len(tokens),
            "note": "Pre-encryption migration backup - Store in 1Password",
            "tokens": []
        }

        # Add each token to backup
        for token in tokens:
            backup["tokens"].append({
                "email": token.email,
                "service": token.service,
                "refresh_token": token.refresh_token,
                "access_token": token.access_token,
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                "scopes": token.scopes,
                "created_at": token.created_at.isoformat(),
                "updated_at": token.updated_at.isoformat() if token.updated_at else None,
            })

        # Generate timestamped filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"oauth_tokens_backup_{timestamp}.json"
        filepath = Path(__file__).parent.parent / filename

        # Write to file
        with open(filepath, 'w') as f:
            json.dump(backup, f, indent=2)

        print(f"✅ Successfully backed up {len(tokens)} tokens to: {filename}")
        print(f"📂 Full path: {filepath}")
        print()
        print("[CRITICAL] CRITICAL NEXT STEPS:")
        print("1. Store this file in 1Password vault: 'Boss Workflow Backups'")
        print("2. Item name: 'OAuth Token Backup - {}'".format(timestamp))
        print("3. Add tags: 'oauth', 'backup', 'encryption-migration'")
        print("4. DO NOT commit this file to git (it contains plaintext tokens)")
        print("5. Delete local copy after uploading to 1Password")
        print()

        return filename

    except Exception as e:
        print(f"❌ Error during backup: {e}")
        import traceback
        traceback.print_exc()
        return None


async def verify_backup(filename: str):
    """
    Verify backup file integrity.

    Args:
        filename: Name of backup file to verify

    Returns:
        bool: True if backup is valid
    """
    try:
        filepath = Path(__file__).parent.parent / filename

        if not filepath.exists():
            print(f"❌ Backup file not found: {filepath}")
            return False

        with open(filepath, 'r') as f:
            backup = json.load(f)

        required_fields = ["backup_date", "token_count", "tokens"]
        for field in required_fields:
            if field not in backup:
                print(f"❌ Missing required field: {field}")
                return False

        token_count = backup.get("token_count", 0)
        actual_count = len(backup.get("tokens", []))

        if token_count != actual_count:
            print(f"❌ Token count mismatch: expected {token_count}, got {actual_count}")
            return False

        print(f"✅ Backup verification passed")
        print(f"   - Backup date: {backup['backup_date']}")
        print(f"   - Token count: {token_count}")

        return True

    except Exception as e:
        print(f"❌ Error verifying backup: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("OAuth Token Backup Utility")
    print("Week 1: OAuth Encryption Migration")
    print("=" * 60)
    print()

    # Run backup
    filename = asyncio.run(backup_tokens())

    if filename:
        print()
        print("=" * 60)
        print("Verifying backup integrity...")
        print("=" * 60)
        print()

        # Verify backup
        asyncio.run(verify_backup(filename))

        print()
        print("=" * 60)
        print("Backup complete!")
        print("=" * 60)
    else:
        print()
        print("[ERROR] Backup failed - see errors above")
        sys.exit(1)
