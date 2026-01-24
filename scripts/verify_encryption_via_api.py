#!/usr/bin/env python3
"""
Verify OAuth token encryption via Railway API endpoint.

This script checks that all tokens in the database are encrypted.
"""

import requests
import sys

# Railway production URL
BASE_URL = "https://boss-workflow-production.up.railway.app"

def verify_encryption():
    """Verify encryption via API endpoint."""
    print("[INFO] Verifying OAuth token encryption...")
    print(f"[INFO] Endpoint: {BASE_URL}/api/admin/verify-oauth-encryption")
    print()

    try:
        response = requests.get(
            f"{BASE_URL}/api/admin/verify-oauth-encryption",
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            print(f"[SUCCESS] Verification completed!")
            print()

            if 'stats' in data:
                stats = data['stats']
                print("[STATS] Encryption Status:")
                print(f"  Total tokens: {stats.get('total', 0)}")
                print(f"  Encrypted: {stats.get('encrypted', 0)}")
                print(f"  Plaintext: {stats.get('plaintext', 0)}")
                print()

                # Calculate coverage
                total = stats.get('total', 0)
                if total > 0:
                    encrypted = stats.get('encrypted', 0)
                    coverage = (encrypted / total) * 100
                    print(f"[COVERAGE] {coverage:.1f}% of tokens encrypted ({encrypted}/{total})")

                    if coverage >= 100:
                        print("[SUCCESS] 100% encryption coverage - deployment complete!")
                        return True
                    else:
                        print(f"[WARNING] Only {coverage:.1f}% encrypted - some tokens remain plaintext")
                        if 'plaintext_tokens' in data:
                            print()
                            print("[PLAINTEXT] Tokens still unencrypted:")
                            for token in data['plaintext_tokens']:
                                print(f"  - {token}")
                        return False
                else:
                    print("[WARNING] No tokens found in database")
                    return True

            return True
        else:
            print(f"[ERROR] Verification failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"[ERROR] Failed to verify encryption: {e}")
        return False


if __name__ == "__main__":
    success = verify_encryption()
    sys.exit(0 if success else 1)
