"""
ISCC-Log service: the live transparency tree over the committed LogRecords.

This module is the Django-aware integration layer between the pure Merkle math
(``iscc_hub.merkle``), the checkpoint codec (``iscc_hub.checkpoint_note``), and
the persisted log (``LogRecord``/``LogState``). The committed records are the
source of truth; tiles, proofs, and checkpoints are recomputed from them on
demand (ISCC-Log §11.2), so no separate tile cache has to be kept consistent.

The HTTP read surface (``iscc_hub.log_api``) and the receipt evidence builder
call into here; the write path (the sequencer) is untouched and never blocks on
tree work.

Pilot scope (deliberate, post-pilot optimizations):

- Tiles, tree heads, and inclusion proofs are recomputed from ``LogRecord`` on
  every request (O(n) / O(n·log n)). At pilot scale (~51k entries) this is cheap
  and keeps the tile store discardable. The plan's persisted full-tile cache plus
  O(log n) incremental tree head is deferred — purely a performance change behind
  the same read API, swappable later without touching the wire format.
- ``get_checkpoint`` refreshes the checkpoint lazily on read when the tree has
  grown, so a read can take the sequencer's write lock briefly (see the function
  note). Read-replica serving (reads that never write) is a post-pilot concern;
  for the single-writer SQLite/Postgres pilot the coupling is negligible.
"""

import base64

import iscc_crypto as icr
from django.conf import settings
from django.db import transaction

from iscc_hub import checkpoint_note, merkle
from iscc_hub.models import LogRecord, LogState


def log_origin():
    # type: () -> str
    """Return the checkpoint origin: the scheme-less log prefix, no trailing slash."""
    return f"{settings.ISCC_HUB_DOMAIN}/log"


def storage_url():
    # type: () -> str
    """Return the verifier-facing base URL of the log (https origin)."""
    return f"https://{settings.ISCC_HUB_DOMAIN}/log"


def hub_keypair():
    # type: () -> icr.KeyPair
    """Return the Hub's Ed25519 keypair from settings.ISCC_HUB_SECKEY."""
    return icr.key_from_secret(settings.ISCC_HUB_SECKEY)


def verifier_key():
    # type: () -> str
    """Return the signed-note verifier key string for this Hub's log (for fsck)."""
    pubkey = hub_keypair().pk_obj.public_bytes_raw()
    return checkpoint_note.verifier_key(log_origin(), pubkey)


def current_tree_size():
    # type: () -> int
    """Return the number of committed records (the current tree size)."""
    state = LogState.objects.filter(pk=int(settings.ISCC_HUB_ID)).first()
    return state.tree_size if state else 0


def _leaf_hashes(start, end):
    # type: (int, int) -> list[bytes]
    """Return RFC 6962 leaf hashes for records ``[start, end)`` in index order."""
    records = (
        LogRecord.objects.filter(index__gte=start, index__lt=end).order_by("index").values_list("record", flat=True)
    )
    hashes = [merkle.leaf_hash(bytes(r)) for r in records]
    # The 0-based index sequence is gapless by construction (sequencer invariant);
    # a short count means a hole in the log, which would silently sign a wrong root.
    # Fail loud instead so the lazy/scheduled builder can retry rather than publish it.
    if len(hashes) != end - start:
        raise RuntimeError(f"log gap: expected {end - start} records in [{start}, {end}), found {len(hashes)}")
    return hashes


def tree_head(size):
    # type: (int) -> bytes
    """Return the RFC 6962 tree head over the first ``size`` records."""
    return merkle.tree_head(_leaf_hashes(0, size))


def inclusion_proof(index, size):
    # type: (int, int) -> list[bytes]
    """Return the RFC 6962 inclusion proof for ``index`` against tree ``size``."""
    return merkle.inclusion_proof(index, _leaf_hashes(0, size))


def _resolve_width(avail, requested):
    # type: (int, int) -> int|None
    """
    Resolve the served width for a tile/bundle, or None if it is not published.

    :param avail: Number of complete entries currently available for this tile.
    :param requested: 0 for a full-tile request, else the requested partial width.
    :return: The width to serve (256 for full), or None to signal 404.
    """
    if avail <= 0:
        return None
    full = avail >= merkle.TILE_WIDTH
    if requested == 0:
        return merkle.TILE_WIDTH if full else None
    if requested > min(avail, merkle.TILE_WIDTH - 1):
        return None
    return requested


def get_hash_tile(level, index, width):
    # type: (int, int, int) -> bytes|None
    """
    Return the hash-tile bytes at ``level``/``index``, or None if not published.

    :param level: Tile level ``L``.
    :param index: Tile index ``K`` within the level.
    :param width: 0 for a full tile, else the requested partial width (1..255).
    :return: Concatenated 32-byte node hashes, or None for a 404.
    """
    size = current_tree_size()
    count_at_level = size >> (level * merkle.TILE_HEIGHT)
    avail = count_at_level - index * merkle.TILE_WIDTH
    w = _resolve_width(avail, width)
    if w is None:
        return None
    sub = 1 << (level * merkle.TILE_HEIGHT)
    base_leaf = index * merkle.TILE_WIDTH * sub
    local = _leaf_hashes(base_leaf, base_leaf + w * sub)
    return merkle.hash_tile(level, local)


def get_entry_bundle(index, width):
    # type: (int, int) -> bytes|None
    """
    Return the entry-bundle bytes at ``index``, or None if not published.

    :param index: Entry-bundle index ``K``.
    :param width: 0 for a full bundle, else the requested partial width (1..255).
    :return: tlog-tiles entry-bundle bytes, or None for a 404.
    """
    size = current_tree_size()
    avail = size - index * merkle.ENTRY_BUNDLE_WIDTH
    w = _resolve_width(avail, width)
    if w is None:
        return None
    start = index * merkle.ENTRY_BUNDLE_WIDTH
    records = (
        LogRecord.objects.filter(index__gte=start, index__lt=start + w)
        .order_by("index")
        .values_list("record", flat=True)
    )
    return merkle.entry_bundle([bytes(r) for r in records])


def build_checkpoint():
    # type: () -> str
    """
    Build, persist, and return a signed checkpoint at the current tree size.

    The expensive tree-head computation runs outside the lock; a short
    transaction persists the result on ``LogState`` under a monotonic guard so a
    concurrent writer never regresses a published checkpoint (ISCC-Log §8).

    :return: The full signed checkpoint text.
    """
    hub_id = int(settings.ISCC_HUB_ID)
    size = current_tree_size()
    root = tree_head(size)
    text = checkpoint_note.sign_checkpoint(log_origin(), size, root, hub_keypair())
    with transaction.atomic():
        state, _ = LogState.objects.select_for_update().get_or_create(pk=hub_id)
        if state.checkpoint:
            _, old_size, _ = checkpoint_note.parse_checkpoint(state.checkpoint)
            if old_size >= size:
                return state.checkpoint
        state.checkpoint = text
        state.save(update_fields=["checkpoint"])
        return text


def get_checkpoint():
    # type: () -> str
    """
    Return the latest signed checkpoint, refreshing it if the tree has grown.

    Refresh happens lazily on read: when the tree has grown past the persisted
    checkpoint this calls ``build_checkpoint`` (a short write under the IMMEDIATE
    lock), so a read can briefly contend the sequencer's writer lock. This is an
    accepted pilot trade-off; making reads pure (task-only publishing, read-replica
    safe) is a post-pilot change.

    :return: The full signed checkpoint text covering the current tree size.
    """
    size = current_tree_size()
    state = LogState.objects.filter(pk=int(settings.ISCC_HUB_ID)).first()
    if state and state.checkpoint:
        _, old_size, _ = checkpoint_note.parse_checkpoint(state.checkpoint)
        if old_size == size:
            return state.checkpoint
    return build_checkpoint()


def inclusion_evidence(index):
    # type: (int) -> dict|None
    """
    Build the VC ``evidence`` member proving inclusion of leaf ``index``.

    Returns an ``IsccLogInclusionProof`` carrying the verbatim signed checkpoint,
    its tree size, the leaf index, and the base64-encoded RFC 6962 inclusion
    proof — a self-verifying artifact (ISCC-Log §10.1). Returns None when no
    published checkpoint covers the leaf yet.

    :param index: Zero-based leaf index of the declaration record.
    :return: The evidence dict, or None if uncovered by the current checkpoint.
    """
    checkpoint = get_checkpoint()
    _, tree_size, _ = checkpoint_note.parse_checkpoint(checkpoint)
    if index >= tree_size:
        return None
    proof = inclusion_proof(index, tree_size)
    return {
        "type": "IsccLogInclusionProof",
        "checkpoint": checkpoint,
        "treeSize": tree_size,
        "leafIndex": index,
        "inclusionProof": [base64.b64encode(h).decode("ascii") for h in proof],
    }
