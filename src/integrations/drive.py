"""
Google Drive integration for file storage.

Stores proof files, task documents, and attachments.
Organizes by task/project for easy access.
"""

import logging
import io
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import json
import mimetypes

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

from config import settings

logger = logging.getLogger(__name__)


class GoogleDriveIntegration:
    """
    Google Drive integration for storing task files.

    Features:
    - Upload proof screenshots/files
    - Organize files by task/project
    - Share files with team members
    - Generate shareable links
    """

    SCOPES = [
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/drive.metadata.readonly'
    ]

    def __init__(self):
        self.service = None
        self._initialized = False
        self.root_folder_id = settings.drive_folder_id

    async def initialize(self) -> bool:
        """Initialize Google Drive API connection."""
        if not settings.google_credentials_json:
            logger.warning("Google credentials not configured for Drive")
            return False

        try:
            # Parse credentials (async)
            if settings.google_credentials_json.startswith('{'):
                creds_dict = await asyncio.to_thread(json.loads, settings.google_credentials_json)
            else:
                def _read_creds_file(path):
                    with open(path, 'r') as f:
                        return json.load(f)
                creds_dict = await asyncio.to_thread(_read_creds_file, settings.google_credentials_json)

            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=self.SCOPES
            )

            self.service = build('drive', 'v3', credentials=credentials)
            self._initialized = True

            # Create root folder if not exists
            if not self.root_folder_id:
                self.root_folder_id = await self._get_or_create_folder("BossWorkflow")

            logger.info("Google Drive integration initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Google Drive: {e}")
            return False

    async def _get_or_create_folder(
        self,
        name: str,
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """Get existing folder or create new one."""
        try:
            # Search for existing folder
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            query += " and trashed=false"

            results = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.files().list(
                        q=query,
                        spaces='drive',
                        fields='files(id, name)'
                    ).execute()
                ),
                timeout=30.0
            )

            files = results.get('files', [])
            if files:
                return files[0]['id']

            # Create new folder
            file_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]

            folder = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.files().create(
                        body=file_metadata,
                        fields='id'
                    ).execute()
                ),
                timeout=30.0
            )

            logger.info(f"Created folder: {name}")
            return folder.get('id')

        except Exception as e:
            logger.error(f"Error creating folder {name}: {e}")
            return None

    async def upload_file(
        self,
        file_path: str,
        task_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """
        Upload a file to Google Drive.

        Args:
            file_path: Path to the file to upload
            task_id: Optional task ID to organize under
            description: Optional file description

        Returns:
            Dict with file_id, web_link, and download_link
        """
        if not self._initialized:
            await self.initialize()

        if not self.service:
            return None

        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"File not found: {file_path}")
                return None

            # Determine parent folder
            parent_id = self.root_folder_id
            if task_id:
                parent_id = await self._get_or_create_folder(
                    f"Task_{task_id}",
                    self.root_folder_id
                )

            # Determine mime type
            mime_type, _ = mimetypes.guess_type(str(path))
            mime_type = mime_type or 'application/octet-stream'

            # File metadata
            file_metadata = {
                'name': path.name,
                'description': description or f"Uploaded {datetime.now().isoformat()}"
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]

            # Upload
            media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
            file = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id, webViewLink, webContentLink'
                    ).execute()
                ),
                timeout=30.0
            )

            logger.info(f"Uploaded file: {path.name} -> {file.get('id')}")

            return {
                'file_id': file.get('id'),
                'web_link': file.get('webViewLink'),
                'download_link': file.get('webContentLink')
            }

        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return None

    async def upload_bytes(
        self,
        data: bytes,
        filename: str,
        mime_type: str,
        task_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """
        Upload bytes data to Google Drive.

        Useful for uploading Telegram photos directly.
        """
        if not self._initialized:
            await self.initialize()

        if not self.service:
            return None

        try:
            # Determine parent folder
            parent_id = self.root_folder_id
            if task_id:
                parent_id = await self._get_or_create_folder(
                    f"Task_{task_id}",
                    self.root_folder_id
                )

            # File metadata
            file_metadata = {
                'name': filename,
                'description': description or f"Uploaded {datetime.now().isoformat()}"
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]

            # Upload from bytes
            media = MediaIoBaseUpload(
                io.BytesIO(data),
                mimetype=mime_type,
                resumable=True
            )
            file = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id, webViewLink, webContentLink'
                    ).execute()
                ),
                timeout=30.0
            )

            logger.info(f"Uploaded bytes as: {filename} -> {file.get('id')}")

            return {
                'file_id': file.get('id'),
                'web_link': file.get('webViewLink'),
                'download_link': file.get('webContentLink')
            }

        except Exception as e:
            logger.error(f"Error uploading bytes: {e}")
            return None

    async def share_file(
        self,
        file_id: str,
        email: str,
        role: str = "reader"
    ) -> bool:
        """
        Share a file with someone.

        Args:
            file_id: Google Drive file ID
            email: Email to share with
            role: Permission role (reader, writer, commenter)
        """
        if not self.service:
            return False

        try:
            permission = {
                'type': 'user',
                'role': role,
                'emailAddress': email
            }

            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.permissions().create(
                        fileId=file_id,
                        body=permission,
                        sendNotificationEmail=False
                    ).execute()
                ),
                timeout=30.0
            )

            logger.info(f"Shared file {file_id} with {email}")
            return True

        except Exception as e:
            logger.error(f"Error sharing file: {e}")
            return False

    async def make_public(self, file_id: str) -> Optional[str]:
        """
        Make a file publicly accessible and return the link.
        """
        if not self.service:
            return None

        try:
            # Add public permission
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }

            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.permissions().create(
                        fileId=file_id,
                        body=permission
                    ).execute()
                ),
                timeout=30.0
            )

            # Get the web link
            file = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.files().get(
                        fileId=file_id,
                        fields='webViewLink'
                    ).execute()
                ),
                timeout=30.0
            )

            return file.get('webViewLink')

        except Exception as e:
            logger.error(f"Error making file public: {e}")
            return None

    async def list_task_files(self, task_id: str) -> List[Dict[str, Any]]:
        """List all files for a specific task."""
        if not self.service:
            return []

        try:
            # Get task folder
            folder_id = await self._get_or_create_folder(
                f"Task_{task_id}",
                self.root_folder_id
            )

            if not folder_id:
                return []

            # List files in folder
            results = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.files().list(
                        q=f"'{folder_id}' in parents and trashed=false",
                        spaces='drive',
                        fields='files(id, name, mimeType, webViewLink, createdTime, size)'
                    ).execute()
                ),
                timeout=30.0
            )

            return results.get('files', [])

        except Exception as e:
            logger.error(f"Error listing task files: {e}")
            return []

    async def delete_file(self, file_id: str) -> bool:
        """Delete a file from Drive."""
        if not self.service:
            return False

        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.service.files().delete(fileId=file_id).execute()
                ),
                timeout=30.0
            )
            logger.info(f"Deleted file: {file_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False


# Singleton
drive_integration = GoogleDriveIntegration()


def get_drive_integration() -> GoogleDriveIntegration:
    return drive_integration
