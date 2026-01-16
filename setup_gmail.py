"""
One-time Gmail OAuth2 setup script.

Run this once to authorize access to your Gmail.
A browser will open - log in with corporationout@gmail.com and authorize.
"""

import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Paths
CREDENTIALS_PATH = Path("data/gmail_credentials.json")
TOKEN_PATH = Path("data/gmail_token.json")

# Scopes needed
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.labels'
]

def main():
    print("=" * 50)
    print("Gmail OAuth2 Setup for Boss Workflow")
    print("=" * 50)
    print()

    if not CREDENTIALS_PATH.exists():
        print(f"ERROR: OAuth credentials not found at {CREDENTIALS_PATH}")
        print("Please ensure gmail_credentials.json is in the data folder.")
        return

    creds = None

    # Check for existing token
    if TOKEN_PATH.exists():
        print("Found existing token, checking if valid...")
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing...")
            creds.refresh(Request())
        else:
            print()
            print("Opening browser for authorization...")
            print("Please log in with: corporationout@gmail.com")
            print()

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}")

    # Test the connection
    print()
    print("Testing Gmail connection...")
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        print(f"SUCCESS! Connected to Gmail.")
        print(f"Found {len(labels)} labels in your mailbox.")
        print()

        # Get unread count
        results = service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=1
        ).execute()
        unread = results.get('resultSizeEstimate', 0)
        print(f"You have approximately {unread} unread emails.")

    except Exception as e:
        print(f"ERROR testing connection: {e}")
        return

    print()
    print("=" * 50)
    print("Setup complete! Email digests are ready to go.")
    print("=" * 50)


if __name__ == "__main__":
    main()
