"""
Checkpoint creation for ISCC Hub event log integrity.

## Canonical Merkle Tree Construction

This module uses pymerkle with BLAKE3 for building Merkle trees. The exact construction is:

1. **Leaf nodes**: BLAKE3(0x00 || BLAKE3(event))
   - The event_hash from our database is the pure BLAKE3(event)
   - pymerkle applies BLAKE3(0x00 || event_hash) when we pass it as entry data
   - This double-hashing with prefix prevents second-preimage attacks

2. **Interior nodes**: BLAKE3(0x01 || left_child || right_child)
   - pymerkle automatically applies the 0x01 prefix for interior nodes
   - Children are concatenated left-to-right

3. **Odd nodes**: Promoted to next level without duplication
   - When a level has an odd number of nodes, the last node is promoted as-is

This construction is cryptographically secure and maintains compatibility with pymerkle's
proof verification system. The double-hashing of leaves is intentional and provides
defense-in-depth against attacks.
"""

import base64
import hashlib
from binascii import unhexlify

import blake3
import pymerkle.constants
from django.conf import settings
from django.db import IntegrityError, models
from pymerkle import InmemoryTree as MerkleTree
from tsp_client.algorithms import DigestAlgorithm
from tsp_client.signer import SigningSettings, TSPSigner

from iscc_hub.models import Checkpoint, Event


def _initialize_blake3_for_pymerkle():
    # type: () -> None
    """
    Initialize BLAKE3 support for pymerkle.

    This function patches hashlib and pymerkle to support BLAKE3.
    Should be called once during module initialization.
    """
    if not hasattr(hashlib, "blake3"):
        hashlib.blake3 = blake3.blake3  # type: ignore[attr-defined]

    if "blake3" not in pymerkle.constants.ALGORITHMS:
        pymerkle.constants.ALGORITHMS.append("blake3")


# Initialize BLAKE3 support on module import
_initialize_blake3_for_pymerkle()


def build_merkle_tree(hashes):
    # type: (list[str]) -> MerkleTree
    """
    Build a Merkle tree from a list of hex-encoded hashes using BLAKE3.

    The tree construction follows RFC 6962-style security:
    - Each event_hash becomes a leaf: BLAKE3(0x00 || unhexlify(event_hash))
    - Interior nodes: BLAKE3(0x01 || left || right)

    :param hashes: List of hex-encoded hash strings (pure event hashes)
    :return: MerkleTree instance with BLAKE3 and security prefixes
    """
    if not hashes:
        raise ValueError("Cannot build merkle tree from empty list")

    tree = MerkleTree(algorithm="blake3")
    for hash_hex in hashes:
        # pymerkle will compute BLAKE3(0x00 || unhexlify(hash_hex))
        tree.append_entry(unhexlify(hash_hex))

    return tree


def get_checkpoint_hash(merkle_root, prev_hash):
    # type: (str, str) -> str
    """
    Calculate checkpoint hash as Blake3(merkle_root || prev).

    :param merkle_root: Hex-encoded merkle root
    :param prev_hash: Hex-encoded previous checkpoint hash
    :return: Hex-encoded checkpoint hash
    """
    combined = unhexlify(merkle_root) + unhexlify(prev_hash)
    return blake3.blake3(combined).hexdigest()


def create_rfc3161_timestamp(checkpoint_hash):
    # type: (str) -> str
    """
    Create RFC3161 timestamp for checkpoint hash.

    The Blake3 checkpoint hash is passed as the message to be timestamped.
    The TSA will internally compute SHA-256(blake3_hash) and timestamp it.

    TSA Configuration (via Django settings):
    - ISCC_HUB_TIMESTAMP_SERVERS: List of TSA server URLs (tries each until success)

    :param checkpoint_hash: Hex-encoded Blake3 checkpoint hash
    :return: Base64-encoded RFC3161 timestamp token
    :raises: Exception if all TSA servers fail
    """
    # Convert Blake3 hash from hex to bytes
    blake3_hash_bytes = unhexlify(checkpoint_hash)

    # Get TSA servers from Django settings
    tsa_servers = settings.ISCC_HUB_TIMESTAMP_SERVERS

    # SHA256 is the protocol constant for TSA digest algorithm
    digest_algo = DigestAlgorithm.SHA256

    # Try TSA servers in order
    errors = []

    # If no servers configured, try with default tsp-client server
    if not tsa_servers:  # pragma: no cover
        tsa_servers = [None]  # None will use tsp-client default

    for server_url in tsa_servers:
        try:
            # Create signer
            signer = TSPSigner()

            # Create signing settings for this specific server
            if server_url:
                signing_settings = SigningSettings(tsp_server=server_url, digest_algorithm=digest_algo)
            else:
                # Use default server with configured digest algorithm
                signing_settings = SigningSettings(digest_algorithm=digest_algo)  # pragma: no cover

            # Pass Blake3 hash as the message - TSA will compute digest internally
            token_bytes = signer.sign(blake3_hash_bytes, signing_settings=signing_settings)

            # Success - return the token
            return base64.b64encode(token_bytes).decode("ascii")

        except Exception as e:
            # Record error and try next server
            server_name = server_url or "default TSA"
            errors.append(f"{server_name}: {e}")
            continue

    # All servers failed
    error_msg = "All TSA servers failed:\n" + "\n".join(errors)
    raise Exception(error_msg)


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
        start_seq = last_checkpoint.end + 1
        prev_hash = str(last_checkpoint.hash)
    else:
        start_seq = 1
        # Genesis checkpoint uses Blake3 hash of empty bytes
        prev_hash = blake3.blake3(b"").hexdigest()

    # Snapshot the end boundary first to ensure consistency
    # This prevents including events added during processing
    max_seq_result = Event.objects.aggregate(max_seq=models.Max("seq"))
    end_seq = max_seq_result["max_seq"]

    if end_seq is None or end_seq < start_seq:
        raise ValueError("No events to checkpoint")

    # Now fetch events within the snapshot boundaries
    events = Event.objects.filter(seq__gte=start_seq, seq__lte=end_seq).order_by("seq")

    # Get event hashes
    event_list = list(events.values("seq", "event_hash"))
    if not event_list:
        # Shouldn't happen given our checks above, but be defensive
        raise ValueError("No events to checkpoint")

    event_hashes = [e["event_hash"] for e in event_list]

    # Build merkle tree and get root
    tree = build_merkle_tree(event_hashes)
    merkle_root = tree.get_state().hex()

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
    try:
        checkpoint = Checkpoint.objects.create(
            start=start_seq,
            end=end_seq,
            merkle_root=merkle_root,
            prev=prev_hash,
            hash=checkpoint_hash,
            timestamp_type=timestamp_type,
            timestamp_token=timestamp_token,
        )
    except IntegrityError:
        # Another worker created a checkpoint starting from the same point
        # Return the existing checkpoint (which may have a different end_seq)
        existing = Checkpoint.objects.filter(start=start_seq).first()
        if existing:
            return existing
        # If somehow we can't find it, re-raise the error
        raise

    return checkpoint
