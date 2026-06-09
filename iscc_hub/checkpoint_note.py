"""
C2SP signed-note checkpoint codec for the ISCC-Log.

Pure, dependency-light functions implementing the load-bearing checkpoint wire
format (ISCC-Log §8, C2SP tlog-checkpoint + signed-note). The bytes must match
the Go reference (golang.org/x/mod/sumdb/note) exactly, since every
Monitor/Verifier and the Tessera ``fsck`` tool parse them.

Format
------
The checkpoint body is exactly three newline-terminated lines::

    <origin>\\n<tree_size>\\n<base64(root)>\\n

The full signed checkpoint is the body, a blank separator line, then one
signature line::

    <body>\\n— <name> <base64(key_id || signature)>\\n

The Ed25519 signature is computed over the body text (up to and including its
final newline, excluding the blank separator). ``name`` equals ``origin``. The
4-byte key id is ``SHA-256(name || 0x0A || 0x01 || pubkey32)[:4]`` as a
big-endian uint32 (``0x01`` = Ed25519), prepended to the 64-byte signature and
base64-encoded.
"""

import base64
import hashlib
import struct

import iscc_crypto as icr

# signed-note algorithm identifier for Ed25519.
_ALG_ED25519 = 1
# Em dash + space that starts every signed-note signature line.
_SIG_PREFIX = "— "


def checkpoint_body(origin, tree_size, root):
    # type: (str, int, bytes) -> str
    """
    Return the three-line checkpoint body (signed-note text), newline-terminated.

    :param origin: The Hub's stable origin string (scheme-less, no trailing slash).
    :param tree_size: Number of records committed; decimal, no leading zeros.
    :param root: The 32-byte SHA-256 Merkle tree head.
    :return: The body text ending in its final newline.
    """
    return f"{origin}\n{tree_size}\n{base64.b64encode(root).decode('ascii')}\n"


def key_id(name, pubkey):
    # type: (str, bytes) -> int
    """
    Return the signed-note 4-byte key id as a big-endian uint32.

    :param name: The key name (equal to the checkpoint origin).
    :param pubkey: The 32-byte Ed25519 public key.
    :return: The key id (first 4 bytes of SHA-256(name || 0x0A || 0x01 || pubkey)).
    """
    h = hashlib.sha256()
    h.update(name.encode("utf-8"))
    h.update(b"\x0a")
    h.update(bytes([_ALG_ED25519]))
    h.update(pubkey)
    return struct.unpack(">I", h.digest()[:4])[0]


def verifier_key(name, pubkey):
    # type: (str, bytes) -> str
    """
    Return the signed-note verifier key string (``name+hash+base64``).

    This is the value passed to Tessera ``fsck --public_key`` (as a file). It is
    NOT the on-wire signature-line name, which is the bare ``name``.

    :param name: The key name (equal to the checkpoint origin).
    :param pubkey: The 32-byte Ed25519 public key.
    :return: The verifier key string.
    """
    encoded = bytes([_ALG_ED25519]) + pubkey
    return f"{name}+{key_id(name, pubkey):08x}+{base64.b64encode(encoded).decode('ascii')}"


def signature_line(name, key_hash, signature):
    # type: (str, int, bytes) -> str
    """
    Return a signed-note signature line (newline-terminated).

    :param name: The signer name (the checkpoint origin).
    :param key_hash: The signer's 4-byte key id as a uint32.
    :param signature: The 64-byte Ed25519 signature over the note text.
    :return: ``— <name> <base64(key_hash || signature)>\\n``.
    """
    value = struct.pack(">I", key_hash) + signature
    return f"{_SIG_PREFIX}{name}{' '}{base64.b64encode(value).decode('ascii')}\n"


def sign_checkpoint(origin, tree_size, root, keypair):
    # type: (str, int, bytes, icr.KeyPair) -> str
    """
    Build and sign a full C2SP checkpoint with the Hub's Ed25519 key.

    :param origin: The Hub's origin string (also the signer name).
    :param tree_size: Number of records committed.
    :param root: The 32-byte SHA-256 Merkle tree head.
    :param keypair: An iscc_crypto KeyPair (provides ``sk_obj``/``pk_obj``).
    :return: The full signed checkpoint text.
    """
    body = checkpoint_body(origin, tree_size, root)
    pubkey = keypair.pk_obj.public_bytes_raw()
    signature = keypair.sk_obj.sign(body.encode("utf-8"))
    line = signature_line(origin, key_id(origin, pubkey), signature)
    return f"{body}\n{line}"


def parse_checkpoint(text):
    # type: (str) -> tuple[str, int, bytes]
    """
    Parse a checkpoint's body into ``(origin, tree_size, root)`` (no signature check).

    :param text: The full checkpoint text (or just the body).
    :return: Tuple of (origin, tree_size, 32-byte root).
    :raises ValueError: If the body is malformed.
    """
    lines = text.split("\n")
    if len(lines) < 3:
        raise ValueError("checkpoint body has too few lines")
    origin = lines[0]
    try:
        tree_size = int(lines[1])
    except ValueError:
        raise ValueError("checkpoint tree size is not an integer") from None
    if tree_size < 0 or (lines[1] != "0" and lines[1].startswith("0")):
        raise ValueError("checkpoint tree size has leading zeros or is negative")
    try:
        root = base64.b64decode(lines[2], validate=True)
    except Exception:
        raise ValueError("checkpoint root is not valid base64") from None
    if len(root) != 32:
        raise ValueError(f"checkpoint root is {len(root)} bytes, expected 32")
    return origin, tree_size, root


def verify_checkpoint(text, name, pubkey):
    # type: (str, str, bytes) -> tuple[int, bytes]
    """
    Verify a checkpoint's Hub signature and return ``(tree_size, root)``.

    Mirrors the reference verifier: confirm the signature line carries the
    expected name and key id and that the Ed25519 signature is valid over the
    body text.

    :param text: The full signed checkpoint text.
    :param name: The expected signer name (the checkpoint origin).
    :param pubkey: The 32-byte Ed25519 public key.
    :return: Tuple of (tree_size, 32-byte root).
    :raises ValueError: If the structure or signature does not verify.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    origin, tree_size, root = parse_checkpoint(text)
    body = checkpoint_body(origin, tree_size, root)
    sep, _, sig_block = text.partition(body)
    if sep != "" or not sig_block.startswith("\n"):
        raise ValueError("checkpoint body/signature separator is malformed")
    sig_lines = [line for line in sig_block[1:].split("\n") if line]
    expected_prefix = f"{_SIG_PREFIX}{name} "
    for line in sig_lines:
        if not line.startswith(expected_prefix):
            continue
        value = base64.b64decode(line[len(expected_prefix) :], validate=True)
        if len(value) != 4 + 64:
            raise ValueError("signature value has wrong length")
        if struct.unpack(">I", value[:4])[0] != key_id(name, pubkey):
            raise ValueError("signature key id mismatch")
        try:
            ed25519.Ed25519PublicKey.from_public_bytes(pubkey).verify(value[4:], body.encode("utf-8"))
        except InvalidSignature:
            raise ValueError("checkpoint signature is invalid") from None
        return tree_size, root
    raise ValueError(f"no signature line for name {name!r}")
