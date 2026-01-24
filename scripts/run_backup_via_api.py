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

            # Save backup data locally
            if 'backup_data' in data:
                import json
                from pathlib import Path

                backup_dir = Path.cwd() / "backups"
                backup_dir.mkdir(exist_ok=True)
                local_file = backup_dir / f"oauth_tokens_backup_{data['timestamp']}.json"

                with open(local_file, 'w') as f:
                    json.dump(data['backup_data'], f, indent=2)

                print()
                print(f"[SAVED] Backup saved locally to: {local_file}")

            print()
            print("[CRITICAL] Next steps:")
            print(f"1. Store {local_file} in 1Password vault: 'Boss Workflow Backups'")
            print("2. Item name: 'OAuth Token Backup - {}'".format(data.get('timestamp', 'N/A')))
            print("3. Add tags: 'oauth', 'backup', 'encryption-migration'")
            print("4. Do NOT commit to git")
            print(f"5. Delete local copy after uploading: {local_file}")
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
