#!/usr/bin/env python
"""
Generate realistic fixture data for testing.

This script creates a fresh database, populates it with realistic ISCC declarations
using valid IsccNotes, and dumps the data as Django fixtures.
"""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import django
import iscc_core as ic
import iscc_crypto as icr

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure Django with a temporary database for fixture generation
temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
temp_db_path = temp_db.name
temp_db.close()

os.environ["DJANGO_SETTINGS_MODULE"] = "iscc_hub.settings"
os.environ["ISCC_HUB_DB_NAME"] = temp_db_path
os.environ.setdefault("ISCC_HUB_ID", "1")
os.environ.setdefault("ISCC_HUB_DOMAIN", "hub.example.com")
os.environ.setdefault("ISCC_HUB_SECKEY", "zHuboTestKeyFixtureGeneration")

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import transaction  # noqa: E402

from iscc_hub.models import Event, IsccDeclaration  # noqa: E402
from iscc_hub.sequencer import sequence_declaration  # noqa: E402


def create_iscc_from_text(text="Hello World!"):
    # type: (str) -> dict
    """Generate ISCC codes from text content."""
    text_bytes = BytesIO(text.encode("utf-8"))
    text_bytes_copy = BytesIO(text.encode("utf-8"))

    mcode = ic.gen_meta_code(text, "Test Description", bits=256)
    ccode = ic.gen_text_code(text, bits=256)
    dcode = ic.gen_data_code(text_bytes, bits=256)
    icode = ic.gen_instance_code(text_bytes_copy, bits=256)

    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    result = {}
    result.update(mcode)
    result.update(ccode)
    result.update(dcode)
    result.update(icode)
    result["iscc"] = iscc_code
    result["units"] = [mcode["iscc"], ccode["iscc"], dcode["iscc"]]

    return result


def create_minimal_note(timestamp, nonce=None, keypair=None):
    # type: (str, str|None, icr.KeyPair|None) -> dict
    """Create a minimal signed IsccNote."""
    nonce = nonce or icr.create_nonce(1)  # Use hub_id=1
    keypair = keypair or icr.key_generate()
    data = create_iscc_from_text()

    minimal_note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
    }

    return icr.sign_json(minimal_note, keypair)


def create_full_note(timestamp, nonce=None, keypair=None):
    # type: (str, str|None, icr.KeyPair|None) -> dict
    """Create a full signed IsccNote with optional fields."""
    nonce = nonce or icr.create_nonce(1)
    keypair = keypair or icr.key_generate()
    data = create_iscc_from_text()

    full_note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
        "gateway": "https://example.com/iscc_id/{iscc_id}/metadata",
        "units": data["units"],
        "metahash": data["metahash"],
    }

    return icr.sign_json(full_note, keypair)


def create_note_with_units(timestamp, nonce=None, keypair=None):
    # type: (str, str|None, icr.KeyPair|None) -> dict
    """Create a signed IsccNote with units field."""
    nonce = nonce or icr.create_nonce(1)
    keypair = keypair or icr.key_generate()
    data = create_iscc_from_text("Different content for variety")

    note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
        "units": data["units"],
    }

    return icr.sign_json(note, keypair)


def create_update_note(iscc_id, timestamp, keypair=None):
    # type: (str, str, icr.KeyPair|None) -> dict
    """Create an update note for an existing ISCC-ID."""
    keypair = keypair or icr.key_generate()
    data = create_iscc_from_text("Updated content")

    # Use a different nonce for the update
    nonce = icr.create_nonce(1)

    update_note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
        "gateway": "https://updated.example.com/{iscc_id}",
    }

    return icr.sign_json(update_note, keypair)


def create_timestamp(base_time, offset_seconds=0):
    # type: (datetime, int) -> str
    """
    Create a timestamp with millisecond precision.

    :param base_time: Base datetime object
    :param offset_seconds: Seconds to add to base time
    :return: ISO format timestamp string with millisecond precision
    """
    timestamp = base_time + timedelta(seconds=offset_seconds)
    # Format with millisecond precision (3 decimal places)
    return timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def generate_fixtures():
    # type: () -> None
    """Generate realistic fixture data."""
    print(f"Using temporary database: {temp_db_path}")

    # Run migrations to create tables
    print("Running migrations...")
    call_command("migrate", verbosity=0)

    # Clear any existing data
    Event.objects.all().delete()
    IsccDeclaration.objects.all().delete()

    # Base time for realistic timestamps
    base_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

    print("Creating test data...")

    # Generate multiple keypairs for different actors
    keypair1 = icr.key_generate()
    keypair2 = icr.key_generate()
    keypair3 = icr.key_generate()

    # 1. Create initial declaration with full IsccNote
    note1 = create_full_note(timestamp=create_timestamp(base_time, 0), keypair=keypair1)
    with transaction.atomic():
        sequence_declaration(note1, actor=note1["signature"]["pubkey"])
    print("  - Created full declaration")

    # 2. Create minimal declaration
    note2 = create_minimal_note(
        timestamp=create_timestamp(base_time, 3600),  # 1 hour later
        keypair=keypair2,
    )
    with transaction.atomic():
        sequence_declaration(note2, actor=note2["signature"]["pubkey"])
    print("  - Created minimal declaration")

    # 3. Create declaration with units
    note3 = create_note_with_units(
        timestamp=create_timestamp(base_time, 7200),  # 2 hours later
        keypair=keypair3,
    )
    with transaction.atomic():
        sequence_declaration(note3, actor=note3["signature"]["pubkey"])
    print("  - Created declaration with units")

    # 4. Create another minimal declaration (different content)
    note4 = create_minimal_note(
        timestamp=create_timestamp(base_time, 10800),  # 3 hours later
        keypair=keypair1,  # Same actor as first
    )
    with transaction.atomic():
        sequence_declaration(note4, actor=note4["signature"]["pubkey"])
    print("  - Created another declaration from first actor")

    # 5. Create an update to the first declaration
    # Get the first declaration to update
    first_declaration = IsccDeclaration.objects.first()
    if first_declaration:
        # Use same keypair to update own declaration
        update_note = create_update_note(
            iscc_id=first_declaration.iscc_id,
            timestamp=create_timestamp(base_time, 86400),  # 1 day later
            keypair=keypair1,
        )
        # Process the update - it will create a new declaration with same ISCC-ID
        with transaction.atomic():
            sequence_declaration(
                update_note,
                actor=update_note["signature"]["pubkey"],
                update_iscc_id=first_declaration.iscc_id,
            )
        print("  - Created update declaration")

    # 6. Create a deletion event
    # Get a declaration to delete
    declaration_to_delete = IsccDeclaration.objects.filter(deleted=False).last()
    if declaration_to_delete:
        # Create a delete event (reusing minimal note structure)
        delete_note = create_minimal_note(
            timestamp=create_timestamp(base_time, 172800),  # 2 days later
            keypair=keypair2,
        )

        # Process as deletion
        with transaction.atomic():
            event = Event.objects.create(
                event_type=Event.EventType.DELETED,
                iscc_id=declaration_to_delete.iscc_id,
                iscc_note=delete_note,
            )
            # Update the declaration's deleted flag
            declaration_to_delete.deleted = True
            declaration_to_delete.event_seq = event.seq
            declaration_to_delete.save()
        print("  - Created deletion event")

    # Print summary
    print(f"\nCreated {Event.objects.count()} events")
    print(f"Created {IsccDeclaration.objects.count()} declarations")
    print(f"  - Active: {IsccDeclaration.objects.filter(deleted=False).count()}")
    print(f"  - Deleted: {IsccDeclaration.objects.filter(deleted=True).count()}")

    # Dump the fixtures
    output_file = Path(__file__).parent.parent / "iscc_hub" / "fixtures" / "test_data.json"
    print(f"\nDumping fixtures to {output_file}...")

    with open(output_file, "w") as f:
        call_command(
            "dumpdata",
            "iscc_hub.Event",
            "iscc_hub.IsccDeclaration",
            format="json",
            indent=2,
            stdout=f,
        )

    print(f"Fixtures saved to {output_file}")

    # Close database connection before cleanup
    from django import db

    db.connections.close_all()

    # Clean up temporary database
    try:
        os.unlink(temp_db_path)
        print("Cleaned up temporary database")
    except PermissionError:
        print(f"Note: Temporary database at {temp_db_path} could not be deleted (Windows file lock)")
        print("It will be cleaned up automatically on next reboot")


if __name__ == "__main__":
    try:
        generate_fixtures()
    except Exception as e:
        print(f"Error generating fixtures: {e}")
        # Try to clean up on error
        if "temp_db_path" in locals() and os.path.exists(temp_db_path):
            try:
                from django import db

                db.connections.close_all()
                os.unlink(temp_db_path)
            except Exception:
                pass
        sys.exit(1)
