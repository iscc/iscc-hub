"""
Tests for iscc_hub.checkpoint_note (C2SP signed-note checkpoint codec).

Pure-Python coverage of the byte-exact checkpoint format, key-id derivation,
verifier-key string, and signature verification. A Go-gated cross-check against
the reference note tooling lives in test_conformance.py.
"""

import base64

import iscc_crypto as icr
import pytest
from django.conf import settings

from iscc_hub import checkpoint_note as cn
from iscc_hub import merkle

ORIGIN = "testserver/log"


def _keypair():
    # type: () -> icr.KeyPair
    """Return the Hub test keypair from settings."""
    return icr.key_from_secret(settings.ISCC_HUB_SECKEY)


def _pubkey():
    # type: () -> bytes
    """Return the 32-byte Ed25519 public key of the test keypair."""
    return _keypair().pk_obj.public_bytes_raw()


def test_checkpoint_body_is_three_terminated_lines():
    # type: () -> None
    """The body is exactly origin/size/base64(root), each newline-terminated."""
    root = bytes(range(32))
    body = cn.checkpoint_body(ORIGIN, 42, root)
    assert body == f"testserver/log\n42\n{base64.b64encode(root).decode()}\n"
    assert body.endswith("\n")
    assert body.count("\n") == 3


def test_key_id_known_value():
    # type: () -> None
    """key_id matches the value computed by the reference algorithm."""
    assert cn.key_id(ORIGIN, _pubkey()) == 0xD929C044


def test_verifier_key_format():
    # type: () -> None
    """The verifier key is name+hash+base64(0x01||pubkey)."""
    pub = _pubkey()
    vkey = cn.verifier_key(ORIGIN, pub)
    name, hash_hex, key_b64 = vkey.split("+")
    assert name == ORIGIN
    assert hash_hex == f"{cn.key_id(ORIGIN, pub):08x}"
    assert base64.b64decode(key_b64) == bytes([1]) + pub


def test_signature_line_structure():
    # type: () -> None
    """A signature line is '— name base64(keyid||sig)' terminated by a newline."""
    line = cn.signature_line(ORIGIN, 0x01020304, b"\xaa" * 64)
    assert line.startswith(f"— {ORIGIN} ")
    assert line.endswith("\n")
    value = base64.b64decode(line[len("— " + ORIGIN + " ") :])
    assert value[:4] == bytes([1, 2, 3, 4])
    assert value[4:] == b"\xaa" * 64


def test_sign_and_verify_round_trip():
    # type: () -> None
    """A signed checkpoint verifies and exposes the right size and root."""
    root = merkle.tree_head([merkle.leaf_hash(b"a"), merkle.leaf_hash(b"b")])
    text = cn.sign_checkpoint(ORIGIN, 2, root, _keypair())
    # Exact structure: body, blank separator, one signature line.
    body = cn.checkpoint_body(ORIGIN, 2, root)
    assert text.startswith(body + "\n— ")
    tree_size, parsed_root = cn.verify_checkpoint(text, ORIGIN, _pubkey())
    assert tree_size == 2
    assert parsed_root == root


def test_verify_empty_tree_checkpoint():
    # type: () -> None
    """The empty-tree checkpoint round-trips with size 0 and the empty root."""
    text = cn.sign_checkpoint(ORIGIN, 0, merkle.EMPTY_ROOT, _keypair())
    tree_size, root = cn.verify_checkpoint(text, ORIGIN, _pubkey())
    assert tree_size == 0
    assert root == merkle.EMPTY_ROOT


@pytest.mark.parametrize(
    "text",
    [
        "origin\n2",  # too few lines
        "origin\nnotint\nAAAA\n",  # non-integer size
        "origin\n007\nAAAA\n",  # leading zeros
        "origin\n-1\nAAAA\n",  # negative size
        "origin\n2\nnot base64!!\n",  # invalid base64 root
        f"origin\n2\n{base64.b64encode(b'short').decode()}\n",  # wrong root length
    ],
)
def test_parse_checkpoint_rejects_malformed(text):
    # type: (str) -> None
    """parse_checkpoint rejects malformed bodies."""
    with pytest.raises(ValueError):
        cn.parse_checkpoint(text)


def test_verify_rejects_missing_blank_separator():
    # type: () -> None
    """A checkpoint without the blank separator line fails verification."""
    root = merkle.EMPTY_ROOT
    body = cn.checkpoint_body(ORIGIN, 0, root)
    line = cn.signature_line(ORIGIN, cn.key_id(ORIGIN, _pubkey()), _keypair().sk_obj.sign(body.encode()))
    bad = body + line  # missing the blank separator newline
    with pytest.raises(ValueError, match="separator"):
        cn.verify_checkpoint(bad, ORIGIN, _pubkey())


def test_verify_rejects_wrong_name():
    # type: () -> None
    """Verification under the wrong signer name finds no matching signature line."""
    text = cn.sign_checkpoint(ORIGIN, 0, merkle.EMPTY_ROOT, _keypair())
    with pytest.raises(ValueError, match="no signature line"):
        cn.verify_checkpoint(text, "other/log", _pubkey())


def test_verify_rejects_no_signature_line():
    # type: () -> None
    """A checkpoint body with no signature line fails verification."""
    body = cn.checkpoint_body(ORIGIN, 0, merkle.EMPTY_ROOT)
    with pytest.raises(ValueError, match="no signature line"):
        cn.verify_checkpoint(body + "\n", ORIGIN, _pubkey())


def test_verify_rejects_key_id_mismatch():
    # type: () -> None
    """A signature line carrying the wrong key id is rejected."""
    body = cn.checkpoint_body(ORIGIN, 0, merkle.EMPTY_ROOT)
    sig = _keypair().sk_obj.sign(body.encode())
    bad_line = cn.signature_line(ORIGIN, 0xDEADBEEF, sig)
    with pytest.raises(ValueError, match="key id mismatch"):
        cn.verify_checkpoint(body + "\n" + bad_line, ORIGIN, _pubkey())


def test_verify_rejects_bad_signature_length():
    # type: () -> None
    """A signature value of the wrong length is rejected."""
    body = cn.checkpoint_body(ORIGIN, 0, merkle.EMPTY_ROOT)
    bad_line = cn.signature_line(ORIGIN, cn.key_id(ORIGIN, _pubkey()), b"short")
    with pytest.raises(ValueError, match="wrong length"):
        cn.verify_checkpoint(body + "\n" + bad_line, ORIGIN, _pubkey())


def test_verify_rejects_invalid_signature():
    # type: () -> None
    """A signature over different bytes fails Ed25519 verification."""
    body = cn.checkpoint_body(ORIGIN, 0, merkle.EMPTY_ROOT)
    wrong_sig = _keypair().sk_obj.sign(b"different message")
    bad_line = cn.signature_line(ORIGIN, cn.key_id(ORIGIN, _pubkey()), wrong_sig)
    with pytest.raises(ValueError, match="invalid"):
        cn.verify_checkpoint(body + "\n" + bad_line, ORIGIN, _pubkey())
