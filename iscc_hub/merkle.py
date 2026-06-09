"""
RFC 6962 / C2SP tlog-tiles Merkle tree primitives for the ISCC-Log.

Pure, dependency-free functions implementing the load-bearing wire formats of
the transparency log: SHA-256 RFC 6962 hashing, tree heads, inclusion and
consistency proofs, height-8 hash tiles, and tlog-tiles entry bundles. The
records are the source of truth; everything here is a deterministic function of
the committed record bytes (ISCC-Log §6, §7, §10).

Hashing is fixed to SHA-256 with no alternatives (ISCC-Log §6):

- leaf hash:      ``SHA-256(0x00 || record)``
- interior node:  ``SHA-256(0x01 || left || right)``
- empty tree:     ``SHA-256("")``

Byte-exactness is asserted against checked-in known-answer vectors generated
from the Go reference libraries (see tests/vectors/tlog_kat.json).
"""

import hashlib
import struct

# Tile height fixed at 8 by the tlog-tiles profile: a full tile holds 256 entries.
TILE_HEIGHT = 8
TILE_WIDTH = 1 << TILE_HEIGHT  # 256
ENTRY_BUNDLE_WIDTH = TILE_WIDTH  # 256

# RFC 6962 domain-separation prefixes.
_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"

# The RFC 6962 hash of an empty tree is SHA-256 of the empty string.
EMPTY_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(record):
    # type: (bytes) -> bytes
    """Return the RFC 6962 leaf hash ``SHA-256(0x00 || record)``."""
    return hashlib.sha256(_LEAF_PREFIX + record).digest()


def node_hash(left, right):
    # type: (bytes, bytes) -> bytes
    """Return the RFC 6962 interior-node hash ``SHA-256(0x01 || left || right)``."""
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


def _split(n):
    # type: (int) -> int
    """Return the largest power of two strictly less than ``n`` (``n`` >= 2)."""
    k = 1
    while (k << 1) < n:
        k <<= 1
    return k


def _mth(leaves, lo, hi):
    # type: (list[bytes], int, int) -> bytes
    """Return the RFC 6962 Merkle tree hash over ``leaves[lo:hi]`` (leaf hashes)."""
    n = hi - lo
    if n == 1:
        return leaves[lo]
    k = _split(n)
    return node_hash(_mth(leaves, lo, lo + k), _mth(leaves, lo + k, hi))


def tree_head(leaf_hashes):
    # type: (list[bytes]) -> bytes
    """
    Return the RFC 6962 tree head over the given leaf hashes.

    :param leaf_hashes: Leaf hashes (already ``leaf_hash``-ed) in record order.
    :return: 32-byte Merkle tree hash; the empty-tree root for an empty list.
    """
    if not leaf_hashes:
        return EMPTY_ROOT
    return _mth(leaf_hashes, 0, len(leaf_hashes))


def inclusion_proof(index, leaf_hashes):
    # type: (int, list[bytes]) -> list[bytes]
    """
    Return the RFC 6962 §2.1.1 inclusion proof for ``index`` in the tree.

    :param index: Zero-based leaf index to prove (``0 <= index < len``).
    :param leaf_hashes: Leaf hashes of the whole tree, in record order.
    :return: Sibling hashes a verifier combines from the leaf up to the root.
    """
    n = len(leaf_hashes)
    if not (0 <= index < n):
        raise ValueError(f"index {index} out of range for tree size {n}")
    return _path(index, leaf_hashes, 0, n)


def _path(m, leaves, lo, hi):
    # type: (int, list[bytes], int, int) -> list[bytes]
    """Return RFC 6962 PATH(m, leaves[lo:hi]) for global leaf index ``m``."""
    n = hi - lo
    if n == 1:
        return []
    k = _split(n)
    if m < lo + k:
        return _path(m, leaves, lo, lo + k) + [_mth(leaves, lo + k, hi)]
    return _path(m, leaves, lo + k, hi) + [_mth(leaves, lo, lo + k)]


def consistency_proof(old_size, leaf_hashes):
    # type: (int, list[bytes]) -> list[bytes]
    """
    Return the RFC 6962 §2.1.2 consistency proof between ``old_size`` and now.

    :param old_size: The earlier tree size ``m`` (``0 < m <= len``).
    :param leaf_hashes: Leaf hashes of the current (larger) tree, in record order.
    :return: Hashes relating the old root to the current root (empty if equal).
    """
    n = len(leaf_hashes)
    if not (0 < old_size <= n):
        raise ValueError(f"old_size {old_size} out of range for tree size {n}")
    if old_size == n:
        return []
    return _subproof(old_size, leaf_hashes, 0, n, True)


def _subproof(m, leaves, lo, hi, b):
    # type: (int, list[bytes], int, int, bool) -> list[bytes]
    """Return RFC 6962 SUBPROOF(m, leaves[lo:hi], b)."""
    n = hi - lo
    if m == n:
        return [] if b else [_mth(leaves, lo, hi)]
    k = _split(n)
    if m <= k:
        return _subproof(m, leaves, lo, lo + k, b) + [_mth(leaves, lo + k, hi)]
    return _subproof(m - k, leaves, lo + k, hi, False) + [_mth(leaves, lo, lo + k)]


def root_from_inclusion_proof(leaf, index, size, proof):
    # type: (bytes, int, int, list[bytes]) -> bytes
    """
    Reconstruct the tree root from a leaf hash and its RFC 6962 inclusion proof.

    Mirrors the reference verifier (``transparency-dev/merkle``): a Verifier
    combines the leaf with the sibling hashes and checks the result against a
    trusted checkpoint root.

    :param leaf: The leaf hash being proven.
    :param index: Zero-based leaf index.
    :param size: Tree size the proof is against (``index < size``).
    :param proof: Sibling hashes from ``inclusion_proof``.
    :return: The reconstructed 32-byte root.
    """
    if not (0 <= index < size):
        raise ValueError(f"index {index} out of range for tree size {size}")
    inner = (index ^ (size - 1)).bit_length()
    border = bin(index >> inner).count("1")
    if len(proof) != inner + border:
        raise ValueError(f"wrong proof size {len(proof)}, expected {inner + border}")
    res = leaf
    for i in range(inner):
        if (index >> i) & 1 == 0:
            res = node_hash(res, proof[i])
        else:
            res = node_hash(proof[i], res)
    for i in range(inner, inner + border):
        res = node_hash(proof[i], res)
    return res


def hash_tile(tile_level, tile_leaf_hashes):
    # type: (int, list[bytes]) -> bytes
    """
    Return the bytes of a hash tile from the leaf hashes it covers.

    A hash tile at level ``L`` holds the complete perfect-subtree hashes at tree
    level ``L * 8``, concatenated as 32-byte values (tlog-tiles §7.1).

    :param tile_level: Tile level ``L`` (0 = leaf-level tile).
    :param tile_leaf_hashes: The leaf hashes under this tile (the records whose
        leaves fall in ``[K*256*2^(L*8), …)``), enough to form ``W`` complete
        subtrees of ``2^(L*8)`` leaves each.
    :return: Concatenated 32-byte node hashes (``W * 32`` bytes).
    """
    sub = 1 << (tile_level * TILE_HEIGHT)
    width = len(tile_leaf_hashes) // sub
    return b"".join(_mth(tile_leaf_hashes, j * sub, (j + 1) * sub) for j in range(width))


def entry_bundle(records):
    # type: (list[bytes]) -> bytes
    """
    Return the tlog-tiles entry-bundle bytes for a list of record byte strings.

    Each record is framed as a single big-endian ``uint16`` length prefix
    followed by the record bytes; frames are concatenated with no trailing
    length (C2SP tlog-tiles entry-bundle encoding).

    :param records: Record byte strings in index order (up to 256).
    :return: The concatenated entry-bundle bytes.
    """
    return b"".join(struct.pack(">H", len(r)) + r for r in records)


def format_index(n):
    # type: (int) -> str
    """
    Encode a tile/bundle index in the tlog-tiles thousands-grouped path form.

    Digits are grouped in threes from the least-significant end, each group
    zero-padded to three digits; every group except the least-significant is
    ``x``-prefixed and groups are slash-separated (e.g. ``1234067`` ->
    ``x001/x234/067``).
    """
    s = f"{n % 1000:03d}"
    n //= 1000
    while n > 0:
        s = f"x{n % 1000:03d}/{s}"
        n //= 1000
    return s


def tile_path(level, index, width=0):
    # type: (int, int, int) -> str
    """Return the tlog-tiles hash-tile path ``tile/<L>/<N>[.p/<W>]``."""
    suffix = f".p/{width}" if width else ""
    return f"tile/{level}/{format_index(index)}{suffix}"


def entries_path(index, width=0):
    # type: (int, int) -> str
    """Return the tlog-tiles entry-bundle path ``tile/entries/<N>[.p/<W>]``."""
    suffix = f".p/{width}" if width else ""
    return f"tile/entries/{format_index(index)}{suffix}"


def parse_tile_index(tail):
    # type: (str) -> tuple[int, int]
    """
    Parse a tlog-tiles index path tail into ``(index, width)``.

    ``width`` is 0 for a full tile, or 1..255 for a ``.p/<W>`` partial tile.
    Mirrors the reference parser (``tessera/api/layout``): all groups but the
    last are ``x``-prefixed, the last is not, and every group is exactly three
    decimal digits below 1000.

    :param tail: The path tail after the level, e.g. ``x001/x234/067.p/8``.
    :return: Tuple of (index, width).
    :raises ValueError: If the encoding is malformed.
    """
    parts = tail.split("/")
    width = 0
    if ".p" in tail:
        if len(parts) < 2 or not parts[-2].endswith(".p"):
            raise ValueError(f"malformed partial tile path: {tail}")
        try:
            width = int(parts[-1])
        except ValueError:
            raise ValueError(f"malformed tile width: {tail}") from None
        if not (1 <= width < TILE_WIDTH):
            raise ValueError(f"tile width out of range: {tail}")
        parts = parts[:-1]
        parts[-1] = parts[-1][:-2]
    if not parts or parts[-1].startswith("x"):
        raise ValueError(f"malformed tile index: {tail}")
    if any(not p.startswith("x") for p in parts[:-1]):
        raise ValueError(f"malformed tile index: {tail}")
    index = 0
    for part in parts:
        digits = part[1:] if part.startswith("x") else part
        if len(digits) != 3 or not digits.isdigit():
            raise ValueError(f"malformed tile index group: {tail}")
        index = index * 1000 + int(digits)
    return index, width
