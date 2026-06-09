"""
Tests for the ISCC-Log HTTP read surface and the content-negotiation routing fix.

The hash-tile / entry-bundle / checkpoint endpoints are cross-checked against the
checked-in Go reference vectors by populating LogRecord with the same canonical
record content (``iscc-log-entry-<i>``). The routing fix is guarded by fetching
the binary/JSON endpoints with no Accept header (as Go clients and fsck do).
"""

import json
from datetime import UTC, datetime
from functools import lru_cache
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from iscc_hub import checkpoint_note, log_tree, merkle
from iscc_hub.iscc_id import IsccID
from iscc_hub.models import LogRecord, LogState

VECTORS_PATH = Path(__file__).resolve().parent / "vectors" / "tlog_kat.json"
SAMPLE_PUBKEY = "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1"
SAMPLE_DATAHASH = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"


@lru_cache(maxsize=1)
def _vectors():
    # type: () -> dict
    """Load and cache the checked-in KAT vectors."""
    return json.loads(VECTORS_PATH.read_text())


def _populate_log(n):
    # type: (int) -> None
    """Insert n LogRecords with the canonical KAT record content and set tree_size=n."""
    base_ts = 1735689600_000_000
    rows = []
    for i in range(n):
        rows.append(
            LogRecord(
                index=i,
                record=f"iscc-log-entry-{i}".encode(),
                iscc_id=bytes(IsccID.from_timestamp(base_ts + i, 1)),
                type=LogRecord.RecordType.DECLARATION,
                nonce=f"{i:032x}",
                datahash=SAMPLE_DATAHASH,
                pubkey=SAMPLE_PUBKEY,
                event_time=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
    LogRecord.objects.bulk_create(rows)
    LogState.objects.update_or_create(pk=1, defaults={"tree_size": n, "last_timestamp_us": base_ts + n})


@pytest.mark.django_db(transaction=True)
def test_checkpoint_empty_tree(client):
    # type: (object) -> None
    """GET /log/checkpoint on an empty tree returns a verifiable size-0 checkpoint."""
    response = client.get("/log/checkpoint")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert response["Cache-Control"] == "max-age=10"
    text = response.content.decode()
    pubkey = log_tree.hub_keypair().pk_obj.public_bytes_raw()
    tree_size, root = checkpoint_note.verify_checkpoint(text, log_tree.log_origin(), pubkey)
    assert tree_size == 0
    assert root == merkle.EMPTY_ROOT


@pytest.mark.django_db(transaction=True)
def test_checkpoint_matches_reference_root(client):
    # type: (object) -> None
    """A populated checkpoint verifies and commits the Go reference root."""
    _populate_log(257)
    response = client.get("/log/checkpoint")
    assert response.status_code == 200
    pubkey = log_tree.hub_keypair().pk_obj.public_bytes_raw()
    tree_size, root = checkpoint_note.verify_checkpoint(response.content.decode(), log_tree.log_origin(), pubkey)
    assert tree_size == 257
    assert root.hex() == _vectors()["roots"]["257"]


@pytest.mark.django_db(transaction=True)
def test_hash_tiles_match_reference(client):
    # type: (object) -> None
    """Served hash tiles match the Go reference bytes for size 257."""
    _populate_log(257)
    for path, expected in _vectors()["hash_tiles"]["257"].items():
        response = client.get(f"/log/{path}")
        assert response.status_code == 200, path
        assert response["Content-Type"] == "application/octet-stream"
        assert response.content.hex() == expected, path
    # A full tile is served immutable; a partial tile is short-lived.
    assert "immutable" in client.get("/log/tile/0/000")["Cache-Control"]
    assert client.get("/log/tile/0/001.p/1")["Cache-Control"] == "max-age=10"


@pytest.mark.django_db(transaction=True)
def test_entry_bundles_match_reference(client):
    # type: (object) -> None
    """Served entry bundles match the Go reference bytes for size 257."""
    _populate_log(257)
    for path, expected in _vectors()["entry_bundles"]["257"].items():
        response = client.get(f"/log/{path}")
        assert response.status_code == 200, path
        assert response["Content-Type"] == "application/octet-stream"
        assert response.content.hex() == expected, path


@pytest.mark.django_db(transaction=True)
def test_tile_not_published_returns_404(client):
    # type: (object) -> None
    """Unpublished tiles/bundles return 404."""
    _populate_log(100)
    # Full L0 tile requested while only 100 leaves exist (a partial).
    assert client.get("/log/tile/0/000").status_code == 404
    # Partial wider than the available tree.
    assert client.get("/log/tile/0/000.p/101").status_code == 404
    assert client.get("/log/tile/entries/000.p/101").status_code == 404
    # Index beyond the tree.
    assert client.get("/log/tile/0/005").status_code == 404
    assert client.get("/log/tile/entries/005").status_code == 404
    # Available partial prefixes are served.
    assert client.get("/log/tile/0/000.p/99").status_code == 200
    assert client.get("/log/tile/entries/000.p/99").status_code == 200
    assert client.get("/log/tile/0/000.p/100").status_code == 200
    assert client.get("/log/tile/entries/000.p/100").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_published_partial_widths_remain_available_as_log_grows(client):
    # type: (object) -> None
    """Checkpoint-derived partial tile and bundle widths stay fetchable after growth."""
    _populate_log(99)
    log_tree.get_checkpoint()
    old_tile = client.get("/log/tile/0/000.p/99")
    old_bundle = client.get("/log/tile/entries/000.p/99")
    assert old_tile.status_code == 200
    assert old_bundle.status_code == 200

    _populate_log_extend(99, 100)
    assert client.get("/log/tile/0/000.p/99").content == old_tile.content
    assert client.get("/log/tile/entries/000.p/99").content == old_bundle.content

    _populate_log_extend(100, 256)
    assert client.get("/log/tile/0/000.p/99").content == old_tile.content
    assert client.get("/log/tile/entries/000.p/99").content == old_bundle.content
    assert client.get("/log/tile/0/000").status_code == 200
    assert client.get("/log/tile/entries/000").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_tile_malformed_path_returns_404(client):
    # type: (object) -> None
    """Malformed tile paths and out-of-range levels return 404."""
    _populate_log(3)
    assert client.get("/log/tile/0/00a").status_code == 404
    assert client.get("/log/tile/0/000.p/0").status_code == 404
    assert client.get("/log/tile/64/000").status_code == 404
    assert client.get("/log/tile/entries/x12/000").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_inclusion_proof_reconstructs_checkpoint_root(client):
    # type: (object) -> None
    """log_tree.inclusion_proof yields a proof that reconstructs the checkpoint root."""
    _populate_log(257)
    size = log_tree.current_tree_size()
    root = log_tree.tree_head(size)
    proof = log_tree.inclusion_proof(256, size)
    leaf = merkle.leaf_hash(b"iscc-log-entry-256")
    assert merkle.root_from_inclusion_proof(leaf, 256, size, proof) == root


@pytest.mark.django_db(transaction=True)
def test_checkpoint_is_monotonic_and_cached(client):
    # type: (object) -> None
    """A refreshed checkpoint never regresses and is reused when the size is unchanged."""
    _populate_log(3)
    first = log_tree.get_checkpoint()
    # Same size: served from the persisted state verbatim.
    assert log_tree.get_checkpoint() == first
    # Grow the tree; the checkpoint advances.
    _populate_log_extend(3, 257)
    grown = log_tree.get_checkpoint()
    assert grown != first
    _, size, _ = checkpoint_note.parse_checkpoint(grown)
    assert size == 257


def _populate_log_extend(start, end):
    # type: (int, int) -> None
    """Append records [start, end) to an already-populated log and bump tree_size."""
    base_ts = 1735689600_000_000
    rows = [
        LogRecord(
            index=i,
            record=f"iscc-log-entry-{i}".encode(),
            iscc_id=bytes(IsccID.from_timestamp(base_ts + i, 1)),
            type=LogRecord.RecordType.DECLARATION,
            nonce=f"{i:032x}",
            datahash=SAMPLE_DATAHASH,
            pubkey=SAMPLE_PUBKEY,
            event_time=datetime(2025, 1, 1, tzinfo=UTC),
        )
        for i in range(start, end)
    ]
    LogRecord.objects.bulk_create(rows)
    LogState.objects.update_or_create(pk=1, defaults={"tree_size": end, "last_timestamp_us": base_ts + end})


def test_storage_url_derives_from_domain():
    # type: () -> None
    """storage_url is the https log prefix derived from the Hub domain."""
    assert log_tree.storage_url() == "https://testserver/log"


def test_verifier_key_matches_checkpoint_codec():
    # type: () -> None
    """The Hub verifier key is the signed-note vkey for its origin and public key."""
    pubkey = log_tree.hub_keypair().pk_obj.public_bytes_raw()
    assert log_tree.verifier_key() == checkpoint_note.verifier_key(log_tree.log_origin(), pubkey)


@pytest.mark.django_db(transaction=True)
def test_build_checkpoint_idempotent_under_unchanged_size():
    # type: () -> None
    """Rebuilding at an unchanged size returns the persisted checkpoint (monotonic guard)."""
    _populate_log(3)
    first = log_tree.build_checkpoint()
    assert log_tree.build_checkpoint() == first


@pytest.mark.django_db(transaction=True)
def test_inclusion_evidence_none_when_uncovered():
    # type: () -> None
    """inclusion_evidence returns None for a leaf index the checkpoint does not cover."""
    _populate_log(3)
    assert log_tree.inclusion_evidence(3) is None


@pytest.mark.django_db(transaction=True)
def test_tree_head_detects_log_gap():
    # type: () -> None
    """Requesting more leaves than exist fails loud instead of signing a short tree."""
    _populate_log(3)
    with pytest.raises(RuntimeError, match="log gap"):
        log_tree.tree_head(5)


@pytest.mark.django_db(transaction=True)
def test_log_endpoints_reachable_without_accept_header(client):
    # type: (object) -> None
    """The routing fix makes /log/* reachable to clients that send no Accept header."""
    _populate_log(3)
    for headers in ({}, {"HTTP_ACCEPT": "*/*"}):
        cp = client.get("/log/checkpoint", **headers)
        assert cp.status_code == 200
        assert cp["Content-Type"] == "text/plain; charset=utf-8"
        tile = client.get("/log/tile/0/000.p/3", **headers)
        assert tile.status_code == 200
        assert tile["Content-Type"] == "application/octet-stream"


@pytest.mark.django_db(transaction=True)
def test_refresh_checkpoint_command_persists_checkpoint():
    # type: () -> None
    """The refresh_checkpoint command persists a signed checkpoint at the current tree size."""
    _populate_log(5)
    assert LogState.objects.get(pk=1).checkpoint == ""  # nothing published yet
    out = StringIO()
    call_command("refresh_checkpoint", stdout=out)
    state = LogState.objects.get(pk=1)
    _, tree_size, _ = checkpoint_note.parse_checkpoint(state.checkpoint)
    assert tree_size == log_tree.current_tree_size() == 5
    assert "tree size 5" in out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_search_and_receipt_reachable_without_accept_header(client, minimal_iscc_note):
    # type: (object, dict) -> None
    """/search and the receipt GET are reachable without an Accept header."""
    from iscc_hub.sequencer import sequence_iscc_note

    _, iscc_id_bytes = sequence_iscc_note(minimal_iscc_note)
    iscc_id = str(IsccID(iscc_id_bytes))
    datahash = minimal_iscc_note["datahash"]

    for headers in ({}, {"HTTP_ACCEPT": "*/*"}):
        search = client.get(f"/search?datahash={datahash}", **headers)
        assert search.status_code == 200
        assert "json" in search["Content-Type"]
        assert any(item["iscc_id"] == iscc_id for item in search.json())

        receipt = client.get(f"/declaration/{iscc_id}/receipt", **headers)
        assert receipt.status_code == 200
        assert "json" in receipt["Content-Type"]
