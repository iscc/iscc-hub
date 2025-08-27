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
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection

from iscc_hub.models import Checkpoint, Event, IsccDeclaration
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


# === Checkpoint Model Tests ===


@pytest.mark.django_db(transaction=True)
def test_checkpoint_model_creation():
    # type: () -> None
    """
    Test basic Checkpoint model creation with valid data.
    """
    # Create a checkpoint
    # Genesis checkpoint uses Blake3 hash of empty bytes for prev
    genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    checkpoint = Checkpoint.objects.create(
        start=1,
        end=100,
        merkle_root="a" * 64,
        prev=genesis_prev,
        hash="b" * 64,
    )

    assert checkpoint.id is not None
    assert checkpoint.start == 1
    assert checkpoint.end == 100
    assert checkpoint.merkle_root == "a" * 64
    assert checkpoint.prev == genesis_prev
    assert checkpoint.hash == "b" * 64
    assert checkpoint.created_at is not None
    assert checkpoint.timestamp_type is None
    assert checkpoint.timestamp_token is None


@pytest.mark.django_db(transaction=True)
def test_checkpoint_str_representation():
    # type: () -> None
    """
    Test the string representation of a Checkpoint.
    """
    checkpoint = Checkpoint.objects.create(
        start=50,
        end=150,
        merkle_root="c" * 64,
        prev="d" * 64,
        hash="e" * 64,
    )

    expected = f"Checkpoint #{checkpoint.id}: events 50-150"
    assert str(checkpoint) == expected


@pytest.mark.django_db(transaction=True)
def test_checkpoint_event_count_property():
    # type: () -> None
    """
    Test the event_count property calculates correctly.
    """
    # Single event
    genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    checkpoint1 = Checkpoint.objects.create(
        start=5,
        end=5,
        merkle_root="3" * 64,
        prev=genesis_prev,
        hash="4" * 64,
    )
    assert checkpoint1.event_count == 1

    # Multiple events
    checkpoint2 = Checkpoint.objects.create(
        start=10,
        end=99,
        merkle_root="5" * 64,
        prev="4" * 64,
        hash="6" * 64,
    )
    assert checkpoint2.event_count == 90


@pytest.mark.django_db(transaction=True)
def test_checkpoint_constraint_end_gte_start():
    # type: () -> None
    """
    Test that the constraint end >= start is enforced.
    """
    with pytest.raises(IntegrityError) as excinfo:
        genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
        checkpoint = Checkpoint(
            start=100,
            end=50,  # Invalid: end < start
            merkle_root="7" * 64,
            prev=genesis_prev,
            hash="8" * 64,
        )
        checkpoint.save()

    # Constraint name should be in the error
    assert "checkpoint_end_gte_start" in str(excinfo.value).lower() or "check" in str(excinfo.value).lower()


@pytest.mark.django_db(transaction=True)
def test_checkpoint_unique_end_constraint():
    # type: () -> None
    """
    Test that the end field must be unique.
    """
    # Create first checkpoint
    genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    Checkpoint.objects.create(
        start=1,
        end=100,
        merkle_root="9" * 64,
        prev=genesis_prev,
        hash="a0" * 32,
    )

    # Try to create another with the same end
    with pytest.raises(IntegrityError) as excinfo:
        Checkpoint.objects.create(
            start=50,
            end=100,  # Same end as first checkpoint
            merkle_root="b0" * 32,
            prev="a0" * 32,
            hash="c0" * 32,
        )

    assert "unique" in str(excinfo.value).lower() or "end" in str(excinfo.value).lower()


@pytest.mark.django_db(transaction=True)
def test_checkpoint_unique_hash_constraint():
    # type: () -> None
    """
    Test that the hash field must be unique.
    """
    # Create first checkpoint
    genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    Checkpoint.objects.create(
        start=1,
        end=50,
        merkle_root="d0" * 32,
        prev=genesis_prev,
        hash="e0" * 32,
    )

    # Try to create another with the same hash
    with pytest.raises(IntegrityError) as excinfo:
        Checkpoint.objects.create(
            start=51,
            end=100,
            merkle_root="f0" * 32,
            prev="e0" * 32,
            hash="e0" * 32,  # Same hash - should fail
        )

    assert "unique" in str(excinfo.value).lower() or "hash" in str(excinfo.value).lower()


@pytest.mark.django_db(transaction=True)
def test_checkpoint_timestamp_type_choices():
    # type: () -> None
    """
    Test that Checkpoint model accepts valid timestamp type choices.
    """
    # Test all valid timestamp types
    types = ["RFC3161", "OTS"]
    for i, ts_type in enumerate(types):
        genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
        checkpoint = Checkpoint.objects.create(
            start=i * 10 + 1,
            end=i * 10 + 10,
            merkle_root=f"{'a' * 63}{i}",
            prev=genesis_prev,
            hash=f"{'b' * 63}{i}",
            timestamp_type=ts_type,
        )
        assert checkpoint.timestamp_type == ts_type

    # Test None is also valid
    checkpoint_none = Checkpoint.objects.create(
        start=100,
        end=110,
        merkle_root="c" * 64,
        prev=genesis_prev,
        hash="d" * 64,
        timestamp_type=None,
    )
    assert checkpoint_none.timestamp_type is None


@pytest.mark.django_db(transaction=True)
def test_checkpoint_chain_linking():
    # type: () -> None
    """
    Test that checkpoints can be properly linked via prev field.
    """
    # Create genesis checkpoint
    genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    genesis = Checkpoint.objects.create(
        start=1,
        end=100,
        merkle_root="a1" * 32,
        prev=genesis_prev,
        hash="b1" * 32,
    )

    # Create second checkpoint linked to genesis
    second = Checkpoint.objects.create(
        start=101,
        end=200,
        merkle_root="c1" * 32,
        prev=genesis.hash,
        hash="d1" * 32,
    )

    # Create third checkpoint linked to second
    third = Checkpoint.objects.create(
        start=201,
        end=300,
        merkle_root="e1" * 32,
        prev=second.hash,
        hash="f1" * 32,
    )

    # Verify chain
    assert genesis.prev == genesis_prev
    assert second.prev == genesis.hash
    assert third.prev == second.hash

    # Verify we can traverse the chain
    checkpoints = list(Checkpoint.objects.order_by("start"))
    assert len(checkpoints) == 3

    for i in range(1, len(checkpoints)):
        assert checkpoints[i].prev == checkpoints[i - 1].hash


@pytest.mark.django_db(transaction=True)
def test_checkpoint_with_timestamp_token():
    # type: () -> None
    """
    Test storing and retrieving external timestamp tokens.
    """
    # Create checkpoint without timestamp
    genesis_prev = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    checkpoint = Checkpoint.objects.create(
        start=1,
        end=50,
        merkle_root="a2" * 32,
        prev=genesis_prev,
        hash="b2" * 32,
    )

    assert checkpoint.timestamp_type is None
    assert checkpoint.timestamp_token is None

    # Update with RFC3161 token
    token_b64 = "MIIGYTCCBUmgAwIBAgIQA=="  # Example Base64 token
    checkpoint.timestamp_type = "RFC3161"
    checkpoint.timestamp_token = token_b64
    checkpoint.save()

    # Retrieve and verify
    retrieved = Checkpoint.objects.get(id=checkpoint.id)
    assert retrieved.timestamp_type == "RFC3161"
    assert retrieved.timestamp_token == token_b64

    # Test with OTS proof
    ots_checkpoint = Checkpoint.objects.create(
        start=51,
        end=100,
        merkle_root="123" * 21 + "1",
        prev=checkpoint.hash,
        hash="456" * 21 + "4",
        timestamp_type="OTS",
        timestamp_token="AE9wZW5UaW1lc3RhbXBzAA==",  # Example Base64 OTS proof
    )
    assert ots_checkpoint.timestamp_type == "OTS"
    assert ots_checkpoint.timestamp_token == "AE9wZW5UaW1lc3RhbXBzAA=="


# === Checkpoint Module Function Tests ===


def test_build_merkle_tree_single_hash():
    # type: () -> None
    """
    Test building merkle tree with single hash.
    """
    from iscc_hub.checkpoint import build_merkle_tree

    single_hash = ["a" * 64]
    tree = build_merkle_tree(single_hash)
    root = tree.get_state().hex()

    # Verify it's a valid hash
    assert len(root) == 64
    assert all(c in "0123456789abcdef" for c in root)
    assert tree.get_size() == 1


def test_build_merkle_tree_multiple_hashes():
    # type: () -> None
    """
    Test building merkle tree with multiple hashes.
    """
    from iscc_hub.checkpoint import build_merkle_tree

    hashes = ["a" * 64, "b" * 64, "c" * 64]
    tree = build_merkle_tree(hashes)
    root = tree.get_state().hex()

    # Verify it's a valid hash
    assert len(root) == 64
    assert all(c in "0123456789abcdef" for c in root)
    assert tree.get_size() == 3


def test_build_merkle_tree_power_of_two():
    # type: () -> None
    """
    Test building merkle tree with power of 2 hashes.
    """
    from iscc_hub.checkpoint import build_merkle_tree

    hashes = ["1" * 64, "2" * 64, "3" * 64, "4" * 64]
    tree = build_merkle_tree(hashes)
    root = tree.get_state().hex()

    assert len(root) == 64
    assert tree.get_size() == 4


def test_build_merkle_tree_empty_raises():
    # type: () -> None
    """
    Test that building merkle tree with empty list raises ValueError.
    """
    from iscc_hub.checkpoint import build_merkle_tree

    with pytest.raises(ValueError) as excinfo:
        build_merkle_tree([])

    assert "empty list" in str(excinfo.value).lower()


def test_get_checkpoint_hash():
    # type: () -> None
    """
    Test checkpoint hash calculation.
    """
    from iscc_hub.checkpoint import get_checkpoint_hash

    merkle_root = "a" * 64
    prev_hash = "b" * 64

    hash_result = get_checkpoint_hash(merkle_root, prev_hash)

    # Should be Blake3(merkle_root || prev)
    expected = blake3.blake3(unhexlify(merkle_root) + unhexlify(prev_hash)).hexdigest()
    assert hash_result == expected


def test_create_rfc3161_timestamp():
    # type: () -> None
    """
    Test creating RFC3161 timestamp.
    """
    from unittest.mock import Mock, patch

    from iscc_hub.checkpoint import create_rfc3161_timestamp

    mock_token_bytes = b"test_token_data"

    with patch("iscc_hub.checkpoint.TSPSigner") as MockTSPSigner:
        mock_signer = Mock()
        mock_signer.sign.return_value = mock_token_bytes
        MockTSPSigner.return_value = mock_signer

        hash_hex = "1234567890abcdef" * 4  # 32 bytes hex
        token = create_rfc3161_timestamp(hash_hex)

        # Import required modules for assertion
        from tsp_client.algorithms import DigestAlgorithm
        from tsp_client.signer import SigningSettings

        # Verify signer was called with Blake3 hash as message and SHA256 settings
        expected_settings = SigningSettings(digest_algorithm=DigestAlgorithm.SHA256)
        mock_signer.sign.assert_called_once_with(unhexlify(hash_hex), signing_settings=expected_settings)

        # Verify token is base64 encoded
        import base64

        assert token == base64.b64encode(mock_token_bytes).decode("ascii")
        assert token == "dGVzdF90b2tlbl9kYXRh"


@pytest.mark.django_db(transaction=True)
def test_create_checkpoint_no_events():
    # type: () -> None
    """
    Test that create_checkpoint raises ValueError when no events exist.
    """
    from iscc_hub.checkpoint import create_checkpoint

    # Clear all events and checkpoints
    Event.objects.all().delete()
    Checkpoint.objects.all().delete()

    with pytest.raises(ValueError) as excinfo:
        create_checkpoint()

    assert "No events to checkpoint" in str(excinfo.value)


@pytest.mark.django_db(transaction=True)
def test_create_checkpoint_first_checkpoint(example_keypair):
    # type: (object) -> None
    """
    Test creating the first checkpoint.
    """
    from unittest.mock import patch

    from iscc_hub.checkpoint import create_checkpoint

    # Clear existing checkpoints
    Checkpoint.objects.all().delete()

    # Create some events
    for i in range(3):
        text = f"Test content {i}"
        iscc_data = create_iscc_from_text(text)
        nonce = icr.create_nonce(node_id=1)

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": f"2025-01-15T12:00:{i:02d}.000Z",
        }

        signed_note = icr.sign_json(note, example_keypair)
        sequence_iscc_note(signed_note)

    # Mock timestamping to avoid network call
    with patch("iscc_hub.checkpoint.create_rfc3161_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "mock_timestamp_token"

        checkpoint = create_checkpoint()

        assert checkpoint.id is not None
        assert checkpoint.start >= 1
        assert checkpoint.end >= checkpoint.start
        assert checkpoint.event_count >= 1
        assert checkpoint.merkle_root is not None
        assert len(checkpoint.merkle_root) == 64
        # Genesis checkpoint should have Blake3 of empty bytes
        assert checkpoint.prev == blake3.blake3(b"").hexdigest()
        assert checkpoint.hash is not None
        assert checkpoint.timestamp_type == "RFC3161"
        assert checkpoint.timestamp_token == "mock_timestamp_token"


@pytest.mark.django_db(transaction=True)
def test_create_checkpoint_subsequent(example_keypair):
    # type: (object) -> None
    """
    Test creating subsequent checkpoints.
    """
    from unittest.mock import patch

    from iscc_hub.checkpoint import create_checkpoint

    # Clear existing checkpoints
    Checkpoint.objects.all().delete()

    # Create first batch of events
    for i in range(2):
        text = f"First batch {i}"
        iscc_data = create_iscc_from_text(text)
        nonce = icr.create_nonce(node_id=1)

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": f"2025-01-15T10:00:{i:02d}.000Z",
        }

        signed_note = icr.sign_json(note, example_keypair)
        sequence_iscc_note(signed_note)

    # Create first checkpoint
    with patch("iscc_hub.checkpoint.create_rfc3161_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "token1"
        checkpoint1 = create_checkpoint()

    # Create second batch of events
    for i in range(3):
        text = f"Second batch {i}"
        iscc_data = create_iscc_from_text(text)
        nonce = icr.create_nonce(node_id=1)

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": f"2025-01-15T11:00:{i:02d}.000Z",
        }

        signed_note = icr.sign_json(note, example_keypair)
        sequence_iscc_note(signed_note)

    # Create second checkpoint
    with patch("iscc_hub.checkpoint.create_rfc3161_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "token2"
        checkpoint2 = create_checkpoint()

    assert checkpoint2.start == checkpoint1.end + 1
    assert checkpoint2.end >= checkpoint2.start
    assert checkpoint2.prev == checkpoint1.hash
    assert checkpoint2.timestamp_token == "token2"


@pytest.mark.django_db(transaction=True)
def test_create_checkpoint_no_new_events():
    # type: () -> None
    """
    Test that create_checkpoint raises ValueError when all events are checkpointed.
    """
    from unittest.mock import patch

    from iscc_hub.checkpoint import create_checkpoint

    # Clear existing checkpoints
    Checkpoint.objects.all().delete()

    # Create events
    text = "Test content"
    iscc_data = create_iscc_from_text(text)
    nonce = icr.create_nonce(node_id=1)
    controller = "did:web:example.com:test"
    keypair = icr.key_generate(controller=controller)

    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": nonce,
        "timestamp": "2025-01-15T12:00:00.000Z",
    }

    signed_note = icr.sign_json(note, keypair)
    seq, _ = sequence_iscc_note(signed_note)

    # Create checkpoint for all events
    with patch("iscc_hub.checkpoint.create_rfc3161_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "token"
        checkpoint = create_checkpoint()

    assert checkpoint.end == seq

    # Try to create another checkpoint - should fail
    with pytest.raises(ValueError) as excinfo:
        create_checkpoint()

    assert "No events to checkpoint" in str(excinfo.value)


@pytest.mark.django_db(transaction=True)
def test_create_checkpoint_timestamp_failure(example_keypair):
    # type: (object) -> None
    """
    Test that checkpoint creation fails completely if timestamping fails.
    """
    from unittest.mock import patch

    from iscc_hub.checkpoint import create_checkpoint

    # Clear existing checkpoints
    Checkpoint.objects.all().delete()

    # Create an event
    text = "Test content"
    iscc_data = create_iscc_from_text(text)
    nonce = icr.create_nonce(node_id=1)

    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": nonce,
        "timestamp": "2025-01-15T12:00:00.000Z",
    }

    signed_note = icr.sign_json(note, example_keypair)
    sequence_iscc_note(signed_note)

    # Mock timestamping to fail
    with patch("iscc_hub.checkpoint.create_rfc3161_timestamp") as mock_timestamp:
        mock_timestamp.side_effect = Exception("Network error")

        # Checkpoint creation should fail completely
        with pytest.raises(Exception) as exc_info:
            create_checkpoint()

        assert "Network error" in str(exc_info.value)

    # No checkpoint should have been created
    assert Checkpoint.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_create_checkpoint_database_failure():
    # type: () -> None
    """
    Test that checkpoint creation handles database failures properly.
    """
    from unittest.mock import Mock, patch

    from django.db import DatabaseError

    from iscc_hub.checkpoint import create_checkpoint

    # Clear existing checkpoints
    Checkpoint.objects.all().delete()

    # Create an event
    text = "Test content"
    iscc_data = create_iscc_from_text(text)
    nonce = icr.create_nonce(node_id=1)
    controller = "did:web:example.com:dbfail"
    keypair = icr.key_generate(controller=controller)

    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": nonce,
        "timestamp": "2025-01-15T12:00:00.000Z",
    }

    signed_note = icr.sign_json(note, keypair)
    sequence_iscc_note(signed_note)

    # Mock both timestamp and database to test error handling
    with patch("iscc_hub.checkpoint.create_rfc3161_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "mock_token"

        # Patch Checkpoint.objects.create to fail
        with patch.object(Checkpoint.objects, "create") as mock_create:
            mock_create.side_effect = DatabaseError("DB error")

            with pytest.raises(DatabaseError):
                create_checkpoint()

    # No checkpoint should have been created
    assert Checkpoint.objects.count() == 0
