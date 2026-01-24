"""
OAuth Encryption Production Deployment.

Q1 2026: Week 4 - Deploy OAuth encryption to production with gradual migration.
Run this after verifying staging tests pass.
"""
import asyncio
import sys
from datetime import datetime
from typing import Dict, List
from src.database.repositories.oauth import get_oauth_repository
from src.utils.encryption import get_token_encryption


async def check_prerequisites() -> bool:
    """Verify all prerequisites before deployment."""
    print("\n=== Checking Prerequisites ===")

    checks = []

    # 1. Check ENCRYPTION_KEY exists
    try:
        encryption = get_token_encryption()
        encryption.encrypt(b"test")
        print("[SUCCESS] ENCRYPTION_KEY configured correctly")
        checks.append(True)
    except Exception as e:
        print(f"[ERROR] ENCRYPTION_KEY missing or invalid: {e}")
        checks.append(False)

    # 2. Check database connection
    try:
        from src.database.connection import get_database
        db = get_database()
        await db.initialize()
        print("[SUCCESS] Database connection working")
        checks.append(True)
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        checks.append(False)

    # 3. Check backup exists
    import os
    backup_dir = "backups/oauth_tokens"
    if os.path.exists(backup_dir) and os.listdir(backup_dir):
        print(f"[SUCCESS] Backup found in {backup_dir}")
        checks.append(True)
    else:
        print(f"[ERROR] No backup found in {backup_dir}")
        print("   Run scripts/backup_oauth_tokens.py first!")
        checks.append(False)

    # 4. Check staging tests passed
    staging_report = "docs/oauth_week3_validation_report.md"
    if os.path.exists(staging_report):
        with open(staging_report, 'r') as f:
            content = f.read()
            if "GO" in content and "5/5" in content:
                print(f"[SUCCESS] Staging tests passed (5/5)")
                checks.append(True)
            else:
                print(f"[ERROR] Staging tests not passed")
                checks.append(False)
    else:
        print(f"[ERROR] Staging report not found")
        checks.append(False)

    return all(checks)


async def get_plaintext_tokens() -> List[Dict]:
    """Find all plaintext tokens in database."""
    print("\n=== Scanning for Plaintext Tokens ===")

    from src.database.models import OAuthTokenDB
    from src.database.connection import get_database
    from sqlalchemy import select

    db = get_database()
    await db.initialize()

    plaintext_tokens = []

    async with db.session() as session:
        result = await session.execute(select(OAuthTokenDB))
        tokens = result.scalars().all()

        for token in tokens:
            # Fernet encrypted tokens start with "gAAAAA"
            if not token.refresh_token.startswith("gAAAAA"):
                plaintext_tokens.append({
                    "email": token.email,
                    "service": token.service,
                    "created_at": token.created_at,
                })

    print(f"Found {len(plaintext_tokens)} plaintext tokens")
    return plaintext_tokens


async def encrypt_plaintext_tokens(limit: int = None) -> Dict:
    """Encrypt all plaintext tokens (gradual migration)."""
    print("\n=== Encrypting Plaintext Tokens ===")

    repo = get_oauth_repository()
    plaintext = await get_plaintext_tokens()

    if limit:
        plaintext = plaintext[:limit]
        print(f"Limiting to {limit} tokens for gradual rollout")

    results = {"success": 0, "failed": 0, "errors": []}

    for token_info in plaintext:
        email = token_info["email"]
        service = token_info["service"]

        try:
            # Get current token (plaintext)
            current = await repo.get_token(email, service)

            if not current:
                print(f"[WARNING]  Token disappeared: {email}/{service}")
                continue

            # Re-save (will auto-encrypt via repository)
            await repo.store_token(
                email=email,
                service=service,
                refresh_token=current["refresh_token"],
                access_token=current.get("access_token", ""),
                expires_at=current.get("expires_at")
            )

            results["success"] += 1
            print(f"[SUCCESS] Encrypted: {email}/{service}")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{email}/{service}: {str(e)}")
            print(f"[ERROR] Failed: {email}/{service} - {e}")

    return results


async def verify_encryption_coverage() -> Dict:
    """Verify 100% of tokens are encrypted."""
    print("\n=== Verifying Encryption Coverage ===")

    from src.database.models import OAuthTokenDB
    from src.database.connection import get_database
    from sqlalchemy import select

    db = get_database()
    await db.initialize()

    stats = {"total": 0, "encrypted": 0, "plaintext": 0}

    async with db.session() as session:
        result = await session.execute(select(OAuthTokenDB))
        tokens = result.scalars().all()

        for token in tokens:
            stats["total"] += 1

            if token.refresh_token.startswith("gAAAAA"):
                stats["encrypted"] += 1
            else:
                stats["plaintext"] += 1

    coverage = (stats["encrypted"] / stats["total"] * 100) if stats["total"] > 0 else 0

    print(f"Total tokens: {stats['total']}")
    print(f"Encrypted: {stats['encrypted']}")
    print(f"Plaintext: {stats['plaintext']}")
    print(f"Coverage: {coverage:.1f}%")

    return stats


async def deploy_gradual():
    """Gradual deployment - encrypt in batches."""
    print("=" * 60)
    print("OAuth Encryption Production Deployment - GRADUAL")
    print("=" * 60)

    # Step 1: Prerequisites
    if not await check_prerequisites():
        print("\n[ERROR] Prerequisites not met. Fix issues and try again.")
        return False

    # Step 2: Get plaintext count
    plaintext = await get_plaintext_tokens()
    total_plaintext = len(plaintext)

    if total_plaintext == 0:
        print("\n[SUCCESS] No plaintext tokens found. Deployment already complete!")
        return True

    print(f"\n📊 Found {total_plaintext} plaintext tokens to encrypt")

    # Step 3: Gradual rollout (10% batches)
    batch_size = max(1, total_plaintext // 10)  # 10% at a time
    batches = (total_plaintext + batch_size - 1) // batch_size

    print(f"🔄 Gradual rollout: {batches} batches of ~{batch_size} tokens")

    for batch_num in range(batches):
        print(f"\n--- Batch {batch_num + 1}/{batches} ---")

        # Encrypt one batch
        results = await encrypt_plaintext_tokens(limit=batch_size)

        print(f"Results: {results['success']} success, {results['failed']} failed")

        # Wait 10 seconds between batches (monitor for issues)
        if batch_num < batches - 1:
            print("⏱️  Waiting 10 seconds before next batch...")
            await asyncio.sleep(10)

    # Step 4: Verify 100% coverage
    stats = await verify_encryption_coverage()

    if stats["plaintext"] == 0:
        print("\n🎉 SUCCESS! 100% of tokens encrypted")
        return True
    else:
        print(f"\n[WARNING]  WARNING: {stats['plaintext']} tokens still plaintext")
        return False


async def deploy_full():
    """Full deployment - encrypt all at once."""
    print("=" * 60)
    print("OAuth Encryption Production Deployment - FULL")
    print("=" * 60)

    # Step 1: Prerequisites
    if not await check_prerequisites():
        print("\n[ERROR] Prerequisites not met. Fix issues and try again.")
        return False

    # Step 2: Encrypt all
    results = await encrypt_plaintext_tokens(limit=None)

    print(f"\nResults: {results['success']} success, {results['failed']} failed")

    if results["errors"]:
        print("\nErrors:")
        for error in results["errors"]:
            print(f"  - {error}")

    # Step 3: Verify coverage
    stats = await verify_encryption_coverage()

    if stats["plaintext"] == 0:
        print("\n🎉 SUCCESS! 100% of tokens encrypted")
        return True
    else:
        print(f"\n[WARNING]  WARNING: {stats['plaintext']} tokens still plaintext")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deploy OAuth encryption to production")
    parser.add_argument(
        "--mode",
        choices=["gradual", "full"],
        default="gradual",
        help="Deployment mode (gradual=10%% batches, full=all at once)"
    )

    args = parser.parse_args()

    if args.mode == "gradual":
        success = asyncio.run(deploy_gradual())
    else:
        success = asyncio.run(deploy_full())

    sys.exit(0 if success else 1)
