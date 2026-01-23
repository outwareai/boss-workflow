# Repository Unit Tests

Q3 2026: Comprehensive unit tests for database repositories.

## Test Coverage Target: 70%+

### Test Files
- `test_task_repository.py` - TaskRepository (37+ methods) ✅ TEMPLATE COMPLETE
- `test_audit_repository.py` - AuditRepository (15+ methods) 🔄 TODO
- `test_team_repository.py` - TeamRepository (12+ methods) 🔄 TODO
- `test_project_repository.py` - ProjectRepository 🔄 TODO
- `test_conversation_repository.py` - ConversationRepository 🔄 TODO
- `test_oauth_repository.py` - OAuthTokenRepository 🔄 TODO
- `test_time_tracking_repository.py` - TimeTrackingRepository 🔄 TODO
- `test_attendance_repository.py` - AttendanceRepository 🔄 TODO
- `test_ai_memory_repository.py` - AIMemoryRepository 🔄 TODO
- `test_recurring_repository.py` - RecurringTaskRepository 🔄 TODO
- `test_staff_context_repository.py` - StaffContextRepository 🔄 TODO

## Running Tests

```bash
# Run all repository tests
pytest tests/unit/repositories/ -v

# Run with coverage
pytest tests/unit/repositories/ -v --cov=src/database/repositories --cov-report=html

# Run specific test file
pytest tests/unit/repositories/test_task_repository.py -v

# Run specific test
pytest tests/unit/repositories/test_task_repository.py::test_create_task_success -v
```

## Test Pattern

Each test file should follow this structure:

```python
"""
Unit tests for {Repository}.

Q3 2026: Part of 70% coverage goal.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from src.database.repositories.{module} import {Repository}

@pytest.fixture
def mock_database():
    """Mock database with session context manager."""
    # ... standard pattern

@pytest.fixture
def repository(mock_database):
    """Create repository with mocked database."""
    # ... standard pattern

# CREATE tests
async def test_create_success(repository): ...
async def test_create_duplicate(repository): ...

# READ tests
async def test_get_by_id_found(repository): ...
async def test_get_by_id_not_found(repository): ...

# UPDATE tests
async def test_update_success(repository): ...
async def test_update_not_found(repository): ...

# DELETE tests
async def test_delete_success(repository): ...
async def test_delete_not_found(repository): ...

# Edge cases
async def test_concurrent_operations(repository): ...
async def test_transaction_rollback(repository): ...
```

## Best Practices

1. **Use AsyncMock for async methods**
2. **Mock database sessions, not actual DB**
3. **Test happy path AND edge cases**
4. **Test error handling (not found, duplicates, validation)**
5. **Test relationships (subtasks, dependencies)**
6. **Use meaningful test names** (test_{method}_{scenario})
7. **Follow existing patterns** from test_task_repository.py

## See Also

- `../test_api_validation.py` - API input validation tests
- `../test_encryption.py` - Encryption tests  
- `../test_rate_limiting.py` - Rate limiting tests
- `../../TEST.MD` - Complete testing documentation
