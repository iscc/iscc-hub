"""
Management command to initialize checkpoint scheduling if not already configured.
"""

import logging
from typing import Any

from django.core.management.base import BaseCommand
from django_q.models import Schedule

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Initialize periodic tasks if not already configured"

    def handle(self, *args, **options):
        # type: (*Any, **Any) -> None
        """Handle the management command."""
        # Checkpoint schedule
        checkpoint_name = "Periodic Checkpointing"
        existing_checkpoint = Schedule.objects.filter(func="iscc_hub.tasks.checkpoint_task").exists()

        if existing_checkpoint:
            self.stdout.write(self.style.SUCCESS("✓ Checkpoint schedule already exists (no changes made)"))
        else:
            # Create a new schedule for daily at 00:00 UTC
            Schedule.objects.create(
                name=checkpoint_name,
                func="iscc_hub.tasks.checkpoint_task",
                schedule_type=Schedule.CRON,
                cron="0 0 * * *",  # Daily at 00:00 UTC
                repeats=-1,  # Repeat forever
            )
            self.stdout.write(self.style.SUCCESS("✓ Created checkpoint schedule (daily at 00:00 UTC)"))

        # Hub sync schedule
        hub_sync_name = "Hub List Synchronization"
        existing_hub_sync = Schedule.objects.filter(func="iscc_hub.tasks.sync_hub_list").exists()

        if existing_hub_sync:
            self.stdout.write(self.style.SUCCESS("✓ Hub sync schedule already exists (no changes made)"))
        else:
            # Create a new schedule for hourly hub list sync
            Schedule.objects.create(
                name=hub_sync_name,
                func="iscc_hub.tasks.sync_hub_list",
                schedule_type=Schedule.CRON,
                cron="0 * * * *",  # Every hour at minute 0
                repeats=-1,  # Repeat forever
            )
            self.stdout.write(self.style.SUCCESS("✓ Created hub sync schedule (every hour)"))
