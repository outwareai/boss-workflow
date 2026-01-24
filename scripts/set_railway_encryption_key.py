#!/usr/bin/env python3
"""
Set ENCRYPTION_KEY in Railway production environment via web interface instructions.

Since Railway CLI requires interactive service selection, this script provides
the exact steps to set the variable via Railway dashboard.
"""

import sys

ENCRYPTION_KEY = "c3WYh2a7spWMMDZdH2kaVD8e0FQheMM7J_UkaLkqAOQ="

print("=" * 80)
print("RAILWAY ENCRYPTION KEY SETUP INSTRUCTIONS")
print("=" * 80)
print()
print("Since Railway CLI requires interactive selection, please set the variable manually:")
print()
print("1. Go to: https://railway.app/project/glorious-illumination")
print("2. Select 'boss-workflow' service")
print("3. Click 'Variables' tab")
print("4. Click '+ New Variable'")
print("5. Set:")
print(f"   Variable Name: ENCRYPTION_KEY")
print(f"   Variable Value: {ENCRYPTION_KEY}")
print()
print("6. Click 'Add' and redeploy the service")
print()
print("=" * 80)
print()
print("ALTERNATIVE: Use Railway CLI interactively:")
print()
print("1. Run: railway link")
print("2. Select: glorious-illumination → boss-workflow")
print(f"3. Run: railway variables set ENCRYPTION_KEY={ENCRYPTION_KEY}")
print()
print("=" * 80)
print()
print("After setting the variable, run:")
print("  python scripts/backup_oauth_tokens.py")
print("  python scripts/deploy_oauth_encryption_production.py --mode gradual")
print()
