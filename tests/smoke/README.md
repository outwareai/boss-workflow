# Pre-Deployment Smoke Tests

## Overview

This directory contains **critical pre-deployment smoke tests** that must pass before any code is deployed to production. These tests validate that core system functionality is working correctly.

## What Are Smoke Tests?

Smoke tests are quick, high-level tests that verify the most critical functionality:
- They run in seconds (not minutes)
- They catch obvious breaks immediately
- They block deployments if they fail
- They're designed to be run **before** each deployment

## Test Coverage

The smoke tests verify 6 critical intents and edge cases:

### Critical Intents (Must Work)
1. **Task Creation** - Boss can create tasks
2. **Status Modification** - Tasks can change status
3. **Boss Approval** - Boss can approve completed work
4. **Boss Rejection** - Boss can reject work and provide feedback
5. **Help Command** - Users can get help
6. **Status Check** - Users can view their tasks

### Edge Cases (Must Not Crash)
- Empty messages
- Whitespace-only messages
- Very long messages (5000+ characters)
- Unicode characters (Chinese, Arabic, Bengali, etc.)
- Case insensitivity

## Running Smoke Tests

### Linux/Mac

```bash
# Run all smoke tests
bash scripts/pre_deploy_check.sh

# Run with verbose output
bash scripts/pre_deploy_check.sh verbose

# Run specific test
pytest tests/smoke/test_critical_intents.py::TestCriticalIntents::test_create_task_intent -v

# Run and stop on first failure
pytest tests/smoke/test_critical_intents.py -x -v
```

### Windows

```bash
# Run all smoke tests
scripts\pre_deploy_check.bat

# Run with verbose output
scripts\pre_deploy_check.bat verbose

# Run specific test
pytest tests\smoke\test_critical_intents.py::TestCriticalIntents::test_create_task_intent -v
```

### Direct Pytest

```bash
# Run with coverage
pytest tests/smoke/test_critical_intents.py -v --cov=src.ai.intent

# Run with JUnit XML output (for CI/CD)
pytest tests/smoke/test_critical_intents.py -v --junit-xml=results.xml

# Run with detailed failure info
pytest tests/smoke/test_critical_intents.py -v --tb=long
```

## Exit Codes

- **0** - All tests passed (safe to deploy)
- **1** - One or more tests failed (deployment blocked)

## CI/CD Integration

### GitHub Actions

The workflow `.github/workflows/smoke-tests.yml` automatically:
- Runs on push to master/main/staging
- Runs on pull requests
- Tests against Python 3.11 and 3.12
- Uploads test results as artifacts
- Comments on PRs with results
- Blocks deployment if tests fail

### Railway Deployment

The `railway.json` configuration includes:
- Health check endpoint: `/health`
- Health check timeout: 100 seconds
- Restart policy: ON_FAILURE (max 3 retries)

To manually trigger Railway redeploy after fixes:

```bash
railway redeploy -s boss-workflow --yes
```

## Test Structure

```
tests/smoke/
├── __init__.py                      # Module marker
├── test_critical_intents.py         # All smoke tests
└── README.md                        # This file

scripts/
├── pre_deploy_check.sh              # Linux/Mac script
└── pre_deploy_check.bat             # Windows script

.github/workflows/
└── smoke-tests.yml                  # GitHub Actions workflow
```

## Interpreting Results

### All Tests Pass

```
✅ ALL CRITICAL TESTS PASSED
Status: Safe to deploy
```

The system is ready for production deployment. All critical functionality is verified.

### Tests Fail

```
❌ CRITICAL TESTS FAILED
Status: BLOCKING DEPLOYMENT

Action required:
1. Review test output above
2. Fix failing tests
3. Run this script again
4. Once tests pass, deployment will proceed
```

If tests fail, you must:
1. Read the error message carefully
2. Fix the code that broke
3. Re-run tests locally
4. Commit fix: `git add . && git commit -m "fix(smoke): Fix critical intent test"`
5. Push: `git push`
6. Wait for GitHub Actions to confirm

## Adding New Smoke Tests

When adding critical functionality, add a corresponding smoke test:

```python
@pytest.mark.asyncio
async def test_my_critical_feature(self, intent_detector):
    """
    CRITICAL: Description of why this is critical.
    
    This feature is essential because...
    """
    # Test implementation
    intent, data = await intent_detector.detect_intent("test message")
    assert intent == UserIntent.MY_INTENT, "Feature broken!"
```

Then update this README to document the new test.

## Debugging Failed Tests

### Check Intent Detection

```python
from src.ai.intent import get_intent_detector

detector = get_intent_detector()

# Test a message
intent, data = await detector.detect_intent("create task for john")
print(f"Intent: {intent}")
print(f"Data: {data}")
```

### Check AI Response

If AI-based tests fail, check:
1. DeepSeek API key is valid in `.env`
2. API has quota remaining
3. Network connection is working
4. Check test logs: `pytest tests/smoke/ -v -s`

### Check Mock Behavior

All AI calls are mocked in smoke tests to avoid external dependencies:

```python
with patch.object(intent_detector, '_ai_classify') as mock_ai:
    mock_ai.return_value = (UserIntent.CREATE_TASK, {"message": "test"})
    # Test with mocked response
```

## Performance

Expected runtime:
- Full smoke test suite: **20-30 seconds**
- Single test: **2-5 seconds**

If tests take longer, check:
1. System resources (CPU/memory)
2. Network latency
3. Mock delays in test code

## Troubleshooting

### Pytest Not Found

```bash
pip install -r requirements.txt
```

### Async Test Errors

The tests use `pytest-asyncio`. If you see async errors:

```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio==0.24.0

# Force PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/smoke/
```

### Mock Errors

If mocking fails, check:
1. Correct import path: `from src.ai.intent import IntentDetector`
2. Correct method name: `_ai_classify`
3. Mock return type matches expected (tuple of intent, dict)

### Slow Tests

To identify slow tests:

```bash
pytest tests/smoke/ -v --durations=10
```

## Best Practices

1. **Run before committing** - Always run smoke tests before pushing code
2. **Fix immediately** - Don't commit broken tests
3. **Keep tests fast** - Mock external calls
4. **Use verbose mode** - For debugging failures
5. **Check CI/CD** - Wait for GitHub Actions confirmation

## Links

- [Smoke Testing Best Practices](https://en.wikipedia.org/wiki/Smoke_testing)
- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [DeepSeek API](https://platform.deepseek.com/)

## Support

If you encounter issues:

1. Check this README
2. Review test output carefully
3. Enable verbose mode: `bash scripts/pre_deploy_check.sh verbose`
4. Check logs: `pytest tests/smoke/ -vvv -s`
5. Ask for help in #development-help
