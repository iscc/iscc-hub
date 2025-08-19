"""
ISCC Hub Sequencer - Critical component for atomic ISCC declaration processing.

This module provides atomic sequencing of ISCC declarations with:
- Gapless sequence numbers
- Unique nonce enforcement
- Monotonic microsecond timestamp generation (ISCC-ID)
- Durable transaction handling
"""

import json
import time
from binascii import unhexlify

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connection

from iscc_hub.exceptions import NonceError


class SequencerError(Exception):
    """Base exception for sequencer errors."""

    pass


@sync_to_async
def asequence_iscc_note(iscc_note):  # pragma: no cover
    """Async wrapper for sequence_iscc_note."""
    return sequence_iscc_note(iscc_note)


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
    # Extract required fields from the note
    nonce = iscc_note.get("nonce")
    iscc_code = iscc_note.get("iscc_code")
    datahash = iscc_note.get("datahash")
    iscc_note.get("gateway", "")
    iscc_note.get("metahash", "")

    # Extract actor from signature
    signature = iscc_note.get("signature", {})
    actor = signature.get("pubkey", "")

    if not all([nonce, iscc_code, datahash, actor]):
        raise SequencerError("Missing required fields in IsccNote")

    # Convert hex strings to bytes for storage
    assert nonce is not None and datahash is not None  # Type narrowing for pyright
    nonce_bytes = unhexlify(nonce)
    datahash_bytes = unhexlify(datahash)  # Store full datahash with '1e20' prefix

    # Check if we're in an atomic block or transaction
    if connection.in_atomic_block:
        raise SequencerError(
            "Sequencer cannot be called within an atomic block or transaction. "
            "This function requires direct control over SQLite's BEGIN IMMEDIATE transaction."
        )

    # Ensure we're in autocommit mode
    if not connection.get_autocommit():
        raise SequencerError(
            "Sequencer requires autocommit mode to be enabled. "
            "Please ensure the connection is in autocommit mode before calling this function."
        )

    with connection.cursor() as cursor:
        try:
            # Try to start immediate transaction for exclusive write lock
            # This will fail if we're already in a transaction
            try:
                cursor.execute("BEGIN IMMEDIATE")
            except Exception as e:
                if "cannot start a transaction within a transaction" in str(e):
                    raise SequencerError(
                        "Cannot start transaction - already in a transaction. "
                        "Ensure no implicit transactions are active."
                    ) from e
                raise

            # 1. Skip manual nonce check - let database constraint handle it

            # 2. Get the last sequence number and timestamp
            cursor.execute("""
                SELECT seq, iscc_id
                FROM iscc_event
                ORDER BY seq DESC
                LIMIT 1
            """)
            row = cursor.fetchone()

            if row:
                last_seq = row[0]
                last_iscc_id_bytes = row[1]
                # Extract timestamp from last ISCC-ID (52-bit timestamp, 12-bit hub_id)
                last_timestamp_us = int.from_bytes(last_iscc_id_bytes, "big") >> 12
            else:
                last_seq = 0
                last_timestamp_us = 0

            # 3. Generate new sequence number
            new_seq = last_seq + 1

            # 4. Generate new monotonic microsecond timestamp
            current_time_us = time.time_ns() // 1000  # nanoseconds to microseconds

            # Ensure monotonic increase
            if current_time_us <= last_timestamp_us:
                new_timestamp_us = last_timestamp_us + 1
            else:
                new_timestamp_us = current_time_us

            # 5. Create ISCC-ID from timestamp and hub_id
            hub_id = settings.ISCC_HUB_ID
            if not (0 <= hub_id <= 4095):
                cursor.execute("ROLLBACK")
                raise SequencerError(f"Invalid hub_id: {hub_id}")

            # Combine 52-bit timestamp with 12-bit hub_id
            iscc_id_uint = (new_timestamp_us << 12) | hub_id
            iscc_id_bytes = iscc_id_uint.to_bytes(8, "big")

            # 6. Insert into iscc_event table
            # Convert iscc_note to JSON string
            iscc_note_json = json.dumps(iscc_note)

            cursor.execute(
                """
                INSERT INTO iscc_event (seq, event_type, iscc_id, nonce, datahash, iscc_note, event_time)
                VALUES (%s, %s, %s, %s, %s, json(%s), strftime('%%Y-%%m-%%d %%H:%%M:%%f', 'now'))
            """,
                (
                    new_seq,
                    1,  # EventType.CREATED
                    iscc_id_bytes,
                    nonce_bytes,
                    datahash_bytes,
                    iscc_note_json,
                ),
            )

            # 7. Commit the transaction durably
            cursor.execute("COMMIT")

            return new_seq, iscc_id_bytes

        except Exception as e:
            # Ensure rollback on any error
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass  # Rollback might fail if connection is broken

            # Check for nonce constraint violation
            error_msg = str(e).lower()
            if "unique constraint" in error_msg and "nonce" in error_msg:
                raise NonceError("Nonce already used", is_reuse=True) from e

            # Re-raise with context
            if isinstance(e, NonceError | SequencerError):
                raise
            else:
                raise SequencerError(f"Sequencing failed: {e}") from e
