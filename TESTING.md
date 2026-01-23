# TESTING.md - Boss Workflow Testing Standards

## Testing Philosophy

**A test passes ONLY if the actual outcome matches expectations.**

Bad testing (what we had before):
- Check logs for "complexity=3" → PASS
- Task might be broken, title garbage, assignee lost → Still shows PASS

Good testing (what we have now):
- Send task → Answer questions → Check database
- Task title contains "notification"? → YES/NO
- Assignee is "Mayank"? → YES/NO
- Any garbage in title like "1tomorrow"? → YES/NO

---

## Test Framework Overview

### Files

| File | Purpose |
|------|---------|
| `test_framework.py` | **PRIMARY** - Proper test framework with validation |
| `test_full_loop.py` | Quick manual testing, Railway log checking |
| `test_all.py` | Unit tests |

### When to Use Which

| Scenario | Tool |
|----------|------|
| After fixing bugs | `python test_framework.py run-all` |
| After any code change | `python test_framework.py run-all` |
| Quick health check | `python test_full_loop.py verify-deploy` |
| Debugging a specific issue | `python test_full_loop.py full-test "message"` |
| Before deploying | `python test_framework.py run-all` |

---

## Test Case Structure

Every test case has:

```python
TestCase(
    id="conv-001",
    name="Human readable name",
    description="What this tests",
    tags=["conversation", "critical"],
    steps=[
        ConversationStep(action="send", message="Create task..."),
        ConversationStep(action="wait", wait_seconds=10),
        ConversationStep(
            action="validate_task",
            expected_task=ExpectedTask(
                title_contains="expected text",
                title_not_contains="garbage",
                assignee="Mayank"
            )
        )
    ]
)
```

### Expected Task Validation

| Field | What it checks |
|-------|----------------|
| `title_contains` | Task title must contain this text |
| `title_not_contains` | Task title must NOT contain this (catches garbage) |
| `assignee` | Exact assignee match (case-insensitive) |
| `priority` | Expected priority level |
| `has_deadline` | Whether deadline should exist |
| `description_contains` | Description must contain this text |

---

## Running Tests

### Run All Tests (Recommended)
```bash
python test_framework.py run-all
```

Output:
```
======================================================================
 RUNNING ALL TESTS
======================================================================

Running 5 tests...

  Running: Simple task creates directly
    ✓ PASSED

  Running: Answer parsing preserves task context
    ✗ FAILED - Title should contain 'notification' but got '1tomorrow 2a'

======================================================================
 TEST RESULTS SUMMARY
======================================================================
  ✓ [conv-001] Simple task creates directly: PASSED
  ✗ [conv-002] Answer parsing preserves task context: FAILED
      Error: Title should contain 'notification' but got '1tomorrow 2a'
----------------------------------------------------------------------
  TOTAL: 5 | PASSED: 4 | FAILED: 1
======================================================================

⚠️  SOME TESTS FAILED - Review errors above
```

### Run Specific Suite
```bash
python test_framework.py run conversation
python test_framework.py run validation
```

### List All Tests
```bash
python test_framework.py list
```

---

## Adding New Tests

### 1. Identify What to Test

Ask: "If this broke, what would the symptom be?"

Example: "Answer parsing bug"
- Symptom: Task title becomes the user's answer ("1tomorrow 2a") instead of original task

### 2. Write the Test Case

```python
TestCase(
    id="conv-002",
    name="Answer parsing preserves task context",
    description="When user answers questions, original task should be preserved",
    tags=["conversation", "answer-parsing", "critical"],
    steps=[
        # Step 1: Send a complex task that triggers questions
        ConversationStep(
            action="send",
            message="Create task for Mayank: Build notification system"
        ),
        # Step 2: Wait for bot to process and ask questions
        ConversationStep(action="wait", wait_seconds=12),
        # Step 3: Answer the questions
        ConversationStep(action="send", message="1tomorrow 2a"),
        # Step 4: Wait for bot to process answers
        ConversationStep(action="wait", wait_seconds=10),
        # Step 5: Validate the final task
        ConversationStep(
            action="validate_task",
            expected_task=ExpectedTask(
                title_contains="notification",      # Original title preserved
                title_not_contains="1tomorrow",     # Answer NOT in title
                assignee="Mayank"                   # Assignee preserved
            )
        )
    ]
)
```

### 3. Add to Test Suite

Add your test to the appropriate function in `test_framework.py`:
- `get_conversation_tests()` - Multi-turn conversation tests
- `get_validation_tests()` - Output validation tests

---

## Test-Driven Bug Fixing

When a bug is reported:

### 1. First, Write a Failing Test

```python
# User reported: "When I answer questions, the title becomes my answer"

TestCase(
    id="bug-123",
    name="Answer should not become title",
    steps=[
        ConversationStep(action="send", message="Create task: Build API"),
        ConversationStep(action="wait", wait_seconds=10),
        ConversationStep(action="send", message="1tomorrow"),  # Answer
        ConversationStep(action="wait", wait_seconds=8),
        ConversationStep(
            action="validate_task",
            expected_task=ExpectedTask(
                title_contains="API",           # Should have original
                title_not_contains="1tomorrow"  # Should NOT have answer
            )
        )
    ]
)
```

### 2. Run Test - It Should FAIL

```bash
python test_framework.py run-all
# ✗ [bug-123] Answer should not become title: FAILED
#     Error: Title should contain 'API' but got '1tomorrow'
```

### 3. Fix the Bug

Make code changes to fix the issue.

### 4. Run Test Again - It Should PASS

```bash
python test_framework.py run-all
# ✓ [bug-123] Answer should not become title: PASSED
```

### 5. Keep the Test

The test stays in the suite forever to prevent regression.

---

## What Tests Should Cover

### Critical Paths (Must Test)

1. **Simple task flow** - Task created without questions
2. **Complex task flow** - Questions asked, answers processed, task created
3. **Answer parsing** - "1answer 2answer" format works
4. **Context preservation** - Title/assignee not lost during conversation
5. **Correction handling** - "change assignee to X" updates task

### Validation Points

Every test should validate:
- Task was created (exists in database)
- Title matches user intent
- Assignee is correct
- No garbage in fields (answer text in title, etc.)

---

## CI/CD Integration

### Before Every Deploy

```bash
# 1. Run full test suite
python test_framework.py run-all

# 2. Only deploy if ALL tests pass
# If any fail, DO NOT DEPLOY
```

### After Deploy

```bash
# 1. Verify deployment health
python test_full_loop.py verify-deploy

# 2. Run smoke tests
python test_framework.py run validation
```

---

## Troubleshooting

### Test Fails But Bot Seems to Work

Check:
1. Is the test expectation correct?
2. Is there a timing issue (need longer wait)?
3. Is the task in the database but with different values?

### Test Passes But Bot is Broken

Your test expectations are too loose. Add:
- `title_not_contains` to catch garbage
- More specific `title_contains`
- Check `assignee` explicitly

### Flaky Tests (Sometimes Pass, Sometimes Fail)

Usually timing issues:
1. Increase `wait_seconds`
2. Add retry logic for validation
3. Check if Railway is slow (cold start)

---

## Maintenance

### Weekly

- Review any new bugs reported
- Add tests for each bug before fixing
- Run full suite to check for regressions

### After Any Code Change

- Run `python test_framework.py run-all`
- Don't commit if tests fail

### Quarterly

- Review test coverage
- Add tests for any untested paths
- Remove obsolete tests

---

*Last updated: 2026-01-23*
