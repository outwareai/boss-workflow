# E2E Testing Guide

Complete guide for running and writing end-to-end tests for Boss Workflow.

## Quick Start

```bash
# Run all E2E tests
python run_e2e_tests.py

# Run critical flows only
python run_e2e_tests.py --critical

# Run with coverage
python run_e2e_tests.py --coverage

# Run smoke tests (fastest)
python run_e2e_tests.py --smoke
```

## Test Organization

### By Category

**Critical Flows** (`test_critical_flows.py`)
- Task creation (simple, complex, with deadline, with priority)
- Task modification (status change, reassignment)
- Rejection flows (boss rejects, cancellation)
- Query flows (search, status, help, team status)
- Multi-task flows (multiple tasks, dependencies)
- Edge cases (invalid assignee, ambiguous task, rapid messages)

**Performance** (`test_performance.py`)
- Response times (< 2s simple, < 5s complex, < 1s queries)
- Concurrency (5 users, 10 users, comparison)
- Throughput (100 messages, conversation memory)
- Scalability (large descriptions, many tasks)
- Resource usage (memory cleanup, leak detection)
- Regression baselines

**Examples** (`test_example.py`)
- Template tests showing framework usage
- Debugging utilities
- Common patterns

### By Speed

**Smoke Tests** (< 30 seconds)
```bash
pytest tests/e2e/ -m smoke
```
Critical paths only - run before every commit.

**Integration Tests** (< 5 minutes)
```bash
pytest tests/e2e/test_critical_flows.py
```
All critical flows - run before pushing.

**Full Suite** (< 15 minutes)
```bash
pytest tests/e2e/
```
Everything including performance - run in CI.

## Writing Tests

### Step 1: Choose Test Type

**Simple Message/Response Test**
```python
@pytest.mark.asyncio
async def test_my_simple_test():
    sim = ConversationSimulator()
    await sim.send_message("Hello")
    sim.assert_contains("hello")
    await sim.cleanup()
```

**Task Creation Test**
```python
@pytest.mark.asyncio
async def test_create_task():
    sim = ConversationSimulator()
    await sim.run_conversation([
        "Create task for John: My task",
        "yes"
    ])
    sim.assert_task_created()
    task = await sim.assert_task_in_database(
        title_contains="my task",
        assignee="John"
    )
    await sim.cleanup()
```

**Multi-Turn Conversation Test**
```python
@pytest.mark.asyncio
async def test_conversation_flow():
    sim = ConversationSimulator()

    # Turn 1: Create task
    await sim.send_message("Create task for Zea: Update docs")
    sim.assert_confirmation_requested()

    # Turn 2: Reject
    await sim.send_message("no")
    sim.assert_question_asked()

    # Turn 3: Provide feedback
    await sim.send_message("Add more details")

    # Verify no task created yet
    await sim.assert_no_task_created()

    await sim.cleanup()
```

**Performance Test**
```python
@pytest.mark.asyncio
async def test_fast_response():
    sim = ConversationSimulator()

    start = time.time()
    await sim.send_message("/status")
    duration = time.time() - start

    assert duration < 1.0, f"Too slow: {duration}s"

    await sim.cleanup()
```

### Step 2: Add Markers

```python
@pytest.mark.asyncio        # Required for async tests
@pytest.mark.e2e            # Marks as E2E test
@pytest.mark.smoke          # Optional: smoke test
@pytest.mark.performance    # Optional: performance test
async def test_my_test():
    pass
```

### Step 3: Write Clear Documentation

```python
async def test_task_creation_with_deadline():
    """
    Test: Boss creates task with deadline.

    Flow:
    1. Boss: "Create task for John: Fix bug by tomorrow"
    2. Bot: Shows preview with deadline
    3. Boss: "yes"
    4. Bot: Creates task with deadline set

    Validates:
    - Task created with correct title
    - Assignee set correctly
    - Deadline parsed and set
    - Deadline within expected range
    """
    # Test implementation
```

### Step 4: Run and Debug

```bash
# Run your test
pytest tests/e2e/test_critical_flows.py::test_my_test -v

# With verbose output
pytest tests/e2e/test_critical_flows.py::test_my_test -vv -s

# With debugger
pytest tests/e2e/test_critical_flows.py::test_my_test --pdb
```

## Debugging Failed Tests

### 1. Print Conversation History

```python
sim.print_conversation()  # Shows full back-and-forth
```

Output:
```
============================================================
CONVERSATION HISTORY
============================================================

Turn 1 (14:23:45)
USER: Create task for John: Fix bug
BOT:  I'll create a task for John...

Turn 2 (14:23:47)
USER: yes
BOT:  Task TASK-20260125-001 created successfully...

============================================================
```

### 2. Check Created Tasks

```python
print(f"Created tasks: {sim.created_tasks}")
# Output: ['TASK-20260125-001', 'TASK-20260125-002']
```

### 3. Inspect Database State

```python
task = await sim.assert_task_in_database(task_id=sim.created_tasks[-1])
print(f"Task: {task.to_dict()}")
```

### 4. Check Last Response

```python
response = sim.get_last_response()
print(f"Bot said: {response}")
```

### 5. Run with Debug Logging

```bash
pytest tests/e2e/test_my_test.py -vv -s --log-cli-level=DEBUG
```

## Common Patterns

### Pattern: Create Task and Verify

```python
async def test_pattern():
    sim = ConversationSimulator()

    # Create
    await sim.send_message("Create task for John: Test")
    await sim.send_message("yes")

    # Verify response
    sim.assert_task_created()

    # Verify database
    task = await sim.assert_task_in_database(
        title_contains="test",
        assignee="John",
        status=TaskStatus.PENDING
    )

    await sim.cleanup()
```

### Pattern: Test Rejection Flow

```python
async def test_pattern():
    sim = ConversationSimulator()

    # Initial request
    await sim.send_message("Create task: Vague description")

    # Reject
    await sim.send_message("no")

    # Should ask for clarification
    sim.assert_question_asked()

    # No task created
    await sim.assert_no_task_created()

    await sim.cleanup()
```

### Pattern: Test Multi-User Concurrency

```python
async def test_pattern():
    import asyncio

    sims = [ConversationSimulator(user_id=f"USER_{i}") for i in range(5)]

    # All send simultaneously
    await asyncio.gather(*[
        sim.send_message("Hello")
        for sim in sims
    ])

    # Cleanup all
    for sim in sims:
        await sim.cleanup()
```

### Pattern: Measure Performance

```python
async def test_pattern():
    sim = ConversationSimulator()

    # Measure
    times = []
    for _ in range(10):
        start = time.time()
        await sim.send_message("/status")
        times.append(time.time() - start)

    # Analyze
    avg = sum(times) / len(times)
    assert avg < 1.0, f"Average {avg}s exceeds 1s"

    await sim.cleanup()
```

## Assertions Reference

### Response Assertions

```python
sim.assert_contains("text")              # Contains text (case-insensitive)
sim.assert_not_contains("text")          # Doesn't contain text
sim.assert_question_asked()              # Bot asked a question (has '?')
sim.assert_confirmation_requested()      # Bot requested confirmation
```

### Task Assertions

```python
sim.assert_task_created()                # Task ID in response

await sim.assert_task_in_database(       # Task exists with properties
    task_id="TASK-123",                  # Specific ID (or uses last created)
    title_contains="bug",                # Title substring match
    assignee="John",                     # Exact assignee match
    status=TaskStatus.PENDING            # Exact status match
)

await sim.assert_no_task_created()       # No tasks created since test start
```

### Conversation Assertions

```python
count = await sim.get_conversation_count()  # Number of turns
sim.print_conversation()                    # Debug print
```

## CI/CD Integration

### GitHub Actions

Tests run on:
- Push to master
- Pull requests
- Manual workflow dispatch

Jobs:
1. **e2e** - Full suite with coverage
2. **e2e-smoke** - Critical flows only
3. **e2e-performance** - Performance tests (master only)

### Local Pre-Commit

```bash
# Quick smoke test before commit
python run_e2e_tests.py --smoke

# Full critical flows before push
python run_e2e_tests.py --critical
```

## Performance Baselines

Update these when system improves:

| Metric | Baseline | Current |
|--------|----------|---------|
| Simple task creation | < 3s avg | - |
| Complex task creation | < 5s | - |
| Search query | < 1s | - |
| Status check | < 1s | - |
| 5 concurrent users | All respond | - |
| 10 concurrent users | < 10s total | - |

Track in: `tests/e2e/test_performance.py::TestPerformanceRegression`

## Coverage Goals

- Critical flows: **100%** (all paths tested)
- Edge cases: **90%** (common failures covered)
- Performance tests: **All baselines met**
- Overall E2E coverage: **> 80%**

Check coverage:
```bash
python run_e2e_tests.py --coverage
open htmlcov/index.html
```

## Best Practices

### DO ✅

1. **Always cleanup**: `await sim.cleanup()` in every test
2. **Test both happy and sad paths**: Success and failure
3. **Use meaningful assertions**: Check actual behavior
4. **Keep tests isolated**: No dependencies between tests
5. **Document flows**: Clear docstrings with steps
6. **Mock external services**: Don't rely on real Discord/Sheets
7. **Set timeouts**: Prevent hanging with `--timeout`
8. **Track performance**: Add baseline tests
9. **Run smoke tests frequently**: Before every commit
10. **Update baselines**: When system improves

### DON'T ❌

1. **Don't skip cleanup**: Leaves junk data
2. **Don't test implementation details**: Test behavior
3. **Don't make tests dependent**: Each should run alone
4. **Don't hardcode IDs**: Use dynamic detection
5. **Don't ignore flaky tests**: Fix root cause
6. **Don't test external services**: Mock them
7. **Don't use sleep excessively**: Use proper waits
8. **Don't commit failing tests**: Fix before pushing
9. **Don't ignore performance**: Track regressions
10. **Don't over-assert**: Test what matters

## Troubleshooting

### Tests Hang

**Problem**: Test never completes
**Solution**:
```bash
pytest tests/e2e/ --timeout=300  # 5 min timeout
```

### Database Errors

**Problem**: Connection refused / table not found
**Solution**:
```bash
# Check PostgreSQL is running
# Run migrations
python -c "from src.database import init_db; import asyncio; asyncio.run(init_db())"
```

### Import Errors

**Problem**: Cannot import module
**Solution**:
```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-timeout
```

### Flaky Tests

**Problem**: Test passes sometimes, fails other times
**Solutions**:
- Add retry logic for external calls
- Increase wait times if timing-related
- Use proper async waits instead of sleep
- Mock unreliable external services

### Cleanup Failures

**Problem**: Cleanup doesn't remove test data
**Solution**:
```sql
-- Manual cleanup in PostgreSQL
DELETE FROM tasks WHERE id LIKE 'TASK-%' AND assignee = 'John';
```

## Advanced Topics

### Custom Simulators

```python
class CustomSimulator(ConversationSimulator):
    """Simulator with custom behavior."""

    async def send_message(self, message: str):
        # Add custom pre-processing
        message = message.upper()
        return await super().send_message(message)
```

### Test Data Factories

```python
from dataclasses import dataclass

@dataclass
class TaskFactory:
    """Factory for creating test tasks."""

    @staticmethod
    def simple_task(assignee: str = "John") -> str:
        return f"Create task for {assignee}: Test task"

    @staticmethod
    def urgent_task(assignee: str = "John") -> str:
        return f"URGENT: Critical bug for {assignee}"
```

### Parameterized Tests

```python
@pytest.mark.parametrize("assignee,expected", [
    ("John", "John"),
    ("Zea", "Zea"),
    ("Mayank", "Mayank"),
])
async def test_task_for_each_assignee(assignee, expected):
    sim = ConversationSimulator()
    await sim.send_message(f"Create task for {assignee}: Test")
    await sim.send_message("yes")

    task = await sim.assert_task_in_database(assignee=expected)
    await sim.cleanup()
```

### Fixtures

```python
@pytest.fixture
async def simulator():
    """Fixture providing a simulator with cleanup."""
    sim = ConversationSimulator()
    yield sim
    await sim.cleanup()

async def test_with_fixture(simulator):
    await simulator.send_message("Hello")
    simulator.assert_contains("hello")
    # No cleanup needed - fixture handles it
```

## Future Enhancements

- [ ] Visual regression testing (screenshot comparison)
- [ ] Load testing (100+ concurrent users)
- [ ] Chaos engineering (random failures)
- [ ] Integration with production monitoring
- [ ] Automatic performance regression alerts
- [ ] Test data factories for complex scenarios
- [ ] Parallel test execution
- [ ] Test report dashboard
- [ ] Video recording of failed tests
- [ ] Automatic test generation from user sessions

---

**Last Updated**: 2026-01-25
**Framework Version**: 1.0.0
**Maintainer**: Boss Workflow Team
