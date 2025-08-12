"""
Atomic sequential processing of ISCC declarations.

This module handles the sequential assignment of ISCC-IDs and manages
the Event log and IsccDeclaration materialization with guaranteed
serializability and monotonic ordering.
"""

import random
import time

from django.conf import settings
from django.db import OperationalError, connection, transaction

from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Event, IsccDeclaration


class SequencerError(Exception):
    """
    Base exception for sequencer errors.
    """

    pass


class RetryTransaction(Exception):
    """
    Raised when transaction should be retried due to temporal drift.
    """

    pass


def get_last_iscc_id():
    # type: () -> bytes|None
    """
    Get the last ISCC-ID from the Event log.

    Uses raw SQL for performance to bypass Django ORM field conversions.

    :return: Last ISCC-ID as bytes or None if no events exist
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT iscc_id FROM iscc_event ORDER BY seq DESC LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else None


def generate_iscc_id(last_iscc_id_bytes):
    # type: (bytes|None) -> bytes
    """
    Generate a new monotonic ISCC-ID.

    Ensures the new ISCC-ID timestamp is:
    1. Greater than the last ISCC-ID timestamp
    2. Not too far ahead of real time (max 1 second drift)

    :param last_iscc_id_bytes: Previous ISCC-ID as bytes or None
    :return: New ISCC-ID as bytes
    :raises RetryTransaction: If temporal drift exceeds maximum
    """
    MAX_DRIFT_MS = 1000  # Max 1 second ahead of real time
    hub_id = getattr(settings, "ISCC_HUB_ID", 0)

    # Get current time in microseconds
    now_us = time.time_ns() // 1_000

    if last_iscc_id_bytes:
        # Extract timestamp from last ISCC-ID (52-bit timestamp, 12-bit hub-id)
        last_us = int.from_bytes(last_iscc_id_bytes, "big") >> 12

        # Check if we're too far ahead of real time
        drift_us = last_us - now_us
        if drift_us > (MAX_DRIFT_MS * 1000):
            # Sleep for half the drift to allow catch-up
            sleep_time = (drift_us - (MAX_DRIFT_MS * 1000)) / 2_000_000
            time.sleep(sleep_time)
            raise RetryTransaction("Temporal drift exceeded maximum")

        # Ensure monotonic ordering
        if now_us <= last_us:
            now_us = last_us + 1

    # Generate new ISCC-ID (52-bit timestamp + 12-bit hub-id)
    iscc_id_uint = (now_us << 12) | hub_id
    return iscc_id_uint.to_bytes(8, "big")


def create_event(iscc_note, iscc_id_bytes, event_type=Event.EventType.CREATED):
    # type: (dict, bytes, int) -> Event
    """
    Create and save a new Event record.

    :param iscc_note: The IsccNote dictionary to log
    :param iscc_id_bytes: The ISCC-ID as bytes
    :param event_type: Type of event (CREATED, UPDATED, DELETED)
    :return: Saved Event instance
    """
    event = Event(event_type=event_type, iscc_id=iscc_id_bytes, iscc_note=iscc_note)
    event.save(force_insert=True)
    return event


def materialize_declaration(event, iscc_note, actor):
    # type: (Event, dict, str) -> IsccDeclaration
    """
    Create or update the materialized IsccDeclaration from an Event.

    :param event: The Event that triggered this materialization
    :param iscc_note: The IsccNote dictionary
    :param actor: The actor's public key
    :return: Created or updated IsccDeclaration
    """
    # Get or create the declaration
    declaration, created = IsccDeclaration.objects.update_or_create(
        iscc_id=event.iscc_id,
        defaults={
            "event_seq": event.seq,
            "iscc_code": iscc_note["iscc_code"],
            "datahash": iscc_note["datahash"],
            "nonce": iscc_note["nonce"],
            "actor": actor,
            "gateway": iscc_note.get("gateway", ""),
            "metahash": iscc_note.get("metahash", ""),
            "deleted": event.event_type == Event.EventType.DELETED,
        },
    )

    return declaration


def sequence_declaration(iscc_note, actor, update_iscc_id=None):
    # type: (dict, str, str|None) -> tuple[Event, IsccDeclaration]
    """
    Atomically sequence an ISCC declaration.

    Performs the following operations atomically:
    1. Generates a monotonic ISCC-ID
    2. Creates an Event log entry
    3. Materializes the IsccDeclaration

    This function should be called within a transaction context.
    Django's transaction management or sequence_declaration_with_retry
    should be used to ensure proper transaction handling.

    :param iscc_note: The validated IsccNote dictionary
    :param actor: The actor's public key
    :param update_iscc_id: Optional ISCC-ID for update operations
    :return: Tuple of (Event, IsccDeclaration)
    :raises SequencerError: If sequencing fails
    :raises RetryTransaction: If transaction should be retried
    """
    try:
        # Get the last ISCC-ID
        last_iscc_id_bytes = get_last_iscc_id()

        # Determine event type
        if update_iscc_id:
            event_type = Event.EventType.UPDATED
            # For updates, use the existing ISCC-ID
            iscc_id_bytes = IsccID(update_iscc_id).bytes_body
        else:
            event_type = Event.EventType.CREATED
            # Generate new ISCC-ID
            iscc_id_bytes = generate_iscc_id(last_iscc_id_bytes)

        # Create Event log entry
        event = create_event(iscc_note, iscc_id_bytes, event_type)

        # Materialize declaration
        declaration = materialize_declaration(event, iscc_note, actor)

        return event, declaration

    except RetryTransaction:
        # Retry the entire operation
        return sequence_declaration(iscc_note, actor, update_iscc_id)

    except Exception as e:
        raise SequencerError(f"Failed to sequence declaration: {e}") from e


def sequence_declaration_with_retry(iscc_note, actor, update_iscc_id=None, max_retries=10):
    # type: (dict, str, str|None, int) -> tuple[Event, IsccDeclaration]
    """
    Sequence a declaration with automatic retry on database lock.

    Implements exponential backoff with jitter for handling concurrent
    access to the database.

    :param iscc_note: The validated IsccNote dictionary
    :param actor: The actor's public key
    :param update_iscc_id: Optional ISCC-ID for update operations
    :param max_retries: Maximum number of retry attempts
    :return: Tuple of (Event, IsccDeclaration)
    :raises SequencerError: If sequencing fails after all retries
    """
    base_delay = 0.0005  # 0.5ms base delay

    for attempt in range(max_retries):
        try:
            return sequence_declaration(iscc_note, actor, update_iscc_id)

        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                # Exponential backoff with jitter
                delay = min(
                    base_delay * (2**attempt) + random.random() * 0.001,
                    0.05,  # Cap at 50ms
                )
                time.sleep(delay)
                continue
            raise SequencerError(f"Failed to sequence after {max_retries} attempts: {e}") from e

        except SequencerError:
            raise

        except Exception as e:
            raise SequencerError(f"Unexpected error during sequencing: {e}") from e

    raise SequencerError(f"Failed to sequence after {max_retries} attempts")


def delete_declaration(iscc_id, actor):
    # type: (str, str) -> tuple[Event, IsccDeclaration]
    """
    Mark a declaration as deleted.

    Creates a DELETE event and updates the materialized declaration.

    :param iscc_id: The ISCC-ID to delete
    :param actor: The actor requesting deletion
    :return: Tuple of (Event, IsccDeclaration)
    :raises SequencerError: If deletion fails
    """
    with transaction.atomic():
        try:
            # Get the declaration with a lock
            iscc_id_bytes = IsccID(iscc_id).bytes_body
            declaration = IsccDeclaration.objects.select_for_update().get(iscc_id=iscc_id_bytes)

            # Verify ownership
            if declaration.actor != actor:
                raise SequencerError("Cannot delete declaration owned by another actor")

            # Reconstruct the iscc_note from the declaration
            # Note: timestamp is not needed for deletion events as it's in the ISCC-ID
            iscc_note = {
                "iscc_code": declaration.iscc_code,
                "datahash": declaration.datahash,
                "nonce": declaration.nonce,
                "timestamp": "2025-01-01T00:00:00Z",  # Placeholder - not used in deletion
            }

            if declaration.gateway:
                iscc_note["gateway"] = declaration.gateway
            if declaration.metahash:
                iscc_note["metahash"] = declaration.metahash

            # Create deletion event
            event = create_event(iscc_note, iscc_id_bytes, Event.EventType.DELETED)

            # Mark declaration as deleted
            declaration.deleted = True
            declaration.event_seq = event.seq
            declaration.save()

            return event, declaration

        except IsccDeclaration.DoesNotExist as e:
            raise SequencerError(f"ISCC-ID not found: {iscc_id}") from e
        except Exception as e:
            raise SequencerError(f"Failed to delete declaration: {e}") from e
