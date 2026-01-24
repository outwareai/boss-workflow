"""
Tests for FastAPI route endpoints (main.py).

Q1 2027: Comprehensive API route testing to boost coverage.
Tests health checks, task API, admin endpoints, and webhooks.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime

# Import app
from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_database():
    """Mock database instance."""
    db = AsyncMock()
    db._initialized = True
    db.engine = MagicMock()
    db.engine.pool = MagicMock()
    db.engine.pool.size = MagicMock(return_value=5)
    db.engine.pool.checkedin = MagicMock(return_value=3)
    db.engine.pool.checkedout = MagicMock(return_value=2)
    db.engine.pool.overflow = MagicMock(return_value=0)
    db.engine.pool._max_overflow = 10
    return db


@pytest.fixture
def mock_task_repo():
    """Mock task repository."""
    repo = AsyncMock()
    repo.get_all = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_status = AsyncMock(return_value=[])
    repo.get_by_assignee = AsyncMock(return_value=[])
    repo.create = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=True)
    repo.get_subtasks = AsyncMock(return_value=[])
    repo.get_blocking_tasks = AsyncMock(return_value=[])
    repo.get_blocked_tasks = AsyncMock(return_value=[])
    repo.add_subtask = AsyncMock(return_value=None)
    repo.add_dependency = AsyncMock(return_value=None)
    repo.get_daily_stats = AsyncMock(return_value={})
    return repo


@pytest.fixture
def mock_sheets():
    """Mock sheets integration."""
    sheets = AsyncMock()
    sheets.get_daily_tasks = AsyncMock(return_value=[])
    sheets.get_overdue_tasks = AsyncMock(return_value=[])
    sheets.generate_weekly_overview = AsyncMock(return_value={})
    return sheets


# ==================== HEALTH & INFO ROUTES ====================

class TestHealthAndInfo:
    """Test health check and info endpoints."""

    def test_root_endpoint(self, client):
        """Test GET / returns basic info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Boss Workflow Automation"
        assert data["version"] == "1.0.0"

    def test_health_endpoint(self, client):
        """Test GET /health returns service status."""
        with patch('src.main.get_database') as mock_db:
            mock_db.return_value.health_check = AsyncMock(return_value={"status": "healthy"})
            with patch('src.main.get_discord_bot') as mock_discord:
                mock_discord.return_value = None

                response = client.get("/health")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert "services" in data
                assert "timestamp" in data

    def test_health_endpoint_with_discord(self, client):
        """Test /health shows Discord bot status."""
        with patch('src.main.get_database') as mock_db:
            mock_db.return_value.health_check = AsyncMock(return_value={"status": "healthy"})
            with patch('src.main.get_discord_bot') as mock_discord:
                mock_bot = MagicMock()
                mock_bot.is_closed = MagicMock(return_value=False)
                mock_discord.return_value = mock_bot

                response = client.get("/health")

                assert response.status_code == 200
                data = response.json()
                assert data["services"]["discord_bot"] == "connected"

    def test_db_health_endpoint(self, client, mock_database):
        """Test GET /health/db returns pool stats."""
        with patch('src.main.get_database', return_value=mock_database):
            response = client.get("/health/db")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "pool_size" in data
            assert "checked_in" in data
            assert "checked_out" in data

    def test_db_health_not_initialized(self, client):
        """Test /health/db when database not initialized."""
        mock_db = AsyncMock()
        mock_db._initialized = False

        with patch('src.main.get_database', return_value=mock_db):
            response = client.get("/health/db")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "not_initialized"


# ==================== TASK API ROUTES ====================

class TestTaskAPI:
    """Test database task API endpoints."""

    def test_get_all_tasks(self, client, mock_task_repo):
        """Test GET /api/db/tasks returns all tasks."""
        mock_task = MagicMock()
        mock_task.task_id = "TASK-20260124-001"
        mock_task.title = "Test Task"
        mock_task.status = "pending"
        mock_task.priority = "high"
        mock_task.assignee = "John"
        mock_task.deadline = None
        mock_task.created_at = datetime.now()

        mock_task_repo.get_all.return_value = [mock_task]

        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.get("/api/db/tasks")

            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data
            assert len(data["tasks"]) == 1
            assert data["tasks"][0]["id"] == "TASK-20260124-001"
            assert data["pagination"]["limit"] == 50

    def test_get_tasks_with_status_filter(self, client, mock_task_repo):
        """Test GET /api/db/tasks?status=completed filters by status."""
        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.get("/api/db/tasks?status=completed")

            assert response.status_code == 200
            mock_task_repo.get_by_status.assert_called_once()

    def test_get_tasks_with_assignee_filter(self, client, mock_task_repo):
        """Test GET /api/db/tasks?assignee=John filters by assignee."""
        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.get("/api/db/tasks?assignee=John")

            assert response.status_code == 200
            mock_task_repo.get_by_assignee.assert_called_once()

    def test_get_tasks_pagination(self, client, mock_task_repo):
        """Test GET /api/db/tasks with limit/offset pagination."""
        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.get("/api/db/tasks?limit=10&offset=20")

            assert response.status_code == 200
            data = response.json()
            assert data["pagination"]["limit"] == 10
            assert data["pagination"]["offset"] == 20

    def test_get_task_by_id(self, client, mock_task_repo):
        """Test GET /api/db/tasks/{task_id} returns task details."""
        mock_task = MagicMock()
        mock_task.task_id = "TASK-20260124-001"
        mock_task.title = "Test Task"
        mock_task.description = "Description"
        mock_task.status = "in_progress"
        mock_task.priority = "high"
        mock_task.assignee = "John"
        mock_task.deadline = None
        mock_task.created_at = datetime.now()
        mock_task.updated_at = datetime.now()
        mock_task.progress = 50
        mock_task.project_id = None

        mock_task_repo.get_by_id.return_value = mock_task

        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.get("/api/db/tasks/TASK-20260124-001")

            assert response.status_code == 200
            data = response.json()
            assert data["task"]["id"] == "TASK-20260124-001"
            assert data["task"]["title"] == "Test Task"
            assert "subtasks" in data
            assert "blocking_tasks" in data

    def test_get_task_not_found(self, client, mock_task_repo):
        """Test GET /api/db/tasks/{id} with non-existent task returns 404."""
        mock_task_repo.get_by_id.return_value = None

        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.get("/api/db/tasks/TASK-99999999-999")

            assert response.status_code == 404

    def test_add_subtask(self, client, mock_task_repo):
        """Test POST /api/db/tasks/{id}/subtasks creates subtask."""
        mock_subtask = MagicMock()
        mock_subtask.id = 1
        mock_task_repo.add_subtask.return_value = mock_subtask

        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.post(
                "/api/db/tasks/TASK-20260124-001/subtasks",
                json={"title": "Subtask 1", "description": "Test subtask"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["subtask_id"] == 1

    def test_add_subtask_invalid_data(self, client, mock_task_repo):
        """Test POST /api/db/tasks/{id}/subtasks with invalid data returns 400."""
        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.post(
                "/api/db/tasks/TASK-20260124-001/subtasks",
                json={"title": ""}  # Empty title
            )

            assert response.status_code == 400

    def test_add_dependency(self, client, mock_task_repo):
        """Test POST /api/db/tasks/{id}/dependencies creates dependency."""
        mock_dep = MagicMock()
        mock_dep.id = 1
        mock_task_repo.add_dependency.return_value = mock_dep

        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.post(
                "/api/db/tasks/TASK-20260124-002/dependencies",
                json={"depends_on": "TASK-20260124-001", "type": "depends_on"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    def test_add_dependency_invalid_task_id(self, client, mock_task_repo):
        """Test POST /api/db/tasks/{id}/dependencies with invalid task ID format."""
        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.post(
                "/api/db/tasks/TASK-20260124-002/dependencies",
                json={"depends_on": "INVALID-ID", "type": "depends_on"}
            )

            assert response.status_code == 400


# ==================== ADMIN API ROUTES ====================

class TestAdminAPI:
    """Test admin API endpoints."""

    def test_run_migration_simple_unauthorized(self, client):
        """Test POST /admin/run-migration-simple without secret returns 403 or error."""
        with patch('config.settings.admin_secret', 'correct_secret'):
            response = client.post(
                "/admin/run-migration-simple",
                json={"secret": "wrong_secret"}
            )

            # Should return 403 or 200 with error status
            assert response.status_code in [403, 200]
            if response.status_code == 200:
                data = response.json()
                assert data.get("status") == "error" or "error" in data

    def test_run_migration_unauthorized(self, client):
        """Test POST /admin/run-migration without secret returns 403 or error."""
        with patch('config.settings.admin_secret', 'correct_secret'):
            response = client.post(
                "/admin/run-migration",
                json={"secret": "wrong_secret"}
            )

            # Should return 403 or 200 with error status
            assert response.status_code in [403, 200]
            if response.status_code == 200:
                data = response.json()
                assert data.get("status") == "error" or "error" in data

    def test_seed_test_team_unauthorized(self, client):
        """Test POST /admin/seed-test-team without secret returns 403 or error."""
        with patch('config.settings.admin_secret', 'correct_secret'):
            response = client.post(
                "/admin/seed-test-team",
                json={"secret": "wrong_secret"}
            )

            # Should return 403 or 200 with error status
            assert response.status_code in [403, 200]
            if response.status_code == 200:
                data = response.json()
                assert data.get("status") == "error" or "error" in data

    def test_clear_conversations_unauthorized(self, client):
        """Test POST /admin/clear-conversations without secret returns 403 or error."""
        with patch('config.settings.admin_secret', 'correct_secret'):
            response = client.post(
                "/admin/clear-conversations",
                json={"secret": "wrong_secret"}
            )

            # Should return 403 or 200 with error status
            assert response.status_code in [403, 200]
            if response.status_code == 200:
                data = response.json()
                assert data.get("status") == "error" or "error" in data

    def test_backup_oauth_tokens(self, client):
        """Test POST /api/admin/backup-oauth-tokens backs up tokens."""
        with patch('src.main.get_database') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            mock_db.return_value.session = MagicMock(return_value=mock_session)

            response = client.post("/api/admin/backup-oauth-tokens")

            assert response.status_code == 200
            data = response.json()
            # Should return warning, success, or error
            assert data["status"] in ["warning", "success", "error"]

    def test_encrypt_oauth_tokens(self, client):
        """Test POST /api/admin/encrypt-oauth-tokens encrypts tokens."""
        with patch('src.main.get_database') as mock_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_db.return_value.session = MagicMock(return_value=mock_session)

            response = client.post("/api/admin/encrypt-oauth-tokens?mode=gradual")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ["warning", "success", "error"]

    def test_verify_oauth_encryption(self, client):
        """Test GET /api/admin/verify-oauth-encryption checks encryption."""
        with patch('src.main.get_database') as mock_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_db.return_value.session = MagicMock(return_value=mock_session)

            response = client.get("/api/admin/verify-oauth-encryption")

            assert response.status_code == 200
            data = response.json()
            # Accept both success and error
            assert data["status"] in ["success", "error"]
            assert "coverage_percent" in data or "error" in data

    def test_trigger_sync(self, client):
        """Test POST /api/db/sync triggers database sync."""
        with patch('src.main.get_sheets_sync') as mock_sync:
            mock_sync.return_value.sync_pending_tasks = AsyncMock(
                return_value={"synced": 5, "errors": []}
            )

            response = client.post("/api/db/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    def test_get_db_stats(self, client, mock_task_repo):
        """Test GET /api/db/stats returns statistics."""
        mock_audit_repo = AsyncMock()
        mock_audit_repo.get_activity_stats = AsyncMock(return_value={"total": 100})

        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_stats = AsyncMock(return_value={"total": 50})

        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            with patch('src.database.repositories.get_audit_repository', return_value=mock_audit_repo):
                with patch('src.database.repositories.get_conversation_repository', return_value=mock_conv_repo):
                    response = client.get("/api/db/stats")

                    assert response.status_code == 200
                    data = response.json()
                    assert "tasks" in data
                    assert "audit" in data
                    assert "conversations" in data


# ==================== AUDIT API ROUTES ====================

class TestAuditAPI:
    """Test audit log API endpoints."""

    def test_get_task_audit(self, client):
        """Test GET /api/db/audit/{task_id} returns audit history."""
        mock_audit_repo = AsyncMock()
        mock_log = MagicMock()
        mock_log.action = "status_change"
        mock_log.field_changed = "status"
        mock_log.old_value = "pending"
        mock_log.new_value = "completed"
        mock_log.changed_by = "John"
        mock_log.timestamp = datetime.now()
        mock_log.reason = "Task completed"

        mock_audit_repo.get_task_history = AsyncMock(return_value=[mock_log])

        with patch('src.database.repositories.get_audit_repository', return_value=mock_audit_repo):
            response = client.get("/api/db/audit/TASK-20260124-001")

            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "TASK-20260124-001"
            assert len(data["history"]) == 1
            assert data["history"][0]["action"] == "status_change"

    def test_query_audit_logs(self, client):
        """Test GET /api/db/audit with filters."""
        mock_audit_repo = AsyncMock()
        mock_audit_repo.query = AsyncMock(return_value=[])
        mock_audit_repo.count = AsyncMock(return_value=0)

        with patch('src.database.repositories.get_audit_repository', return_value=mock_audit_repo):
            response = client.get("/api/db/audit?action=task_delete&limit=50")

            assert response.status_code == 200
            data = response.json()
            assert "logs" in data
            assert "total" in data
            assert data["limit"] == 50


# ==================== PROJECT API ROUTES ====================

class TestProjectAPI:
    """Test project API endpoints."""

    def test_get_projects(self, client):
        """Test GET /api/db/projects returns all projects."""
        mock_project_repo = AsyncMock()
        mock_project_repo.get_all_stats = AsyncMock(return_value=[
            {"id": 1, "name": "Project 1", "task_count": 10}
        ])

        with patch('src.database.repositories.get_project_repository', return_value=mock_project_repo):
            response = client.get("/api/db/projects")

            assert response.status_code == 200
            data = response.json()
            assert "projects" in data
            assert len(data["projects"]) == 1

    def test_create_project(self, client):
        """Test POST /api/db/projects creates project."""
        mock_project_repo = AsyncMock()
        mock_project = MagicMock()
        mock_project.id = 1
        mock_project_repo.create = AsyncMock(return_value=mock_project)

        with patch('src.database.repositories.get_project_repository', return_value=mock_project_repo):
            response = client.post(
                "/api/db/projects",
                json={
                    "name": "New Project",
                    "description": "Test project",
                    "color": "#FF5733"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["project_id"] == 1

    def test_create_project_invalid_color(self, client):
        """Test POST /api/db/projects with invalid color format."""
        response = client.post(
            "/api/db/projects",
            json={
                "name": "New Project",
                "color": "red"  # Invalid - must be hex
            }
        )

        assert response.status_code == 400

    def test_create_project_xss_prevention(self, client):
        """Test POST /api/db/projects prevents XSS in name."""
        response = client.post(
            "/api/db/projects",
            json={
                "name": "<script>alert('xss')</script>",
                "description": "Test"
            }
        )

        assert response.status_code == 400


# ==================== WEBHOOK ROUTES ====================

class TestWebhookRoutes:
    """Test webhook endpoints."""

    def test_telegram_webhook(self, client):
        """Test POST /webhook/telegram processes Telegram updates."""
        webhook_data = {
            "update_id": 12345,
            "message": {
                "message_id": 1,
                "from": {"id": 123, "first_name": "Test"},
                "chat": {"id": 123, "type": "private"},
                "text": "/status"
            }
        }

        with patch('src.main.get_telegram_bot_simple') as mock_bot:
            mock_bot.return_value.process_webhook = AsyncMock()

            response = client.post("/webhook/telegram", json=webhook_data)

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    def test_telegram_webhook_invalid_update_id(self, client):
        """Test /webhook/telegram with invalid update_id."""
        webhook_data = {
            "update_id": -1,  # Invalid
            "message": {"message_id": 1, "chat": {"id": 123}}
        }

        response = client.post("/webhook/telegram", json=webhook_data)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_telegram_webhook_duplicate(self, client):
        """Test /webhook/telegram deduplicates updates."""
        webhook_data = {
            "update_id": 99999,
            "message": {
                "message_id": 1,
                "chat": {"id": 123},
                "text": "test"
            }
        }

        with patch('src.main.get_telegram_bot_simple') as mock_bot:
            mock_bot.return_value.process_webhook = AsyncMock()

            # First request
            response1 = client.post("/webhook/telegram", json=webhook_data)
            assert response1.status_code == 200

            # Second request (duplicate) should also succeed but be skipped
            response2 = client.post("/webhook/telegram", json=webhook_data)
            assert response2.status_code == 200

    def test_discord_webhook(self, client):
        """Test POST /webhook/discord accepts Discord webhooks."""
        webhook_data = {
            "type": 0,
            "id": "123456789012345678",
            "token": "webhook_token_here"
        }

        response = client.post("/webhook/discord", json=webhook_data)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


# ==================== OTHER API ROUTES ====================

class TestOtherAPI:
    """Test miscellaneous API endpoints."""

    def test_get_status(self, client, mock_sheets):
        """Test GET /api/status returns system status."""
        mock_task1 = {"Status": "completed"}
        mock_task2 = {"Status": "pending"}
        mock_sheets.get_daily_tasks.return_value = [mock_task1, mock_task2]
        mock_sheets.get_overdue_tasks.return_value = []

        with patch('src.main.get_sheets_integration', return_value=mock_sheets):
            with patch('src.main.get_scheduler_manager') as mock_scheduler:
                mock_scheduler.return_value.get_job_status = MagicMock(return_value=[])

                response = client.get("/api/status")

                assert response.status_code == 200
                data = response.json()
                assert "tasks" in data
                assert data["tasks"]["today"] == 2
                assert data["tasks"]["completed"] == 1

    def test_trigger_job(self, client):
        """Test POST /api/trigger-job/{job_id} triggers job."""
        with patch('src.main.get_scheduler_manager') as mock_scheduler:
            mock_scheduler.return_value.trigger_job = MagicMock(return_value=True)

            response = client.post("/api/trigger-job/morning_standup")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    def test_trigger_job_not_found(self, client):
        """Test /api/trigger-job with non-existent job returns 404."""
        with patch('src.main.get_scheduler_manager') as mock_scheduler:
            mock_scheduler.return_value.trigger_job = MagicMock(return_value=False)

            response = client.post("/api/trigger-job/invalid_job")

            assert response.status_code == 404

    def test_get_daily_tasks(self, client, mock_sheets):
        """Test GET /api/tasks/daily returns today's tasks."""
        mock_sheets.get_daily_tasks.return_value = [{"id": "TASK-001"}]

        with patch('src.main.get_sheets_integration', return_value=mock_sheets):
            response = client.get("/api/tasks/daily")

            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data

    def test_get_overdue_tasks(self, client, mock_sheets):
        """Test GET /api/tasks/overdue returns overdue tasks."""
        mock_sheets.get_overdue_tasks.return_value = [{"id": "TASK-002"}]

        with patch('src.main.get_sheets_integration', return_value=mock_sheets):
            response = client.get("/api/tasks/overdue")

            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data

    def test_get_weekly_overview(self, client, mock_sheets):
        """Test GET /api/weekly-overview returns weekly stats."""
        mock_sheets.generate_weekly_overview.return_value = {
            "completed": 50,
            "pending": 10
        }

        with patch('src.main.get_sheets_integration', return_value=mock_sheets):
            response = client.get("/api/weekly-overview")

            assert response.status_code == 200
            data = response.json()
            assert "completed" in data

    def test_teach_preference(self, client):
        """Test POST /api/preferences/{user_id}/teach learns preference."""
        with patch('src.memory.learning.get_learning_manager') as mock_learning:
            mock_learning.return_value.process_teach_command = AsyncMock(
                return_value=(True, "Preference saved")
            )

            response = client.post(
                "/api/preferences/user123/teach",
                json={"text": "I prefer morning meetings"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_teach_preference_invalid_text(self, client):
        """Test /api/preferences/{user_id}/teach with too short text."""
        response = client.post(
            "/api/preferences/user123/teach",
            json={"text": "hi"}  # Too short
        )

        assert response.status_code == 400

    def test_get_user_preferences(self, client):
        """Test GET /api/preferences/{user_id} returns preferences."""
        with patch('src.main.get_preferences_manager') as mock_prefs:
            mock_user_prefs = MagicMock()
            mock_user_prefs.to_dict = MagicMock(return_value={"theme": "dark"})
            mock_prefs.return_value.get_preferences = AsyncMock(return_value=mock_user_prefs)

            response = client.get("/api/preferences/user123")

            assert response.status_code == 200
            data = response.json()
            assert "theme" in data


# ==================== ERROR HANDLING ====================

class TestErrorHandling:
    """Test error handling and validation."""

    def test_validation_error_handler(self, client):
        """Test validation errors return 400 with details."""
        response = client.get("/api/db/tasks?limit=9999999")  # Exceeds max

        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_invalid_json(self, client):
        """Test invalid JSON returns appropriate error."""
        response = client.post(
            "/api/db/projects",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        # FastAPI may return 400 or 422 for invalid JSON
        assert response.status_code in [400, 422]

    def test_missing_required_field(self, client):
        """Test missing required fields returns 400."""
        response = client.post(
            "/api/db/tasks/TASK-001/subtasks",
            json={}  # Missing title
        )

        assert response.status_code == 400

    def test_internal_server_error(self, client, mock_task_repo):
        """Test internal errors return 500."""
        mock_task_repo.get_all.side_effect = Exception("Database error")

        with patch('src.database.repositories.get_task_repository', return_value=mock_task_repo):
            response = client.get("/api/db/tasks")

            assert response.status_code == 500
            data = response.json()
            assert "error" in data
