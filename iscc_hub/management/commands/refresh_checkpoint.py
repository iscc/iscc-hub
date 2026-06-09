"""
Management command to refresh the published C2SP signed-note checkpoint.

The checkpoint also rebuilds lazily on read, so this command is a freshness
optimization that an external scheduler (or the entrypoint loop) can run
periodically; a missed run self-heals on the next read of ``/log/checkpoint``.
"""

from typing import Any

from django.core.management.base import BaseCommand

from iscc_hub import log_tree
from iscc_hub.checkpoint_note import parse_checkpoint


class Command(BaseCommand):
    help = "Refresh the signed checkpoint over the log at the current tree size"

    def handle(self, *args, **options):
        # type: (*Any, **Any) -> None
        """Build the checkpoint and report the covered tree size."""
        checkpoint = log_tree.build_checkpoint()
        _, tree_size, _ = parse_checkpoint(checkpoint)
        self.stdout.write(self.style.SUCCESS(f"Checkpoint refreshed at tree size {tree_size}"))
