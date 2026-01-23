# TEST.MD - Boss Workflow Test Documentation

**Last Updated:** 2026-01-23 (v2.3.0)

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Test Categories](#test-categories)
3. [Quick Reference](#quick-reference)
4. [End-to-End Tests](#end-to-end-tests)
5. [Integration Tests](#integration-tests)
6. [Unit Tests](#unit-tests)
7. [Best Practices](#best-practices)
8. [CI/CD Integration](#cicd-integration)

---

## Overview

The Boss Workflow project has **12 test files** organized into **3 categories**:

| Category | Files | Purpose |
|----------|-------|---------|
| **End-to-End** | 3 files | Full pipeline testing (Telegram → Bot → Discord) |
| **Integration** | 6 files | Component integration, intent detection, conversations |
| **Unit** | 3 files | Pydantic validation, encryption, rate limiting |

**Total Lines of Test Code:** ~4,100 lines

---

## Test Categories

### 🔵 End-to-End Tests (E2E)
Test the complete workflow from user input to final output.

### 🟢 Integration Tests
Test how components work together without external dependencies.

### 🟡 Unit Tests
Test individual functions and models in isolation.

---

## Quick Reference

### Run All Tests
```bash
# Comprehensive integration test
python test_all.py

# Full E2E test suite (v2.3)
python test_full_loop.py test-all

# Unit tests (pytest required)
pytest tests/unit/
```

### Run Specific Test Categories
```bash
# Intent detection only
python test_intents.py

# Task operations only
python test_task_ops.py

# Conversation flows only
python test_conversation.py

# Simple task test (no questions)
python test_full_loop.py test-simple

# Complex task test (with questions)
python test_full_loop.py test-complex

# Role routing test (Mayank→DEV, Zea→ADMIN)
python test_full_loop.py test-routing
```

### Pre/Post Deployment
```bash
# Verify Railway deployment health
python test_full_loop.py verify-deploy

# Check Railway logs for errors
python test_full_loop.py check-logs
```

---

## End-to-End Tests

### 1. `test_full_loop.py` (1,019 lines) ⭐ **PRIMARY E2E FRAMEWORK**

**Purpose:** Complete Telegram → Bot → Discord pipeline testing with Railway integration.

**Key Features:**
- Direct Railway webhook simulation
- Real-time log parsing
- Discord output verification
- Database task verification
- Session continuity support

**Commands:**

#### Basic Commands
```bash
python test_full_loop.py send "message"         # Send to bot
python test_full_loop.py respond "yes"          # Answer confirmation
python test_full_loop.py read-telegram          # See bot responses
python test_full_loop.py read-discord           # See Discord output
python test_full_loop.py read-tasks             # See database tasks
python test_full_loop.py full-test "message"    # Complete test cycle
```

#### Specialized Tests (v2.3)
```bash
python test_full_loop.py test-simple            # Simple task (complexity 1-3, no questions)
python test_full_loop.py test-complex           # Complex task (complexity 7+, questions asked)
python test_full_loop.py test-routing           # Mayank→DEV, Zea→ADMIN routing
python test_full_loop.py test-all               # Run all 3 tests in sequence
```

#### Pre/Post Deployment
```bash
python test_full_loop.py verify-deploy          # Check Railway health after deploy
python test_full_loop.py check-logs             # Quick check for errors in logs
```

#### Session Continuity
```bash
python test_full_loop.py save-progress "task"   # Save current progress
python test_full_loop.py resume                 # Show saved progress
```

#### Conversation Flow Tests
```bash
python test_full_loop.py test-conversation      # Full multi-turn conversation test
python test_full_loop.py test-answer-parsing    # Test answer format parsing
```

**Test Results Saved To:**
- `test_simple_results.json` - Simple task test results
- `test_all_results.json` - Full test suite results (simple, complex, routing)

**When to Use:**
- ✅ After deployment to verify production works
- ✅ Before major releases to validate E2E flow
- ✅ When debugging Telegram/Discord integration issues
- ✅ When testing role-based routing (v2.2.0)
- ✅ When testing complexity detection (v2.2.0)

---

### 2. `test_framework.py` (548 lines)

**Purpose:** PROPER test framework that validates ACTUAL OUTCOMES, not just log keywords.

**Key Features:**
- Outcome-based validation (vs. log keyword matching)
- Database verification
- Discord channel verification
- Task state verification

**Commands:**
```bash
python test_framework.py
```

**Test Coverage:**
- Task creation flow
- Multi-turn conversations
- Task completion flow
- Database consistency

**When to Use:**
- ✅ When you need high-confidence outcome validation
- ✅ When testing database state changes
- ✅ When log-based tests are unreliable

---

### 3. `test_telegram_discord.py` (316 lines)

**Purpose:** Test Telegram → Discord pipeline with real API integrations.

**Key Features:**
- Real Telegram API usage
- Discord webhook verification
- Message formatting validation
- Async/await testing

**Commands:**
```bash
python test_telegram_discord.py
```

**Test Coverage:**
- Telegram message sending
- Discord webhook posting
- Message formatting
- API error handling

**When to Use:**
- ✅ When testing Telegram/Discord API changes
- ✅ When debugging webhook issues
- ✅ When validating message formatting

---

## Integration Tests

### 4. `test_all.py` (415 lines)

**Purpose:** Comprehensive integration test for all major components.

**Commands:**
```bash
python test_all.py
```

**Test Coverage:**
- ✅ DeepSeek AI connection
- ✅ Google Sheets integration
- ✅ Discord webhook posting
- ✅ Google Calendar integration
- ✅ Redis connection (optional)
- ✅ Task creation flow
- ✅ Intent detection
- ✅ Task completion flow

**Output Example:**
```
==================================================
Testing DeepSeek AI...
==================================================
[PASS]: DeepSeek AI
       Model: deepseek-chat

==================================================
Testing Google Sheets Integration...
==================================================
[PASS]: Google Sheets Integration
       Test task written to sheet

...

==================================================
FINAL SUMMARY
==================================================
Total Tests: 8
Passed: 7
Failed: 1
Success Rate: 87.5%
```

**When to Use:**
- ✅ After changing integration configurations
- ✅ Before deploying to production
- ✅ When debugging integration failures

---

### 5. `test_intents.py` (111 lines)

**Purpose:** Unit tests for intent detection without needing Redis/external services.

**Commands:**
```bash
python test_intents.py
```

**Test Coverage:**
71 test cases covering:
- Task creation patterns
- Status checks
- Clear/delete commands
- Greetings
- Help requests
- Spec generation
- Task completion
- Cancel operations

**Output Example:**
```
============================================================
   INTENT DETECTION TESTS
============================================================
[PASS] Simple task assignment
       Input: 'Mayank fix the login bug'
       Expected: create_task, Got: create_task

[PASS] Task with deadline
       Input: 'Sarah needs to update the docs by tomorrow'
       Expected: create_task, Got: create_task

...

============================================================
   SUMMARY
============================================================
  Passed: 69/71
  Failed: 2/71
```

**When to Use:**
- ✅ After modifying `src/ai/intent.py`
- ✅ When adding new intent types
- ✅ When debugging intent classification issues

---

### 6. `test_task_ops.py` (109 lines)

**Purpose:** Test comprehensive task operations (modify, reassign, priority, etc.).

**Commands:**
```bash
python test_task_ops.py
```

**Test Coverage:**
- ✅ Modify task (title/description)
- ✅ Reassign task
- ✅ Change priority
- ✅ Change deadline
- ✅ Change status
- ✅ Add tags
- ✅ Add subtasks
- ✅ Add dependencies
- ✅ Duplicate task

**Output Example:**
```
============================================================
COMPREHENSIVE TASK OPERATIONS - IMPLEMENTATION TEST
============================================================

Testing Intent Detection...
  [PASS] 'change the title of TASK-001 to 'New Title'' -> modify_task
  [PASS] 'reassign TASK-001 to Sarah' -> reassign_task
  [PASS] 'make TASK-001 urgent' -> change_priority
  ...

Intent Detection: 9 passed, 0 failed

Testing Clarifier Methods...

1. Testing extract_modification_details()...
  [PASS] Extracted title: Fix Login Bug

2. Testing parse_deadline()...
  [PASS] Parsed deadline: 2026-01-24T00:00:00

Clarifier Methods: All tests passed

============================================================
[SUCCESS] ALL TESTS PASSED - Implementation complete!
============================================================
```

**When to Use:**
- ✅ After modifying task operation handlers
- ✅ When adding new task modification features
- ✅ When debugging clarifier methods

---

### 7. `test_conversations.py` (349 lines)

**Purpose:** Simulate real user interactions to test intent detection and handler responses.

**Commands:**
```bash
python test_conversations.py
```

**Test Coverage:**
- Multi-turn conversations
- Context preservation
- Intent switching
- Confirmation flows

**When to Use:**
- ✅ When testing conversation state management
- ✅ When debugging multi-turn flows
- ✅ When validating context preservation

---

### 8. `test_conversation.py` (405 lines)

**Purpose:** REAL conversation tester with actual back-and-forth interactions.

**Commands:**
```bash
python test_conversation.py
```

**Test Coverage:**
- Actual conversation simulation
- Bot response validation
- Context switching
- Error handling

**When to Use:**
- ✅ When testing realistic conversation flows
- ✅ When debugging conversation edge cases

---

### 9. `test_advanced.py` (486 lines)

**Purpose:** Test subtask extraction, corrections, edge cases, and multi-task scenarios.

**Commands:**
```bash
python test_advanced.py
```

**Test Coverage:**
- Subtask extraction
- Task corrections
- Edge cases (special characters, long text)
- Multi-task batch processing

**When to Use:**
- ✅ When testing advanced AI features
- ✅ When debugging subtask extraction
- ✅ When validating edge case handling

---

## Unit Tests

### 10. `tests/unit/test_api_validation.py` (330 lines) ✅ **PYTEST**

**Purpose:** Test Pydantic validation models for API input validation (Q1 2026).

**Commands:**
```bash
pytest tests/unit/test_api_validation.py -v
```

**Test Coverage:**
- ✅ `SubtaskCreate` validation (title/description length, required fields)
- ✅ `DependencyCreate` validation (task ID format, dependency types)
- ✅ `TaskFilter` validation (limit/offset bounds, default values)
- ✅ `AdminAuthRequest` validation (secret format)
- ✅ `TeamMemberCreate` validation (name/role/IDs, XSS prevention)
- ✅ `TeachingRequest` validation (text length, whitespace handling)
- ✅ `TriggerJobRequest` validation (job ID format)
- ✅ `OnboardingDataEnhanced` validation (XSS prevention, email format)
- ✅ `OAuthCallback` validation (code/state format, XSS prevention)
- ✅ `TelegramUpdate` validation (update ID bounds)
- ✅ `DiscordWebhookPayload` validation (type range, snowflake ID format)

**Output Example:**
```
tests/unit/test_api_validation.py::TestSubtaskCreate::test_valid_subtask PASSED
tests/unit/test_api_validation.py::TestSubtaskCreate::test_title_too_short PASSED
tests/unit/test_api_validation.py::TestSubtaskCreate::test_title_too_long PASSED
...

======================== 45 passed in 0.23s ========================
```

**When to Use:**
- ✅ After modifying `src/models/api_validation.py`
- ✅ When adding new API validation models
- ✅ Before deploying API changes to production

---

### 11. `tests/unit/test_encryption.py` (74 lines) ✅ **PYTEST**

**Purpose:** Test Fernet encryption implementation (Q1 2026).

**Commands:**
```bash
pytest tests/unit/test_encryption.py -v
```

**Test Coverage:**
- ✅ Encryption/decryption round-trip
- ✅ Invalid key handling
- ✅ Tampered data detection
- ✅ Empty string handling

**When to Use:**
- ✅ After modifying encryption utilities
- ✅ When updating encryption keys
- ✅ Before deploying security changes

---

### 12. `tests/unit/test_rate_limiting.py` (136 lines) ✅ **PYTEST**

**Purpose:** Test rate limiting implementation (Q1 2026).

**Commands:**
```bash
pytest tests/unit/test_rate_limiting.py -v
```

**Test Coverage:**
- ✅ Rate limit enforcement
- ✅ Token bucket algorithm
- ✅ Time window reset
- ✅ Multiple user isolation

**When to Use:**
- ✅ After modifying rate limiting logic
- ✅ When changing rate limits
- ✅ Before deploying API throttling changes

---

## Best Practices

### 1. Test Naming Conventions
```
test_<component>.py           # Integration tests
test_<feature>_ops.py         # Operation-focused tests
tests/unit/test_<model>.py    # Unit tests (pytest)
```

### 2. Running Tests Before Deployment
```bash
# Step 1: Run unit tests (fast, no dependencies)
pytest tests/unit/ -v

# Step 2: Run integration tests (requires config)
python test_intents.py
python test_task_ops.py

# Step 3: Run E2E tests (requires Railway deployment)
python test_full_loop.py verify-deploy
python test_full_loop.py test-all
```

### 3. Test Result Interpretation

**test_full_loop.py Output:**
```json
{
  "tests": [
    {
      "name": "simple",
      "passed": true,
      "complexity": 3,
      "questions": 0
    },
    {
      "name": "complex",
      "passed": true,
      "complexity": 6,
      "questions": 2
    },
    {
      "name": "routing",
      "passed": false,
      "mayank": false,
      "zea": false
    }
  ],
  "timestamp": "2026-01-23T13:49:15.215082"
}
```

**Interpretation:**
- `passed: true` → Test passed ✅
- `passed: false` → Test failed ❌ (check Railway logs)
- `complexity: 3` → Simple task (1-3), no questions expected
- `complexity: 6` → Medium task (4-6), 1-2 questions expected
- `questions: 0` → No questions asked
- `questions: 2` → 2 questions asked

### 4. Debugging Failed Tests

**Step 1: Check Railway Logs**
```bash
python test_full_loop.py check-logs
# OR
railway logs -s boss-workflow --lines 100
```

**Step 2: Check Database State**
```bash
curl "https://boss-workflow-production.up.railway.app/api/db/stats"
curl "https://boss-workflow-production.up.railway.app/api/db/tasks"
```

**Step 3: Verify Deployment Health**
```bash
python test_full_loop.py verify-deploy
```

**Step 4: Re-run Specific Test**
```bash
python test_full_loop.py test-simple    # If simple failed
python test_full_loop.py test-complex   # If complex failed
python test_full_loop.py test-routing   # If routing failed
```

---

## CI/CD Integration

### GitHub Actions (Recommended)

Create `.github/workflows/test.yml`:

```yaml
name: Test Suite

on:
  push:
    branches: [ master ]
  pull_request:
    branches: [ master ]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest
      - name: Run unit tests
        run: pytest tests/unit/ -v

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run integration tests
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: |
          python test_intents.py
          python test_task_ops.py

  e2e-tests:
    runs-on: ubuntu-latest
    needs: integration-tests
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Verify Railway deployment
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_BOSS_CHAT_ID: ${{ secrets.TELEGRAM_BOSS_CHAT_ID }}
        run: python test_full_loop.py verify-deploy
```

### Railway Deployment Hooks

Add to `railway.toml`:

```toml
[deploy]
healthcheck_path = "/health"
healthcheck_timeout = 300

[deploy.hooks]
post_deploy = "python test_full_loop.py verify-deploy"
```

---

## Test Coverage Summary

| Category | Files | Tests | Status |
|----------|-------|-------|--------|
| **End-to-End** | 3 | ~15 test scenarios | ✅ Active |
| **Integration** | 6 | ~120 test cases | ✅ Active |
| **Unit (pytest)** | 3 | ~65 test cases | ✅ Active |
| **Total** | 12 | ~200 test cases | ✅ Active |

---

## Maintenance

### Adding New Tests

**For Unit Tests (Pydantic models):**
1. Create `tests/unit/test_<model>.py`
2. Use pytest style: `class Test<Feature>:` with `def test_<scenario>(self):`
3. Run: `pytest tests/unit/test_<model>.py -v`

**For Integration Tests (component testing):**
1. Create `test_<component>.py` in project root
2. Use asyncio style: `async def test_<feature>():`
3. Run: `python test_<component>.py`

**For E2E Tests (full pipeline):**
1. Add command to `test_full_loop.py`
2. Add test function in main command handler
3. Run: `python test_full_loop.py <command>`

### Deprecating Old Tests

When a test file is no longer needed:
1. Move to `tests/deprecated/`
2. Update this TEST.MD file
3. Add deprecation notice to file header

---

## Known Issues & Limitations

### test_full_loop.py
- ⚠️ `test-routing` currently fails due to active preview conversations preventing new task creation
- ⚠️ Task descriptions with "and" trigger batch mode (e.g., "Review API and fix bugs" → 2 tasks)
- ⚠️ Requires Railway deployment to be running
- ⚠️ Depends on specific Discord channel configuration

### test_all.py
- ⚠️ Requires all integrations configured (Sheets, Discord, Calendar)
- ⚠️ Writes test data to production sheets

### Unit Tests
- ✅ No known issues (isolated, deterministic)

---

## Questions & Support

**For test failures:**
1. Check Railway logs: `python test_full_loop.py check-logs`
2. Verify deployment: `python test_full_loop.py verify-deploy`
3. Review this TEST.MD for test-specific guidance

**For adding new tests:**
1. Follow [Adding New Tests](#adding-new-tests) guidelines
2. Update TEST.MD with new test documentation
3. Add to CI/CD pipeline if appropriate

**For test maintenance:**
- Update TEST.MD when tests are added/removed/modified
- Keep test results files (`.json`) in `.gitignore`
- Document test failures in GitHub issues

---

**Last Updated:** 2026-01-23 (v2.3.0)
**Maintained By:** Boss Workflow Team
**Contributing:** See CLAUDE.MD for development workflow
