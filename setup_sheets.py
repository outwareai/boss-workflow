"""
Google Sheets Advanced Setup Script

Creates a professional, polished task management spreadsheet with:
- Borders and gridlines
- Example data rows
- Comprehensive data validation
- Alternating row colors
- Professional formatting
"""

import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

import gspread
from google.oauth2.service_account import Credentials

GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON', '')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '')

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


def rgb(r, g, b):
    """Convert RGB (0-255) to Google Sheets color format."""
    return {'red': r/255, 'green': g/255, 'blue': b/255}


def get_or_create_sheet(spreadsheet, name, rows=1000, cols=20):
    """Delete existing and create fresh worksheet."""
    # Safe name for printing (strip emojis)
    safe_name = name.encode('ascii', 'ignore').decode('ascii').strip()
    try:
        ws = spreadsheet.worksheet(name)
        spreadsheet.del_worksheet(ws)
        print(f"  Deleted existing: {safe_name}")
    except gspread.WorksheetNotFound:
        pass
    ws = spreadsheet.add_worksheet(title=name, rows=rows, cols=cols)
    print(f"  Created fresh: {safe_name}")
    return ws


def add_borders(requests, sheet_id, start_row, end_row, start_col, end_col, style='SOLID', color=None):
    """Add borders to a range."""
    if color is None:
        color = rgb(200, 200, 200)

    border_style = {
        'style': style,
        'color': color
    }

    requests.append({
        'updateBorders': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': start_row,
                'endRowIndex': end_row,
                'startColumnIndex': start_col,
                'endColumnIndex': end_col
            },
            'top': border_style,
            'bottom': border_style,
            'left': border_style,
            'right': border_style,
            'innerHorizontal': border_style,
            'innerVertical': border_style
        }
    })


def add_alternating_colors(requests, sheet_id, start_row, end_row, start_col, end_col):
    """Add alternating row colors (banding)."""
    requests.append({
        'addBanding': {
            'bandedRange': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': start_row,
                    'endRowIndex': end_row,
                    'startColumnIndex': start_col,
                    'endColumnIndex': end_col
                },
                'rowProperties': {
                    'headerColor': rgb(26, 26, 51),  # Dark blue header
                    'firstBandColor': rgb(255, 255, 255),  # White
                    'secondBandColor': rgb(245, 245, 250)  # Light gray-blue
                }
            }
        }
    })


def setup_advanced_sheets(spreadsheet):
    """Setup all sheets with professional formatting."""

    print("\n" + "="*50)
    print("Creating Professional Google Sheets")
    print("="*50)

    requests = []

    # Delete ALL old sheets (without emojis and default)
    sheets_to_keep = []  # We'll recreate everything
    old_sheet_names = ['Sheet1', 'Daily Tasks', 'Dashboard', 'Team', 'Weekly Reports',
                       'Monthly Reports', 'Notes Log', 'Archive', 'Settings',
                       'Tasks', 'Reports', 'Notes']

    for old_name in old_sheet_names:
        try:
            old_sheet = spreadsheet.worksheet(old_name)
            spreadsheet.del_worksheet(old_sheet)
            print(f"  Removed old sheet: {old_name}")
        except:
            pass

    # ========================================
    # 1. DAILY TASKS - Main Task Tracker
    # ========================================
    print("\n[1/8] Setting up Daily Tasks...")

    tasks_sheet = get_or_create_sheet(spreadsheet, "📋 Daily Tasks", rows=1000, cols=20)
    tasks_id = tasks_sheet.id

    # Headers
    task_headers = [
        "ID", "Title", "Description", "Assignee", "Priority", "Status",
        "Type", "Deadline", "Created", "Updated", "Effort", "Progress",
        "Tags", "Created By", "Notes", "Blocked By"
    ]

    # Example data
    today = datetime.now()
    task_examples = [
        ["TASK-001", "Fix login authentication bug", "Users unable to login with Google OAuth", "John", "urgent", "in_progress", "bug", (today + timedelta(days=1)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d %H:%M"), today.strftime("%Y-%m-%d %H:%M"), "4 hours", "50%", "auth, urgent", "Boss", "2", ""],
        ["TASK-002", "Design new dashboard UI", "Create mockups for the analytics dashboard", "Sarah", "high", "pending", "feature", (today + timedelta(days=5)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d %H:%M"), today.strftime("%Y-%m-%d %H:%M"), "2 days", "0%", "design, ui", "Boss", "0", ""],
        ["TASK-003", "Update API documentation", "Document all REST endpoints", "Mike", "medium", "in_review", "task", (today + timedelta(days=3)).strftime("%Y-%m-%d"), (today - timedelta(days=2)).strftime("%Y-%m-%d %H:%M"), today.strftime("%Y-%m-%d %H:%M"), "1 day", "90%", "docs", "Sarah", "1", ""],
        ["TASK-004", "Research competitor pricing", "Analyze top 5 competitors", "John", "low", "completed", "research", (today - timedelta(days=1)).strftime("%Y-%m-%d"), (today - timedelta(days=5)).strftime("%Y-%m-%d %H:%M"), (today - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"), "3 hours", "100%", "research", "Boss", "3", ""],
        ["TASK-005", "Server migration planning", "Plan AWS to GCP migration", "Sarah", "high", "blocked", "task", (today + timedelta(days=10)).strftime("%Y-%m-%d"), (today - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"), today.strftime("%Y-%m-%d %H:%M"), "1 week", "25%", "infrastructure", "Boss", "0", "TASK-001"],
    ]

    # Write data
    tasks_sheet.update(values=[task_headers] + task_examples, range_name='A1')

    # Column widths
    col_widths = [90, 220, 280, 100, 85, 100, 80, 100, 130, 130, 80, 75, 120, 90, 60, 90]
    for i, w in enumerate(col_widths):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': tasks_id, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i+1}, 'properties': {'pixelSize': w}, 'fields': 'pixelSize'}})

    # Header formatting
    requests.append({
        'repeatCell': {
            'range': {'sheetId': tasks_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 16},
            'cell': {
                'userEnteredFormat': {
                    'backgroundColor': rgb(26, 26, 51),
                    'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255), 'fontSize': 10},
                    'horizontalAlignment': 'CENTER',
                    'verticalAlignment': 'MIDDLE'
                }
            },
            'fields': 'userEnteredFormat'
        }
    })

    # Row height for header
    requests.append({'updateDimensionProperties': {'range': {'sheetId': tasks_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 35}, 'fields': 'pixelSize'}})

    # Freeze header + first column
    requests.append({'updateSheetProperties': {'properties': {'sheetId': tasks_id, 'gridProperties': {'frozenRowCount': 1, 'frozenColumnCount': 1}}, 'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'}})

    # Add borders
    add_borders(requests, tasks_id, 0, 100, 0, 16)

    # Add alternating colors
    add_alternating_colors(requests, tasks_id, 0, 100, 0, 16)

    # DATA VALIDATIONS
    # Priority dropdown
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': tasks_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 4, 'endColumnIndex': 5},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in ['low', 'medium', 'high', 'urgent']]}, 'showCustomUi': True, 'strict': True}
        }
    })

    # Status dropdown
    statuses = ['pending', 'in_progress', 'in_review', 'completed', 'blocked', 'delayed', 'on_hold', 'cancelled']
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': tasks_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 5, 'endColumnIndex': 6},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in statuses]}, 'showCustomUi': True, 'strict': True}
        }
    })

    # Type dropdown
    types = ['task', 'bug', 'feature', 'research', 'meeting', 'review']
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': tasks_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 6, 'endColumnIndex': 7},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in types]}, 'showCustomUi': True, 'strict': True}
        }
    })

    # Progress dropdown
    progress_vals = ['0%', '10%', '25%', '50%', '75%', '90%', '100%']
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': tasks_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 11, 'endColumnIndex': 12},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in progress_vals]}, 'showCustomUi': True, 'strict': True}
        }
    })

    # CONDITIONAL FORMATTING
    # Priority colors
    priority_colors = [('urgent', rgb(255, 99, 71)), ('high', rgb(255, 165, 0)), ('medium', rgb(255, 215, 0)), ('low', rgb(144, 238, 144))]
    for i, (val, col) in enumerate(priority_colors):
        requests.append({
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': [{'sheetId': tasks_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 4, 'endColumnIndex': 5}],
                    'booleanRule': {'condition': {'type': 'TEXT_EQ', 'values': [{'userEnteredValue': val}]}, 'format': {'backgroundColor': col, 'textFormat': {'bold': True}}}
                },
                'index': i
            }
        })

    # Status colors
    status_colors = [
        ('completed', rgb(144, 238, 144)), ('in_progress', rgb(135, 206, 250)), ('pending', rgb(220, 220, 220)),
        ('blocked', rgb(255, 99, 71)), ('in_review', rgb(221, 160, 221)), ('delayed', rgb(255, 218, 185)),
        ('on_hold', rgb(192, 192, 192)), ('cancelled', rgb(169, 169, 169))
    ]
    for i, (val, col) in enumerate(status_colors):
        requests.append({
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': [{'sheetId': tasks_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 5, 'endColumnIndex': 6}],
                    'booleanRule': {'condition': {'type': 'TEXT_EQ', 'values': [{'userEnteredValue': val}]}, 'format': {'backgroundColor': col}}
                },
                'index': len(priority_colors) + i
            }
        })

    # Overdue highlighting (entire row turns red if deadline passed and not completed)
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{'sheetId': tasks_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 0, 'endColumnIndex': 16}],
                'booleanRule': {
                    'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=AND($H2<TODAY(), $F2<>"completed", $H2<>"")'}]},
                    'format': {'backgroundColor': rgb(255, 200, 200)}
                }
            },
            'index': len(priority_colors) + len(status_colors)
        }
    })

    print("  [OK] Daily Tasks: headers, examples, dropdowns, colors, borders")

    # ========================================
    # 2. DASHBOARD
    # ========================================
    print("\n[2/8] Setting up Dashboard...")

    dash_sheet = get_or_create_sheet(spreadsheet, "📊 Dashboard", rows=40, cols=12)
    dash_id = dash_sheet.id

    dashboard_data = [
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "BOSS WORKFLOW DASHBOARD", "", "", "", "", "", "", "", "", "", ""],
        ["", f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "OVERVIEW", "", "", "", "", "DEADLINES", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "Metric", "Count", "", "", "", "Deadline", "Count", "", "", "", ""],
        ["", "Total Tasks", "=COUNTA('📋 Daily Tasks'!A2:A1000)", "", "", "", "Due Today", "=COUNTIFS('📋 Daily Tasks'!H2:H1000,TODAY(),'📋 Daily Tasks'!F2:F1000,\"<>completed\",'📋 Daily Tasks'!A2:A1000,\"<>\")", "", "", "", ""],
        ["", "Open Tasks", "=COUNTIFS('📋 Daily Tasks'!F2:F1000,\"<>completed\",'📋 Daily Tasks'!F2:F1000,\"<>\",'📋 Daily Tasks'!A2:A1000,\"<>\")", "", "", "", "Due Tomorrow", "=COUNTIFS('📋 Daily Tasks'!H2:H1000,TODAY()+1,'📋 Daily Tasks'!F2:F1000,\"<>completed\",'📋 Daily Tasks'!A2:A1000,\"<>\")", "", "", "", ""],
        ["", "Completed", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"completed\")", "", "", "", "Due This Week", "=COUNTIFS('📋 Daily Tasks'!H2:H1000,\">=\"&TODAY(),'📋 Daily Tasks'!H2:H1000,\"<\"&TODAY()+7,'📋 Daily Tasks'!F2:F1000,\"<>completed\",'📋 Daily Tasks'!A2:A1000,\"<>\")", "", "", "", ""],
        ["", "In Progress", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"in_progress\")", "", "", "", "Overdue", "=COUNTIFS('📋 Daily Tasks'!H2:H1000,\"<\"&TODAY(),'📋 Daily Tasks'!F2:F1000,\"<>completed\",'📋 Daily Tasks'!H2:H1000,\"<>\",'📋 Daily Tasks'!A2:A1000,\"<>\")", "", "", "", ""],
        ["", "Blocked", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"blocked\")", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "BY PRIORITY", "", "", "", "", "BY STATUS", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "Priority", "Count", "%", "", "", "Status", "Count", "%", "", "", ""],
        ["", "Urgent", "=COUNTIF('📋 Daily Tasks'!E2:E1000,\"urgent\")", "=IFERROR(ROUND(C17/$C$8*100,1),0)&\"%\"", "", "", "Pending", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"pending\")", "=IFERROR(ROUND(H17/$C$8*100,1),0)&\"%\"", "", "", ""],
        ["", "High", "=COUNTIF('📋 Daily Tasks'!E2:E1000,\"high\")", "=IFERROR(ROUND(C18/$C$8*100,1),0)&\"%\"", "", "", "In Progress", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"in_progress\")", "=IFERROR(ROUND(H18/$C$8*100,1),0)&\"%\"", "", "", ""],
        ["", "Medium", "=COUNTIF('📋 Daily Tasks'!E2:E1000,\"medium\")", "=IFERROR(ROUND(C19/$C$8*100,1),0)&\"%\"", "", "", "In Review", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"in_review\")", "=IFERROR(ROUND(H19/$C$8*100,1),0)&\"%\"", "", "", ""],
        ["", "Low", "=COUNTIF('📋 Daily Tasks'!E2:E1000,\"low\")", "=IFERROR(ROUND(C20/$C$8*100,1),0)&\"%\"", "", "", "Completed", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"completed\")", "=IFERROR(ROUND(H20/$C$8*100,1),0)&\"%\"", "", "", ""],
        ["", "", "", "", "", "", "Blocked", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"blocked\")", "=IFERROR(ROUND(H21/$C$8*100,1),0)&\"%\"", "", "", ""],
        ["", "", "", "", "", "", "Delayed", "=COUNTIF('📋 Daily Tasks'!F2:F1000,\"delayed\")", "=IFERROR(ROUND(H22/$C$8*100,1),0)&\"%\"", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "COMPLETION RATE", "", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "=IFERROR(ROUND(COUNTIF('📋 Daily Tasks'!F2:F1000,\"completed\")/COUNTA('📋 Daily Tasks'!A2:A1000)*100,1),0)&\"% Complete\"", "", "", "", "", "", "", "", "", "", ""],
    ]

    dash_sheet.update(values=dashboard_data, range_name='A1', value_input_option='USER_ENTERED')

    # Dashboard formatting
    requests.append({'repeatCell': {'range': {'sheetId': dash_id, 'startRowIndex': 1, 'endRowIndex': 2, 'startColumnIndex': 1, 'endColumnIndex': 5}, 'cell': {'userEnteredFormat': {'textFormat': {'bold': True, 'fontSize': 20, 'foregroundColor': rgb(26, 26, 51)}}}, 'fields': 'userEnteredFormat'}})

    # Section headers
    for row in [4, 13, 23]:
        requests.append({'repeatCell': {'range': {'sheetId': dash_id, 'startRowIndex': row, 'endRowIndex': row+1, 'startColumnIndex': 1, 'endColumnIndex': 9}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(240, 240, 245), 'textFormat': {'bold': True, 'fontSize': 12}}}, 'fields': 'userEnteredFormat'}})

    # Table headers
    for row in [6, 15]:
        requests.append({'repeatCell': {'range': {'sheetId': dash_id, 'startRowIndex': row, 'endRowIndex': row+1, 'startColumnIndex': 1, 'endColumnIndex': 4}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(26, 26, 51), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255)}}}, 'fields': 'userEnteredFormat'}})
        requests.append({'repeatCell': {'range': {'sheetId': dash_id, 'startRowIndex': row, 'endRowIndex': row+1, 'startColumnIndex': 6, 'endColumnIndex': 9}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(26, 26, 51), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255)}}}, 'fields': 'userEnteredFormat'}})

    # Big completion rate
    requests.append({'repeatCell': {'range': {'sheetId': dash_id, 'startRowIndex': 25, 'endRowIndex': 26, 'startColumnIndex': 1, 'endColumnIndex': 4}, 'cell': {'userEnteredFormat': {'textFormat': {'bold': True, 'fontSize': 28, 'foregroundColor': rgb(34, 139, 34)}, 'horizontalAlignment': 'CENTER'}}, 'fields': 'userEnteredFormat'}})

    # Add borders to tables
    add_borders(requests, dash_id, 6, 12, 1, 4)
    add_borders(requests, dash_id, 6, 12, 6, 9)
    add_borders(requests, dash_id, 15, 22, 1, 4)
    add_borders(requests, dash_id, 15, 22, 6, 9)

    # Column widths
    for i, w in enumerate([30, 150, 80, 60, 30, 30, 150, 80, 60]):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': dash_id, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i+1}, 'properties': {'pixelSize': w}, 'fields': 'pixelSize'}})

    print("  [OK] Dashboard: metrics, formulas, formatting")

    # ========================================
    # 3. TEAM DIRECTORY
    # ========================================
    print("\n[3/8] Setting up Team Directory...")

    team_sheet = get_or_create_sheet(spreadsheet, "👥 Team", rows=50, cols=6)
    team_id = team_sheet.id

    # New simplified structure:
    # - Name: Used for Telegram mentions (e.g., "Mayank fix this")
    # - Discord ID: Numeric ID for Discord @mentions (e.g., "392400310108291092")
    # - Email: Google email for Calendar/Tasks integration
    # - Role: Developer, Marketing, or Admin (for channel routing)
    # - Status: Active, On Leave, Inactive
    # - Calendar ID: Google Calendar ID for direct event creation (usually same as email)
    team_headers = ["Name", "Discord ID", "Email", "Role", "Status", "Active Tasks", "Calendar ID"]

    # Start with empty data - will be populated via /syncteam command
    # The setup script creates structure only, no mock data
    team_examples = []

    team_sheet.update(values=[team_headers] + team_examples, range_name='A1', value_input_option='USER_ENTERED')

    # Header formatting - blue theme
    requests.append({'repeatCell': {'range': {'sheetId': team_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 7}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(51, 77, 128), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255), 'fontSize': 10}, 'horizontalAlignment': 'CENTER'}}, 'fields': 'userEnteredFormat'}})

    requests.append({'updateDimensionProperties': {'range': {'sheetId': team_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 35}, 'fields': 'pixelSize'}})
    requests.append({'updateSheetProperties': {'properties': {'sheetId': team_id, 'gridProperties': {'frozenRowCount': 1}}, 'fields': 'gridProperties.frozenRowCount'}})

    # Column widths - optimized for new structure
    # Name: 120, Discord ID: 200, Email: 220, Role: 100, Status: 80, Active Tasks: 100, Calendar ID: 220
    for i, w in enumerate([120, 200, 220, 100, 80, 100, 220]):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': team_id, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i+1}, 'properties': {'pixelSize': w}, 'fields': 'pixelSize'}})

    add_borders(requests, team_id, 0, 50, 0, 7)
    add_alternating_colors(requests, team_id, 0, 50, 0, 7)

    # Role dropdown - 3 categories for Discord channel routing
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': team_id, 'startRowIndex': 1, 'endRowIndex': 50, 'startColumnIndex': 3, 'endColumnIndex': 4},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in ['Developer', 'Marketing', 'Admin']]}, 'showCustomUi': True, 'strict': True}
        }
    })

    # Status dropdown
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': team_id, 'startRowIndex': 1, 'endRowIndex': 50, 'startColumnIndex': 4, 'endColumnIndex': 5},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in ['Active', 'On Leave', 'Inactive']]}, 'showCustomUi': True}
        }
    })

    print("  [OK] Team: headers, validation, no mock data (use /syncteam)")

    # ========================================
    # 4. WEEKLY REPORTS
    # ========================================
    print("\n[4/8] Setting up Weekly Reports...")

    weekly_sheet = get_or_create_sheet(spreadsheet, "📅 Weekly Reports", rows=200, cols=22)
    weekly_id = weekly_sheet.id

    weekly_headers = [
        "Week #", "Year", "Start Date", "End Date", "Generated",
        # Task Metrics
        "Tasks Created", "Tasks Completed", "Tasks Pending", "Tasks Blocked", "Completion Rate",
        # Priority Breakdown
        "Urgent Done", "High Done", "Medium Done", "Low Done",
        # Team Performance
        "Top Performer", "Top Performer Tasks", "Team Members Active",
        # Time & Quality
        "Avg Days to Complete", "Overdue Tasks", "On-Time Rate",
        # Summary
        "Key Highlights", "Blockers & Issues"
    ]

    weekly_examples = [
        ["3", "2026", "2026-01-13", "2026-01-19", datetime.now().strftime("%Y-%m-%d %H:%M"),
         "18", "14", "3", "1", "77.8%",
         "2", "5", "4", "3",
         "Sarah", "6", "4",
         "2.3", "1", "92.9%",
         "Completed dashboard redesign; Fixed auth bug", "Waiting on API docs from vendor"],
        ["2", "2026", "2026-01-06", "2026-01-12", "2026-01-12 17:00",
         "15", "12", "2", "1", "80.0%",
         "1", "4", "5", "2",
         "John", "5", "4",
         "1.8", "0", "100%",
         "Launched v2.0; Team onboarding complete", "None"],
    ]

    weekly_sheet.update(values=[weekly_headers] + weekly_examples, range_name='A1')

    # Header formatting - dark green
    requests.append({'repeatCell': {'range': {'sheetId': weekly_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 22}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(26, 102, 77), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255), 'fontSize': 10}, 'horizontalAlignment': 'CENTER', 'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat'}})

    requests.append({'updateDimensionProperties': {'range': {'sheetId': weekly_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 45}, 'fields': 'pixelSize'}})
    requests.append({'updateSheetProperties': {'properties': {'sheetId': weekly_id, 'gridProperties': {'frozenRowCount': 1, 'frozenColumnCount': 2}}, 'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'}})

    # Column widths
    col_widths_weekly = [60, 50, 90, 90, 130, 90, 100, 90, 90, 95, 80, 75, 85, 70, 110, 120, 130, 130, 90, 90, 250, 250]
    for i, w in enumerate(col_widths_weekly):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': weekly_id, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i+1}, 'properties': {'pixelSize': w}, 'fields': 'pixelSize'}})

    add_borders(requests, weekly_id, 0, 60, 0, 22)
    add_alternating_colors(requests, weekly_id, 0, 60, 0, 22)

    # Conditional formatting for completion rate
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{'sheetId': weekly_id, 'startRowIndex': 1, 'endRowIndex': 100, 'startColumnIndex': 9, 'endColumnIndex': 10}],
                'booleanRule': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=VALUE(SUBSTITUTE(J2,"%",""))>=80'}]}, 'format': {'backgroundColor': rgb(144, 238, 144)}}
            }, 'index': 0
        }
    })
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{'sheetId': weekly_id, 'startRowIndex': 1, 'endRowIndex': 100, 'startColumnIndex': 9, 'endColumnIndex': 10}],
                'booleanRule': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=AND(VALUE(SUBSTITUTE(J2,"%",""))>=60,VALUE(SUBSTITUTE(J2,"%",""))<80)'}]}, 'format': {'backgroundColor': rgb(255, 255, 150)}}
            }, 'index': 1
        }
    })
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{'sheetId': weekly_id, 'startRowIndex': 1, 'endRowIndex': 100, 'startColumnIndex': 9, 'endColumnIndex': 10}],
                'booleanRule': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=VALUE(SUBSTITUTE(J2,"%",""))<60'}]}, 'format': {'backgroundColor': rgb(255, 150, 150)}}
            }, 'index': 2
        }
    })

    print("  [OK] Weekly Reports: comprehensive metrics template")

    # ========================================
    # 5. MONTHLY REPORTS
    # ========================================
    print("\n[5/8] Setting up Monthly Reports...")

    monthly_sheet = get_or_create_sheet(spreadsheet, "📆 Monthly Reports", rows=100, cols=28)
    monthly_id = monthly_sheet.id

    monthly_headers = [
        "Month", "Year", "Generated",
        # Volume Metrics
        "Tasks Created", "Tasks Completed", "Tasks Cancelled", "Completion Rate",
        # Priority Breakdown
        "Urgent Created", "Urgent Done", "High Created", "High Done", "Medium Created", "Medium Done", "Low Created", "Low Done",
        # Status Summary
        "Pending EOM", "In Progress EOM", "Blocked EOM",
        # Team Performance
        "Top Performer", "Top Tasks Done", "Most Improved", "Team Size", "Avg Tasks/Person",
        # Time Metrics
        "Avg Days to Complete", "Fastest Completion", "Overdue Count", "On-Time Rate",
        # Narrative
        "Monthly Summary"
    ]

    monthly_examples = [
        ["January", "2026", datetime.now().strftime("%Y-%m-%d"),
         "78", "65", "3", "83.3%",
         "8", "7", "25", "22", "30", "26", "15", "10",
         "8", "5", "2",
         "Sarah", "18", "Mike", "5", "13.0",
         "2.4", "0.5", "3", "95.4%",
         "Strong start to year. Completed major dashboard redesign. Auth system overhaul finished. Team velocity improving."],
        ["December", "2025", "2025-12-31",
         "62", "58", "2", "93.5%",
         "5", "5", "20", "19", "25", "24", "12", "10",
         "4", "2", "0",
         "John", "16", "Sarah", "5", "11.6",
         "1.9", "0.3", "1", "98.3%",
         "Excellent month. Holiday period but maintained high productivity. All critical bugs resolved. Q4 goals achieved."],
    ]

    monthly_sheet.update(values=[monthly_headers] + monthly_examples, range_name='A1')

    # Header formatting - purple
    requests.append({'repeatCell': {'range': {'sheetId': monthly_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 28}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(102, 51, 102), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255), 'fontSize': 10}, 'horizontalAlignment': 'CENTER', 'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat'}})

    requests.append({'updateDimensionProperties': {'range': {'sheetId': monthly_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 45}, 'fields': 'pixelSize'}})
    requests.append({'updateSheetProperties': {'properties': {'sheetId': monthly_id, 'gridProperties': {'frozenRowCount': 1, 'frozenColumnCount': 2}}, 'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'}})

    # Column widths
    col_widths_monthly = [80, 50, 100, 90, 100, 100, 100, 90, 80, 85, 75, 100, 95, 80, 75, 90, 105, 90, 100, 100, 100, 75, 110, 130, 115, 95, 90, 350]
    for i, w in enumerate(col_widths_monthly):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': monthly_id, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i+1}, 'properties': {'pixelSize': w}, 'fields': 'pixelSize'}})

    add_borders(requests, monthly_id, 0, 30, 0, 28)
    add_alternating_colors(requests, monthly_id, 0, 30, 0, 28)

    # Conditional formatting for completion rate (column G = index 6)
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{'sheetId': monthly_id, 'startRowIndex': 1, 'endRowIndex': 50, 'startColumnIndex': 6, 'endColumnIndex': 7}],
                'booleanRule': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=VALUE(SUBSTITUTE(G2,"%",""))>=80'}]}, 'format': {'backgroundColor': rgb(144, 238, 144)}}
            }, 'index': 0
        }
    })
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{'sheetId': monthly_id, 'startRowIndex': 1, 'endRowIndex': 50, 'startColumnIndex': 6, 'endColumnIndex': 7}],
                'booleanRule': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=AND(VALUE(SUBSTITUTE(G2,"%",""))>=60,VALUE(SUBSTITUTE(G2,"%",""))<80)'}]}, 'format': {'backgroundColor': rgb(255, 255, 150)}}
            }, 'index': 1
        }
    })
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{'sheetId': monthly_id, 'startRowIndex': 1, 'endRowIndex': 50, 'startColumnIndex': 6, 'endColumnIndex': 7}],
                'booleanRule': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=VALUE(SUBSTITUTE(G2,"%",""))<60'}]}, 'format': {'backgroundColor': rgb(255, 150, 150)}}
            }, 'index': 2
        }
    })

    print("  [OK] Monthly Reports: comprehensive metrics template")

    # ========================================
    # 6. NOTES LOG
    # ========================================
    print("\n[6/8] Setting up Notes Log...")

    notes_sheet = get_or_create_sheet(spreadsheet, "📝 Notes Log", rows=2000, cols=8)
    notes_id = notes_sheet.id

    notes_headers = ["Timestamp", "Task ID", "Task Title", "Author", "Type", "Content", "Pinned"]
    notes_examples = [
        [datetime.now().strftime("%Y-%m-%d %H:%M"), "TASK-001", "Fix login authentication bug", "John", "update", "Found the root cause - OAuth token expiring too early", "No"],
        [(datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"), "TASK-003", "Update API documentation", "Mike", "question", "Should we include deprecated endpoints?", "Yes"],
        [(datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M"), "TASK-002", "Design new dashboard UI", "Sarah", "blocker", "Waiting for brand guidelines from marketing", "Yes"],
    ]

    notes_sheet.update(values=[notes_headers] + notes_examples, range_name='A1')

    requests.append({'repeatCell': {'range': {'sheetId': notes_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 7}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(77, 77, 102), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255), 'fontSize': 10}, 'horizontalAlignment': 'CENTER'}}, 'fields': 'userEnteredFormat'}})

    requests.append({'updateDimensionProperties': {'range': {'sheetId': notes_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 35}, 'fields': 'pixelSize'}})
    requests.append({'updateSheetProperties': {'properties': {'sheetId': notes_id, 'gridProperties': {'frozenRowCount': 1}}, 'fields': 'gridProperties.frozenRowCount'}})

    for i, w in enumerate([140, 90, 180, 100, 80, 400, 60]):
        requests.append({'updateDimensionProperties': {'range': {'sheetId': notes_id, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i+1}, 'properties': {'pixelSize': w}, 'fields': 'pixelSize'}})

    add_borders(requests, notes_id, 0, 100, 0, 7)
    add_alternating_colors(requests, notes_id, 0, 100, 0, 7)

    # Note type dropdown
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': notes_id, 'startRowIndex': 1, 'endRowIndex': 2000, 'startColumnIndex': 4, 'endColumnIndex': 5},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in ['update', 'question', 'blocker', 'resolution', 'general']]}, 'showCustomUi': True}
        }
    })

    # Pinned dropdown
    requests.append({
        'setDataValidation': {
            'range': {'sheetId': notes_id, 'startRowIndex': 1, 'endRowIndex': 2000, 'startColumnIndex': 6, 'endColumnIndex': 7},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': 'Yes'}, {'userEnteredValue': 'No'}]}, 'showCustomUi': True}
        }
    })

    print("  [OK] Notes Log: template with examples, dropdowns")

    # ========================================
    # 7. TASK ARCHIVE
    # ========================================
    print("\n[7/8] Setting up Task Archive...")

    archive_sheet = get_or_create_sheet(spreadsheet, "🗃️ Archive", rows=5000, cols=18)
    archive_id = archive_sheet.id

    archive_headers = ["ID", "Title", "Description", "Assignee", "Priority", "Final Status", "Type", "Deadline", "Created", "Completed", "Days to Complete", "Notes Count", "Archived On"]
    archive_examples = [
        ["TASK-000", "Initial project setup", "Set up repo and CI/CD", "John", "high", "completed", "task", "2025-12-15", "2025-12-10", "2025-12-14", "4", "2", datetime.now().strftime("%Y-%m-%d")],
    ]

    archive_sheet.update(values=[archive_headers] + archive_examples, range_name='A1')

    requests.append({'repeatCell': {'range': {'sheetId': archive_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 13}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(102, 102, 102), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255), 'fontSize': 10}, 'horizontalAlignment': 'CENTER'}}, 'fields': 'userEnteredFormat'}})

    requests.append({'updateDimensionProperties': {'range': {'sheetId': archive_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 35}, 'fields': 'pixelSize'}})
    requests.append({'updateSheetProperties': {'properties': {'sheetId': archive_id, 'gridProperties': {'frozenRowCount': 1}}, 'fields': 'gridProperties.frozenRowCount'}})

    add_borders(requests, archive_id, 0, 100, 0, 13)
    add_alternating_colors(requests, archive_id, 0, 100, 0, 13)

    print("  [OK] Task Archive: historical records")

    # ========================================
    # 8. SETTINGS
    # ========================================
    print("\n[8/8] Setting up Settings...")

    settings_sheet = get_or_create_sheet(spreadsheet, "⚙️ Settings", rows=50, cols=8)
    settings_id = settings_sheet.id

    settings_data = [
        ["⚙️ WORKFLOW SETTINGS", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["👥 TEAM MEMBERS", "", "", "", "", "", "", ""],
        ["See '👥 Team' sheet for team directory", "", "", "", "", "", "", ""],
        ["Use /syncteam command to populate from config/team.py", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["📋 ROLE CATEGORIES (for Discord routing)", "", "", "", "", "", "", ""],
        ["Developer", "→ Dev category channels", "", "", "", "", "", ""],
        ["Marketing", "→ Marketing category channels", "", "", "", "", "", ""],
        ["Admin", "→ Admin category channels", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["📋 TASK TYPES", "", "", "🎯 PRIORITIES", "", "", "", ""],
        ["Type", "Description", "", "Priority", "Description", "Color", "", ""],
        ["task", "General task", "", "urgent", "Immediate action", "Red", "", ""],
        ["bug", "Bug/defect fix", "", "high", "Important", "Orange", "", ""],
        ["feature", "New feature", "", "medium", "Normal", "Yellow", "", ""],
        ["research", "Research/analysis", "", "low", "When possible", "Green", "", ""],
        ["meeting", "Meeting/call", "", "", "", "", "", ""],
        ["review", "Code/design review", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["📊 STATUS OPTIONS", "", "", "", "", "", "", ""],
        ["Status", "Description", "Color", "", "", "", "", ""],
        ["pending", "Not started", "Gray", "", "", "", "", ""],
        ["in_progress", "Being worked on", "Blue", "", "", "", "", ""],
        ["in_review", "Under review", "Purple", "", "", "", "", ""],
        ["completed", "Done", "Green", "", "", "", "", ""],
        ["blocked", "Stuck/waiting", "Red", "", "", "", "", ""],
        ["delayed", "Behind schedule", "Orange", "", "", "", "", ""],
        ["on_hold", "Paused", "Gray", "", "", "", "", ""],
        ["cancelled", "Not doing", "Dark Gray", "", "", "", "", ""],
    ]

    settings_sheet.update(values=settings_data, range_name='A1')

    # Title
    requests.append({'repeatCell': {'range': {'sheetId': settings_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 4}, 'cell': {'userEnteredFormat': {'textFormat': {'bold': True, 'fontSize': 16, 'foregroundColor': rgb(26, 26, 51)}}}, 'fields': 'userEnteredFormat'}})

    # Section headers
    for row in [2, 9, 18]:
        requests.append({'repeatCell': {'range': {'sheetId': settings_id, 'startRowIndex': row, 'endRowIndex': row+1, 'startColumnIndex': 0, 'endColumnIndex': 6}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(240, 240, 245), 'textFormat': {'bold': True, 'fontSize': 11}}}, 'fields': 'userEnteredFormat'}})

    # Table headers
    for row, cols in [(3, 5), (10, 3), (10, 6), (19, 3)]:
        end_col = cols if row != 10 else 3
        start_col = 0 if cols == 5 or cols == 3 else 3
        requests.append({'repeatCell': {'range': {'sheetId': settings_id, 'startRowIndex': row, 'endRowIndex': row+1, 'startColumnIndex': start_col, 'endColumnIndex': start_col + end_col}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(26, 26, 51), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255)}}}, 'fields': 'userEnteredFormat'}})

    # Also format row 10 columns D-F
    requests.append({'repeatCell': {'range': {'sheetId': settings_id, 'startRowIndex': 10, 'endRowIndex': 11, 'startColumnIndex': 3, 'endColumnIndex': 6}, 'cell': {'userEnteredFormat': {'backgroundColor': rgb(26, 26, 51), 'textFormat': {'bold': True, 'foregroundColor': rgb(255, 255, 255)}}}, 'fields': 'userEnteredFormat'}})

    add_borders(requests, settings_id, 3, 8, 0, 5)
    add_borders(requests, settings_id, 10, 17, 0, 3)
    add_borders(requests, settings_id, 10, 15, 3, 6)
    add_borders(requests, settings_id, 19, 28, 0, 3)

    print("  [OK] Settings: team list, types, priorities, statuses")

    # ========================================
    # APPLY MONTSERRAT FONT TO ALL SHEETS
    # ========================================
    print("\n[*] Applying Montserrat font to all sheets...")

    all_sheet_ids = [tasks_id, dash_id, team_id, weekly_id, monthly_id, notes_id, archive_id, settings_id]
    for sid in all_sheet_ids:
        requests.append({
            'repeatCell': {
                'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1000, 'startColumnIndex': 0, 'endColumnIndex': 20},
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'fontFamily': 'Montserrat'}
                    }
                },
                'fields': 'userEnteredFormat.textFormat.fontFamily'
            }
        })

    # ========================================
    # EXECUTE ALL REQUESTS
    # ========================================
    print("\n" + "="*50)
    print("Applying all formatting...")
    print("="*50)

    # Execute in batches to avoid API limits
    batch_size = 100
    for i in range(0, len(requests), batch_size):
        batch = requests[i:i+batch_size]
        spreadsheet.batch_update({'requests': batch})
        print(f"  Batch {i//batch_size + 1}: {len(batch)} requests applied")

    return True


def main():
    print("\n" + "="*60)
    print("  BOSS WORKFLOW - Advanced Google Sheets Setup")
    print("="*60)

    print(f"\n[*] Sheet ID: {GOOGLE_SHEET_ID[:20]}..." if GOOGLE_SHEET_ID else "\n[X] Sheet ID: NOT SET")
    print(f"[*] Credentials: {'SET' if GOOGLE_CREDENTIALS_JSON else 'NOT SET'}")

    if not GOOGLE_SHEET_ID or not GOOGLE_CREDENTIALS_JSON:
        print("\n[X] ERROR: Missing configuration. Check .env file.")
        return

    print("\n[*] Connecting to Google Sheets...")
    try:
        creds_data = json.loads(GOOGLE_CREDENTIALS_JSON)
        credentials = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        print(f"[OK] Connected to: {spreadsheet.title}")
    except Exception as e:
        print(f"\n[X] ERROR: {e}")
        return

    try:
        setup_advanced_sheets(spreadsheet)
    except Exception as e:
        print(f"\n[X] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "="*60)
    print("  [OK] SUCCESS! Professional sheets created.")
    print("="*60)
    print("""
Features Applied:
  - 8 professional tabs with consistent styling
  - Example data in all sheets
  - Dropdown menus (Priority, Status, Type, Progress, Role, etc.)
  - Conditional formatting (color-coded priorities & statuses)
  - Overdue task highlighting
  - Borders and gridlines
  - Alternating row colors (banding)
  - Frozen headers and columns
  - Optimized column widths
  - Dashboard with live formulas

View your sheet at:
""")
    print(f"  https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}")
    print()


if __name__ == "__main__":
    main()
