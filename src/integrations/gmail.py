"""
Gmail integration for reading and summarizing emails.

Uses Google API to fetch emails and DeepSeek to generate summaries.
Sends morning and evening digests via Telegram.

Supports:
- Service Account (Google Workspace with domain-wide delegation)
- OAuth2 (Personal Gmail - requires one-time browser auth)
"""

import logging
import base64
import os
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
import json
import re
from pathlib import Path
import aiofiles

from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings

logger = logging.getLogger(__name__)

# Token storage path
TOKEN_PATH = Path("data/gmail_token.json")
CREDENTIALS_PATH = Path("data/gmail_credentials.json")


@dataclass
class EmailMessage:
    """Represents a parsed email message."""
    id: str
    thread_id: str
    subject: str
    sender: str
    sender_email: str
    recipients: List[str]
    date: datetime
    snippet: str
    body_text: str
    body_html: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    is_unread: bool = False
    has_attachments: bool = False
    attachment_names: List[str] = field(default_factory=list)

    @property
    def is_important(self) -> bool:
        """Check if email is marked important."""
        return "IMPORTANT" in self.labels

    @property
    def is_starred(self) -> bool:
        """Check if email is starred."""
        return "STARRED" in self.labels

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to dict for summarization."""
        return {
            "subject": self.subject,
            "from": f"{self.sender} <{self.sender_email}>",
            "date": self.date.strftime("%Y-%m-%d %H:%M"),
            "snippet": self.snippet[:200],
            "body": self.body_text[:2000],  # Limit for API
            "is_important": self.is_important,
            "has_attachments": self.has_attachments,
            "attachments": self.attachment_names[:5]
        }


@dataclass
class EmailDigest:
    """Summary of emails for a time period."""
    period: str  # "morning" or "evening"
    start_time: datetime
    end_time: datetime
    total_emails: int
    unread_count: int
    important_count: int
    emails: List[EmailMessage]
    summary: str = ""
    action_items: List[str] = field(default_factory=list)
    priority_emails: List[Dict] = field(default_factory=list)

    def to_telegram_message(self) -> str:
        """Format digest for Telegram."""
        emoji = "☀️" if self.period == "morning" else "🌙"
        lines = [
            f"{emoji} **{self.period.title()} Email Digest**",
            f"_{self.start_time.strftime('%b %d')} - {self.end_time.strftime('%H:%M')}_",
            "",
            f"📬 **{self.total_emails}** emails | **{self.unread_count}** unread | **{self.important_count}** important",
            "",
        ]

        if self.summary:
            lines.append("**Summary:**")
            lines.append(self.summary)
            lines.append("")

        if self.action_items:
            lines.append("**Action Items:**")
            for item in self.action_items[:5]:
                lines.append(f"  • {item}")
            lines.append("")

        if self.priority_emails:
            lines.append("**Priority Emails:**")
            for email in self.priority_emails[:5]:
                subject = email.get("subject", "No subject")[:40]
                sender = email.get("from", "Unknown")[:20]
                lines.append(f"  📧 {subject}...")
                lines.append(f"     _{sender}_")
            lines.append("")

        lines.append("─────────────────")

        return "\n".join(lines)


class GmailIntegration:
    """
    Gmail integration for reading and summarizing emails.

    Supports two authentication methods:
    1. Service Account (Google Workspace with domain-wide delegation)
    2. OAuth2 (Personal Gmail - requires one-time browser auth)

    For personal Gmail (like corporationout@gmail.com), use OAuth2.
    """

    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.labels'
    ]

    def __init__(self):
        self.service = None
        self.user_email = settings.gmail_user_email
        self._initialized = False
        self._auth_method = None  # "oauth2" or "service_account"

    async def is_available(self) -> bool:
        """Check if Gmail integration is available."""
        if not self._initialized:
            await self.initialize()
        return self._initialized and self.service is not None

    async def initialize(self) -> bool:
        """Initialize Gmail API connection."""
        if not self.user_email:
            logger.warning("Gmail user email not configured")
            return False

        # Ensure data directory exists
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Try OAuth2 first (for personal Gmail)
        if await self._try_oauth2():
            return True

        # Fall back to service account (for Workspace)
        if await self._try_service_account():
            return True

        logger.error("Failed to initialize Gmail with any auth method")
        return False

    async def _try_oauth2(self) -> bool:
        """Try OAuth2 authentication for personal Gmail."""
        try:
            creds = None

            # First, check for token in environment variable (Railway deployment)
            if settings.gmail_oauth_token:
                try:
                    token_data = await asyncio.to_thread(json.loads, settings.gmail_oauth_token)
                    creds = OAuth2Credentials.from_authorized_user_info(
                        token_data, self.SCOPES
                    )
                    logger.info("Loaded Gmail token from environment variable")
                except Exception as e:
                    logger.warning(f"Failed to load token from env var: {e}")

            # Fall back to token file (local development)
            if not creds and TOKEN_PATH.exists():
                creds = OAuth2Credentials.from_authorized_user_file(
                    str(TOKEN_PATH), self.SCOPES
                )
                logger.info("Loaded Gmail token from file")

            # Refresh or get new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    logger.info("Gmail token refreshed")
                else:
                    # Need OAuth2 credentials file for new token
                    if not CREDENTIALS_PATH.exists():
                        # Try to create from environment
                        if settings.gmail_oauth_credentials:
                            await asyncio.to_thread(CREDENTIALS_PATH.parent.mkdir, parents=True, exist_ok=True)
                            async with aiofiles.open(CREDENTIALS_PATH, 'w') as f:
                                await f.write(settings.gmail_oauth_credentials)
                        else:
                            logger.info("No OAuth2 credentials found. Run setup_gmail_oauth() first.")
                            return False

                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(CREDENTIALS_PATH), self.SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                # Save token for next time (local file)
                try:
                    await asyncio.to_thread(TOKEN_PATH.parent.mkdir, parents=True, exist_ok=True)
                    async with aiofiles.open(TOKEN_PATH, 'w') as f:
                        await f.write(creds.to_json())
                except Exception as e:
                    logger.warning(f"Could not save token to file: {e}")

            # Build service
            self.service = build('gmail', 'v1', credentials=creds)
            self._initialized = True
            self._auth_method = "oauth2"

            logger.info(f"Gmail initialized via OAuth2 for {self.user_email}")
            return True

        except Exception as e:
            logger.debug(f"OAuth2 init failed: {e}")
            return False

    async def _try_service_account(self) -> bool:
        """Try service account authentication (for Workspace)."""
        if not settings.google_credentials_json:
            return False

        try:
            # Parse credentials (async)
            if settings.google_credentials_json.startswith('{'):
                creds_dict = await asyncio.to_thread(json.loads, settings.google_credentials_json)
            else:
                async def _read_creds_file_async(path):
                    async with aiofiles.open(path, 'r') as f:
                        content = await f.read()
                        return await asyncio.to_thread(json.loads, content)
                creds_dict = await _read_creds_file_async(settings.google_credentials_json)

            # Create credentials with domain-wide delegation
            credentials = ServiceAccountCredentials.from_service_account_info(
                creds_dict,
                scopes=self.SCOPES
            )

            # Delegate to user email
            delegated_credentials = credentials.with_subject(self.user_email)

            # Build service
            self.service = build('gmail', 'v1', credentials=delegated_credentials)
            self._initialized = True
            self._auth_method = "service_account"

            logger.info(f"Gmail initialized via Service Account for {self.user_email}")
            return True

        except Exception as e:
            logger.debug(f"Service account init failed: {e}")
            return False

    async def get_emails_since(
        self,
        hours: int = 12,
        max_results: int = 50,
        unread_only: bool = False
    ) -> List[EmailMessage]:
        """
        Get emails from the last N hours.

        Args:
            hours: Number of hours to look back
            max_results: Maximum emails to fetch
            unread_only: Only fetch unread emails

        Returns:
            List of EmailMessage objects
        """
        if not self._initialized:
            await self.initialize()

        if not self.service:
            return []

        try:
            # Build query
            after_time = datetime.now() - timedelta(hours=hours)
            after_timestamp = int(after_time.timestamp())

            query = f"after:{after_timestamp}"
            if unread_only:
                query += " is:unread"

            # Fetch message IDs
            results = await asyncio.wait_for(
                asyncio.to_thread(
                    self.service.users().messages().list(
                        userId='me',
                        q=query,
                        maxResults=max_results
                    ).execute
                ),
                timeout=30.0
            )

            messages = results.get('messages', [])
            if not messages:
                return []

            # Fetch full message details
            emails = []
            for msg_ref in messages:
                try:
                    email = await self._get_email_details(msg_ref['id'])
                    if email:
                        emails.append(email)
                except Exception as e:
                    logger.error(f"Error fetching email {msg_ref['id']}: {e}")

            # Sort by date descending
            emails.sort(key=lambda x: x.date, reverse=True)

            logger.info(f"Fetched {len(emails)} emails from last {hours} hours")
            return emails

        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []

    async def _get_email_details(self, message_id: str) -> Optional[EmailMessage]:
        """Get full details of a single email."""
        try:
            msg = await asyncio.wait_for(
                asyncio.to_thread(
                    self.service.users().messages().get(
                        userId='me',
                        id=message_id,
                        format='full'
                    ).execute
                ),
                timeout=30.0
            )

            # Parse headers
            headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}

            subject = headers.get('subject', '(No subject)')
            from_header = headers.get('from', '')
            to_header = headers.get('to', '')
            date_header = headers.get('date', '')

            # Parse sender
            sender_match = re.match(r'(.+?)\s*<(.+?)>', from_header)
            if sender_match:
                sender_name = sender_match.group(1).strip('" ')
                sender_email = sender_match.group(2)
            else:
                sender_name = from_header
                sender_email = from_header

            # Parse date
            try:
                email_date = parsedate_to_datetime(date_header)
            except (ValueError, TypeError, AttributeError) as e:
                logger.debug(f"Invalid email date header, using current time: {e}")
                email_date = datetime.now()

            # Parse recipients
            recipients = [r.strip() for r in to_header.split(',')]

            # Get body
            body_text, body_html, attachments = self._parse_body(msg.get('payload', {}))

            # Check labels
            labels = msg.get('labelIds', [])
            is_unread = 'UNREAD' in labels

            return EmailMessage(
                id=message_id,
                thread_id=msg.get('threadId', ''),
                subject=subject,
                sender=sender_name,
                sender_email=sender_email,
                recipients=recipients,
                date=email_date,
                snippet=msg.get('snippet', ''),
                body_text=body_text,
                body_html=body_html,
                labels=labels,
                is_unread=is_unread,
                has_attachments=len(attachments) > 0,
                attachment_names=attachments
            )

        except Exception as e:
            logger.error(f"Error parsing email {message_id}: {e}")
            return None

    def _parse_body(self, payload: Dict) -> tuple[str, Optional[str], List[str]]:
        """Parse email body from payload."""
        body_text = ""
        body_html = None
        attachments = []

        def extract_parts(part):
            nonlocal body_text, body_html, attachments

            mime_type = part.get('mimeType', '')
            filename = part.get('filename', '')

            if filename:
                attachments.append(filename)

            if 'body' in part and 'data' in part['body']:
                data = part['body']['data']
                decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

                if mime_type == 'text/plain' and not body_text:
                    body_text = decoded
                elif mime_type == 'text/html' and not body_html:
                    body_html = decoded

            if 'parts' in part:
                for subpart in part['parts']:
                    extract_parts(subpart)

        extract_parts(payload)

        # If no plain text, convert HTML
        if not body_text and body_html:
            body_text = re.sub(r'<[^>]+>', ' ', body_html)
            body_text = re.sub(r'\s+', ' ', body_text).strip()

        return body_text, body_html, attachments

    async def get_unread_count(self) -> int:
        """Get count of unread emails."""
        if not self._initialized:
            await self.initialize()

        if not self.service:
            return 0

        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(
                    self.service.users().messages().list(
                        userId='me',
                        q='is:unread',
                        maxResults=1
                    ).execute
                ),
                timeout=30.0
            )

            return results.get('resultSizeEstimate', 0)

        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return 0

    async def create_digest(
        self,
        period: str,
        hours: int = 12
    ) -> EmailDigest:
        """
        Create an email digest for the specified period.

        Args:
            period: "morning" or "evening"
            hours: Hours to look back

        Returns:
            EmailDigest with summary
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        emails = await self.get_emails_since(hours=hours, max_results=50)

        unread_count = sum(1 for e in emails if e.is_unread)
        important_count = sum(1 for e in emails if e.is_important)

        # Identify priority emails
        priority_emails = [
            e.to_summary_dict() for e in emails
            if e.is_important or e.is_unread
        ][:10]

        digest = EmailDigest(
            period=period,
            start_time=start_time,
            end_time=end_time,
            total_emails=len(emails),
            unread_count=unread_count,
            important_count=important_count,
            emails=emails,
            priority_emails=priority_emails
        )

        return digest


# Singleton
gmail_integration = GmailIntegration()


def get_gmail_integration() -> GmailIntegration:
    return gmail_integration
