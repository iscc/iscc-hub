"""
Management command to sync or import hub configurations.

Can sync from GitHub (default) or import from a local YAML file (for development).
"""

from pathlib import Path

import yaml
from django.core.management.base import BaseCommand
from django.db import transaction

from iscc_hub.models import Hub
from iscc_hub.tasks import sync_hub_list


class Command(BaseCommand):
    help = "Sync hub configurations from GitHub or import from a local YAML file"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--file",
            type=str,
            help="Path to a local YAML file to import (for development). If not provided, syncs from GitHub.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing hubs before importing (only works with --file)",
        )

    def handle(self, *args, **options):
        """Sync hubs from GitHub or import from local file."""
        yaml_file = options.get("file")

        # If no file specified, sync from GitHub
        if not yaml_file:
            self.stdout.write("Syncing hub list from GitHub...")
            result = sync_hub_list()

            if result["status"] == "success":
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Hub sync completed successfully: "
                        f"{result['created']} created, {result['updated']} updated, "
                        f"{result['deactivated']} deactivated"
                    )
                )
            elif result["status"] == "partial":
                self.stdout.write(self.style.WARNING(f"Hub sync completed with errors: {result.get('errors', [])}"))
            else:
                self.stderr.write(self.style.ERROR(f"Hub sync failed: {result.get('error', 'Unknown error')}"))
            return

        # Import from local file (development mode)
        yaml_path = Path(yaml_file)

        if not yaml_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {yaml_path}"))
            return

        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to read YAML file: {e}"))
            return

        if not data or "hubs" not in data:
            self.stderr.write(self.style.ERROR("No 'hubs' section found in YAML file"))
            return

        with transaction.atomic():
            if options["clear"]:
                Hub.objects.all().delete()
                self.stdout.write(self.style.WARNING("Cleared existing hubs"))

            created_count = 0
            updated_count = 0

            for hub_data in data["hubs"]:
                hub_id = hub_data.get("hub_id")
                if hub_id is None:
                    self.stderr.write(self.style.WARNING(f"Skipping hub without hub_id: {hub_data}"))
                    continue

                hub, created = Hub.objects.update_or_create(
                    hub_id=hub_id,
                    defaults={
                        "pubkey": hub_data.get("pubkey", ""),
                        "url": hub_data.get("url", ""),
                        "active": hub_data.get("active", True),
                    },
                )

                if created:
                    created_count += 1
                    self.stdout.write(f"  Created hub {hub_id}: {hub.url}")
                else:
                    updated_count += 1
                    self.stdout.write(f"  Updated hub {hub_id}: {hub.url}")

        self.stdout.write(self.style.SUCCESS(f"Import complete: {created_count} created, {updated_count} updated"))
