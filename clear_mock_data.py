"""
Clear all mock/example data from Google Sheets.
Keeps headers intact, only removes example data rows.
"""

import json
import os

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


def clear_sheet_data(spreadsheet, sheet_name, start_row=2):
    """Clear all data from a sheet starting from start_row (1-indexed), keeping headers."""
    # Safe name for printing (strip emojis)
    safe_name = sheet_name.encode('ascii', 'ignore').decode('ascii').strip()
    try:
        ws = spreadsheet.worksheet(sheet_name)
        # Get number of rows and columns
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            print(f"  {safe_name}: Already empty (only headers)")
            return

        num_rows = len(all_values)
        num_cols = len(all_values[0]) if all_values else 1

        # Clear data rows (keep header at row 1)
        if num_rows > 1:
            # Create empty rows
            empty_data = [[''] * num_cols for _ in range(num_rows - 1)]
            ws.update(values=empty_data, range_name=f'A{start_row}')
            print(f"  {safe_name}: Cleared {num_rows - 1} data rows")
        else:
            print(f"  {safe_name}: No data to clear")
    except gspread.WorksheetNotFound:
        print(f"  {safe_name}: Sheet not found, skipping")
    except Exception as e:
        print(f"  {safe_name}: Error - {e}")


def main():
    print("\n" + "="*50)
    print("  Clearing Mock Data from Google Sheets")
    print("="*50)

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

    print("\n[*] Clearing mock data from sheets...")

    # Sheets with mock data to clear
    sheets_to_clear = [
        "📋 Daily Tasks",
        "📅 Weekly Reports",
        "📆 Monthly Reports",
        "📝 Notes Log",
        "🗃️ Archive",
        "⏰ Time Logs",
        "📊 Time Reports",
    ]

    for sheet_name in sheets_to_clear:
        clear_sheet_data(spreadsheet, sheet_name)

    # Note: We DON'T clear:
    # - 👥 Team (has real team data)
    # - 📊 Dashboard (has formulas, no mock data)
    # - ⚙️ Settings (has config, not mock data)

    print("\n" + "="*50)
    print("  [OK] Mock data cleared!")
    print("="*50)
    print("\nSheets preserved:")
    print("  - Team (your real team data)")
    print("  - Dashboard (formulas)")
    print("  - Settings (configuration)")
    print()


if __name__ == "__main__":
    main()
