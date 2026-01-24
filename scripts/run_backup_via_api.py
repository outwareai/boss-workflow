#!/usr/bin/env python3
"""
Trigger OAuth token backup via Railway API endpoint.

This script calls the Railway-hosted API to run the backup,
which avoids database connection issues from local machines.
"""

import requests
import sys
import time

# Railway production URL
BASE_URL = "https://boss-workflow-production.up.railway.app"

def trigger_backup():
    """Trigger backup via API endpoint."""
    print("[INFO] Triggering OAuth token backup via Railway API...")
    print(f"[INFO] Endpoint: {BASE_URL}/api/admin/backup-oauth-tokens")
    print()

    try:
        response = requests.post(
            f"{BASE_URL}/api/admin/backup-oauth-tokens",
            timeout=120  # 2 minute timeout for backup operation
        )

        if response.status_code == 200:
            data = response.json()
            print("[SUCCESS] Backup completed successfully!")
            print()
            print(f"Backup file: {data.get('filename', 'N/A')}")
            print(f"Token count: {data.get('token_count', 'N/A')}")
            print(f"Timestamp: {data.get('timestamp', 'N/A')}")
            print()
            print("[CRITICAL] Next steps:")
            print("1. Download backup from Railway logs")
            print("2. Store in 1Password vault: 'Boss Workflow Backups'")
            print("3. Do NOT commit to git")
            return True
        else:
            print(f"[ERROR] Backup failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print("[ERROR] Backup timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to trigger backup: {e}")
        return False


if __name__ == "__main__":
    success = trigger_backup()
    sys.exit(0 if success else 1)
