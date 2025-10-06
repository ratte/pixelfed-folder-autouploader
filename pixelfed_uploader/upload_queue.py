"""Upload queue for managing pending uploads with retry logic."""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class UploadQueue:
    """Manages a persistent queue of files to upload."""

    def __init__(self, queue_file: Path):
        """
        Initialize the upload queue.

        Args:
            queue_file: Path to the JSON file storing the queue
        """
        self.queue_file = queue_file
        self.queue: List[Dict] = []
        self._load_queue()

    def _load_queue(self):
        """Load the queue from disk."""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    self.queue = json.load(f)
                logger.info(f"Loaded {len(self.queue)} items from queue")
            except Exception as e:
                logger.error(f"Failed to load queue: {e}")
                self.queue = []
        else:
            self.queue = []

    def _save_queue(self):
        """Save the queue to disk."""
        try:
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.queue_file, 'w') as f:
                json.dump(self.queue, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save queue: {e}")

    def add(self, file_path: str, caption: str = ""):
        """
        Add a file to the upload queue.

        Args:
            file_path: Path to the file to upload
            caption: Optional caption for the post
        """
        item = {
            'file_path': file_path,
            'caption': caption,
            'added_at': datetime.now().isoformat(),
            'retry_count': 0,
            'last_attempt': None,
            'error': None
        }
        self.queue.append(item)
        self._save_queue()
        logger.info(f"Added to queue: {file_path}")

    def get_next(self) -> Optional[Dict]:
        """
        Get the next item to upload with exponential backoff.

        Returns:
            Next queue item, or None if queue is empty or all items are in backoff
        """
        if not self.queue:
            return None

        now = time.time()

        for item in self.queue:
            # If never attempted, return it
            if item['last_attempt'] is None:
                return item

            # Calculate backoff delay (exponential: 10s, 30s, 60s, 120s, 300s, ...)
            retry_count = item['retry_count']
            if retry_count == 0:
                backoff_delay = 0
            elif retry_count == 1:
                backoff_delay = 10
            elif retry_count == 2:
                backoff_delay = 30
            elif retry_count == 3:
                backoff_delay = 60
            elif retry_count == 4:
                backoff_delay = 120
            else:
                backoff_delay = 300  # Max 5 minutes

            # Check if enough time has passed since last attempt
            last_attempt_time = datetime.fromisoformat(item['last_attempt']).timestamp()
            if now - last_attempt_time >= backoff_delay:
                return item

        return None

    def mark_success(self, item: Dict):
        """
        Mark an item as successfully uploaded and remove it from queue.

        Args:
            item: The queue item that was successfully uploaded
        """
        try:
            self.queue.remove(item)
            self._save_queue()
            logger.info(f"Removed from queue (success): {item['file_path']}")
        except ValueError:
            logger.warning(f"Item not found in queue: {item['file_path']}")

    def mark_failure(self, item: Dict, error: str):
        """
        Mark an item as failed and update retry count.

        Args:
            item: The queue item that failed
            error: Error message
        """
        try:
            idx = self.queue.index(item)
            self.queue[idx]['retry_count'] += 1
            self.queue[idx]['last_attempt'] = datetime.now().isoformat()
            self.queue[idx]['error'] = error
            self._save_queue()
            logger.warning(
                f"Upload failed (attempt {self.queue[idx]['retry_count']}): {item['file_path']} - {error}"
            )
        except ValueError:
            logger.warning(f"Item not found in queue: {item['file_path']}")

    def size(self) -> int:
        """
        Get the number of items in the queue.

        Returns:
            Number of items in queue
        """
        return len(self.queue)

    def get_stats(self) -> Dict:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        if not self.queue:
            return {
                'total': 0,
                'never_attempted': 0,
                'retrying': 0,
                'max_retry_count': 0
            }

        never_attempted = sum(1 for item in self.queue if item['last_attempt'] is None)
        retrying = sum(1 for item in self.queue if item['last_attempt'] is not None)
        max_retry_count = max((item['retry_count'] for item in self.queue), default=0)

        return {
            'total': len(self.queue),
            'never_attempted': never_attempted,
            'retrying': retrying,
            'max_retry_count': max_retry_count
        }
