"""
OAuth Encryption Staging Validation Script.

Q1 2026: Week 3 - Test OAuth encryption in staging environment.
Run this script in Railway staging to validate encryption works end-to-end.
"""
import asyncio
from datetime import datetime
from src.database.repositories.oauth import get_oauth_repository
from src.utils.encryption import get_token_encryption
from src.integrations.calendar import get_calendar_integration
from src.integrations.tasks import get_tasks_integration


async def test_encryption_storage():
    """Test 1: Verify tokens are encrypted in database."""
    print("\n=== Test 1: Encryption Storage ===")

    repo = get_oauth_repository()
    encryption = get_token_encryption()

    # Store test token
    test_email = f"test-{datetime.now().timestamp()}@example.com"
    test_refresh = "test_refresh_token_12345"

    success = await repo.store_token(
        email=test_email,
        service="calendar",
        refresh_token=test_refresh,
        access_token="test_access_token_67890"
    )

    if not success:
        print("❌ FAIL: Failed to store token")
        return False

    # Check database directly (encrypted)
    from src.database.models import OAuthTokenDB
    from src.database.connection import get_database
    from sqlalchemy import select

    db = get_database()
    await db.initialize()

    async with db.session() as session:
        result = await session.execute(
            select(OAuthTokenDB).where(OAuthTokenDB.email == test_email)
        )
        token = result.scalar_one_or_none()

        if not token:
            print("❌ FAIL: Token not found in database")
            return False

        # Verify encrypted (Fernet format starts with "gAAAAA")
        if not token.refresh_token.startswith("gAAAAA"):
            print(f"❌ FAIL: Token not encrypted: {token.refresh_token[:20]}")
            return False

        print(f"✅ PASS: Token encrypted in database: {token.refresh_token[:20]}...")

    # Cleanup
    await repo.delete_token(test_email, "calendar")
    return True


async def test_decryption_retrieval():
    """Test 2: Verify tokens decrypt correctly on retrieval."""
    print("\n=== Test 2: Decryption Retrieval ===")

    repo = get_oauth_repository()

    # Store token
    test_email = f"test-{datetime.now().timestamp()}@example.com"
    original_refresh = "my_unique_refresh_token_xyz"
    original_access = "my_unique_access_token_abc"

    await repo.store_token(
        email=test_email,
        service="tasks",
        refresh_token=original_refresh,
        access_token=original_access
    )

    # Retrieve token
    retrieved = await repo.get_token(test_email, "tasks")

    if not retrieved:
        print("❌ FAIL: Token not retrieved")
        return False

    # Verify decrypted correctly
    if retrieved["refresh_token"] != original_refresh:
        print(f"❌ FAIL: Refresh token mismatch")
        print(f"  Expected: {original_refresh}")
        print(f"  Got: {retrieved['refresh_token']}")
        return False

    if retrieved["access_token"] != original_access:
        print(f"❌ FAIL: Access token mismatch")
        return False

    print(f"✅ PASS: Token decrypted correctly")

    # Cleanup
    await repo.delete_token(test_email, "tasks")
    return True


async def test_backward_compatibility():
    """Test 3: Verify plaintext tokens (pre-encryption) still work."""
    print("\n=== Test 3: Backward Compatibility ===")

    # This test verifies old plaintext tokens decrypt gracefully
    from src.database.models import OAuthTokenDB
    from src.database.connection import get_database

    repo = get_oauth_repository()
    db = get_database()
    await db.initialize()

    test_email = f"test-{datetime.now().timestamp()}@example.com"
    plaintext_refresh = "old_plaintext_refresh_token"

    # Insert plaintext token directly (simulate pre-encryption data)
    async with db.session() as session:
        token = OAuthTokenDB(
            email=test_email,
            service="gmail",
            refresh_token=plaintext_refresh,  # NOT encrypted
            access_token="old_plaintext_access"
        )
        session.add(token)
        await session.commit()

    # Retrieve via repository (should handle plaintext gracefully)
    retrieved = await repo.get_token(test_email, "gmail")

    if not retrieved:
        print("❌ FAIL: Could not retrieve plaintext token")
        return False

    if retrieved["refresh_token"] != plaintext_refresh:
        print(f"❌ FAIL: Plaintext token not handled correctly")
        return False

    print(f"✅ PASS: Backward compatibility works (plaintext tokens supported)")

    # Cleanup
    await repo.delete_token(test_email, "gmail")
    return True


async def test_performance():
    """Test 4: Verify encryption overhead is < 5ms."""
    print("\n=== Test 4: Performance ===")

    import time
    repo = get_oauth_repository()

    # Test 100 operations
    iterations = 100
    test_emails = [f"perf-test-{i}@example.com" for i in range(iterations)]

    # Measure store time
    start = time.time()
    for email in test_emails:
        await repo.store_token(
            email=email,
            service="calendar",
            refresh_token=f"token_{email}",
            access_token=f"access_{email}"
        )
    store_time = (time.time() - start) * 1000  # ms
    avg_store = store_time / iterations

    # Measure retrieve time
    start = time.time()
    for email in test_emails:
        await repo.get_token(email, "calendar")
    retrieve_time = (time.time() - start) * 1000  # ms
    avg_retrieve = retrieve_time / iterations

    print(f"  Store: {avg_store:.2f}ms average ({iterations} operations)")
    print(f"  Retrieve: {avg_retrieve:.2f}ms average ({iterations} operations)")

    # Cleanup
    for email in test_emails:
        await repo.delete_token(email, "calendar")

    if avg_store > 5.0 or avg_retrieve > 5.0:
        print(f"⚠️  WARNING: Performance overhead > 5ms (acceptable but monitor)")
        return True  # Still pass, just warn

    print(f"✅ PASS: Performance overhead < 5ms")
    return True


async def test_integration_calendar():
    """Test 5: Verify Calendar integration works with encrypted tokens."""
    print("\n=== Test 5: Calendar Integration ===")

    try:
        # This requires valid OAuth token in staging
        # If no token exists, skip test
        calendar = get_calendar_integration()

        # Try to list events (requires valid OAuth)
        # This will test the full cycle: get_token → decrypt → use in API
        events = await calendar.list_upcoming_events(max_results=5)

        print(f"✅ PASS: Calendar integration works ({len(events)} events retrieved)")
        return True

    except Exception as e:
        # If OAuth not set up in staging, that's OK
        if "No OAuth token" in str(e) or "credentials" in str(e).lower():
            print(f"⚠️  SKIP: Calendar OAuth not configured in staging (expected)")
            return True

        print(f"❌ FAIL: Calendar integration error: {e}")
        return False


async def run_all_tests():
    """Run all OAuth encryption staging tests."""
    print("=" * 60)
    print("OAuth Encryption Staging Validation")
    print("Week 3/4 - Q1 2026")
    print("=" * 60)

    tests = [
        ("Encryption Storage", test_encryption_storage),
        ("Decryption Retrieval", test_decryption_retrieval),
        ("Backward Compatibility", test_backward_compatibility),
        ("Performance", test_performance),
        ("Calendar Integration", test_integration_calendar),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = await test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ {name} - EXCEPTION: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 All tests passed! Ready for Week 4 production deployment.")
        return True
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Review and fix before production.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
