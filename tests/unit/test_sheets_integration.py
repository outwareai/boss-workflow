"""
Unit tests for Google Sheets integration.

Tests Google Sheets operations including:
- Task CRUD operations
- Team member management
- Report generation
- Search and filtering
- Batch operations
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import gspread.exceptions

from src.integrations.sheets import GoogleSheetsIntegration, SHEET_DAILY_TASKS


@pytest.fixture
def sheets():
    """Create Google Sheets integration instance."""
    instance = GoogleSheetsIntegration()
    instance.spreadsheet = MagicMock()  # Initialize spreadsheet
    return instance


@pytest.fixture
def mock_worksheet():
    """Create mock worksheet."""
    worksheet = MagicMock()
    worksheet.get_all_records.return_value = []
    worksheet.get_all_values.return_value = [["Header1", "Header2"]]
    worksheet.append_row = MagicMock()
    worksheet.update = MagicMock()
    return worksheet


@pytest.fixture
def sample_task_data():
    """Sample task data for testing."""
    return {
        'id': 'TASK-001',
        'title': 'Fix login bug',
        'description': 'Users cannot log in',
        'assignee': 'Mayank',
        'priority': 'high',
        'status': 'pending',
        'task_type': 'bug',
        'deadline': '2026-02-01',
        'created_at': '2026-01-24 10:00',
        'updated_at': '2026-01-24 10:00'
    }


class TestGoogleSheetsIntegration:
    """Test Google Sheets integration functionality."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, sheets):
        """Test successful initialization."""
        with patch('gspread.authorize') as mock_auth:
            mock_client = MagicMock()
            mock_spreadsheet = MagicMock()
            mock_spreadsheet.title = "Boss Workflow"
            mock_client.open_by_key.return_value = mock_spreadsheet
            mock_auth.return_value = mock_client

            result = await sheets.initialize()

            assert result is True
            assert sheets._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_failure(self, sheets):
        """Test initialization failure."""
        with patch('gspread.authorize') as mock_auth:
            mock_auth.side_effect = Exception("Auth failed")

            result = await sheets.initialize()

            assert result is False

    @pytest.mark.asyncio
    async def test_add_task_success(self, sheets, sample_task_data, mock_worksheet):
        """Test adding task to sheet."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.get_all_values.return_value = [["Header"], ["Row1"]]

            row_num = await sheets.add_task(sample_task_data)

            assert row_num == 2
            mock_worksheet.append_row.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_task_not_initialized(self, sheets, sample_task_data):
        """Test adding task when not initialized."""
        sheets._initialized = False
        with patch.object(sheets, 'initialize') as mock_init:
            mock_init.return_value = False

            result = await sheets.add_task(sample_task_data)

            assert result is None

    @pytest.mark.asyncio
    async def test_update_task_success(self, sheets, mock_worksheet):
        """Test updating task."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_cell = MagicMock()
            mock_cell.row = 2
            mock_worksheet.find.return_value = mock_cell
            # Extend row to have enough columns (16 columns for Daily Tasks)
            mock_worksheet.row_values.return_value = ['TASK-001', 'Old Title', 'Desc', '', '', '', '', '', '', '', '', '', '', '', '', '']

            result = await sheets.update_task('TASK-001', {'title': 'New Title', 'status': 'in_progress'})

            assert result is True
            mock_worksheet.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, sheets, mock_worksheet):
        """Test updating non-existent task."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.find.return_value = None

            result = await sheets.update_task('TASK-999', {'status': 'done'})

            assert result is False

    @pytest.mark.asyncio
    async def test_get_task_success(self, sheets, mock_worksheet):
        """Test getting task by ID."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_cell = MagicMock()
            mock_cell.row = 2
            mock_worksheet.find.return_value = mock_cell

            # First call returns headers, second returns task row
            headers = ['ID', 'Title', 'Description']
            task_row = ['TASK-001', 'Fix bug', 'Critical bug']
            mock_worksheet.row_values = MagicMock(side_effect=[headers, task_row])

            task = await sheets.get_task('TASK-001')

            assert task is not None
            assert task.get('ID') == 'TASK-001' or task.get('Id') == 'TASK-001' or 'TASK-001' in str(task)

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, sheets, mock_worksheet):
        """Test getting non-existent task."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.find.return_value = None

            task = await sheets.get_task('TASK-999')

            assert task is None

    @pytest.mark.asyncio
    async def test_delete_task_success(self, sheets, mock_worksheet):
        """Test deleting task."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_cell = MagicMock()
            mock_cell.row = 2
            mock_worksheet.find.return_value = mock_cell

            result = await sheets.delete_task('TASK-001')

            assert result is True
            mock_worksheet.delete_rows.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_delete_task_header_protection(self, sheets, mock_worksheet):
        """Test that header row cannot be deleted."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_cell = MagicMock()
            mock_cell.row = 1  # Header row
            mock_worksheet.find.return_value = mock_cell

            result = await sheets.delete_task('TASK-001')

            assert result is False
            mock_worksheet.delete_rows.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_tasks(self, sheets, mock_worksheet):
        """Test getting all tasks."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.get_all_records.return_value = [
                {'ID': 'TASK-001', 'Title': 'Task 1'},
                {'ID': 'TASK-002', 'Title': 'Task 2'}
            ]

            tasks = await sheets.get_all_tasks()

            assert len(tasks) == 2
            assert tasks[0]['ID'] == 'TASK-001'

    @pytest.mark.asyncio
    async def test_get_tasks_by_status(self, sheets, mock_worksheet):
        """Test filtering tasks by status."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.get_all_records.return_value = [
                {'ID': 'TASK-001', 'Status': 'pending'},
                {'ID': 'TASK-002', 'Status': 'in_progress'},
                {'ID': 'TASK-003', 'Status': 'pending'}
            ]

            tasks = await sheets.get_tasks_by_status('pending')

            assert len(tasks) == 2
            assert all(t['Status'] == 'pending' for t in tasks)

    @pytest.mark.asyncio
    async def test_get_tasks_by_assignee(self, sheets, mock_worksheet):
        """Test filtering tasks by assignee."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.get_all_records.return_value = [
                {'ID': 'TASK-001', 'Assignee': 'Mayank'},
                {'ID': 'TASK-002', 'Assignee': 'Zea'},
                {'ID': 'TASK-003', 'Assignee': 'Mayank'}
            ]

            tasks = await sheets.get_tasks_by_assignee('Mayank')

            assert len(tasks) == 2
            assert all(t['Assignee'] == 'Mayank' for t in tasks)

    @pytest.mark.asyncio
    async def test_add_note(self, sheets, mock_worksheet):
        """Test adding note to task."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            with patch.object(sheets, '_increment_notes_count') as mock_inc:

                result = await sheets.add_note(
                    'TASK-001',
                    'Fix bug',
                    'Boss',
                    'update',
                    'Please prioritize this'
                )

                assert result is True
                mock_worksheet.append_row.assert_called_once()
                mock_inc.assert_called_once_with('TASK-001')

    @pytest.mark.asyncio
    async def test_update_team_member(self, sheets, mock_worksheet):
        """Test adding/updating team member."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            # Member exists - update existing row
            mock_cell = MagicMock()
            mock_cell.row = 2
            mock_worksheet.find.return_value = mock_cell
            mock_worksheet.get_all_values.return_value = [["Header"], ["Mayank", "old_id", "old@email.com"]]
            mock_worksheet.row_values.return_value = ["Mayank", "old_id", "old@email.com", "Developer", "Active", "0", "calendar"]
            with patch.object(sheets, 'get_all_tasks') as mock_tasks:
                mock_tasks.return_value = []

                result = await sheets.update_team_member(
                    'Mayank',
                    '123456789',
                    'mayank@example.com',
                    'Developer',
                    'Active',
                    'mayank@example.com'
                )

                assert result is True
                mock_worksheet.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_team_members(self, sheets, mock_worksheet):
        """Test getting all team members."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.get_all_records.return_value = [
                {'Name': 'Mayank', 'Role': 'Developer'},
                {'Name': 'Zea', 'Role': 'Admin'}
            ]

            members = await sheets.get_all_team_members()

            assert len(members) == 2
            assert members[0]['Name'] == 'Mayank'

    @pytest.mark.asyncio
    async def test_delete_team_member(self, sheets, mock_worksheet):
        """Test deleting team member."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_cell = MagicMock()
            mock_cell.row = 2
            mock_worksheet.find.return_value = mock_cell

            result = await sheets.delete_team_member('Mayank')

            assert result is True
            mock_worksheet.delete_rows.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_generate_weekly_report(self, sheets, mock_worksheet):
        """Test generating weekly report."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            with patch.object(sheets, 'get_all_tasks') as mock_tasks:
                mock_tasks.return_value = [
                    {
                        'ID': 'TASK-001',
                        'Status': 'completed',
                        'Created': '2026-01-20 10:00',
                        'Updated': '2026-01-22 15:00',
                        'Priority': 'high',
                        'Assignee': 'Mayank'
                    }
                ]

                report = await sheets.generate_weekly_report()

                assert 'week_num' in report
                assert 'tasks_completed' in report
                mock_worksheet.append_row.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_monthly_report(self, sheets, mock_worksheet):
        """Test generating monthly report."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            with patch.object(sheets, 'get_all_tasks') as mock_tasks:
                mock_tasks.return_value = [
                    {
                        'ID': 'TASK-001',
                        'Status': 'completed',
                        'Created': '2026-01-05 10:00',
                        'Updated': '2026-01-20 15:00',
                        'Priority': 'high'
                    }
                ]

                report = await sheets.generate_monthly_report(1, 2026)

                assert 'month' in report
                assert 'tasks_completed' in report

    @pytest.mark.asyncio
    async def test_archive_task(self, sheets, mock_worksheet):
        """Test archiving completed task."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            with patch.object(sheets, 'get_task') as mock_get:
                mock_get.return_value = {
                    'ID': 'TASK-001',
                    'Title': 'Test',
                    'Status': 'completed',
                    'Created': '2026-01-20',
                    'Updated': '2026-01-22'
                }
                mock_cell = MagicMock()
                mock_cell.row = 2
                mock_worksheet.find.return_value = mock_cell

                result = await sheets.archive_task('TASK-001')

                assert result is True
                # Should append to archive and delete from daily
                assert mock_worksheet.append_row.call_count == 1
                assert mock_worksheet.delete_rows.call_count == 1

    @pytest.mark.asyncio
    async def test_get_overdue_tasks(self, sheets, mock_worksheet):
        """Test getting overdue tasks."""
        sheets._initialized = True
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        with patch.object(sheets, 'get_all_tasks') as mock_tasks:
            mock_tasks.return_value = [
                {'ID': 'TASK-001', 'Status': 'pending', 'Deadline': yesterday},
                {'ID': 'TASK-002', 'Status': 'pending', 'Deadline': '2026-12-31'}
            ]

            overdue = await sheets.get_overdue_tasks()

            assert len(overdue) == 1
            assert overdue[0]['ID'] == 'TASK-001'

    @pytest.mark.asyncio
    async def test_search_tasks_by_query(self, sheets, mock_worksheet):
        """Test searching tasks by text query."""
        sheets._initialized = True
        with patch.object(sheets, 'get_all_tasks') as mock_tasks:
            mock_tasks.return_value = [
                {'ID': 'TASK-001', 'Title': 'Fix login bug', 'Description': 'Critical'},
                {'ID': 'TASK-002', 'Title': 'Add feature', 'Description': 'New dashboard'}
            ]

            results = await sheets.search_tasks(query='login')

            assert len(results) == 1
            assert results[0]['ID'] == 'TASK-001'

    @pytest.mark.asyncio
    async def test_bulk_update_status(self, sheets):
        """Test bulk status update."""
        sheets._initialized = True
        with patch.object(sheets, 'update_task') as mock_update:
            mock_update.return_value = True
            with patch.object(sheets, 'get_task') as mock_get:
                mock_get.return_value = {'ID': 'TASK-001', 'Title': 'Test'}
                with patch.object(sheets, 'add_note') as mock_note:

                    success, failed = await sheets.bulk_update_status(
                        ['TASK-001', 'TASK-002'],
                        'completed',
                        'Bulk completion'
                    )

                    assert success == 2
                    assert len(failed) == 0

    @pytest.mark.asyncio
    async def test_bulk_assign(self, sheets):
        """Test bulk assignment."""
        sheets._initialized = True
        with patch.object(sheets, 'update_task') as mock_update:
            mock_update.return_value = True

            success, failed = await sheets.bulk_assign(
                ['TASK-001', 'TASK-002'],
                'Mayank'
            )

            assert success == 2
            assert len(failed) == 0

    @pytest.mark.asyncio
    async def test_delete_tasks_batch(self, sheets, mock_worksheet):
        """Test batch task deletion."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_cell1 = MagicMock()
            mock_cell1.row = 2
            mock_cell2 = MagicMock()
            mock_cell2.row = 3
            mock_worksheet.find.side_effect = [mock_cell1, mock_cell2]

            deleted, failed = await sheets.delete_tasks(['TASK-001', 'TASK-002'])

            assert deleted == 2
            assert failed == 0
            # Should delete in reverse order (row 3, then row 2)
            assert mock_worksheet.delete_rows.call_count == 2

    @pytest.mark.asyncio
    async def test_add_attendance_log(self, sheets, mock_worksheet):
        """Test adding attendance log entry."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet

            result = await sheets.add_attendance_log({
                'record_id': 'ATT-20260124-001',
                'date': '2026-01-24',
                'time': '09:00',
                'name': 'Mayank',
                'event': 'in',
                'late': 'No',
                'late_min': 0,
                'channel': 'dev'
            })

            assert result is True
            mock_worksheet.append_row.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_team_sheet(self, sheets, mock_worksheet):
        """Test clearing team sheet while keeping header."""
        sheets._initialized = True
        with patch.object(sheets.spreadsheet, 'worksheet') as mock_ws:
            mock_ws.return_value = mock_worksheet
            mock_worksheet.get_all_values.return_value = [
                ['Header1', 'Header2'],
                ['Data1', 'Data2'],
                ['Data3', 'Data4']
            ]

            result = await sheets.clear_team_sheet(keep_header=True)

            assert result is True
            # Should delete data rows (2 rows)
            assert mock_worksheet.delete_rows.call_count == 2
