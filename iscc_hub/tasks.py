"""
Background tasks for ISCC Hub using Django-Q2.
"""

import logging

import niquests
import yaml
from django.conf import settings
from django.utils import timezone

from iscc_hub import log_tree
from iscc_hub.checkpoint_note import parse_checkpoint

logger = logging.getLogger(__name__)


def checkpoint_task():
    # type: () -> dict
    """
    Refresh the published C2SP signed-note checkpoint over the log.

    :return: Dictionary with task execution details.
    """
    try:
        logger.info("Starting scheduled checkpoint refresh")
        checkpoint = log_tree.build_checkpoint()
        _, tree_size, _ = parse_checkpoint(checkpoint)
        logger.info(f"Checkpoint refreshed at tree size {tree_size}")
        return {
            "status": "success",
            "tree_size": tree_size,
            "message": f"Checkpoint refreshed at tree size {tree_size}",
        }

    except Exception as e:
        logger.error(f"Failed to refresh checkpoint: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat(),
        }


def sync_hub_list():
    # type: () -> dict
    """
    Sync hub list from authoritative GitHub repository.

    Fetches hub configuration from GitHub repository based on realm setting:
    - REALM-0 (testnet): hubs/testnet.yaml
    - REALM-1 (mainnet): hubs/mainnet.yaml

    :return: Dictionary with sync execution details.
    """
    from iscc_hub.models import Hub

    try:
        # Determine which hub list to fetch based on realm
        realm = getattr(settings, "ISCC_HUB_REALM", 0)
        if realm == 0:
            yaml_file = "hubs/testnet.yaml"
            network_name = "testnet"
        else:
            yaml_file = "hubs/mainnet.yaml"
            network_name = "mainnet"

        # Fetch hub list from GitHub
        github_url = f"https://raw.githubusercontent.com/iscc/iscc-hub/main/{yaml_file}"
        logger.info(f"Fetching hub list from {github_url}")

        response = niquests.get(github_url, timeout=30.0)
        response.raise_for_status()

        # Parse YAML data
        response_text = response.text
        if response_text is None:
            raise ValueError("Empty response from GitHub")
        hub_data = yaml.safe_load(response_text)

        # Validate network matches
        if hub_data.get("network") != network_name:
            raise ValueError(f"Network mismatch: expected {network_name}, got {hub_data.get('network')}")

        # Track sync results
        created_count = 0
        updated_count = 0
        deactivated_count = 0
        errors = []

        # Get all hub IDs from authoritative list
        authoritative_hub_ids = {hub["hub_id"] for hub in hub_data.get("hubs", [])}

        # Process each hub from authoritative list
        for hub_info in hub_data.get("hubs", []):
            try:
                hub_id = hub_info["hub_id"]
                pubkey = hub_info["pubkey"]
                url = hub_info.get("url", "")
                active = hub_info.get("active", True)

                # Update or create hub
                hub, created = Hub.objects.update_or_create(
                    hub_id=hub_id,
                    defaults={
                        "pubkey": pubkey,
                        "url": url,
                        "active": active,
                    },
                )

                if created:
                    created_count += 1
                    logger.info(f"Created new hub: {hub_id}")
                else:
                    updated_count += 1
                    logger.debug(f"Updated hub: {hub_id}")

            except Exception as e:
                error_msg = f"Failed to sync hub {hub_info.get('hub_id', 'unknown')}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Deactivate hubs not in authoritative list
        for hub in Hub.objects.filter(active=True):
            if hub.hub_id not in authoritative_hub_ids:
                hub.active = False
                hub.save()
                deactivated_count += 1
                logger.info(f"Deactivated hub not in authoritative list: {hub.hub_id}")

        result = {
            "status": "success" if not errors else "partial",
            "network": network_name,
            "created": created_count,
            "updated": updated_count,
            "deactivated": deactivated_count,
            "total_hubs": len(authoritative_hub_ids),
            "timestamp": timezone.now().isoformat(),
        }

        if errors:
            result["errors"] = errors

        logger.info(
            f"Hub sync completed: {created_count} created, {updated_count} updated, {deactivated_count} deactivated"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to sync hub list: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat(),
        }
