"""
Go-gated conformance tests for the ISCC-Log (the tlog-tiles acceptance gate).

These exercise the live HTTP log against the Tessera/C2SP reference tooling:

- ``notecheck`` verifies a Python-produced checkpoint with the reference
  signed-note verifier (``golang.org/x/mod/sumdb/note`` via
  ``transparency-dev/formats/note``).
- ``runfsck`` runs the Tessera ``fsck`` integrity check against a live server:
  it fetches the checkpoint, verifies the signature, walks every entry bundle,
  recomputes each leaf and hash tile, and checks the reconstructed root against
  the signed checkpoint. Passing ``fsck`` is the acceptance criterion for
  tlog-tiles conformance.

Marked ``slow`` (excluded from the default suite) and skipped when the Go
toolchain or the conformance module is unavailable, so the everyday Python
suite stays green and cross-platform with no Go.
"""

import os
import shutil
import subprocess
from pathlib import Path

import iscc_crypto as icr
import pytest
from django.conf import settings

from iscc_hub import checkpoint_note, log_tree, merkle
from tests.test_log_api import _populate_log

BASE_DIR = Path(__file__).resolve().parent.parent
CONFORMANCE_DIR = BASE_DIR / "conformance"
BIN_DIR = CONFORMANCE_DIR / "_bin"


@pytest.fixture(scope="session")
def go_tools():
    # type: () -> dict
    """Build (or rebuild) the Go conformance binaries; skip if Go is unavailable."""
    go = shutil.which("go")
    if not go or not (CONFORMANCE_DIR / "go.mod").exists():
        pytest.skip("Go toolchain or conformance module not available")
    suffix = ".exe" if os.name == "nt" else ""
    BIN_DIR.mkdir(exist_ok=True)
    tools = {}
    for name in ("notecheck", "runfsck"):
        out = BIN_DIR / f"{name}{suffix}"
        result = subprocess.run(
            [go, "build", "-o", str(out), f"./{name}"],
            cwd=str(CONFORMANCE_DIR),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"go build {name} failed:\n{result.stderr}")
        tools[name] = str(out)
    return tools


@pytest.mark.slow
def test_checkpoint_verifies_with_go_reference(go_tools):
    # type: (dict) -> None
    """A Python-produced checkpoint verifies with the Go reference note tooling."""
    keypair = icr.key_from_secret(settings.ISCC_HUB_SECKEY)
    pubkey = keypair.pk_obj.public_bytes_raw()
    origin = "testserver/log"
    leaves = [merkle.leaf_hash(f"entry-{i}".encode()) for i in range(3)]
    text = checkpoint_note.sign_checkpoint(origin, 3, merkle.tree_head(leaves), keypair)
    vkey = checkpoint_note.verifier_key(origin, pubkey)
    # Send raw bytes; text-mode stdin would translate \n -> \r\n on Windows and
    # corrupt the byte-exact note.
    result = subprocess.run(
        [go_tools["notecheck"], f"--vkey={vkey}"],
        input=text.encode("utf-8"),
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.decode().strip() == f"OK {origin}"


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_fsck_accepts_live_log(go_tools, live_server, tmp_path):
    # type: (dict, object, Path) -> None
    """Tessera fsck accepts the live ISCC-Log (the tlog-tiles acceptance gate)."""
    _populate_log(257)
    vkey_file = tmp_path / "log.vkey"
    vkey_file.write_text(log_tree.verifier_key())
    result = subprocess.run(
        [
            go_tools["runfsck"],
            f"--storage_url={live_server.url}/log",
            f"--origin={log_tree.log_origin()}",
            f"--public_key={vkey_file}",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "FSCK OK" in result.stdout
