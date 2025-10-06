"""Pixelfed API client for uploading media."""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout


logger = logging.getLogger(__name__)


class PixelfedClient:
    """Client for interacting with Pixelfed API."""

    def __init__(self, instance_url: str, access_token: str, default_caption: str = "", cc_license: str = ""):
        """
        Initialize the Pixelfed client.

        Args:
            instance_url: Base URL of the Pixelfed instance (e.g., https://pixelfed.social)
            access_token: OAuth access token for authentication
            default_caption: Default text/tags to add to every post
            cc_license: Creative Commons license to add to every post
        """
        self.instance_url = instance_url.rstrip('/')
        self.access_token = access_token
        self.default_caption = default_caption
        self.cc_license = cc_license
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        })

    def check_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Check if connection to Pixelfed instance is available.

        Returns:
            Tuple of (is_connected, error_message)
        """
        try:
            response = self.session.get(
                f'{self.instance_url}/api/v1/instance',
                timeout=10
            )
            response.raise_for_status()
            logger.debug("Connection check successful")
            return True, None
        except ConnectionError as e:
            error_msg = f"Connection error: {str(e)}"
            logger.warning(error_msg)
            return False, error_msg
        except Timeout as e:
            error_msg = f"Connection timeout: {str(e)}"
            logger.warning(error_msg)
            return False, error_msg
        except RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def upload_media(self, file_path: Path) -> Tuple[Optional[dict], Optional[str]]:
        """
        Upload a media file to Pixelfed.

        Args:
            file_path: Path to the image file to upload

        Returns:
            Tuple of (media object, error message). Media is None if upload failed.
        """
        try:
            if not file_path.exists():
                error_msg = f"File not found: {file_path}"
                logger.error(error_msg)
                return None, error_msg

            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f, self._get_mime_type(file_path))}
                response = self.session.post(
                    f'{self.instance_url}/api/v1/media',
                    files=files,
                    timeout=60
                )
                response.raise_for_status()
                media = response.json()
                logger.info(f"Uploaded media: {file_path.name} (ID: {media.get('id')})")
                return media, None
        except ConnectionError as e:
            error_msg = f"Connection error while uploading {file_path.name}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except Timeout as e:
            error_msg = f"Timeout while uploading {file_path.name}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except RequestException as e:
            error_msg = f"Request failed for {file_path.name}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except FileNotFoundError as e:
            error_msg = f"File not found: {file_path}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error uploading {file_path.name}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

    def create_post(self, media_ids: list[str], caption: str = "") -> Tuple[Optional[dict], Optional[str]]:
        """
        Create a post with uploaded media.

        Args:
            media_ids: List of media IDs to attach to the post
            caption: Optional caption for the post

        Returns:
            Tuple of (post object, error message). Post is None if creation failed.
        """
        try:
            data = {
                'status': caption,
                'media_ids[]': media_ids
            }
            response = self.session.post(
                f'{self.instance_url}/api/v1/statuses',
                data=data,
                timeout=30
            )
            response.raise_for_status()
            post = response.json()
            logger.info(f"Created post: {post.get('url')}")
            return post, None
        except ConnectionError as e:
            error_msg = f"Connection error while creating post: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except Timeout as e:
            error_msg = f"Timeout while creating post: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except RequestException as e:
            error_msg = f"Request failed while creating post: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error creating post: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

    def upload_and_post(self, file_path: Path, caption: str = "") -> Tuple[bool, Optional[str]]:
        """
        Upload a file and immediately create a post with it.

        Args:
            file_path: Path to the image file to upload
            caption: Optional caption for the post (will be combined with default_caption)

        Returns:
            Tuple of (success, error_message)
        """
        media, error = self.upload_media(file_path)
        if not media:
            return False, error

        media_id = media.get('id')
        if not media_id:
            error_msg = f"No media ID returned for {file_path}"
            logger.error(error_msg)
            return False, error_msg

        # Combine the default caption with any provided caption and license
        caption_parts = []
        if caption:
            caption_parts.append(caption)
        if self.default_caption:
            caption_parts.append(self.default_caption)
        if self.cc_license:
            caption_parts.append(self.cc_license)

        full_caption = " ".join(caption_parts)

        post, error = self.create_post([media_id], full_caption)
        if not post:
            return False, error

        return True, None

    @staticmethod
    def _get_mime_type(file_path: Path) -> str:
        """Get MIME type based on file extension."""
        ext = file_path.suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        return mime_types.get(ext, 'application/octet-stream')
