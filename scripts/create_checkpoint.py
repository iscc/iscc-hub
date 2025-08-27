#!/usr/bin/env python
"""
Script to create a cryptographic checkpoint of the event log.
"""

import os
import sys

import django

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iscc_hub.settings")
django.setup()

from iscc_hub.checkpoint import create_checkpoint  # noqa: E402


def main():
    # type: () -> None
    """Create a checkpoint of the event log."""
    try:
        checkpoint = create_checkpoint()
        print(f"✓ Created checkpoint #{checkpoint.id}:")
        print(f"  Events: {checkpoint.start}-{checkpoint.end} ({checkpoint.event_count} total)")
        print(f"  Hash: {checkpoint.hash[:16]}...")
        if checkpoint.timestamp_type:
            print(f"  Timestamp: {checkpoint.timestamp_type}")
        else:
            print("  Timestamp: Pending (will retry in background)")
    except ValueError as e:
        print(f"✗ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Failed to create checkpoint: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
