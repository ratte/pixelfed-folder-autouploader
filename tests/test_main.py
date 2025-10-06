"""Tests for the main application logic."""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from watchdog.events import FileCreatedEvent
from pixelfed_uploader.main import ImageUploadHandler, scan_existing_files


@pytest.fixture
def mock_queue():
    """Create a mock upload queue."""
    queue = Mock()
    queue.add = Mock()
    return queue


@pytest.fixture
def processed_files():
    """Create an empty set for tracking processed files."""
    return set()


@pytest.fixture
def handler(mock_queue, processed_files):
    """Create an ImageUploadHandler instance."""
    return ImageUploadHandler(mock_queue, processed_files)


@pytest.fixture
def temp_watch_folder(tmp_path):
    """Create a temporary watch folder with some test images."""
    watch_folder = tmp_path / "watch"
    watch_folder.mkdir()

    # Create some test image files
    (watch_folder / "image1.jpg").write_bytes(b"fake image 1")
    (watch_folder / "image2.png").write_bytes(b"fake image 2")
    (watch_folder / "document.txt").write_bytes(b"not an image")

    return watch_folder


class TestImageUploadHandler:
    """Test cases for ImageUploadHandler."""

    def test_image_extensions(self):
        """Test that correct image extensions are defined."""
        expected_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        assert ImageUploadHandler.IMAGE_EXTENSIONS == expected_extensions

    def test_initialization(self, handler, mock_queue, processed_files):
        """Test handler initialization."""
        assert handler.upload_queue == mock_queue
        assert handler.processed_files is processed_files

    def test_on_created_ignores_directories(self, handler, tmp_path):
        """Test that directory creation events are ignored."""
        # Create a directory event
        event = FileCreatedEvent(str(tmp_path / "newdir"))
        event.is_directory = True

        handler.on_created(event)

        # Should not add to queue
        handler.upload_queue.add.assert_not_called()

    def test_on_created_ignores_non_images(self, handler, tmp_path):
        """Test that non-image files are ignored."""
        # Create a text file
        text_file = tmp_path / "document.txt"
        text_file.write_text("not an image")

        event = FileCreatedEvent(str(text_file))
        event.is_directory = False

        handler.on_created(event)

        # Should not add to queue
        handler.upload_queue.add.assert_not_called()

    def test_on_created_ignores_already_processed(self, handler, tmp_path, processed_files):
        """Test that already processed files are ignored."""
        # Create an image file
        image_file = tmp_path / "image.jpg"
        image_file.write_bytes(b"fake image")

        # Mark as already processed
        processed_files.add(str(image_file))

        event = FileCreatedEvent(str(image_file))
        event.is_directory = False

        handler.on_created(event)

        # Should not add to queue
        handler.upload_queue.add.assert_not_called()

    @patch('pixelfed_uploader.main.time.sleep')
    def test_on_created_uploads_new_image(self, mock_sleep, handler, tmp_path, processed_files):
        """Test that new image files are added to queue."""
        # Create an image file
        image_file = tmp_path / "new_image.jpg"
        image_file.write_bytes(b"fake image")

        event = FileCreatedEvent(str(image_file))
        event.is_directory = False

        handler.on_created(event)

        # Should sleep to ensure file is written
        mock_sleep.assert_called_once_with(1)

        # Should add to queue
        handler.upload_queue.add.assert_called_once_with(str(image_file))

        # Should mark as processed
        assert str(image_file) in processed_files

    @patch('pixelfed_uploader.main.time.sleep')
    def test_on_created_adds_to_queue_always(self, mock_sleep, handler, tmp_path, processed_files):
        """Test that files are always added to queue."""
        # Create an image file
        image_file = tmp_path / "image.jpg"
        image_file.write_bytes(b"fake image")

        event = FileCreatedEvent(str(image_file))
        event.is_directory = False

        handler.on_created(event)

        # Should add to queue
        handler.upload_queue.add.assert_called_once_with(str(image_file))

        # Should mark as processed (so it won't be re-queued)
        assert str(image_file) in processed_files

    @patch('pixelfed_uploader.main.time.sleep')
    def test_on_created_supports_all_image_formats(self, mock_sleep, handler, tmp_path):
        """Test that all supported image formats are handled."""
        formats = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

        for ext in formats:
            image_file = tmp_path / f"image{ext}"
            image_file.write_bytes(b"fake image")

            event = FileCreatedEvent(str(image_file))
            event.is_directory = False

            handler.on_created(event)

        # Should have added all formats to queue
        assert handler.upload_queue.add.call_count == len(formats)

    @patch('pixelfed_uploader.main.time.sleep')
    def test_on_created_case_insensitive_extensions(self, mock_sleep, handler, tmp_path):
        """Test that file extension checking is case insensitive."""
        # Create an image with uppercase extension
        image_file = tmp_path / "IMAGE.JPG"
        image_file.write_bytes(b"fake image")

        event = FileCreatedEvent(str(image_file))
        event.is_directory = False

        handler.on_created(event)

        # Should still add to queue
        handler.upload_queue.add.assert_called_once()


class TestScanExistingFiles:
    """Test cases for scan_existing_files function."""

    def test_scan_existing_files_finds_images(self, temp_watch_folder):
        """Test that existing images are found."""
        existing = scan_existing_files(temp_watch_folder)

        assert len(existing) == 2
        assert str(temp_watch_folder / "image1.jpg") in existing
        assert str(temp_watch_folder / "image2.png") in existing

    def test_scan_existing_files_ignores_non_images(self, temp_watch_folder):
        """Test that non-image files are ignored."""
        existing = scan_existing_files(temp_watch_folder)

        assert str(temp_watch_folder / "document.txt") not in existing

    def test_scan_existing_files_empty_folder(self, tmp_path):
        """Test scanning an empty folder."""
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()

        existing = scan_existing_files(empty_folder)

        assert len(existing) == 0

    def test_scan_existing_files_mixed_extensions(self, tmp_path):
        """Test scanning folder with various file types."""
        watch_folder = tmp_path / "watch"
        watch_folder.mkdir()

        # Create various file types
        (watch_folder / "photo.jpg").write_bytes(b"image")
        (watch_folder / "graphic.png").write_bytes(b"image")
        (watch_folder / "animation.gif").write_bytes(b"image")
        (watch_folder / "modern.webp").write_bytes(b"image")
        (watch_folder / "readme.md").write_bytes(b"text")
        (watch_folder / "script.py").write_bytes(b"code")

        existing = scan_existing_files(watch_folder)

        assert len(existing) == 4  # Only image files
        assert str(watch_folder / "readme.md") not in existing
        assert str(watch_folder / "script.py") not in existing


class TestMainFunction:
    """Test cases for main function."""

    @patch.dict('os.environ', {
        'PIXELFED_INSTANCE_URL': 'https://pixelfed.test',
        'PIXELFED_ACCESS_TOKEN': 'test_token',
        'WATCH_FOLDER': './watch'
    })
    @patch('pixelfed_uploader.main.time.sleep')
    @patch('pixelfed_uploader.main.Observer')
    @patch('pixelfed_uploader.main.PixelfedClient')
    @patch('pixelfed_uploader.main.UploadQueue')
    @patch('pixelfed_uploader.main.scan_existing_files')
    def test_main_starts_observer(self, mock_scan, mock_queue_class, mock_client_class, mock_observer_class, mock_sleep):
        """Test that main function starts the observer."""
        from pixelfed_uploader.main import main

        # Setup mocks
        mock_scan.return_value = set()
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer
        mock_queue = MagicMock()
        mock_queue.get_stats.return_value = {'total': 0, 'never_attempted': 0, 'retrying': 0}
        mock_queue.size.return_value = 0
        mock_queue_class.return_value = mock_queue

        # Setup mock client
        mock_client = MagicMock()
        mock_client.check_connection.return_value = (True, None)
        mock_client_class.return_value = mock_client

        # Simulate KeyboardInterrupt during the sleep loop
        mock_sleep.side_effect = KeyboardInterrupt()

        # Run main
        main()

        # Verify observer was started
        mock_observer.start.assert_called_once()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()

    @patch('pixelfed_uploader.main.load_dotenv')
    @patch.dict('os.environ', {}, clear=True)
    def test_main_exits_without_config(self, mock_load_dotenv):
        """Test that main exits when configuration is missing."""
        from pixelfed_uploader.main import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
