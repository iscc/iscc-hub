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
        schedule_name = "Periodic Checkpointing"

        # Check if schedule already exists
        existing_schedule = Schedule.objects.filter(func="iscc_hub.tasks.checkpoint_task").exists()

        if existing_schedule:
            self.stdout.write(self.style.SUCCESS("✓ Checkpoint schedule already exists (no changes made)"))
        else:
            # Create a new schedule for daily at 00:00 UTC
            Schedule.objects.create(
                name=schedule_name,
                func="iscc_hub.tasks.checkpoint_task",
                schedule_type=Schedule.CRON,
                cron="0 0 * * *",  # Daily at 00:00 UTC
                repeats=-1,  # Repeat forever
            )
            self.stdout.write(self.style.SUCCESS("✓ Created checkpoint schedule (daily at 00:00 UTC)"))
