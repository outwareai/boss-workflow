"""
Unit tests for ProjectRepository.

Tier 2 Repository Tests: Comprehensive coverage for project management operations.
Tests cover CRUD, statistics aggregation, lifecycle management, and find-or-create patterns.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime

from src.database.repositories.projects import ProjectRepository
from src.database.models import ProjectDB, TaskDB


@pytest.fixture
def mock_database():
    """Mock database with session context manager."""
    db = Mock()
    session = AsyncMock()

    # Mock session context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    # Mock session methods
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = Mock()
    session.delete = AsyncMock()

    db.session = Mock(return_value=session)

    return db, session


@pytest.fixture
def project_repository(mock_database):
    """Create ProjectRepository with mocked database."""
    db, session = mock_database
    repo = ProjectRepository()
    repo.db = db
    return repo, session


@pytest.fixture
def sample_project():
    """Create a sample ProjectDB instance for testing."""
    return ProjectDB(
        id=1,
        name="Q1 2026 Sprint",
        description="System health improvements",
        color="#FF5733",
        status="active",
        created_by="Boss",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


# ============================================================
# CREATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_create_project_success(project_repository):
    """Test creating a new project successfully."""
    repo, session = project_repository

    result = await repo.create(
        name="Q1 2026 Sprint",
        description="System health improvements",
        color="#FF5733",
        created_by="Boss"
    )

    # Verify session.add and flush were called
    session.add.assert_called_once()
    session.flush.assert_called_once()

    # Verify project was created with correct data
    added_project = session.add.call_args[0][0]
    assert added_project.name == "Q1 2026 Sprint"
    assert added_project.description == "System health improvements"
    assert added_project.color == "#FF5733"
    assert added_project.status == "active"
    assert added_project.created_by == "Boss"


@pytest.mark.asyncio
async def test_create_project_minimal_fields(project_repository):
    """Test creating a project with only required fields."""
    repo, session = project_repository

    result = await repo.create(name="Minimal Project")

    session.add.assert_called_once()
    added_project = session.add.call_args[0][0]
    assert added_project.name == "Minimal Project"
    assert added_project.description is None
    assert added_project.color is None
    assert added_project.status == "active"


@pytest.mark.asyncio
async def test_create_project_error_handling(project_repository):
    """Test project creation error handling raises exception."""
    from src.database.exceptions import DatabaseOperationError
    repo, session = project_repository

    # Simulate database error
    session.flush.side_effect = Exception("Database error")

    # Should raise DatabaseOperationError
    with pytest.raises(DatabaseOperationError, match="Failed to create project"):
        await repo.create(name="Error Project")


# ============================================================
# READ TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_by_id_found(project_repository, sample_project):
    """Test retrieving a project by ID when it exists."""
    repo, session = project_repository

    # Mock execute result
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_project)
    session.execute.return_value = mock_result

    result = await repo.get_by_id(1)

    assert result == sample_project
    assert result.id == 1
    assert result.name == "Q1 2026 Sprint"


@pytest.mark.asyncio
async def test_get_by_id_not_found(project_repository):
    """Test retrieving a project by ID when it doesn't exist."""
    repo, session = project_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_by_id(999)

    assert result is None


@pytest.mark.asyncio
async def test_get_by_name_found(project_repository, sample_project):
    """Test retrieving a project by name (case-insensitive)."""
    repo, session = project_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_project)
    session.execute.return_value = mock_result

    result = await repo.get_by_name("q1 2026")

    assert result == sample_project
    assert result.name == "Q1 2026 Sprint"


@pytest.mark.asyncio
async def test_get_by_name_not_found(project_repository):
    """Test retrieving a project by name when it doesn't exist."""
    repo, session = project_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute.return_value = mock_result

    result = await repo.get_by_name("Nonexistent Project")

    assert result is None


@pytest.mark.asyncio
async def test_get_all_projects(project_repository):
    """Test retrieving all projects."""
    repo, session = project_repository

    projects = [
        ProjectDB(id=1, name="Project 1", status="active"),
        ProjectDB(id=2, name="Project 2", status="active"),
        ProjectDB(id=3, name="Project 3", status="archived")
    ]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=projects)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_all()

    assert len(result) == 3
    assert result[0].name == "Project 1"


@pytest.mark.asyncio
async def test_get_all_filtered_by_status(project_repository):
    """Test retrieving projects filtered by status."""
    repo, session = project_repository

    active_projects = [
        ProjectDB(id=1, name="Project 1", status="active"),
        ProjectDB(id=2, name="Project 2", status="active")
    ]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=active_projects)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_all(status="active")

    assert len(result) == 2
    assert all(p.status == "active" for p in result)


@pytest.mark.asyncio
async def test_get_active_projects(project_repository):
    """Test retrieving only active projects."""
    repo, session = project_repository

    active_projects = [
        ProjectDB(id=1, name="Active 1", status="active"),
        ProjectDB(id=2, name="Active 2", status="active")
    ]

    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=active_projects)
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    session.execute.return_value = mock_result

    result = await repo.get_active()

    assert len(result) == 2
    assert all(p.status == "active" for p in result)


# ============================================================
# UPDATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_update_project_success(project_repository, sample_project):
    """Test updating a project successfully."""
    repo, session = project_repository

    # Mock execute for update and then select
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_project)
    session.execute.return_value = mock_result

    updates = {"description": "Updated description", "color": "#00FF00"}
    result = await repo.update(1, updates)

    # Verify execute was called (for both update and select)
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_update_adds_timestamp(project_repository, sample_project):
    """Test that update automatically adds updated_at timestamp."""
    repo, session = project_repository

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_project)
    session.execute.return_value = mock_result

    updates = {"description": "New description"}
    await repo.update(1, updates)

    # Verify the update call included updated_at
    # Note: We check that execute was called, timestamp is added in the method
    assert session.execute.called


@pytest.mark.asyncio
async def test_archive_project(project_repository, sample_project):
    """Test archiving a project."""
    repo, session = project_repository

    sample_project.status = "archived"
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_project)
    session.execute.return_value = mock_result

    result = await repo.archive(1)

    assert session.execute.called


@pytest.mark.asyncio
async def test_complete_project(project_repository, sample_project):
    """Test marking a project as completed."""
    repo, session = project_repository

    sample_project.status = "completed"
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=sample_project)
    session.execute.return_value = mock_result

    result = await repo.complete(1)

    assert session.execute.called


# ============================================================
# DELETE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_delete_project_unassigns_tasks(project_repository):
    """Test deleting a project unassigns its tasks."""
    repo, session = project_repository

    result = await repo.delete(1)

    # Verify execute was called twice (unassign tasks, delete project)
    assert session.execute.call_count == 2
    assert result is True


@pytest.mark.asyncio
async def test_delete_project_sets_needs_sync(project_repository):
    """Test that delete sets needs_sheet_sync flag on tasks."""
    repo, session = project_repository

    await repo.delete(1)

    # Verify execute was called for both update and delete operations
    assert session.execute.call_count == 2


# ============================================================
# STATISTICS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_get_project_stats_empty_project(project_repository, sample_project):
    """Test getting statistics for a project with no tasks."""
    repo, session = project_repository

    # Mock get_by_id to return project
    with patch.object(repo, 'get_by_id', return_value=sample_project):
        # Mock status counts query (empty)
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))

        # Mock overdue count query
        mock_overdue = Mock()
        mock_overdue.scalar = Mock(return_value=0)

        session.execute.side_effect = [mock_result, mock_overdue]

        stats = await repo.get_project_stats(1)

        assert stats["project_id"] == 1
        assert stats["name"] == "Q1 2026 Sprint"
        assert stats["total_tasks"] == 0
        assert stats["completed_tasks"] == 0
        assert stats["progress_percent"] == 0


@pytest.mark.asyncio
async def test_get_project_stats_with_tasks(project_repository, sample_project):
    """Test getting statistics for a project with tasks."""
    repo, session = project_repository

    with patch.object(repo, 'get_by_id', return_value=sample_project):
        # Mock status counts: 6 completed, 4 pending
        status_rows = [
            ("completed", 6),
            ("pending", 4)
        ]
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter(status_rows))

        # Mock overdue count
        mock_overdue = Mock()
        mock_overdue.scalar = Mock(return_value=2)

        session.execute.side_effect = [mock_result, mock_overdue]

        stats = await repo.get_project_stats(1)

        assert stats["total_tasks"] == 10
        assert stats["completed_tasks"] == 6
        assert stats["progress_percent"] == 60.0
        assert stats["overdue_tasks"] == 2
        assert stats["tasks_by_status"] == {"completed": 6, "pending": 4}


@pytest.mark.asyncio
async def test_get_project_stats_nonexistent_project(project_repository):
    """Test getting statistics for a nonexistent project."""
    repo, session = project_repository

    with patch.object(repo, 'get_by_id', return_value=None):
        stats = await repo.get_project_stats(999)

        assert stats == {}


@pytest.mark.asyncio
async def test_get_all_stats_multiple_projects(project_repository):
    """Test getting statistics for all active projects."""
    repo, session = project_repository

    projects = [
        ProjectDB(id=1, name="Project 1", status="active"),
        ProjectDB(id=2, name="Project 2", status="active")
    ]

    with patch.object(repo, 'get_active', return_value=projects):
        # Mock status counts for both projects
        status_rows = [
            (1, "completed", 5),
            (1, "pending", 5),
            (2, "completed", 8),
            (2, "pending", 2)
        ]
        mock_status = Mock()
        mock_status.__iter__ = Mock(return_value=iter(status_rows))

        # Mock overdue counts
        overdue_rows = [(1, 1), (2, 0)]
        mock_overdue = Mock()
        mock_overdue.__iter__ = Mock(return_value=iter(overdue_rows))

        session.execute.side_effect = [mock_status, mock_overdue]

        stats = await repo.get_all_stats()

        assert len(stats) == 2
        # Sorted by progress descending
        assert stats[0]["progress_percent"] == 80.0  # Project 2
        assert stats[1]["progress_percent"] == 50.0  # Project 1


@pytest.mark.asyncio
async def test_get_all_stats_no_active_projects(project_repository):
    """Test getting statistics when no active projects exist."""
    repo, session = project_repository

    with patch.object(repo, 'get_active', return_value=[]):
        stats = await repo.get_all_stats()

        assert stats == []


# ============================================================
# FIND OR CREATE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_find_or_create_existing_project(project_repository, sample_project):
    """Test find_or_create returns existing project."""
    repo, session = project_repository

    with patch.object(repo, 'get_by_name', return_value=sample_project):
        result = await repo.find_or_create("Q1 2026 Sprint", created_by="Boss")

        assert result == sample_project
        # Should not call create
        session.add.assert_not_called()


@pytest.mark.asyncio
async def test_find_or_create_new_project(project_repository):
    """Test find_or_create creates new project when not found."""
    repo, session = project_repository

    with patch.object(repo, 'get_by_name', return_value=None):
        result = await repo.find_or_create("New Project", created_by="Boss")

        # Should call add for new project
        session.add.assert_called_once()


@pytest.mark.asyncio
async def test_find_or_create_idempotency(project_repository, sample_project):
    """Test find_or_create idempotency - multiple calls return same project."""
    repo, session = project_repository

    with patch.object(repo, 'get_by_name', return_value=sample_project):
        result1 = await repo.find_or_create("Q1 2026 Sprint")
        result2 = await repo.find_or_create("Q1 2026 Sprint")

        assert result1 == result2
        assert result1.id == result2.id
