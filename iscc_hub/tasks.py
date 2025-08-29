"""
Background tasks for ISCC Hub using Django-Q2.
"""

import logging

from django.utils import timezone

from iscc_hub.checkpoint import create_checkpoint

logger = logging.getLogger(__name__)


def checkpoint_task():
    # type: () -> dict
    """
    Create a checkpoint.

    :return: Dictionary with task execution details.
    """
    try:
        logger.info("Starting scheduled checkpoint creation")
        checkpoint = create_checkpoint()

        result = {
            "status": "success",
            "checkpoint_id": checkpoint.id,
            "start": checkpoint.start,
            "end": checkpoint.end,
            "hash": checkpoint.hash,
            "created_at": checkpoint.created_at.isoformat(),
            "message": f"Checkpoint created for events {checkpoint.start}-{checkpoint.end}",
        }
        logger.info(f"Checkpoint created for events {checkpoint.start}-{checkpoint.end}")
        return result

    except Exception as e:
        logger.error(f"Failed to create checkpoint: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat(),
        }
