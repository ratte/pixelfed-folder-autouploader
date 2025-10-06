"""Integration tests for the complete upload workflow."""

import pytest
import time
import responses
from pathlib import Path
from unittest.mock import patch, Mock
from pixelfed_uploader.pixelfed_client import PixelfedClient
from pixelfed_uploader.main import ImageUploadHandler, scan_existing_files


@pytest.fixture
def integration_client():
    """Create a real Pixelfed client for integration testing."""
    return PixelfedClient(
        instance_url="https://pixelfed.test",
        access_token="integration_test_token",
        default_caption=""
    )


@pytest.fixture
def test_watch_folder(tmp_path):
    """Create a temporary watch folder for integration tests."""
    watch_folder = tmp_path / "watch"
    watch_folder.mkdir()
    return watch_folder


class TestEndToEndWorkflow:
    """End-to-end integration tests."""

    @responses.activate
    @patch('pixelfed_uploader.main.time.sleep')
    def test_complete_upload_workflow(self, mock_sleep, integration_client, test_watch_folder):
        """Test the complete workflow from file creation to queue to upload."""
        # Setup API mocks
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"id": "media_456", "url": "https://pixelfed.test/media/456.jpg"},
            status=200
        )
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/statuses",
            json={"id": "post_789", "url": "https://pixelfed.test/post/789"},
            status=200
        )

        # Create a new image file
        new_image = test_watch_folder / "vacation.jpg"
        new_image.write_bytes(b"beautiful vacation photo")

        # Setup mock queue
        mock_queue = Mock()
        processed_files = set()
        handler = ImageUploadHandler(mock_queue, processed_files)

        # Simulate file creation event
        from watchdog.events import FileCreatedEvent
        event = FileCreatedEvent(str(new_image))
        event.is_directory = False

        # Process the event (adds to queue)
        handler.on_created(event)

        # Verify file was added to queue
        mock_queue.add.assert_called_once_with(str(new_image))

        # Verify file was marked as processed
        assert str(new_image) in processed_files

        # Now test actual upload from queue
        success, error = integration_client.upload_and_post(new_image)
        assert success is True
        assert error is None
        assert len(responses.calls) == 2

    @responses.activate
    def test_multiple_files_upload(self, integration_client, test_watch_folder):
        """Test uploading multiple files in sequence."""
        # Create multiple images
        images = []
        for i in range(3):
            img = test_watch_folder / f"photo_{i}.jpg"
            img.write_bytes(f"photo {i}".encode())
            images.append(img)

        # Setup API mocks for all uploads
        for i in range(3):
            responses.add(
                responses.POST,
                "https://pixelfed.test/api/v1/media",
                json={"id": f"media_{i}"},
                status=200
            )
            responses.add(
                responses.POST,
                "https://pixelfed.test/api/v1/statuses",
                json={"id": f"post_{i}", "url": f"https://pixelfed.test/post/{i}"},
                status=200
            )

        # Upload all images
        results = []
        for img in images:
            success, error = integration_client.upload_and_post(img)
            results.append(success)

        # Verify all succeeded
        assert all(results)
        assert len(responses.calls) == 6  # 3 uploads + 3 posts

    @responses.activate
    @patch('pixelfed_uploader.main.time.sleep')
    def test_mixed_file_types(self, mock_sleep, integration_client, test_watch_folder):
        """Test that only image files are added to queue."""
        # Create various file types
        image_file = test_watch_folder / "photo.jpg"
        image_file.write_bytes(b"image data")

        text_file = test_watch_folder / "notes.txt"
        text_file.write_bytes(b"text data")

        # Setup handler with mock queue
        mock_queue = Mock()
        processed_files = set()
        handler = ImageUploadHandler(mock_queue, processed_files)

        # Simulate events
        from watchdog.events import FileCreatedEvent

        img_event = FileCreatedEvent(str(image_file))
        img_event.is_directory = False
        handler.on_created(img_event)

        txt_event = FileCreatedEvent(str(text_file))
        txt_event.is_directory = False
        handler.on_created(txt_event)

        # Only image should be added to queue
        mock_queue.add.assert_called_once_with(str(image_file))
        assert str(image_file) in processed_files
        assert str(text_file) not in processed_files

    def test_scan_and_ignore_existing(self, test_watch_folder):
        """Test that existing files are scanned and ignored."""
        # Create some existing images
        existing1 = test_watch_folder / "old_photo1.jpg"
        existing1.write_bytes(b"old photo 1")

        existing2 = test_watch_folder / "old_photo2.png"
        existing2.write_bytes(b"old photo 2")

        # Scan the folder
        existing_files = scan_existing_files(test_watch_folder)

        # Verify existing files were found
        assert len(existing_files) == 2
        assert str(existing1) in existing_files
        assert str(existing2) in existing_files

    @responses.activate
    def test_retry_on_failure(self, integration_client, test_watch_folder):
        """Test that failed uploads return error and can be retried."""
        # First attempt fails, second succeeds
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"error": "Server error"},
            status=500
        )
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/media",
            json={"id": "media_123"},
            status=200
        )
        responses.add(
            responses.POST,
            "https://pixelfed.test/api/v1/statuses",
            json={"id": "post_123", "url": "https://pixelfed.test/post/123"},
            status=200
        )

        # Create image
        image = test_watch_folder / "retry_photo.jpg"
        image.write_bytes(b"photo data")

        # First attempt (should fail)
        success, error = integration_client.upload_and_post(image)
        assert success is False
        assert error is not None

        # Second attempt (should succeed)
        success, error = integration_client.upload_and_post(image)
        assert success is True
        assert error is None

    @responses.activate
    def test_different_image_formats(self, integration_client, test_watch_folder):
        """Test uploading different image formats."""
        formats = {
            'photo.jpg': 'image/jpeg',
            'graphic.png': 'image/png',
            'animation.gif': 'image/gif',
            'modern.webp': 'image/webp',
        }

        for filename, expected_mime in formats.items():
            # Setup mock
            responses.add(
                responses.POST,
                "https://pixelfed.test/api/v1/media",
                json={"id": f"media_{filename}"},
                status=200
            )
            responses.add(
                responses.POST,
                "https://pixelfed.test/api/v1/statuses",
                json={"id": f"post_{filename}", "url": f"https://pixelfed.test/post/{filename}"},
                status=200
            )

            # Create and upload
            image = test_watch_folder / filename
            image.write_bytes(b"fake image data")

            success, error = integration_client.upload_and_post(image)
            assert success is True
            assert error is None

        # All formats should have been uploaded
        assert len(responses.calls) == len(formats) * 2
