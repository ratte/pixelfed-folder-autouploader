"""Tests for the Pixelfed API client."""

import pytest
import responses
from pathlib import Path
from pixelfed_uploader.pixelfed_client import PixelfedClient


@pytest.fixture
def client():
    """Create a test Pixelfed client."""
    return PixelfedClient(
        instance_url="https://pixelfed.test",
        access_token="test_token_123",
        default_caption=""
    )


@pytest.fixture
def temp_image(tmp_path):
    """Create a temporary test image file."""
    image_path = tmp_path / "test_image.jpg"
    image_path.write_bytes(b"fake image data")
    return image_path


class TestPixelfedClient:
    """Test cases for PixelfedClient."""

    def test_initialization(self, client):
        """Test client initialization."""
        assert client.instance_url == "https://pixelfed.test"
        assert client.access_token == "test_token_123"
        assert client.session.headers["Authorization"] == "Bearer test_token_123"
        assert client.session.headers["Accept"] == "application/json"

    def test_initialization_strips_trailing_slash(self):
        """Test that trailing slash is removed from instance URL."""
        client = PixelfedClient(
            instance_url="https://pixelfed.test/",
            access_token="token",
            default_caption=""
        )
        assert client.instance_url == "https://pixelfed.test"

    @responses.activate
    def test_upload_media_success(self, client, temp_image):
        """Test successful media upload."""
        # Mock the API response
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"id": "media_123", "url": "https://pixelfed.test/media/123.jpg"},
            status=200
        )

        media, error = client.upload_media(temp_image)

        assert media is not None
        assert error is None
        assert media["id"] == "media_123"
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == "https://pixelfed.test/api/v1/media"

    @responses.activate
    def test_upload_media_failure(self, client, temp_image):
        """Test failed media upload."""
        # Mock a failed API response
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"error": "Upload failed"},
            status=500
        )

        media, error = client.upload_media(temp_image)

        assert media is None
        assert error is not None

    def test_upload_media_file_not_found(self, client):
        """Test upload with non-existent file."""
        fake_path = Path("/non/existent/file.jpg")
        media, error = client.upload_media(fake_path)
        assert media is None
        assert error is not None

    @responses.activate
    def test_create_post_success(self, client):
        """Test successful post creation."""
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/statuses",
            json={
                "id": "post_123",
                "url": "https://pixelfed.test/post/123"
            },
            status=200
        )

        post, error = client.create_post(["media_123"], "Test caption")

        assert post is not None
        assert error is None
        assert post["id"] == "post_123"
        assert len(responses.calls) == 1

    @responses.activate
    def test_create_post_failure(self, client):
        """Test failed post creation."""
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/statuses",
            json={"error": "Failed to create post"},
            status=400
        )

        post, error = client.create_post(["media_123"], "Test caption")

        assert post is None
        assert error is not None

    @responses.activate
    def test_upload_and_post_success(self, client, temp_image):
        """Test successful upload and post workflow."""
        # Mock media upload
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"id": "media_123"},
            status=200
        )

        # Mock post creation
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/statuses",
            json={"id": "post_123", "url": "https://pixelfed.test/post/123"},
            status=200
        )

        success, error = client.upload_and_post(temp_image, "Test caption")

        assert success is True
        assert error is None
        assert len(responses.calls) == 2

    @responses.activate
    def test_upload_and_post_upload_fails(self, client, temp_image):
        """Test upload_and_post when upload fails."""
        # Mock failed media upload
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"error": "Upload failed"},
            status=500
        )

        success, error = client.upload_and_post(temp_image, "Test caption")

        assert success is False
        assert error is not None
        assert len(responses.calls) == 1  # Only upload attempted

    @responses.activate
    def test_upload_and_post_missing_media_id(self, client, temp_image):
        """Test upload_and_post when media response has no ID."""
        # Mock media upload without ID
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"url": "https://pixelfed.test/media/123.jpg"},
            status=200
        )

        success, error = client.upload_and_post(temp_image, "Test caption")

        assert success is False
        assert error is not None

    @responses.activate
    def test_upload_and_post_post_creation_fails(self, client, temp_image):
        """Test upload_and_post when post creation fails."""
        # Mock successful media upload
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"id": "media_123"},
            status=200
        )

        # Mock failed post creation
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/statuses",
            json={"error": "Failed"},
            status=400
        )

        success, error = client.upload_and_post(temp_image, "Test caption")

        assert success is False
        assert error is not None
        assert len(responses.calls) == 2

    def test_get_mime_type(self):
        """Test MIME type detection."""
        assert PixelfedClient._get_mime_type(Path("test.jpg")) == "image/jpeg"
        assert PixelfedClient._get_mime_type(Path("test.jpeg")) == "image/jpeg"
        assert PixelfedClient._get_mime_type(Path("test.png")) == "image/png"
        assert PixelfedClient._get_mime_type(Path("test.gif")) == "image/gif"
        assert PixelfedClient._get_mime_type(Path("test.webp")) == "image/webp"
        assert PixelfedClient._get_mime_type(Path("test.unknown")) == "application/octet-stream"

    def test_get_mime_type_case_insensitive(self):
        """Test that MIME type detection is case insensitive."""
        assert PixelfedClient._get_mime_type(Path("test.JPG")) == "image/jpeg"
        assert PixelfedClient._get_mime_type(Path("test.PNG")) == "image/png"
