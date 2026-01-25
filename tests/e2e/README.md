# End-to-End Test Suite

Comprehensive conversation flow testing for Boss Workflow.

## Overview

This test suite validates complete user journeys from message input to action completion. It simulates real conversations with the bot and verifies:

- Task creation flows
- Task modification flows
- Query and search flows
- Error handling
- Performance requirements
- Concurrent conversation handling

## Test Structure

```
tests/e2e/
├── framework.py              # Core testing framework
├── test_critical_flows.py    # Critical conversation flows
├── test_performance.py       # Performance and scalability tests
└── README.md                 # This file
```

## Framework Components

### ConversationSimulator

Main class for simulating conversations:

```python
from tests.e2e.framework import ConversationSimulator

sim = ConversationSimulator()

# Send messages
await sim.send_message("Create task for John: Fix bug")
await sim.send_message("yes")

# Make assertions
sim.assert_task_created()
sim.assert_contains("task created")

# Verify database state
task = await sim.assert_task_in_database(
    title_contains="bug",
    assignee="John"
)

# Cleanup
await sim.cleanup()
```

### Available Assertions

```python
# Response content assertions
sim.assert_contains("text")           # Response contains text
sim.assert_not_contains("text")       # Response does NOT contain text
sim.assert_question_asked()           # Bot asked a question
sim.assert_confirmation_requested()   # Bot requested confirmation

# Task assertions
sim.assert_task_created()             # Task ID in response
await sim.assert_task_in_database(    # Task exists with properties
    task_id="TASK-123",
    title_contains="bug",
    assignee="John",
    status=TaskStatus.PENDING
)
await sim.assert_no_task_created()    # No task was created

# Conversation assertions
await sim.get_conversation_count()    # Number of turns
sim.print_conversation()              # Debug print full conversation
```

## Running Tests

### Run all E2E tests
```bash
pytest tests/e2e/ -v
```

### Run specific test class
```bash
pytest tests/e2e/test_critical_flows.py::TestTaskCreationFlows -v
```

### Run specific test
```bash
pytest tests/e2e/test_critical_flows.py::TestTaskCreationFlows::test_simple_task_creation_flow -v
```

### Run with coverage
```bash
pytest tests/e2e/ -v --cov=src --cov-report=html
```

### Run performance tests only
```bash
pytest tests/e2e/test_performance.py -v
```

### Run with timeout (prevent hanging)
```bash
pytest tests/e2e/ -v --timeout=300
```

## Test Categories

### Critical Flows (test_critical_flows.py)

**TestTaskCreationFlows**
- Simple task creation
- Complex task with questions
- Task with deadline
- Task with priority

**TestTaskModificationFlows**
- Status changes
- Task reassignment

**TestRejectionFlows**
- Boss rejects spec
- Cancellation mid-flow

**TestQueryFlows**
- Search tasks
- Status check
- Help request
- Team status

**TestMultiTaskFlows**
- Multiple tasks in sequence
- Task dependencies

**TestEdgeCases**
- Invalid assignee
- Ambiguous task
- Rapid-fire messages

### Performance Tests (test_performance.py)

**TestResponseTimes**
- Simple response < 2s
- Complex response < 5s
- Search response < 1s
- Status check < 1s

**TestConcurrency**
- 5 concurrent users
- 10 concurrent users
- Sequential vs concurrent comparison

**TestThroughput**
- 100 messages in sequence
- Conversation memory under load

**TestScalability**
- Large task descriptions
- Many tasks in database

**TestResourceUsage**
- Memory cleanup
- No memory leaks

**TestPerformanceRegression**
- Baseline performance tracking

## Writing New Tests

### 1. Simple Test

```python
@pytest.mark.asyncio
async def test_my_flow():
    sim = ConversationSimulator()

    # Run conversation
    await sim.run_conversation([
        "Create task for John: My task",
        "yes"
    ])

    # Assert results
    sim.assert_task_created()

    # Cleanup
    await sim.cleanup()
```

### 2. Test with Database Validation

```python
@pytest.mark.asyncio
async def test_with_db_check():
    sim = ConversationSimulator()

    await sim.send_message("Create urgent task for Zea: Fix bug")
    await sim.send_message("yes")

    # Verify in database
    task = await sim.assert_task_in_database(
        title_contains="bug",
        assignee="Zea"
    )

    assert task.priority == TaskPriority.HIGH

    await sim.cleanup()
```

### 3. Test with Custom User

```python
@pytest.mark.asyncio
async def test_staff_user():
    # Simulate non-boss user
    sim = ConversationSimulator(
        user_id="STAFF_123",
        user_name="Staff Member",
        is_boss=False
    )

    # Staff cannot create tasks
    await sim.send_message("Create task")
    sim.assert_contains("permission denied")

    await sim.cleanup()
```

### 4. Performance Test

```python
@pytest.mark.asyncio
async def test_my_performance():
    sim = ConversationSimulator()

    start = time.time()
    await sim.send_message("Do something")
    duration = time.time() - start

    assert duration < 2.0, f"Too slow: {duration}s"

    await sim.cleanup()
```

## CI/CD Integration

Tests run automatically on:
- Every push to master
- Every pull request
- Manual workflow dispatch

See `.github/workflows/e2e-tests.yml` for details.

### GitHub Actions Jobs

1. **e2e** - Full test suite with coverage
2. **e2e-smoke** - Critical flows only (fast)
3. **e2e-performance** - Performance regression tests (master only)

## Best Practices

1. **Always cleanup**: Call `await sim.cleanup()` to remove test data
2. **Use meaningful assertions**: Verify actual behavior, not just "no crash"
3. **Test happy and sad paths**: Success and failure scenarios
4. **Keep tests isolated**: Each test should be independent
5. **Mock external services**: Don't rely on real Discord/Sheets in tests
6. **Set timeouts**: Prevent hanging tests with `--timeout`
7. **Track performance**: Add baseline tests for critical paths

## Debugging Failed Tests

### Print conversation history
```python
sim.print_conversation()  # Shows full conversation
```

### Check created tasks
```python
print(sim.created_tasks)  # List of task IDs
```

### Get last response
```python
print(sim.get_last_response())  # Latest bot message
```

### Run with verbose output
```bash
pytest tests/e2e/test_critical_flows.py::test_my_test -vv -s
```

### Run with debugger
```bash
pytest tests/e2e/test_critical_flows.py::test_my_test --pdb
```

## Performance Baselines

Current baselines (update when system improves):

- Simple task creation: < 3s average
- Complex task creation: < 5s
- Search query: < 1s
- Status check: < 1s
- 5 concurrent users: All respond
- 10 concurrent users: < 10s total

## Coverage Goals

- Critical flows: 100% coverage
- Edge cases: 90% coverage
- Performance tests: All baselines met
- Overall E2E coverage: > 80%

## Troubleshooting

**Tests hang**: Use `--timeout=300` flag

**Database errors**: Check PostgreSQL is running

**Import errors**: Install requirements: `pip install -r requirements.txt`

**Cleanup failures**: Manually clear test data in database

**Flaky tests**: Add retry logic or increase wait times

## Future Enhancements

- [ ] Visual regression tests (screenshot comparison)
- [ ] Load testing (100+ concurrent users)
- [ ] Chaos engineering (random failures)
- [ ] Integration with production monitoring
- [ ] Automatic performance regression alerts
- [ ] Test data factories for complex scenarios
