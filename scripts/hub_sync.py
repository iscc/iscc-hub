#!/usr/bin/env python
"""
Test script for hub list synchronization.

This script runs the hub sync task directly to measure execution time and debug any issues.
"""

import logging
import os
import sys
import time

import django

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iscc_hub.settings")
django.setup()

from django.conf import settings  # noqa: E402

from iscc_hub.tasks import sync_hub_list  # noqa: E402

# Configure logging to see detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def test_sync_with_timing():
    # type: () -> None
    """
    Test hub synchronization with detailed timing information.
    """
    print("\n" + "=" * 80)
    print("TESTING HUB LIST SYNCHRONIZATION")
    print("=" * 80)

    # Print current configuration
    print("\nConfiguration:")
    print(f"  ISCC_HUB_REALM: {getattr(settings, 'ISCC_HUB_REALM', 0)}")
    print(f"  Django-Q2 timeout: {settings.Q_CLUSTER.get('timeout', 'not set')} seconds")
    print(f"  Django-Q2 retry: {settings.Q_CLUSTER.get('retry', 'not set')} seconds")

    # Get the URL that will be fetched
    realm = getattr(settings, "ISCC_HUB_REALM", 0)
    if realm == 0:
        yaml_file = "hubs/testnet.yaml"
        network_name = "testnet"
    else:
        yaml_file = "hubs/mainnet.yaml"
        network_name = "mainnet"

    github_url = f"https://raw.githubusercontent.com/iscc/iscc-hub/main/{yaml_file}"
    print(f"  Target URL: {github_url}")
    print(f"  Network: {network_name}")

    print("\n" + "-" * 80)
    print("Starting synchronization...\n")

    # Measure overall execution time
    start_time = time.perf_counter()

    try:
        # Run the sync task
        result = sync_hub_list()

        # Calculate elapsed time
        elapsed = time.perf_counter() - start_time

        print("\n" + "-" * 80)
        print("RESULTS:")
        print("-" * 80)
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Network: {result.get('network', 'unknown')}")
        print(f"Created: {result.get('created', 0)} hubs")
        print(f"Updated: {result.get('updated', 0)} hubs")
        print(f"Deactivated: {result.get('deactivated', 0)} hubs")
        print(f"Total hubs: {result.get('total_hubs', 0)}")

        if result.get("errors"):
            print("\nErrors encountered:")
            for error in result["errors"]:
                print(f"  - {error}")

        print("\n" + "=" * 80)
        print(f"EXECUTION TIME: {elapsed:.3f} seconds")
        print("=" * 80)

        # Check if this would timeout with current settings
        timeout = settings.Q_CLUSTER.get("timeout", 90)
        if elapsed > timeout:
            print(f"\n⚠️  WARNING: Task took {elapsed:.1f}s but Django-Q2 timeout is {timeout}s")
            print("    This task would TIMEOUT when run through Django-Q2!")
        else:
            print(f"\n✓  Task completed in {elapsed:.1f}s, within {timeout}s timeout")

    except Exception as e:
        elapsed = time.perf_counter() - start_time
        print(f"\n❌ ERROR after {elapsed:.3f} seconds: {e}")
        import traceback

        traceback.print_exc()

        # Check if we hit a network timeout
        if "timeout" in str(e).lower():
            print("\n⚠️  Network timeout detected - this might be why Django-Q2 tasks fail")


def test_individual_operations():
    # type: () -> None
    """
    Test individual operations to identify bottlenecks.
    """
    import niquests
    import yaml

    from iscc_hub.models import Hub

    print("\n" + "=" * 80)
    print("TESTING INDIVIDUAL OPERATIONS")
    print("=" * 80)

    realm = getattr(settings, "ISCC_HUB_REALM", 0)
    if realm == 0:
        yaml_file = "hubs/testnet.yaml"
    else:
        yaml_file = "hubs/mainnet.yaml"

    github_url = f"https://raw.githubusercontent.com/iscc/iscc-hub/main/{yaml_file}"

    # Test 1: Network fetch
    print("\n1. Testing GitHub fetch...")
    start = time.perf_counter()
    try:
        response = niquests.get(github_url, timeout=30.0)
        response.raise_for_status()
        fetch_time = time.perf_counter() - start
        print(f"   ✓ Fetched in {fetch_time:.3f}s (size: {len(response.content)} bytes)")

        # Test 2: YAML parsing
        print("\n2. Testing YAML parsing...")
        start = time.perf_counter()
        hub_data = yaml.safe_load(response.text)
        parse_time = time.perf_counter() - start
        print(f"   ✓ Parsed in {parse_time:.3f}s (found {len(hub_data.get('hubs', []))} hubs)")

        # Test 3: Database operations
        print("\n3. Testing database query...")
        start = time.perf_counter()
        existing_hubs = list(Hub.objects.all())
        query_time = time.perf_counter() - start
        print(f"   ✓ Queried {len(existing_hubs)} existing hubs in {query_time:.3f}s")

        # Test 4: Simulate update_or_create operations
        print("\n4. Simulating update_or_create operations...")
        start = time.perf_counter()
        for _i, hub_info in enumerate(hub_data.get("hubs", [])[:5]):  # Test first 5
            hub_id = hub_info["hub_id"]
            Hub.objects.filter(hub_id=hub_id).exists()
        sim_time = time.perf_counter() - start
        print(f"   ✓ Simulated 5 operations in {sim_time:.3f}s")

        total_time = fetch_time + parse_time + query_time
        print(f"\nTotal time for core operations: {total_time:.3f}s")

    except Exception as e:
        print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    print("Hub Sync Testing Script")
    print("=" * 80)

    # First test individual operations to identify bottlenecks
    test_individual_operations()

    # Then test the full sync
    test_sync_with_timing()

    print("\nTest complete!")
