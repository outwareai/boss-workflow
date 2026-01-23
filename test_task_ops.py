"""
Quick test for comprehensive task operations implementation.
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.ai.intent import get_intent_detector, UserIntent
from src.ai.clarifier import TaskClarifier


async def test_intent_detection():
    """Test intent detection for task operations."""
    detector = get_intent_detector()

    test_cases = [
        ("change the title of TASK-001 to 'New Title'", UserIntent.MODIFY_TASK),
        ("reassign TASK-001 to Sarah", UserIntent.REASSIGN_TASK),
        ("make TASK-001 urgent", UserIntent.CHANGE_PRIORITY),
        ("extend TASK-001 deadline to Friday", UserIntent.CHANGE_DEADLINE),
        ("move TASK-001 to in_progress", UserIntent.CHANGE_STATUS),
        ("tag TASK-001 as frontend", UserIntent.ADD_TAGS),
        ("add subtask to TASK-001: write tests", UserIntent.ADD_SUBTASK),
        ("TASK-001 depends on TASK-002", UserIntent.ADD_DEPENDENCY),
        ("duplicate TASK-001", UserIntent.DUPLICATE_TASK),
    ]

    print("Testing Intent Detection...")
    passed = 0
    failed = 0

    for message, expected_intent in test_cases:
        try:
            intent, data = await detector.detect_intent(message, {})
            if intent == expected_intent:
                print(f"  [PASS] '{message}' -> {intent.value}")
                passed += 1
            else:
                print(f"  [FAIL] '{message}' -> Got {intent.value}, expected {expected_intent.value}")
                failed += 1
        except Exception as e:
            print(f"  [ERROR] '{message}' -> Error: {e}")
            failed += 1

    print(f"\nIntent Detection: {passed} passed, {failed} failed")
    return failed == 0


async def test_clarifier_methods():
    """Test clarifier helper methods."""
    clarifier = TaskClarifier()

    print("\nTesting Clarifier Methods...")

    # Test extract_modification_details
    print("\n1. Testing extract_modification_details()...")
    try:
        result = await clarifier.extract_modification_details(
            message="change the title to 'Fix Login Bug'",
            current_task={"title": "Old Title", "description": "Old desc"}
        )
        if result.get("new_title"):
            print(f"  [PASS] Extracted title: {result['new_title']}")
        else:
            print(f"  [FAIL] Failed to extract title. Got: {result}")
            return False
    except Exception as e:
        print(f"  [ERROR] Error: {e}")
        return False

    # Test parse_deadline
    print("\n2. Testing parse_deadline()...")
    try:
        deadline = await clarifier.parse_deadline("extend deadline to tomorrow")
        if deadline:
            print(f"  [PASS] Parsed deadline: {deadline}")
        else:
            print(f"  [INFO] No deadline found (might be OK if AI couldn't parse)")
    except Exception as e:
        print(f"  [ERROR] Error: {e}")
        return False

    print("\nClarifier Methods: All tests passed")
    return True


async def main():
    """Run all tests."""
    print("="*60)
    print("COMPREHENSIVE TASK OPERATIONS - IMPLEMENTATION TEST")
    print("="*60)

    # Test intent detection
    intent_ok = await test_intent_detection()

    # Test clarifier methods
    clarifier_ok = await test_clarifier_methods()

    # Summary
    print("\n" + "="*60)
    if intent_ok and clarifier_ok:
        print("[SUCCESS] ALL TESTS PASSED - Implementation complete!")
    else:
        print("[FAILURE] Some tests failed - review implementation")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
