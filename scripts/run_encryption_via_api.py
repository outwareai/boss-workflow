#!/usr/bin/env python3
"""
Trigger OAuth encryption migration via Railway API endpoint.

This script calls the Railway-hosted API to run the gradual encryption migration,
which avoids database connection issues from local machines.
"""

import requests
import sys
import time

# Railway production URL
BASE_URL = "https://boss-workflow-production.up.railway.app"

def trigger_encryption(mode="gradual"):
    """Trigger encryption migration via API endpoint."""
    print(f"[INFO] Triggering OAuth encryption migration (mode={mode})...")
    print(f"[INFO] Endpoint: {BASE_URL}/api/admin/encrypt-oauth-tokens")
    print()

    try:
        response = requests.post(
            f"{BASE_URL}/api/admin/encrypt-oauth-tokens",
            json={"mode": mode},
            timeout=300  # 5 minute timeout for encryption operation
        )

        if response.status_code == 200:
            data = response.json()
            print(f"[SUCCESS] Encryption migration completed!")
            print()
            print(f"Status: {data.get('status', 'N/A')}")
            print(f"Mode: {data.get('mode', 'N/A')}")

            if 'stats' in data:
                stats = data['stats']
                print()
                print("[STATS] Migration Results:")
                print(f"  Total tokens: {stats.get('total', 0)}")
                print(f"  Already encrypted: {stats.get('already_encrypted', 0)}")
                print(f"  Newly encrypted: {stats.get('encrypted', 0)}")
                print(f"  Failed: {stats.get('failed', 0)}")
                print(f"  Plaintext remaining: {stats.get('plaintext', 0)}")
                print()

                # Calculate coverage
                total = stats.get('total', 0)
                if total > 0:
                    encrypted_count = stats.get('already_encrypted', 0) + stats.get('encrypted', 0)
                    coverage = (encrypted_count / total) * 100
                    print(f"[COVERAGE] {coverage:.1f}% of tokens encrypted ({encrypted_count}/{total})")

                    if coverage >= 100:
                        print("[SUCCESS] 100% encryption coverage achieved!")
                    elif coverage >= 80:
                        print("[WARNING] Partial encryption - some tokens remain plaintext")
                    else:
                        print("[ERROR] Low encryption coverage - review failed tokens")

            return True
        else:
            print(f"[ERROR] Encryption failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print("[ERROR] Encryption timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to trigger encryption: {e}")
        return False


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "gradual"
    success = trigger_encryption(mode)
    sys.exit(0 if success else 1)
