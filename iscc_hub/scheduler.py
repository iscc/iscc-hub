"""
Simple integrated scheduler for periodic checkpoint creation.
"""

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


class CheckpointScheduler:
    """Background scheduler for periodic checkpoint creation."""

    def __init__(self):
        # type: () -> None
        """Initialize the checkpoint scheduler."""
        self.lock_file = Path(settings.ISCC_HUB_DB_PATH).parent / ".scheduler.lock"
        self.stop_event = threading.Event()
        self.thread = None
        self.is_leader = False

    def acquire_leader_lock(self):
        # type: () -> bool
        """
        Try to become the scheduler leader using file-based locking.

        :return: True if lock acquired, False otherwise
        """
        try:
            # Try to create lock file exclusively
            fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            # Check if lock holder is still alive
            try:
                with open(self.lock_file) as f:
                    pid = int(f.read().strip())
                # Check if process exists (Unix/Windows compatible)
                try:
                    os.kill(pid, 0)
                    return False  # Process exists, we're not leader
                except (ProcessLookupError, PermissionError, OSError):
                    # Process dead or Windows error, take over
                    # Note: PermissionError could mean process exists but belongs to another user.
                    # In restricted environments, this may cause inappropriate takeover.
                    # For typical single-user deployment scenarios, this is acceptable.
                    self.lock_file.unlink()
                    return self.acquire_leader_lock()
            except (ValueError, FileNotFoundError):
                # Invalid or missing lock file, try to acquire
                self.lock_file.unlink(missing_ok=True)
                return self.acquire_leader_lock()

    def release_leader_lock(self):
        # type: () -> None
        """Release the scheduler lock."""
        if self.is_leader:
            self.lock_file.unlink(missing_ok=True)

    def run_scheduler(self):  # pragma: no cover
        # type: () -> None
        """Main scheduler loop."""
        from iscc_hub.checkpoint import create_checkpoint

        # Get interval from settings (default 4 hours)
        interval = getattr(settings, "ISCC_HUB_CHECKPOINT_INTERVAL", 4 * 3600)

        logger.info(f"Starting checkpoint scheduler with interval: {interval}s")

        # Initial delay to let the application fully start
        time.sleep(10)

        while not self.stop_event.is_set():
            try:
                # Wait for interval or stop signal
                if self.stop_event.wait(interval):
                    break

                # Create checkpoint
                start_time = datetime.now()
                logger.info(f"Creating scheduled checkpoint at {start_time}")

                try:
                    checkpoint = create_checkpoint()
                    logger.info(
                        f"Successfully created checkpoint #{checkpoint.id}: "
                        f"events {checkpoint.start}-{checkpoint.end} "
                        f"({checkpoint.event_count} total)"
                    )
                except ValueError as e:
                    # No events to checkpoint - this is normal
                    logger.debug(f"Checkpoint skipped: {e}")
                except Exception as e:
                    logger.error(f"Checkpoint creation failed: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                # Continue running even if checkpoint fails

    def start(self):
        # type: () -> None
        """Start scheduler if we're the leader."""
        # Check if scheduler is enabled
        if not getattr(settings, "ISCC_HUB_CHECKPOINT_ENABLED", True):
            logger.info("Checkpoint scheduler is disabled")
            return

        if not self.acquire_leader_lock():
            logger.info("Another worker is running the scheduler")
            return

        self.is_leader = True
        logger.info(f"Worker PID {os.getpid()} is scheduler leader")

        self.thread = threading.Thread(target=self.run_scheduler, daemon=True, name="CheckpointScheduler")
        self.thread.start()

    def stop(self):  # pragma: no cover
        # type: () -> None
        """Stop the scheduler gracefully."""
        if self.thread and self.thread.is_alive():
            logger.info("Stopping checkpoint scheduler...")
            self.stop_event.set()
            self.thread.join(timeout=5)
            self.release_leader_lock()
            logger.info("Checkpoint scheduler stopped")


# Global scheduler instance
_scheduler = None


def start_scheduler():
    # type: () -> None
    """Start the checkpoint scheduler (called by Gunicorn hook)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CheckpointScheduler()
        _scheduler.start()


def stop_scheduler():  # pragma: no cover
    # type: () -> None
    """Stop the checkpoint scheduler (called by Gunicorn hook)."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
