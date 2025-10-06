"""Shared pytest fixtures and configuration."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_image_data():
    """Provide sample image data for testing."""
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"


@pytest.fixture
def create_test_image(tmp_path):
    """Factory fixture to create test image files."""
    def _create_image(filename, content=b"fake image data"):
        """Create a test image file.

        Args:
            filename: Name of the file to create
            content: Binary content for the file

        Returns:
            Path to the created file
        """
        image_path = tmp_path / filename
        image_path.write_bytes(content)
        return image_path

    return _create_image


@pytest.fixture
def mock_api_responses():
    """Provide common API response data for mocking."""
    return {
        'media_success': {
            'id': 'media_12345',
            'url': 'https://pixelfed.test/media/12345.jpg',
            'type': 'image'
        },
        'post_success': {
            'id': 'post_67890',
            'url': 'https://pixelfed.test/post/67890',
            'created_at': '2024-01-01T12:00:00Z'
        },
        'error': {
            'error': 'An error occurred'
        }
    }
