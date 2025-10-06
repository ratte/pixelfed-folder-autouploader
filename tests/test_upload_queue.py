"""Tests for the upload queue."""

import pytest
import json
import time
from pathlib import Path
from datetime import datetime
from pixelfed_uploader.upload_queue import UploadQueue


@pytest.fixture
def queue_file(tmp_path):
    """Create a temporary queue file."""
    return tmp_path / "test_queue.json"


@pytest.fixture
def queue(queue_file):
    """Create a fresh upload queue."""
    return UploadQueue(queue_file)


class TestUploadQueueInitialization:
    """Test queue initialization and persistence."""

    def test_initialization_creates_empty_queue(self, queue):
        """Test that a new queue starts empty."""
        assert queue.size() == 0
        assert queue.queue == []

    def test_initialization_loads_existing_queue(self, queue_file):
        """Test that existing queue data is loaded."""
        # Create a queue file with some data
        existing_data = [
            {
                'file_path': '/path/to/file1.jpg',
                'caption': '',
                'added_at': '2025-01-01T12:00:00',
                'retry_count': 0,
                'last_attempt': None,
                'error': None
            },
            {
                'file_path': '/path/to/file2.jpg',
                'caption': 'Test',
                'added_at': '2025-01-01T12:05:00',
                'retry_count': 2,
                'last_attempt': '2025-01-01T12:10:00',
                'error': 'Connection error'
            }
        ]

        with open(queue_file, 'w') as f:
            json.dump(existing_data, f)

        # Load the queue
        queue = UploadQueue(queue_file)

        assert queue.size() == 2
        assert queue.queue[0]['file_path'] == '/path/to/file1.jpg'
        assert queue.queue[1]['retry_count'] == 2

    def test_initialization_handles_corrupted_file(self, queue_file):
        """Test that corrupted queue files are handled gracefully."""
        # Write invalid JSON
        with open(queue_file, 'w') as f:
            f.write("invalid json {{{")

        # Should create empty queue instead of crashing
        queue = UploadQueue(queue_file)
        assert queue.size() == 0

    def test_initialization_handles_missing_file(self, queue_file):
        """Test that missing queue files create empty queue."""
        queue = UploadQueue(queue_file)
        assert queue.size() == 0
        assert not queue_file.exists()


class TestQueueOperations:
    """Test basic queue operations."""

    def test_add_item(self, queue, queue_file):
        """Test adding an item to the queue."""
        queue.add('/path/to/image.jpg', 'Test caption')

        assert queue.size() == 1
        item = queue.queue[0]
        assert item['file_path'] == '/path/to/image.jpg'
        assert item['caption'] == 'Test caption'
        assert item['retry_count'] == 0
        assert item['last_attempt'] is None
        assert item['error'] is None
        assert 'added_at' in item

        # Verify it was persisted
        assert queue_file.exists()

    def test_add_multiple_items(self, queue):
        """Test adding multiple items."""
        queue.add('/path/1.jpg')
        queue.add('/path/2.jpg', 'Caption 2')
        queue.add('/path/3.jpg')

        assert queue.size() == 3
        assert queue.queue[1]['caption'] == 'Caption 2'

    def test_add_item_without_caption(self, queue):
        """Test adding item without caption."""
        queue.add('/path/to/image.jpg')

        item = queue.queue[0]
        assert item['caption'] == ''


class TestGetNext:
    """Test getting next item from queue."""

    def test_get_next_from_empty_queue(self, queue):
        """Test getting next item from empty queue."""
        assert queue.get_next() is None

    def test_get_next_never_attempted(self, queue):
        """Test getting item that has never been attempted."""
        queue.add('/path/to/image.jpg')

        item = queue.get_next()

        assert item is not None
        assert item['file_path'] == '/path/to/image.jpg'
        assert item['last_attempt'] is None

    def test_get_next_returns_first_never_attempted(self, queue):
        """Test that get_next returns first item that hasn't been attempted."""
        # Add items
        queue.add('/path/1.jpg')
        queue.add('/path/2.jpg')

        # Get and mark first as failed
        item1 = queue.get_next()
        queue.mark_failure(item1, "Test error")

        # Next call should return second item
        item2 = queue.get_next()
        assert item2['file_path'] == '/path/2.jpg'

    def test_get_next_respects_backoff_first_retry(self, queue):
        """Test that backoff delay is respected for first retry (10s)."""
        queue.add('/path/image.jpg')

        # Mark as failed once
        item = queue.get_next()
        queue.mark_failure(item, "Error")

        # Immediately try to get next - should return None (in backoff)
        assert queue.get_next() is None

        # Simulate waiting 10 seconds
        queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 11
        ).isoformat()

        # Should now be available
        assert queue.get_next() is not None

    def test_get_next_respects_backoff_second_retry(self, queue):
        """Test that backoff delay is respected for second retry (30s)."""
        queue.add('/path/image.jpg')

        # Mark as failed twice
        item = queue.get_next()
        queue.mark_failure(item, "Error 1")
        queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 11
        ).isoformat()

        item = queue.get_next()
        queue.mark_failure(item, "Error 2")

        # Should be in backoff (30s needed)
        assert queue.get_next() is None

        # After 20 seconds - still in backoff
        queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 20
        ).isoformat()
        assert queue.get_next() is None

        # After 31 seconds - available
        queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 31
        ).isoformat()
        assert queue.get_next() is not None

    def test_get_next_exponential_backoff_progression(self, queue):
        """Test the full exponential backoff progression."""
        queue.add('/path/image.jpg')

        # Expected backoff delays for retries 1-5
        backoff_delays = [10, 30, 60, 120, 300]

        for i, delay in enumerate(backoff_delays):
            # Set last attempt to past
            if i > 0:
                queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
                    time.time() - (delay + 1)
                ).isoformat()

            item = queue.get_next()
            assert item is not None, f"Retry {i+1} should be available"
            queue.mark_failure(item, f"Error {i+1}")

    def test_get_next_max_backoff(self, queue):
        """Test that backoff caps at 300 seconds."""
        queue.add('/path/image.jpg')

        # Fail it 10 times
        for i in range(10):
            queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
                time.time() - 301
            ).isoformat()
            item = queue.get_next()
            queue.mark_failure(item, f"Error {i}")

        # Should still use 300s max backoff
        assert queue.get_next() is None

        queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 301
        ).isoformat()
        assert queue.get_next() is not None


class TestMarkSuccess:
    """Test marking items as successful."""

    def test_mark_success_removes_from_queue(self, queue):
        """Test that successful items are removed."""
        queue.add('/path/image.jpg')

        item = queue.get_next()
        queue.mark_success(item)

        assert queue.size() == 0

    def test_mark_success_persists_change(self, queue, queue_file):
        """Test that removal is persisted."""
        queue.add('/path/image.jpg')

        item = queue.get_next()
        queue.mark_success(item)

        # Load fresh queue from file
        new_queue = UploadQueue(queue_file)
        assert new_queue.size() == 0

    def test_mark_success_with_multiple_items(self, queue):
        """Test marking success with multiple items."""
        queue.add('/path/1.jpg')
        queue.add('/path/2.jpg')
        queue.add('/path/3.jpg')

        # Remove middle item
        item = queue.queue[1]
        queue.mark_success(item)

        assert queue.size() == 2
        assert queue.queue[0]['file_path'] == '/path/1.jpg'
        assert queue.queue[1]['file_path'] == '/path/3.jpg'

    def test_mark_success_nonexistent_item(self, queue):
        """Test marking success on item not in queue."""
        queue.add('/path/image.jpg')

        fake_item = {'file_path': '/fake/path.jpg'}
        queue.mark_success(fake_item)  # Should not crash

        assert queue.size() == 1  # Original item still there


class TestMarkFailure:
    """Test marking items as failed."""

    def test_mark_failure_increments_retry_count(self, queue):
        """Test that failure increments retry count."""
        queue.add('/path/image.jpg')

        item = queue.get_next()
        assert item['retry_count'] == 0

        queue.mark_failure(item, "Test error")

        assert queue.queue[0]['retry_count'] == 1
        assert queue.queue[0]['error'] == "Test error"
        assert queue.queue[0]['last_attempt'] is not None

    def test_mark_failure_updates_error_message(self, queue):
        """Test that error message is updated."""
        queue.add('/path/image.jpg')

        item = queue.get_next()
        queue.mark_failure(item, "First error")

        assert queue.queue[0]['error'] == "First error"

        # Update last_attempt to make it available again
        queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 11
        ).isoformat()

        item = queue.get_next()
        queue.mark_failure(item, "Second error")

        assert queue.queue[0]['error'] == "Second error"

    def test_mark_failure_persists_change(self, queue, queue_file):
        """Test that failure is persisted."""
        queue.add('/path/image.jpg')

        item = queue.get_next()
        queue.mark_failure(item, "Test error")

        # Load fresh queue
        new_queue = UploadQueue(queue_file)
        assert new_queue.queue[0]['retry_count'] == 1
        assert new_queue.queue[0]['error'] == "Test error"

    def test_mark_failure_nonexistent_item(self, queue):
        """Test marking failure on item not in queue."""
        queue.add('/path/image.jpg')

        fake_item = {'file_path': '/fake/path.jpg'}
        queue.mark_failure(fake_item, "Error")  # Should not crash

        assert queue.queue[0]['retry_count'] == 0  # Original unchanged


class TestQueueStatistics:
    """Test queue statistics."""

    def test_get_stats_empty_queue(self, queue):
        """Test stats for empty queue."""
        stats = queue.get_stats()

        assert stats['total'] == 0
        assert stats['never_attempted'] == 0
        assert stats['retrying'] == 0
        assert stats['max_retry_count'] == 0

    def test_get_stats_with_new_items(self, queue):
        """Test stats with only new items."""
        queue.add('/path/1.jpg')
        queue.add('/path/2.jpg')
        queue.add('/path/3.jpg')

        stats = queue.get_stats()

        assert stats['total'] == 3
        assert stats['never_attempted'] == 3
        assert stats['retrying'] == 0
        assert stats['max_retry_count'] == 0

    def test_get_stats_with_failed_items(self, queue):
        """Test stats with failed items."""
        queue.add('/path/1.jpg')
        queue.add('/path/2.jpg')
        queue.add('/path/3.jpg')

        # Fail first item twice
        item1 = queue.get_next()
        queue.mark_failure(item1, "Error 1")

        # Wait for backoff - first item becomes available again
        queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 11
        ).isoformat()

        item1_again = queue.get_next()  # Gets item 1 again (past backoff)
        queue.mark_failure(item1_again, "Error 2")

        stats = queue.get_stats()

        assert stats['total'] == 3
        assert stats['never_attempted'] == 2  # Items 2 and 3
        assert stats['retrying'] == 1  # Item 1
        assert stats['max_retry_count'] == 2

    def test_get_stats_max_retry_count(self, queue):
        """Test that max retry count is calculated correctly."""
        queue.add('/path/1.jpg')
        queue.add('/path/2.jpg')

        # Fail first item 3 times
        for i in range(3):
            queue.queue[0]['last_attempt'] = datetime.fromtimestamp(
                time.time() - 301
            ).isoformat()
            item = queue.get_next()
            queue.mark_failure(item, f"Error {i}")

        # Fail second item once
        queue.queue[1]['last_attempt'] = datetime.fromtimestamp(
            time.time() - 301
        ).isoformat()
        item = queue.get_next()
        queue.mark_failure(item, "Error")

        stats = queue.get_stats()

        assert stats['max_retry_count'] == 3

    def test_size_method(self, queue):
        """Test size method."""
        assert queue.size() == 0

        queue.add('/path/1.jpg')
        assert queue.size() == 1

        queue.add('/path/2.jpg')
        queue.add('/path/3.jpg')
        assert queue.size() == 3

        item = queue.queue[0]
        queue.mark_success(item)
        assert queue.size() == 2


class TestQueuePersistence:
    """Test queue persistence across instances."""

    def test_persistence_across_instances(self, queue_file):
        """Test that queue persists across instances."""
        # Create queue and add items
        queue1 = UploadQueue(queue_file)
        queue1.add('/path/1.jpg', 'Caption 1')
        queue1.add('/path/2.jpg', 'Caption 2')

        # Mark one as failed
        item = queue1.get_next()
        queue1.mark_failure(item, "Test error")

        # Create new instance
        queue2 = UploadQueue(queue_file)

        assert queue2.size() == 2
        assert queue2.queue[0]['file_path'] == '/path/1.jpg'
        assert queue2.queue[0]['retry_count'] == 1
        assert queue2.queue[0]['error'] == "Test error"
        assert queue2.queue[1]['file_path'] == '/path/2.jpg'

    def test_persistence_after_success(self, queue_file):
        """Test persistence after successful removal."""
        queue1 = UploadQueue(queue_file)
        queue1.add('/path/1.jpg')
        queue1.add('/path/2.jpg')

        item = queue1.get_next()
        queue1.mark_success(item)

        queue2 = UploadQueue(queue_file)
        assert queue2.size() == 1
        assert queue2.queue[0]['file_path'] == '/path/2.jpg'

    def test_queue_file_creation(self, tmp_path):
        """Test that queue file is created if parent dir exists."""
        queue_file = tmp_path / "test_queue.json"
        queue = UploadQueue(queue_file)

        # File shouldn't exist yet (empty queue)
        assert not queue_file.exists()

        # Add item - file should be created
        queue.add('/path/image.jpg')
        assert queue_file.exists()
