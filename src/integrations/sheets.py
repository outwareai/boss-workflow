"""
Google Sheets integration for task tracking and reporting.

ADVANCED VERSION with:
- Auto-formatted tabs with colors and styling
- Dashboard with live formulas and charts
- Conditional formatting (status colors, overdue highlighting)
- Data validation dropdowns
- Team performance tracking
- Monthly/Weekly auto-reports
- Filtered views for staff
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
from gspread_formatting import (
    CellFormat, Color, TextFormat, NumberFormat,
    format_cell_range, set_column_width, set_row_height,
    set_frozen, DataValidationRule, BooleanCondition,
    ConditionalFormatRule, BooleanRule, GridRange,
    get_conditional_format_rules, set_conditional_format_rules
)

from config import settings
from ..models.task import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


# ============================================
# COLOR PALETTE
# ============================================
class Colors:
    """Color definitions for consistent styling."""
    # Header colors
    HEADER_BG = Color(0.1, 0.1, 0.2)  # Dark blue
    HEADER_TEXT = Color(1, 1, 1)  # White

    # Priority colors
    PRIORITY_URGENT = Color(0.9, 0.2, 0.2)  # Red
    PRIORITY_HIGH = Color(0.9, 0.5, 0.1)  # Orange
    PRIORITY_MEDIUM = Color(0.95, 0.8, 0.2)  # Yellow
    PRIORITY_LOW = Color(0.2, 0.8, 0.4)  # Green

    # Status colors
    STATUS_PENDING = Color(0.9, 0.9, 0.9)  # Light gray
    STATUS_IN_PROGRESS = Color(0.7, 0.85, 1)  # Light blue
    STATUS_COMPLETED = Color(0.7, 0.95, 0.7)  # Light green
    STATUS_BLOCKED = Color(1, 0.8, 0.8)  # Light red
    STATUS_DELAYED = Color(1, 0.9, 0.7)  # Light orange
    STATUS_OVERDUE = Color(1, 0.6, 0.6)  # Red

    # Dashboard colors
    DASHBOARD_BG = Color(0.95, 0.95, 0.98)
    CARD_BG = Color(1, 1, 1)
    ACCENT = Color(0.2, 0.4, 0.8)


class GoogleSheetsIntegration:
    """
    Advanced Google Sheets integration for task tracking.

    Creates and manages multiple sheets:
    - Dashboard: Real-time overview with charts
    - Daily Tasks: Main task tracker
    - Weekly Reports: Auto-generated weekly summaries
    - Monthly Reports: Monthly analytics
    - Team Performance: Per-person metrics
    - Notes Log: All notes across tasks
    - Task Archive: Historical completed tasks
    - Settings: Configuration and team members
    """

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    def __init__(self):
        self.client: Optional[gspread.Client] = None
        self.spreadsheet: Optional[gspread.Spreadsheet] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the Google Sheets client and setup all sheets."""
        if self._initialized:
            return True

        try:
            creds_json = settings.google_credentials_json
            if not creds_json:
                logger.error("No Google credentials configured")
                return False

            creds_data = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_data,
                scopes=self.SCOPES
            )

            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(settings.google_sheet_id)

            # Setup all sheets with advanced formatting
            await self._setup_all_sheets()

            self._initialized = True
            logger.info("Google Sheets integration initialized with advanced formatting")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            return False

    # ============================================
    # SHEET SETUP METHODS
    # ============================================

    async def _setup_all_sheets(self) -> None:
        """Setup all sheets with proper formatting."""
        try:
            # Create sheets in order (Dashboard first for visibility)
            await self._setup_dashboard_sheet()
            await self._setup_daily_tasks_sheet()
            await self._setup_team_performance_sheet()
            await self._setup_weekly_reports_sheet()
            await self._setup_monthly_reports_sheet()
            await self._setup_notes_log_sheet()
            await self._setup_archive_sheet()
            await self._setup_settings_sheet()

            logger.info("All sheets setup completed")
        except Exception as e:
            logger.error(f"Error setting up sheets: {e}")

    async def _setup_daily_tasks_sheet(self) -> gspread.Worksheet:
        """Setup the main Daily Tasks sheet with full formatting."""
        headers = [
            "Task ID", "Title", "Description", "Assignee", "Priority",
            "Status", "Type", "Deadline", "Created", "Updated",
            "Effort", "Acceptance Criteria", "Tags", "Created By",
            "Notes", "Delays", "Progress %", "Days Open"
        ]

        sheet = self._get_or_create_sheet("Daily Tasks", headers, rows=1000, cols=20)

        # Format header row
        header_format = CellFormat(
            backgroundColor=Colors.HEADER_BG,
            textFormat=TextFormat(bold=True, foregroundColor=Colors.HEADER_TEXT, fontSize=11),
            horizontalAlignment='CENTER',
            verticalAlignment='MIDDLE'
        )
        format_cell_range(sheet, 'A1:R1', header_format)

        # Set column widths
        column_widths = {
            'A': 140,   # Task ID
            'B': 250,   # Title
            'C': 350,   # Description
            'D': 120,   # Assignee
            'E': 90,    # Priority
            'F': 120,   # Status
            'G': 100,   # Type
            'H': 140,   # Deadline
            'I': 140,   # Created
            'J': 140,   # Updated
            'K': 80,    # Effort
            'L': 300,   # Acceptance Criteria
            'M': 150,   # Tags
            'N': 120,   # Created By
            'O': 60,    # Notes count
            'P': 60,    # Delays
            'Q': 80,    # Progress %
            'R': 80,    # Days Open
        }
        for col, width in column_widths.items():
            set_column_width(sheet, col, width)

        # Set header row height
        set_row_height(sheet, '1', 40)

        # Freeze header row
        set_frozen(sheet, rows=1)

        # Add data validation for Priority (dropdown)
        priority_rule = DataValidationRule(
            BooleanCondition('ONE_OF_LIST', ['low', 'medium', 'high', 'urgent']),
            showCustomUi=True
        )
        # Apply to column E (rows 2-1000)
        sheet.batch_update({
            'requests': [{
                'setDataValidation': {
                    'range': {
                        'sheetId': sheet.id,
                        'startRowIndex': 1,
                        'endRowIndex': 1000,
                        'startColumnIndex': 4,  # E
                        'endColumnIndex': 5
                    },
                    'rule': {
                        'condition': {
                            'type': 'ONE_OF_LIST',
                            'values': [
                                {'userEnteredValue': 'low'},
                                {'userEnteredValue': 'medium'},
                                {'userEnteredValue': 'high'},
                                {'userEnteredValue': 'urgent'}
                            ]
                        },
                        'showCustomUi': True,
                        'strict': True
                    }
                }
            }]
        })

        # Add data validation for Status (dropdown)
        status_values = [s.value for s in TaskStatus]
        sheet.batch_update({
            'requests': [{
                'setDataValidation': {
                    'range': {
                        'sheetId': sheet.id,
                        'startRowIndex': 1,
                        'endRowIndex': 1000,
                        'startColumnIndex': 5,  # F
                        'endColumnIndex': 6
                    },
                    'rule': {
                        'condition': {
                            'type': 'ONE_OF_LIST',
                            'values': [{'userEnteredValue': s} for s in status_values]
                        },
                        'showCustomUi': True,
                        'strict': True
                    }
                }
            }]
        })

        # Add conditional formatting for Priority colors
        self._add_priority_conditional_formatting(sheet)

        # Add conditional formatting for Status colors
        self._add_status_conditional_formatting(sheet)

        # Add conditional formatting for overdue tasks
        self._add_overdue_conditional_formatting(sheet)

        logger.info("Daily Tasks sheet setup completed")
        return sheet

    async def _setup_dashboard_sheet(self) -> gspread.Worksheet:
        """Setup the Dashboard with live formulas and summary cards."""
        sheet = self._get_or_create_sheet("Dashboard", [], rows=50, cols=15)

        # Clear any existing content
        sheet.clear()

        # Build dashboard layout
        dashboard_data = [
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "BOSS WORKFLOW DASHBOARD", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "TODAY'S OVERVIEW", "", "", "", "THIS WEEK", "", "", "", "TEAM WORKLOAD", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "Total Open Tasks", '=COUNTIF(\'Daily Tasks\'!F:F,"<>completed")-1', "", "", "Created This Week", '=COUNTIF(\'Daily Tasks\'!I:I,">="&(TODAY()-WEEKDAY(TODAY(),2)+1))', "", "", "See Team Performance tab", "", "", "", "", ""],
            ["", "Completed Today", '=COUNTIFS(\'Daily Tasks\'!F:F,"completed",\'Daily Tasks\'!J:J,">="&TODAY())', "", "", "Completed This Week", '=COUNTIFS(\'Daily Tasks\'!F:F,"completed",\'Daily Tasks\'!J:J,">="&(TODAY()-WEEKDAY(TODAY(),2)+1))', "", "", "", "", "", "", "", ""],
            ["", "In Progress", '=COUNTIF(\'Daily Tasks\'!F:F,"in_progress")', "", "", "Completion Rate", '=IFERROR(C8/C7*100,0)&"%"', "", "", "", "", "", "", "", ""],
            ["", "Overdue", '=COUNTIF(\'Daily Tasks\'!F:F,"overdue")', "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "Blocked", '=COUNTIF(\'Daily Tasks\'!F:F,"blocked")', "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "BY PRIORITY", "", "", "", "BY STATUS", "", "", "", "RECENT ACTIVITY", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "Urgent", '=COUNTIF(\'Daily Tasks\'!E:E,"urgent")', "", "", "Pending", '=COUNTIF(\'Daily Tasks\'!F:F,"pending")', "", "", "Check Notes Log for details", "", "", "", "", ""],
            ["", "High", '=COUNTIF(\'Daily Tasks\'!E:E,"high")', "", "", "In Progress", '=COUNTIF(\'Daily Tasks\'!F:F,"in_progress")', "", "", "", "", "", "", "", ""],
            ["", "Medium", '=COUNTIF(\'Daily Tasks\'!E:E,"medium")', "", "", "In Review", '=COUNTIF(\'Daily Tasks\'!F:F,"in_review")', "", "", "", "", "", "", "", ""],
            ["", "Low", '=COUNTIF(\'Daily Tasks\'!E:E,"low")', "", "", "Completed", '=COUNTIF(\'Daily Tasks\'!F:F,"completed")', "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "Delayed", '=COUNTIF(\'Daily Tasks\'!F:F,"delayed")', "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "Blocked", '=COUNTIF(\'Daily Tasks\'!F:F,"blocked")', "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "DEADLINES THIS WEEK", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "Due Today", '=COUNTIFS(\'Daily Tasks\'!H:H,">="&TODAY(),\'Daily Tasks\'!H:H,"<"&TODAY()+1,\'Daily Tasks\'!F:F,"<>completed")', "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "Due Tomorrow", '=COUNTIFS(\'Daily Tasks\'!H:H,">="&TODAY()+1,\'Daily Tasks\'!H:H,"<"&TODAY()+2,\'Daily Tasks\'!F:F,"<>completed")', "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "Due This Week", '=COUNTIFS(\'Daily Tasks\'!H:H,">="&TODAY(),\'Daily Tasks\'!H:H,"<"&TODAY()+7,\'Daily Tasks\'!F:F,"<>completed")', "", "", "", "", "", "", "", "", "", "", "", ""],
        ]

        # Write dashboard data
        sheet.update('A1:O26', dashboard_data, value_input_option='USER_ENTERED')

        # Format title
        title_format = CellFormat(
            textFormat=TextFormat(bold=True, fontSize=24, foregroundColor=Colors.ACCENT),
        )
        format_cell_range(sheet, 'B2', title_format)

        # Format section headers
        section_format = CellFormat(
            textFormat=TextFormat(bold=True, fontSize=14, foregroundColor=Colors.HEADER_BG),
            backgroundColor=Color(0.9, 0.9, 0.95)
        )
        for row in [5, 13, 22]:
            format_cell_range(sheet, f'B{row}:J{row}', section_format)

        # Format metric labels
        label_format = CellFormat(
            textFormat=TextFormat(bold=True, fontSize=11),
        )
        for row in range(7, 12):
            format_cell_range(sheet, f'B{row}', label_format)
            format_cell_range(sheet, f'F{row}', label_format)

        # Format metric values
        value_format = CellFormat(
            textFormat=TextFormat(bold=True, fontSize=14, foregroundColor=Colors.ACCENT),
            horizontalAlignment='CENTER'
        )
        for row in range(7, 12):
            format_cell_range(sheet, f'C{row}', value_format)
            format_cell_range(sheet, f'G{row}', value_format)

        # Set column widths
        set_column_width(sheet, 'A', 30)
        set_column_width(sheet, 'B', 180)
        set_column_width(sheet, 'C', 100)
        set_column_width(sheet, 'D', 30)
        set_column_width(sheet, 'E', 30)
        set_column_width(sheet, 'F', 180)
        set_column_width(sheet, 'G', 100)

        logger.info("Dashboard sheet setup completed")
        return sheet

    async def _setup_team_performance_sheet(self) -> gspread.Worksheet:
        """Setup Team Performance tracking sheet."""
        headers = [
            "Team Member", "Telegram ID", "Role", "Active Tasks",
            "Completed (Week)", "Completed (Month)", "Completion Rate %",
            "Avg Days to Complete", "Overdue Count", "Current Streak",
            "Last Task Completed", "Status"
        ]

        sheet = self._get_or_create_sheet("Team Performance", headers, rows=50, cols=15)

        # Format header
        header_format = CellFormat(
            backgroundColor=Color(0.2, 0.3, 0.5),
            textFormat=TextFormat(bold=True, foregroundColor=Colors.HEADER_TEXT, fontSize=11),
            horizontalAlignment='CENTER'
        )
        format_cell_range(sheet, 'A1:L1', header_format)

        # Set column widths
        widths = {'A': 150, 'B': 120, 'C': 100, 'D': 100, 'E': 130, 'F': 140,
                  'G': 130, 'H': 150, 'I': 120, 'J': 120, 'K': 160, 'L': 100}
        for col, width in widths.items():
            set_column_width(sheet, col, width)

        set_frozen(sheet, rows=1)
        set_row_height(sheet, '1', 40)

        logger.info("Team Performance sheet setup completed")
        return sheet

    async def _setup_weekly_reports_sheet(self) -> gspread.Worksheet:
        """Setup Weekly Reports sheet."""
        headers = [
            "Week Start", "Week End", "Total Created", "Total Completed",
            "Completion Rate %", "Avg Time to Complete", "Tasks by Priority",
            "Top Performer", "Most Delayed", "Overdue Count", "Notes"
        ]

        sheet = self._get_or_create_sheet("Weekly Reports", headers, rows=100, cols=12)

        header_format = CellFormat(
            backgroundColor=Color(0.1, 0.4, 0.3),
            textFormat=TextFormat(bold=True, foregroundColor=Colors.HEADER_TEXT, fontSize=11),
            horizontalAlignment='CENTER'
        )
        format_cell_range(sheet, 'A1:K1', header_format)

        set_frozen(sheet, rows=1)
        set_row_height(sheet, '1', 40)

        logger.info("Weekly Reports sheet setup completed")
        return sheet

    async def _setup_monthly_reports_sheet(self) -> gspread.Worksheet:
        """Setup Monthly Reports sheet."""
        headers = [
            "Month", "Year", "Total Created", "Total Completed", "Completion Rate %",
            "Urgent Tasks", "High Priority", "Medium Priority", "Low Priority",
            "Avg Days to Complete", "Most Productive Day", "Top Performer",
            "Total Delays", "Overdue Count", "Team Size", "Tasks per Person"
        ]

        sheet = self._get_or_create_sheet("Monthly Reports", headers, rows=50, cols=18)

        header_format = CellFormat(
            backgroundColor=Color(0.4, 0.2, 0.4),
            textFormat=TextFormat(bold=True, foregroundColor=Colors.HEADER_TEXT, fontSize=11),
            horizontalAlignment='CENTER'
        )
        format_cell_range(sheet, 'A1:P1', header_format)

        set_frozen(sheet, rows=1)
        set_row_height(sheet, '1', 40)

        logger.info("Monthly Reports sheet setup completed")
        return sheet

    async def _setup_notes_log_sheet(self) -> gspread.Worksheet:
        """Setup Notes Log sheet."""
        headers = ["Timestamp", "Task ID", "Task Title", "Author", "Note Type", "Content", "Pinned"]

        sheet = self._get_or_create_sheet("Notes Log", headers, rows=2000, cols=8)

        header_format = CellFormat(
            backgroundColor=Color(0.3, 0.3, 0.4),
            textFormat=TextFormat(bold=True, foregroundColor=Colors.HEADER_TEXT, fontSize=11),
            horizontalAlignment='CENTER'
        )
        format_cell_range(sheet, 'A1:G1', header_format)

        widths = {'A': 160, 'B': 140, 'C': 200, 'D': 120, 'E': 100, 'F': 400, 'G': 70}
        for col, width in widths.items():
            set_column_width(sheet, col, width)

        set_frozen(sheet, rows=1)

        logger.info("Notes Log sheet setup completed")
        return sheet

    async def _setup_archive_sheet(self) -> gspread.Worksheet:
        """Setup Task Archive sheet (same structure as Daily Tasks)."""
        headers = [
            "Task ID", "Title", "Description", "Assignee", "Priority",
            "Status", "Type", "Deadline", "Created", "Completed",
            "Effort", "Acceptance Criteria", "Tags", "Created By",
            "Notes", "Delays", "Days to Complete", "Archived On"
        ]

        sheet = self._get_or_create_sheet("Task Archive", headers, rows=5000, cols=20)

        header_format = CellFormat(
            backgroundColor=Color(0.4, 0.4, 0.4),
            textFormat=TextFormat(bold=True, foregroundColor=Colors.HEADER_TEXT, fontSize=11),
            horizontalAlignment='CENTER'
        )
        format_cell_range(sheet, 'A1:R1', header_format)

        set_frozen(sheet, rows=1)

        logger.info("Task Archive sheet setup completed")
        return sheet

    async def _setup_settings_sheet(self) -> gspread.Worksheet:
        """Setup Settings sheet for configuration and team members."""
        sheet = self._get_or_create_sheet("Settings", [], rows=50, cols=10)

        settings_data = [
            ["BOSS WORKFLOW SETTINGS", "", "", "", ""],
            ["", "", "", "", ""],
            ["TEAM MEMBERS", "", "", "", ""],
            ["Name", "Telegram ID", "Role", "Email", "Active"],
            ["", "", "", "", ""],
            ["", "", "", "", ""],
            ["", "", "", "", ""],
            ["", "", "", "", ""],
            ["", "", "", "", ""],
            ["", "", "", "", ""],
            ["", "", "", "", ""],
            ["TASK TYPES", "", "", "", ""],
            ["task", "General task", "", "", ""],
            ["bug", "Bug fix", "", "", ""],
            ["feature", "New feature", "", "", ""],
            ["research", "Research/Investigation", "", "", ""],
            ["", "", "", "", ""],
            ["PRIORITY LEVELS", "", "", "", ""],
            ["urgent", "Immediate attention required", "Red", "", ""],
            ["high", "Important, do soon", "Orange", "", ""],
            ["medium", "Normal priority", "Yellow", "", ""],
            ["low", "When time permits", "Green", "", ""],
        ]

        sheet.update('A1:E22', settings_data)

        # Format title
        title_format = CellFormat(
            textFormat=TextFormat(bold=True, fontSize=16, foregroundColor=Colors.ACCENT),
        )
        format_cell_range(sheet, 'A1', title_format)

        # Format section headers
        section_format = CellFormat(
            textFormat=TextFormat(bold=True, fontSize=12),
            backgroundColor=Color(0.9, 0.9, 0.95)
        )
        format_cell_range(sheet, 'A3:E3', section_format)
        format_cell_range(sheet, 'A12:E12', section_format)
        format_cell_range(sheet, 'A18:E18', section_format)

        # Format table headers
        table_header_format = CellFormat(
            textFormat=TextFormat(bold=True),
            backgroundColor=Color(0.85, 0.85, 0.9)
        )
        format_cell_range(sheet, 'A4:E4', table_header_format)

        logger.info("Settings sheet setup completed")
        return sheet

    # ============================================
    # CONDITIONAL FORMATTING
    # ============================================

    def _add_priority_conditional_formatting(self, sheet: gspread.Worksheet) -> None:
        """Add conditional formatting rules for Priority column."""
        rules = get_conditional_format_rules(sheet)

        # Priority: Urgent - Red background
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range('E2:E1000', sheet)],
            booleanRule=BooleanRule(
                condition=BooleanCondition('TEXT_EQ', ['urgent']),
                format=CellFormat(backgroundColor=Color(1, 0.8, 0.8))
            )
        ))

        # Priority: High - Orange background
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range('E2:E1000', sheet)],
            booleanRule=BooleanRule(
                condition=BooleanCondition('TEXT_EQ', ['high']),
                format=CellFormat(backgroundColor=Color(1, 0.9, 0.7))
            )
        ))

        # Priority: Medium - Yellow background
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range('E2:E1000', sheet)],
            booleanRule=BooleanRule(
                condition=BooleanCondition('TEXT_EQ', ['medium']),
                format=CellFormat(backgroundColor=Color(1, 1, 0.7))
            )
        ))

        # Priority: Low - Green background
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range('E2:E1000', sheet)],
            booleanRule=BooleanRule(
                condition=BooleanCondition('TEXT_EQ', ['low']),
                format=CellFormat(backgroundColor=Color(0.8, 1, 0.8))
            )
        ))

        set_conditional_format_rules(sheet, rules)

    def _add_status_conditional_formatting(self, sheet: gspread.Worksheet) -> None:
        """Add conditional formatting rules for Status column."""
        rules = get_conditional_format_rules(sheet)

        status_colors = {
            'completed': Color(0.7, 0.95, 0.7),      # Light green
            'in_progress': Color(0.7, 0.85, 1),      # Light blue
            'pending': Color(0.95, 0.95, 0.95),      # Light gray
            'blocked': Color(1, 0.7, 0.7),           # Light red
            'delayed': Color(1, 0.85, 0.7),          # Light orange
            'overdue': Color(1, 0.6, 0.6),           # Red
            'in_review': Color(0.9, 0.8, 1),         # Light purple
            'on_hold': Color(0.85, 0.85, 0.85),      # Gray
            'waiting': Color(1, 0.95, 0.8),          # Light yellow
            'needs_info': Color(1, 0.9, 0.5),        # Yellow
        }

        for status, color in status_colors.items():
            rules.append(ConditionalFormatRule(
                ranges=[GridRange.from_a1_range('F2:F1000', sheet)],
                booleanRule=BooleanRule(
                    condition=BooleanCondition('TEXT_EQ', [status]),
                    format=CellFormat(backgroundColor=color)
                )
            ))

        set_conditional_format_rules(sheet, rules)

    def _add_overdue_conditional_formatting(self, sheet: gspread.Worksheet) -> None:
        """Add conditional formatting for overdue tasks (entire row)."""
        # This highlights the entire row if status is 'overdue'
        rules = get_conditional_format_rules(sheet)

        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range('A2:R1000', sheet)],
            booleanRule=BooleanRule(
                condition=BooleanCondition('CUSTOM_FORMULA', ['=$F2="overdue"']),
                format=CellFormat(
                    backgroundColor=Color(1, 0.9, 0.9),
                    textFormat=TextFormat(foregroundColor=Color(0.7, 0, 0))
                )
            )
        ))

        set_conditional_format_rules(sheet, rules)

    # ============================================
    # HELPER METHODS
    # ============================================

    def _get_or_create_sheet(self, name: str, headers: List[str], rows: int = 1000, cols: int = 20) -> gspread.Worksheet:
        """Get a worksheet by name or create it with headers."""
        try:
            worksheet = self.spreadsheet.worksheet(name)
            logger.info(f"Found existing sheet: {name}")
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title=name,
                rows=rows,
                cols=cols
            )
            if headers:
                worksheet.update('A1', [headers], value_input_option='RAW')
            logger.info(f"Created new sheet: {name}")

        return worksheet

    # ============================================
    # TASK OPERATIONS
    # ============================================

    async def add_task(self, task: Task) -> Optional[int]:
        """Add a task to the Daily Tasks sheet."""
        if not await self.initialize():
            return None

        try:
            worksheet = self.spreadsheet.worksheet("Daily Tasks")

            # Calculate days open
            days_open = (datetime.now() - task.created_at).days

            # Build row data with extended fields
            row_data = [
                task.id,
                task.title,
                task.description,
                task.assignee or "",
                task.priority.value,
                task.status.value,
                task.task_type,
                task.deadline.strftime('%Y-%m-%d %H:%M') if task.deadline else "",
                task.created_at.strftime('%Y-%m-%d %H:%M'),
                task.updated_at.strftime('%Y-%m-%d %H:%M'),
                task.estimated_effort or "",
                ", ".join([c.description for c in task.acceptance_criteria]),
                ", ".join(task.tags),
                task.created_by,
                str(len(task.notes)),
                str(task.delayed_count),
                "0%",  # Progress
                str(days_open)
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            row_num = len(worksheet.get_all_values())

            logger.info(f"Added task {task.id} to row {row_num}")
            return row_num

        except Exception as e:
            logger.error(f"Error adding task to Sheets: {e}")
            return None

    async def update_task(self, task: Task, row_id: Optional[int] = None) -> bool:
        """Update a task in the sheet."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet("Daily Tasks")

            if not row_id:
                cell = worksheet.find(task.id)
                if not cell:
                    logger.warning(f"Task {task.id} not found in sheet")
                    return False
                row_id = cell.row

            days_open = (datetime.now() - task.created_at).days

            row_data = [
                task.id,
                task.title,
                task.description,
                task.assignee or "",
                task.priority.value,
                task.status.value,
                task.task_type,
                task.deadline.strftime('%Y-%m-%d %H:%M') if task.deadline else "",
                task.created_at.strftime('%Y-%m-%d %H:%M'),
                task.updated_at.strftime('%Y-%m-%d %H:%M'),
                task.estimated_effort or "",
                ", ".join([c.description for c in task.acceptance_criteria]),
                ", ".join(task.tags),
                task.created_by,
                str(len(task.notes)),
                str(task.delayed_count),
                "0%",
                str(days_open)
            ]

            worksheet.update(f'A{row_id}:R{row_id}', [row_data], value_input_option='USER_ENTERED')
            logger.info(f"Updated task {task.id} in row {row_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating task in Sheets: {e}")
            return False

    async def add_note_log(self, task_id: str, task_title: str, note_content: str,
                          author: str, note_type: str, is_pinned: bool = False) -> bool:
        """Add a note to the Notes Log sheet."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet("Notes Log")

            row_data = [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                task_id,
                task_title,
                author,
                note_type,
                note_content,
                "Yes" if is_pinned else "No"
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error adding note to log: {e}")
            return False

    # ============================================
    # REPORTING METHODS
    # ============================================

    async def get_daily_tasks(self, date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get all tasks for a specific date."""
        if not await self.initialize():
            return []

        try:
            worksheet = self.spreadsheet.worksheet("Daily Tasks")
            all_rows = worksheet.get_all_records()

            if date is None:
                date = datetime.now()

            date_str = date.strftime('%Y-%m-%d')

            daily_tasks = [
                row for row in all_rows
                if row.get('Created', '').startswith(date_str)
            ]

            return daily_tasks

        except Exception as e:
            logger.error(f"Error getting daily tasks: {e}")
            return []

    async def get_tasks_by_status(self, status: TaskStatus) -> List[Dict[str, Any]]:
        """Get all tasks with a specific status."""
        if not await self.initialize():
            return []

        try:
            worksheet = self.spreadsheet.worksheet("Daily Tasks")
            all_rows = worksheet.get_all_records()
            return [row for row in all_rows if row.get('Status') == status.value]

        except Exception as e:
            logger.error(f"Error getting tasks by status: {e}")
            return []

    async def get_overdue_tasks(self) -> List[Dict[str, Any]]:
        """Get all overdue tasks."""
        if not await self.initialize():
            return []

        try:
            worksheet = self.spreadsheet.worksheet("Daily Tasks")
            all_rows = worksheet.get_all_records()

            now = datetime.now()
            overdue = []

            for row in all_rows:
                deadline_str = row.get('Deadline', '')
                status = row.get('Status', '')

                if deadline_str and status not in ['completed', 'cancelled']:
                    try:
                        deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
                        if deadline < now:
                            overdue.append(row)
                    except ValueError:
                        pass

            return overdue

        except Exception as e:
            logger.error(f"Error getting overdue tasks: {e}")
            return []

    async def generate_weekly_overview(self) -> Dict[str, Any]:
        """Generate weekly overview statistics."""
        if not await self.initialize():
            return {}

        try:
            worksheet = self.spreadsheet.worksheet("Daily Tasks")
            all_rows = worksheet.get_all_records()

            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)

            weekly_tasks = []
            for row in all_rows:
                created_str = row.get('Created', '')
                if created_str:
                    try:
                        created = datetime.strptime(created_str, '%Y-%m-%d %H:%M')
                        if week_start <= created <= week_end:
                            weekly_tasks.append(row)
                    except ValueError:
                        pass

            total = len(weekly_tasks)
            completed = sum(1 for t in weekly_tasks if t.get('Status') == 'completed')
            in_progress = sum(1 for t in weekly_tasks if t.get('Status') == 'in_progress')
            delayed = sum(1 for t in weekly_tasks if t.get('Status') == 'delayed')
            overdue_count = sum(1 for t in weekly_tasks if t.get('Status') == 'overdue')

            by_assignee = {}
            for task in weekly_tasks:
                assignee = task.get('Assignee', 'Unassigned') or 'Unassigned'
                if assignee not in by_assignee:
                    by_assignee[assignee] = {'total': 0, 'completed': 0}
                by_assignee[assignee]['total'] += 1
                if task.get('Status') == 'completed':
                    by_assignee[assignee]['completed'] += 1

            return {
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': week_end.strftime('%Y-%m-%d'),
                'total_tasks': total,
                'completed': completed,
                'in_progress': in_progress,
                'delayed': delayed,
                'overdue': overdue_count,
                'completion_rate': round((completed / total * 100) if total > 0 else 0, 1),
                'by_assignee': by_assignee
            }

        except Exception as e:
            logger.error(f"Error generating weekly overview: {e}")
            return {}

    async def update_weekly_sheet(self, overview: Dict[str, Any]) -> bool:
        """Update the Weekly Reports sheet with current stats."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet("Weekly Reports")

            # Find top performer
            by_assignee = overview.get('by_assignee', {})
            top_performer = ""
            max_completed = 0
            for assignee, stats in by_assignee.items():
                if stats['completed'] > max_completed:
                    max_completed = stats['completed']
                    top_performer = f"{assignee} ({stats['completed']})"

            # Priority breakdown
            priority_breakdown = "See Daily Tasks"

            row_data = [
                overview.get('week_start', ''),
                overview.get('week_end', ''),
                overview.get('total_tasks', 0),
                overview.get('completed', 0),
                f"{overview.get('completion_rate', 0)}%",
                "",  # Avg time to complete
                priority_breakdown,
                top_performer,
                "",  # Most delayed
                overview.get('overdue', 0),
                ""   # Notes
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error updating weekly sheet: {e}")
            return False

    async def update_monthly_sheet(self, month: int, year: int, stats: Dict[str, Any]) -> bool:
        """Update the Monthly Reports sheet."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet("Monthly Reports")

            row_data = [
                datetime(year, month, 1).strftime('%B'),
                str(year),
                stats.get('total_created', 0),
                stats.get('total_completed', 0),
                f"{stats.get('completion_rate', 0)}%",
                stats.get('urgent_tasks', 0),
                stats.get('high_tasks', 0),
                stats.get('medium_tasks', 0),
                stats.get('low_tasks', 0),
                stats.get('avg_days_to_complete', ''),
                stats.get('most_productive_day', ''),
                stats.get('top_performer', ''),
                stats.get('total_delays', 0),
                stats.get('overdue_count', 0),
                stats.get('team_size', 0),
                stats.get('tasks_per_person', 0)
            ]

            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error updating monthly sheet: {e}")
            return False

    async def archive_completed_tasks(self, days_old: int = 7) -> int:
        """Move completed tasks older than X days to archive."""
        if not await self.initialize():
            return 0

        try:
            daily_sheet = self.spreadsheet.worksheet("Daily Tasks")
            archive_sheet = self.spreadsheet.worksheet("Task Archive")

            all_rows = daily_sheet.get_all_records()
            cutoff = datetime.now() - timedelta(days=days_old)

            rows_to_archive = []
            rows_to_delete = []

            for i, row in enumerate(all_rows, start=2):
                if row.get('Status') == 'completed':
                    updated_str = row.get('Updated', '')
                    if updated_str:
                        try:
                            updated = datetime.strptime(updated_str, '%Y-%m-%d %H:%M')
                            if updated < cutoff:
                                # Add archived timestamp
                                archive_row = list(row.values())
                                archive_row.append(datetime.now().strftime('%Y-%m-%d %H:%M'))
                                rows_to_archive.append(archive_row)
                                rows_to_delete.append(i)
                        except ValueError:
                            pass

            if rows_to_archive:
                archive_sheet.append_rows(rows_to_archive, value_input_option='USER_ENTERED')

            for row_num in reversed(rows_to_delete):
                daily_sheet.delete_rows(row_num)

            logger.info(f"Archived {len(rows_to_archive)} completed tasks")
            return len(rows_to_archive)

        except Exception as e:
            logger.error(f"Error archiving tasks: {e}")
            return 0

    async def update_team_member(self, name: str, telegram_id: str, role: str,
                                 stats: Dict[str, Any]) -> bool:
        """Update or add a team member in Team Performance sheet."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet("Team Performance")

            # Try to find existing row
            try:
                cell = worksheet.find(name)
                row_num = cell.row
            except:
                # Add new row
                row_num = len(worksheet.get_all_values()) + 1

            row_data = [
                name,
                telegram_id,
                role,
                stats.get('active_tasks', 0),
                stats.get('completed_week', 0),
                stats.get('completed_month', 0),
                f"{stats.get('completion_rate', 0)}%",
                stats.get('avg_days', ''),
                stats.get('overdue_count', 0),
                stats.get('current_streak', 0),
                stats.get('last_completed', ''),
                stats.get('status', 'Active')
            ]

            worksheet.update(f'A{row_num}:L{row_num}', [row_data], value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error updating team member: {e}")
            return False

    async def refresh_dashboard(self) -> bool:
        """Refresh the dashboard timestamp."""
        if not await self.initialize():
            return False

        try:
            worksheet = self.spreadsheet.worksheet("Dashboard")
            worksheet.update('B3', f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            return True

        except Exception as e:
            logger.error(f"Error refreshing dashboard: {e}")
            return False


# Singleton instance
sheets_integration = GoogleSheetsIntegration()


def get_sheets_integration() -> GoogleSheetsIntegration:
    """Get the Google Sheets integration instance."""
    return sheets_integration
