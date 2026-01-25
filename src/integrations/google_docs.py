"""
Google Docs API integration for automated documentation.

Creates and formats Google Docs with project specifications,
task breakdowns, and planning details.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import settings

logger = logging.getLogger(__name__)


class GoogleDocsClient:
    """Client for Google Docs API operations."""

    SCOPES = [
        'https://www.googleapis.com/auth/documents',
        'https://www.googleapis.com/auth/drive'
    ]

    def __init__(self):
        self.docs_service = None
        self.drive_service = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize Google Docs and Drive services."""
        if self._initialized:
            return True

        try:
            creds_json = settings.google_credentials_json
            if not creds_json:
                logger.error("No Google credentials configured")
                return False

            creds_data = await asyncio.to_thread(json.loads, creds_json)
            credentials = Credentials.from_service_account_info(
                creds_data,
                scopes=self.SCOPES
            )

            self.docs_service = build('docs', 'v1', credentials=credentials)
            self.drive_service = build('drive', 'v3', credentials=credentials)

            self._initialized = True
            logger.info("Google Docs API initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Docs API: {e}")
            return False

    async def create_document(self, title: str) -> Optional[str]:
        """
        Create a new Google Doc.

        Args:
            title: Document title

        Returns:
            Document ID if successful, None otherwise
        """
        if not await self.initialize():
            return None

        try:
            doc_body = {'title': title}

            doc = await asyncio.to_thread(
                self.docs_service.documents().create(body=doc_body).execute
            )

            doc_id = doc.get('documentId')
            logger.info(f"Created Google Doc: {title} ({doc_id})")
            return doc_id

        except HttpError as e:
            logger.error(f"HTTP error creating document: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            return None

    async def add_content(
        self,
        doc_id: str,
        content: str,
        index: int = 1,
        style: Optional[str] = None
    ):
        """
        Add content to document at specified index.

        Args:
            doc_id: Document ID
            content: Text content to add
            index: Position to insert (default: 1 = start of doc)
            style: Optional named style (HEADING_1, HEADING_2, etc.)
        """
        if not await self.initialize():
            return

        try:
            requests = [
                {
                    'insertText': {
                        'location': {'index': index},
                        'text': content + '\n'
                    }
                }
            ]

            if style:
                requests.append({
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': index,
                            'endIndex': index + len(content) + 1
                        },
                        'paragraphStyle': {
                            'namedStyleType': style
                        },
                        'fields': 'namedStyleType'
                    }
                })

            await asyncio.to_thread(
                self.docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': requests}
                ).execute
            )

        except HttpError as e:
            logger.error(f"HTTP error adding content: {e}")
        except Exception as e:
            logger.error(f"Failed to add content: {e}")

    async def add_table(
        self,
        doc_id: str,
        table_data: List[List[str]],
        index: int = 1
    ):
        """
        Add a table to the document.

        Args:
            doc_id: Document ID
            table_data: 2D list of table cells (rows x columns)
            index: Position to insert table
        """
        if not await self.initialize():
            return

        if not table_data or not table_data[0]:
            logger.warning("Empty table data provided")
            return

        try:
            rows = len(table_data)
            cols = len(table_data[0])

            # Create table
            requests = [
                {
                    'insertTable': {
                        'rows': rows,
                        'columns': cols,
                        'location': {'index': index}
                    }
                }
            ]

            # Execute table creation
            result = await asyncio.to_thread(
                self.docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': requests}
                ).execute
            )

            # Get the document to find table indices
            doc = await asyncio.to_thread(
                self.docs_service.documents().get(documentId=doc_id).execute
            )

            # Find the table we just created
            table_start_index = None
            for element in doc.get('body', {}).get('content', []):
                if 'table' in element:
                    # Check if this is our table based on position
                    if element.get('startIndex', 0) >= index:
                        table_start_index = element.get('startIndex')
                        break

            if table_start_index is None:
                logger.error("Could not find created table")
                return

            # Fill table cells with data
            fill_requests = []
            current_index = table_start_index + 3  # Skip table start tags

            for row_idx, row in enumerate(table_data):
                for col_idx, cell_value in enumerate(row):
                    # Insert text into cell
                    fill_requests.append({
                        'insertText': {
                            'location': {'index': current_index},
                            'text': str(cell_value)
                        }
                    })
                    current_index += len(str(cell_value)) + 2  # +2 for cell end markers

            if fill_requests:
                await asyncio.to_thread(
                    self.docs_service.documents().batchUpdate(
                        documentId=doc_id,
                        body={'requests': fill_requests}
                    ).execute
                )

            logger.info(f"Added {rows}x{cols} table to document {doc_id}")

        except HttpError as e:
            logger.error(f"HTTP error adding table: {e}")
        except Exception as e:
            logger.error(f"Failed to add table: {e}", exc_info=True)

    async def get_shareable_link(self, doc_id: str) -> str:
        """
        Get shareable link for document.

        Args:
            doc_id: Document ID

        Returns:
            Shareable URL
        """
        if not await self.initialize():
            return f"https://docs.google.com/document/d/{doc_id}/edit"

        try:
            # Make document publicly readable (or shared with domain)
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }

            await asyncio.to_thread(
                self.drive_service.permissions().create(
                    fileId=doc_id,
                    body=permission
                ).execute
            )

            logger.info(f"Set public sharing for document {doc_id}")

        except Exception as e:
            logger.warning(f"Could not set public sharing: {e}")

        return f"https://docs.google.com/document/d/{doc_id}/edit"

    async def create_spec_document(
        self,
        title: str,
        session_data: Dict[str, Any],
        task_drafts: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Create a complete specification document.

        Args:
            title: Document title
            session_data: Planning session data
            task_drafts: List of task drafts

        Returns:
            Shareable document URL
        """
        doc_id = await self.create_document(title)
        if not doc_id:
            return None

        try:
            # Add title
            await self.add_content(doc_id, title, index=1, style='HEADING_1')

            # Add metadata
            metadata = f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            metadata += f"Session ID: {session_data.get('session_id', 'N/A')}\n"
            metadata += f"Complexity: {session_data.get('complexity', 'medium')}\n\n"
            await self.add_content(doc_id, metadata, index=1)

            # Add executive summary section
            await self.add_content(doc_id, "Executive Summary", index=1, style='HEADING_2')

            # Add task breakdown table
            await self.add_content(doc_id, "\nTask Breakdown", index=1, style='HEADING_2')

            # Prepare table data
            table_data = [
                ["Task ID", "Title", "Assignee", "Effort (h)", "Priority", "Deadline"]
            ]

            for task in task_drafts:
                table_data.append([
                    task.get('task_id', ''),
                    task.get('title', '')[:50],  # Truncate long titles
                    task.get('assignee', 'Unassigned'),
                    str(task.get('estimated_effort_hours', 'TBD')),
                    task.get('priority', 'medium'),
                    task.get('deadline', '').strftime('%Y-%m-%d') if task.get('deadline') else 'TBD'
                ])

            # Note: Table insertion is complex in Google Docs API
            # For now, we'll add as formatted text instead
            table_text = "\n\n"
            for row in table_data:
                table_text += " | ".join(row) + "\n"

            await self.add_content(doc_id, table_text, index=1)

            # Get shareable link
            url = await self.get_shareable_link(doc_id)
            logger.info(f"Created specification document: {url}")
            return url

        except Exception as e:
            logger.error(f"Failed to populate spec document: {e}", exc_info=True)
            # Return link even if population failed
            return await self.get_shareable_link(doc_id)


# Global instance
google_docs_client = GoogleDocsClient()


def get_google_docs_client() -> GoogleDocsClient:
    """Get the Google Docs client instance."""
    return google_docs_client
