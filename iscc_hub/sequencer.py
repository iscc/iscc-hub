"""
ISCC Hub Sequencer - Critical component for atomic ISCC declaration processing.

This module provides atomic sequencing of ISCC declarations with:
- Gapless sequence numbers
- Unique nonce enforcement
- Monotonic microsecond timestamp generation (ISCC-ID)
- Durable transaction handling
"""

import time
from binascii import unhexlify
from datetime import datetime

import base58
import jcs
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connection

from iscc_hub.exceptions import NonceError, SequencerError
from iscc_hub.iscc_id import IsccID


@sync_to_async
def asequence_iscc_note(iscc_note):  # pragma: no cover
    """Async wrapper for sequence_iscc_note."""
    return sequence_iscc_note(iscc_note)


@sync_to_async
def asequence_iscc_delete(iscc_note_delete, original_datahash):  # pragma: no cover
    """Async wrapper for sequence_iscc_delete."""
    return sequence_iscc_delete(iscc_note_delete, original_datahash)


def sequence_iscc_note(iscc_note):
    # type: (dict) -> tuple[int, bytes]
    """
    Atomically sequence an ISCC note with gapless numbering and monotonic timestamps.

    This function:
    1. Verifies nonce uniqueness (fails if duplicate)
    2. Issues the next gapless sequence number
    3. Issues the next unique microsecond timestamp (ISCC-ID)
    4. Stores the IsccNote in the iscc_event table
    5. Returns the issued seq and iscc_id_bytes

    All operations are atomic - either all succeed or none.

    :param iscc_note: Pre-validated IsccNote dictionary
    :return: Tuple of (sequence_number, iscc_id_bytes)
    :raises NonceConflictError: If nonce already exists
    :raises SequencerError: For other sequencing failures
    """

    # Prepare data before acquiring transaction lock

    nonce_bytes = unhexlify(iscc_note["nonce"])
    datahash_bytes = unhexlify(iscc_note["datahash"])
    pubkey_bytes = base58.b58decode(iscc_note["signature"]["pubkey"][1:])[2:]
    iscc_note_json = jcs.canonicalize(iscc_note)

    with connection.cursor() as cursor:
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT seq, iscc_id FROM iscc_event ORDER BY seq DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                last_seq = row[0]
                last_iscc_id_bytes = row[1]
                last_timestamp_us = int.from_bytes(last_iscc_id_bytes, "big") >> 12
            else:
                last_seq = 0
                last_timestamp_us = 0

            new_seq = last_seq + 1

            current_time_us = time.time_ns() // 1000

            if current_time_us > last_timestamp_us:
                new_timestamp_us = current_time_us
            else:
                time_diff = last_timestamp_us - current_time_us
                if time_diff > 100_000:  # 0.1 second in microseconds
                    raise SequencerError("Timetravel not allowed :)")
                new_timestamp_us = last_timestamp_us + 1

            seconds = new_timestamp_us // 1_000_000
            microseconds = new_timestamp_us % 1_000_000
            event_time_str = (
                datetime.fromtimestamp(seconds).replace(microsecond=microseconds).strftime("%Y-%m-%d %H:%M:%S.%f")
            )

            iscc_id_uint = (new_timestamp_us << 12) | settings.ISCC_HUB_ID
            iscc_id_bytes = iscc_id_uint.to_bytes(8, "big")

            cursor.execute(
                """
                INSERT INTO iscc_event (seq, event_type, iscc_id, nonce, datahash, pubkey, iscc_note, event_time)
                VALUES (%s, %s, %s, %s, %s, %s, json(%s), %s)
            """,
                (new_seq, 1, iscc_id_bytes, nonce_bytes, datahash_bytes, pubkey_bytes, iscc_note_json, event_time_str),
            )

            cursor.execute("COMMIT")
            return new_seq, iscc_id_bytes

        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            error_msg = str(e).lower()
            if "unique constraint" in error_msg and "nonce" in error_msg:
                raise NonceError("Nonce already used", is_reuse=True) from e

            if isinstance(e, NonceError | SequencerError):
                raise
            else:
                raise SequencerError(f"Sequencing failed: {e}") from e


def sequence_iscc_delete(iscc_note_delete, original_datahash):
    # type: (dict, bytes) -> tuple[int, bytes]
    """
    Atomically sequence an ISCC deletion with gapless numbering and monotonic timestamps.

    This function:
    1. Verifies nonce uniqueness (fails if duplicate)
    2. Issues the next gapless sequence number
    3. Issues the next unique microsecond timestamp (ISCC-ID)
    4. Stores the IsccNoteDelete in the iscc_event table as a DELETE event
    5. Returns the issued seq and iscc_id_bytes

    All operations are atomic - either all succeed or none.

    :param iscc_note_delete: Pre-validated IsccNoteDelete dictionary
    :param original_datahash: Datahash bytes from the original CREATED event
    :return: Tuple of (sequence_number, iscc_id_bytes)
    :raises NonceConflictError: If nonce already exists
    :raises SequencerError: For other sequencing failures
    """

    # Prepare data before acquiring transaction lock
    nonce_bytes = unhexlify(iscc_note_delete["nonce"])
    pubkey_bytes = base58.b58decode(iscc_note_delete["signature"]["pubkey"][1:])[2:]
    iscc_note_json = jcs.canonicalize(iscc_note_delete)

    # Use IsccID class to properly decode the ISCC-ID string
    iscc_id_obj = IsccID(iscc_note_delete["iscc_id"])
    iscc_id_bytes = bytes(iscc_id_obj)  # Get the 8-byte body representation

    with connection.cursor() as cursor:
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT seq, iscc_id FROM iscc_event ORDER BY seq DESC LIMIT 1")
            row = cursor.fetchone()

            if row:
                last_seq = row[0]
            else:
                raise SequencerError("No previous event found")

            new_seq = last_seq + 1
            event_time_us = time.time_ns() // 1000
            seconds = event_time_us // 1_000_000
            microseconds = event_time_us % 1_000_000
            event_time_str = (
                datetime.fromtimestamp(seconds).replace(microsecond=microseconds).strftime("%Y-%m-%d %H:%M:%S.%f")
            )

            # Use the original ISCC-ID from the delete request (not generating a new one)
            cursor.execute(
                """
                INSERT INTO iscc_event (seq, event_type, iscc_id, nonce, datahash, pubkey, iscc_note, event_time)
                VALUES (%s, %s, %s, %s, %s, %s, json(%s), %s)
            """,
                (
                    new_seq,
                    3,
                    iscc_id_bytes,
                    nonce_bytes,
                    original_datahash,
                    pubkey_bytes,
                    iscc_note_json,
                    event_time_str,
                ),
            )

            cursor.execute("COMMIT")
            return new_seq, iscc_id_bytes

        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            error_msg = str(e).lower()
            if "unique constraint" in error_msg and "nonce" in error_msg:
                raise NonceError("Nonce already used", is_reuse=True) from e

            if isinstance(e, NonceError | SequencerError):
                raise
            else:
                raise SequencerError(f"Sequencing failed: {e}") from e
