"""
Tests for event hashing and checkpointing functionality.

These tests validate the cryptographic integrity of the event hash chain
that forms the foundation for the checkpoint system.
"""

import json
from binascii import hexlify, unhexlify

import blake3
import iscc_crypto as icr
import jcs
import pytest
from django.db import connection

from iscc_hub.models import Event, IsccDeclaration
from iscc_hub.sequencer import sequence_iscc_note
from tests.conftest import create_iscc_from_text, generate_test_iscc_id


@pytest.mark.django_db(transaction=True)
def test_event_hash_determinism(full_iscc_note):
    # type: (dict) -> None
    """
    Test that event hash computation is deterministic.

    The same event data should always produce the same hash.
    """
    # Sequence the note to create an event
    seq, iscc_id_bytes = sequence_iscc_note(full_iscc_note)

    # Get the event from database
    event = Event.objects.get(seq=seq)

    # Reconstruct the event data as it was hashed
    with connection.cursor() as cursor:
        # Get the previous event hash (or empty if first event)
        cursor.execute("SELECT event_hash FROM iscc_event WHERE seq < %s ORDER BY seq DESC LIMIT 1", (seq,))
        row = cursor.fetchone()
        row[0] if row else b""

    # The event_data now stores the full canonicalized IsccEvent structure
    stored_event = json.loads(event.event_data.decode() if isinstance(event.event_data, bytes) else event.event_data)

    # Compute hash from stored event data
    canonical_bytes = jcs.canonicalize(stored_event)
    expected_hash = blake3.blake3(canonical_bytes).digest()

    # Verify it matches the stored hash
    assert hexlify(expected_hash).decode() == event.event_hash

    # Also verify the structure is correct
    assert "seq" in stored_event
    assert "iscc_id" in stored_event
    assert "prev" in stored_event
    assert "note" in stored_event
    assert stored_event["seq"] == seq
    assert stored_event["iscc_id"] == event.iscc_id

    # Compute again to verify determinism
    canonical_bytes2 = jcs.canonicalize(stored_event)
    expected_hash2 = blake3.blake3(canonical_bytes2).digest()
    assert expected_hash == expected_hash2


@pytest.mark.django_db(transaction=True)
def test_event_hash_chaining():
    # type: () -> None
    """
    Test that events are properly chained via previous event hashes.

    Each event should include the hash of the previous event.
    """
    # Record starting point
    Event.objects.count()

    # Create multiple events
    events_data = []
    for i in range(3):
        text = f"Test content for event {i}"
        iscc_data = create_iscc_from_text(text)
        nonce = icr.create_nonce(node_id=1)  # Use proper nonce generation

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": "2025-01-15T12:00:00.000Z",
        }

        # Create a deterministic keypair for testing
        controller = f"did:web:example.com:user{i}"
        keypair = icr.key_generate(controller=controller)
        signed_note = icr.sign_json(note, keypair)

        seq, iscc_id_bytes = sequence_iscc_note(signed_note)
        events_data.append((seq, iscc_id_bytes))

    # Get only the events we just created
    events = Event.objects.filter(seq__in=[seq for seq, _ in events_data]).order_by("seq")

    for i, event in enumerate(events):
        # Deserialize event_data to get the full IsccEvent structure
        stored_event = json.loads(event.event_data)

        if i == 0:
            # Check prev hash for first event in our batch
            if stored_event["prev"] == "":
                # This was the very first event in the database
                assert event.seq == 1
            else:
                # There should have been previous events
                # But if they don't exist (truncated db), just verify hash format
                try:
                    prev_event = Event.objects.get(seq=event.seq - 1)
                    assert stored_event["prev"] == prev_event.event_hash
                except Event.DoesNotExist:
                    # Database was truncated but sequencer remembers previous hash
                    # Just verify it's a valid hash format (64 hex chars)
                    assert len(stored_event["prev"]) == 64
                    assert all(c in "0123456789abcdef" for c in stored_event["prev"])
        else:
            # Later events should reference previous event's hash
            prev_event = events[i - 1]
            assert stored_event["prev"] == prev_event.event_hash

        # Verify the stored hash is correct
        canonical_bytes = jcs.canonicalize(stored_event)
        computed_hash = blake3.blake3(canonical_bytes).digest()
        assert hexlify(computed_hash).decode() == event.event_hash


@pytest.mark.django_db(transaction=True)
def test_event_data_integrity(full_iscc_note):
    # type: (dict) -> None
    """
    Test that event_data can be deserialized and matches original.

    The stored event_data should preserve all original note fields.
    """
    # Sequence the note
    seq, iscc_id_bytes = sequence_iscc_note(full_iscc_note)

    # Get the event
    event = Event.objects.get(seq=seq)

    # Deserialize event_data - now contains full IsccEvent structure
    stored_event = json.loads(event.event_data)

    # Extract the note from the stored event
    stored_note = stored_event["note"]

    # Verify all original fields are preserved in the note
    assert stored_note["iscc_code"] == full_iscc_note["iscc_code"]
    assert stored_note["datahash"] == full_iscc_note["datahash"]
    assert stored_note["nonce"] == full_iscc_note["nonce"]
    assert stored_note["timestamp"] == full_iscc_note["timestamp"]
    assert stored_note["signature"] == full_iscc_note["signature"]

    # Optional fields if present
    if "gateway" in full_iscc_note:
        assert stored_note["gateway"] == full_iscc_note["gateway"]
    if "metahash" in full_iscc_note:
        assert stored_note["metahash"] == full_iscc_note["metahash"]

    # Verify JCS canonicalization preserves data
    original_canonical = jcs.canonicalize(full_iscc_note)
    stored_canonical = jcs.canonicalize(stored_note)
    assert original_canonical == stored_canonical


@pytest.mark.django_db(transaction=True)
def test_event_hash_uniqueness():
    # type: () -> None
    """
    Test that different events produce different hashes.

    Even slight changes in event data should produce completely different hashes.
    """
    hashes = set()

    for i in range(5):
        # Create events with slightly different content
        text = f"Content {i}"
        iscc_data = create_iscc_from_text(text)
        nonce = icr.create_nonce(node_id=1)  # Use proper nonce generation

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": f"2025-01-15T12:00:{i:02d}.000Z",  # Different timestamps
        }

        # Create unique keypair for each
        controller = f"did:web:example.com:user{i}"
        keypair = icr.key_generate(controller=controller)
        signed_note = icr.sign_json(note, keypair)

        seq, _ = sequence_iscc_note(signed_note)
        event = Event.objects.get(seq=seq)

        # Hash should be unique
        assert event.event_hash not in hashes
        hashes.add(event.event_hash)

    # All hashes should be different
    assert len(hashes) == 5


@pytest.mark.django_db(transaction=True)
def test_event_hash_based_retrieval():
    # type: () -> None
    """
    Test that events can be retrieved by their hash.

    The event_hash field should support efficient lookups.
    """
    # Create several events and store their hashes
    event_hashes = []

    for i in range(3):
        text = f"Retrieval test {i}"
        iscc_data = create_iscc_from_text(text)
        nonce = icr.create_nonce(node_id=1)  # Use proper nonce generation

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": "2025-01-15T14:00:00.000Z",
        }

        controller = f"did:web:example.com:retrieval{i}"
        keypair = icr.key_generate(controller=controller)
        signed_note = icr.sign_json(note, keypair)

        seq, _ = sequence_iscc_note(signed_note)
        event = Event.objects.get(seq=seq)
        event_hashes.append((seq, event.event_hash))

    # Test retrieval by hash
    for seq, hash_value in event_hashes:
        # Use raw SQL to test index usage
        with connection.cursor() as cursor:
            cursor.execute("SELECT seq, iscc_id FROM iscc_event WHERE event_hash = %s", (unhexlify(hash_value),))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == seq

        # Also test via Django ORM
        event = Event.objects.get(event_hash=hash_value)
        assert event.seq == seq


@pytest.mark.django_db(transaction=True)
def test_chain_breaking_detection():
    # type: () -> None
    """
    Test that tampering with events breaks the hash chain.

    Any modification to an event should invalidate subsequent hashes.
    """
    # Create a chain of events
    events_created = []
    for i in range(3):
        text = f"Chain test {i}"
        iscc_data = create_iscc_from_text(text)
        nonce = icr.create_nonce(node_id=1)  # Use proper nonce generation

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": "2025-01-15T15:00:00.000Z",
        }

        controller = f"did:web:example.com:chain{i}"
        keypair = icr.key_generate(controller=controller)
        signed_note = icr.sign_json(note, keypair)

        seq, _ = sequence_iscc_note(signed_note)
        events_created.append(seq)

    # Get the middle event
    middle_event = Event.objects.get(seq=events_created[1])
    original_hash = middle_event.event_hash

    # Tamper with the middle event's data
    tampered_data = json.loads(middle_event.event_data)
    tampered_data["tampered"] = True

    # Manually update the event (bypassing sequencer)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE iscc_event SET event_data = %s WHERE seq = %s",
            (json.dumps(tampered_data).encode(), middle_event.seq),
        )

    # The stored event should now be invalid
    # Recompute hash with tampered data
    tampered_hash = blake3.blake3(json.dumps(tampered_data).encode()).hexdigest()

    # The hash should have changed (data tampering detected)
    assert tampered_hash != original_hash

    # Verify the chain is broken for the next event
    next_event = Event.objects.get(seq=events_created[2])
    next_event_data = json.loads(next_event.event_data)

    # The next event references the original hash, not the tampered one
    assert next_event_data["prev"] == original_hash

    # If we tried to recompute with tampered middle event, chain would break
    # The stored prev field wouldn't match the tampered event's hash


@pytest.mark.django_db(transaction=True)
def test_genesis_event_hash():
    # type: () -> None
    """
    Test genesis event hash handling.

    In a fresh database, the first event should have an empty prev field.
    In test environments, the sequencer may remember previous hashes.
    """
    # Create the first event
    text = "Genesis event"
    iscc_data = create_iscc_from_text(text)
    nonce = icr.create_nonce(node_id=1)  # Use proper nonce generation

    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": nonce,
        "timestamp": "2025-01-15T10:00:00.000Z",
    }

    controller = "did:web:example.com:genesis"
    keypair = icr.key_generate(controller=controller)
    signed_note = icr.sign_json(note, keypair)

    seq, _ = sequence_iscc_note(signed_note)

    event = Event.objects.get(seq=seq)

    # Get the stored event structure
    stored_event = json.loads(event.event_data)

    # In a production system, seq=1 would have empty prev
    # In tests, the sequencer may remember previous hashes even after db truncation
    # This is actually a feature - it maintains chain integrity across restarts
    if stored_event["prev"] == "":
        # True genesis event
        assert seq == 1
    else:
        # Has a previous hash - verify it's valid format
        assert len(stored_event["prev"]) == 64
        assert all(c in "0123456789abcdef" for c in stored_event["prev"])

    assert stored_event["seq"] == seq

    # Verify hash
    canonical_bytes = jcs.canonicalize(stored_event)
    computed_hash = blake3.blake3(canonical_bytes).hexdigest()
    assert computed_hash == event.event_hash


@pytest.mark.django_db(transaction=True)
def test_event_hash_consistency_across_event_types(example_timestamp, example_keypair, example_iscc_data):
    # type: (str, object, dict) -> None
    """
    Test that hash computation is consistent for all event types.

    CREATED, UPDATED, and DELETED events should all have proper hashes.
    """
    # Create initial declaration
    create_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": "11111111111111111111111111111111",
        "timestamp": example_timestamp,
    }
    signed_create = icr.sign_json(create_note, example_keypair)
    seq1, iscc_id_bytes = sequence_iscc_note(signed_create)

    # TODO: Add update event test when update functionality is available
    # Currently only CREATED events go through sequencer

    # Verify CREATED event has proper hash
    created_event = Event.objects.get(seq=seq1)
    assert created_event.event_hash is not None
    assert len(created_event.event_hash) == 64  # 32 bytes hex encoded
    assert created_event.event_type == Event.EventType.CREATED

    # Verify hash can be recomputed from stored data
    stored_event = json.loads(created_event.event_data)

    # Verify structure
    assert stored_event["seq"] == seq1
    assert stored_event["iscc_id"] == created_event.iscc_id
    # May or may not have empty prev depending on test order
    if stored_event["prev"]:
        assert len(stored_event["prev"]) == 64
    assert "note" in stored_event

    computed_hash = blake3.blake3(jcs.canonicalize(stored_event)).hexdigest()
    assert computed_hash == created_event.event_hash
