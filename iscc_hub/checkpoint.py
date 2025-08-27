"""
Checkpoint creation for ISCC Hub event log integrity.
"""

import base64
from typing import Optional

import blake3
from tsp_client.signer import TSPSigner

from iscc_hub.models import Checkpoint, Event


def build_merkle_root(hashes):
    # type: (list[str]) -> str
    """
    Build a Merkle tree root from a list of hex-encoded hashes using Blake3.

    :param hashes: List of hex-encoded hash strings
    :return: Hex-encoded root hash
    """
    if not hashes:
        raise ValueError("Cannot build merkle tree from empty list")

    # Convert hex strings to bytes
    nodes = [bytes.fromhex(h) for h in hashes]

    # Build tree level by level
    while len(nodes) > 1:
        next_level = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                # Hash pair of nodes
                combined = nodes[i] + nodes[i + 1]
            else:
                # Odd node - hash with itself
                combined = nodes[i] + nodes[i]
            next_level.append(blake3.blake3(combined).digest())
        nodes = next_level

    return nodes[0].hex()


def get_checkpoint_hash(merkle_root, prev_hash):
    # type: (str, str) -> str
    """
    Calculate checkpoint hash as Blake3(merkle_root || prev).

    :param merkle_root: Hex-encoded merkle root
    :param prev_hash: Hex-encoded previous checkpoint hash
    :return: Hex-encoded checkpoint hash
    """
    combined = bytes.fromhex(merkle_root) + bytes.fromhex(prev_hash)
    return blake3.blake3(combined).hexdigest()


def create_rfc3161_timestamp(checkpoint_hash):
    # type: (str) -> str
    """
    Create RFC3161 timestamp for checkpoint hash.

    :param checkpoint_hash: Hex-encoded checkpoint hash
    :return: Base64-encoded timestamp token
    """
    hash_bytes = bytes.fromhex(checkpoint_hash)
    signer = TSPSigner()
    # The sign method expects either message or message_digest, not both
    # We pass the raw hash as message_digest
    token_bytes = signer.sign(message_digest=hash_bytes)
    return base64.b64encode(token_bytes).decode("ascii")


def create_checkpoint():
    # type: () -> Checkpoint
    """
    Create a cryptographic checkpoint of the event log.

    Creates a verifiable snapshot of all uncheckpointed events using
    Merkle trees, hash chaining, and RFC3161 timestamping.

    :return: The created Checkpoint object
    :raises ValueError: If no events to checkpoint
    """
    # Get last checkpoint to determine event range
    last_checkpoint = Checkpoint.objects.order_by("id").last()

    if last_checkpoint:
        # Get events after last checkpoint
        start_seq = last_checkpoint.end + 1
        events = Event.objects.filter(seq__gte=start_seq).order_by("seq")
        prev_hash = str(last_checkpoint.hash)
    else:
        # First checkpoint - get all events
        start_seq = 1
        events = Event.objects.all().order_by("seq")
        # Genesis checkpoint uses Blake3 hash of empty bytes
        prev_hash = blake3.blake3(b"").hexdigest()

    # Check if there are events to checkpoint
    if not events.exists():
        raise ValueError("No events to checkpoint")

    # Get event hashes and determine range
    event_list = list(events.values("seq", "event_hash"))
    # No need to check event_list - if exists() returned True, values() will have items

    event_hashes = [e["event_hash"] for e in event_list]
    end_seq = event_list[-1]["seq"]

    # Build merkle tree
    merkle_root = build_merkle_root(event_hashes)

    # Calculate checkpoint hash
    checkpoint_hash = get_checkpoint_hash(merkle_root, prev_hash)

    # Try to acquire RFC3161 timestamp - required for valid checkpoint
    # This is done before database insertion to ensure we have a valid timestamp
    try:
        timestamp_token = create_rfc3161_timestamp(checkpoint_hash)
        timestamp_type = "RFC3161"
    except Exception:
        # Re-raise to prevent checkpoint creation without timestamp
        raise

    # Only create checkpoint in database if timestamping succeeded
    # This ensures we don't block the database if timestamping fails
    checkpoint = Checkpoint.objects.create(
        start=start_seq,
        end=end_seq,
        merkle_root=merkle_root,
        prev=prev_hash,
        hash=checkpoint_hash,
        timestamp_type=timestamp_type,
        timestamp_token=timestamp_token,
    )

    return checkpoint
