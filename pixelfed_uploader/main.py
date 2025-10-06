"""Main application for monitoring folders and uploading to Pixelfed."""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from dotenv import load_dotenv

from .pixelfed_client import PixelfedClient
from .upload_queue import UploadQueue


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ImageUploadHandler(FileSystemEventHandler):
    """Handler for new image files in the watched folder."""

    # Supported image extensions
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

    def __init__(self, upload_queue: UploadQueue, processed_files: Set[str]):
        """
        Initialize the handler.

        Args:
            upload_queue: Queue for managing uploads
            processed_files: Set of already processed file paths
        """
        self.upload_queue = upload_queue
        self.processed_files = processed_files
        super().__init__()

    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if it's an image file
        if file_path.suffix.lower() not in self.IMAGE_EXTENSIONS:
            return

        # Check if already processed
        if str(file_path) in self.processed_files:
            return

        # Wait a bit to ensure file is fully written
        time.sleep(1)

        # Add to queue
        logger.info(f"New image detected: {file_path}")
        self.upload_queue.add(str(file_path))
        self.processed_files.add(str(file_path))


def scan_existing_files(watch_folder: Path) -> Set[str]:
    """
    Scan for existing image files in the folder.

    Args:
        watch_folder: Path to the folder to scan

    Returns:
        Set of existing image file paths
    """
    existing_files = set()
    for file_path in watch_folder.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in ImageUploadHandler.IMAGE_EXTENSIONS:
            existing_files.add(str(file_path))
    logger.info(f"Found {len(existing_files)} existing image files (will be skipped)")
    return existing_files


def process_upload_queue(upload_queue: UploadQueue, client: PixelfedClient) -> None:
    """
    Process pending uploads from the queue.

    Args:
        upload_queue: The upload queue
        client: Pixelfed client for uploading
    """
    # Check if there are items in the queue
    if upload_queue.size() == 0:
        return

    # Check connection first
    is_connected, error = client.check_connection()
    if not is_connected:
        logger.debug(f"No connection to Pixelfed, skipping queue processing: {error}")
        return

    # Process next item
    item = upload_queue.get_next()
    if not item:
        return

    file_path = Path(item['file_path'])
    caption = item.get('caption', '')

    logger.info(f"Processing upload from queue: {file_path.name} (attempt {item['retry_count'] + 1})")

    success, error = client.upload_and_post(file_path, caption)

    if success:
        upload_queue.mark_success(item)
        logger.info(f"Successfully uploaded from queue: {file_path.name}")
    else:
        upload_queue.mark_failure(item, error or "Unknown error")

        # Log queue stats periodically
        stats = upload_queue.get_stats()
        logger.info(
            f"Queue status: {stats['total']} items "
            f"({stats['never_attempted']} pending, {stats['retrying']} retrying)"
        )


def main():
    """Main entry point for the application."""
    # Load environment variables
    load_dotenv()

    # Get configuration from environment
    instance_url = os.getenv('PIXELFED_INSTANCE_URL')
    access_token = os.getenv('PIXELFED_ACCESS_TOKEN')
    watch_folder = os.getenv('WATCH_FOLDER', './watch')
    default_post_text = os.getenv('DEFAULT_POST_TEXT', '')
    cc_license = os.getenv('CC_LICENSE', '')

    # Validate configuration
    if not instance_url or not access_token:
        logger.error("Missing required configuration. Please set PIXELFED_INSTANCE_URL and PIXELFED_ACCESS_TOKEN in .env file")
        sys.exit(1)

    # Create watch folder if it doesn't exist
    watch_path = Path(watch_folder).resolve()
    watch_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting PixelFed Folder Uploader")
    logger.info(f"Instance: {instance_url}")
    logger.info(f"Watching folder: {watch_path}")

    # Initialize Pixelfed client
    client = PixelfedClient(instance_url, access_token, default_post_text, cc_license)

    # Initialize upload queue
    queue_file = watch_path / '.upload_queue.json'
    upload_queue = UploadQueue(queue_file)

    # Scan for existing files (to avoid re-uploading)
    processed_files = scan_existing_files(watch_path)

    # Set up file system observer
    event_handler = ImageUploadHandler(upload_queue, processed_files)
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=False)

    # Start watching
    observer.start()
    logger.info("Monitoring started. Press Ctrl+C to stop.")

    # Log initial queue status
    stats = upload_queue.get_stats()
    if stats['total'] > 0:
        logger.info(
            f"Queue has {stats['total']} pending items "
            f"({stats['never_attempted']} new, {stats['retrying']} retrying)"
        )

    try:
        while True:
            # Process upload queue
            process_upload_queue(upload_queue, client)

            # Sleep for a bit before checking again
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Stopping...")
        observer.stop()

    observer.join()

    # Final queue status
    stats = upload_queue.get_stats()
    if stats['total'] > 0:
        logger.info(f"Stopped with {stats['total']} items still in queue")
    else:
        logger.info("Stopped.")


if __name__ == '__main__':
    main()
