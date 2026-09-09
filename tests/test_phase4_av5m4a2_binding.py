"""AV-5m4a2 focused tests: binding/witness, identity unlink, staged worker.

Does not edit frozen AW-4 or parent-interceptor fixtures. Those remain
observations for Ryan where they still fail.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env, export


def test_failed_initial_binding_write_leaves_no_usable_authority(env, monkeypatch):
    binding = env.mirror._dest_binding_path()
    witness = env.mirror._authority_witness_path()
    original = env.mirror._atomic_local

    def fail(path, data):
        if Path(path) in (binding, witness):
            raise OSError("injected initial binding failure")
        return original(path, data)

    monkeypatch.setattr(env.mirror, "_atomic_local", fail)
    with pytest.raises(OSError):
        env.mirror._write_dest_binding(str(env.vault), "aw-volume", False)
    assert not binding.exists()
    assert not witness.exists()


def test_witness_persistence_failure_is_not_swallowed(env, monkeypatch):
    export(env)
    binding = env.mirror._dest_binding_path()
    before = binding.read_bytes()
    payload = json.loads(before.decode("utf-8"))
    assert payload.get("consented_at_ms") == env.mirror.consent.consented_at_ms
    assert env.mirror._authority_witness_path().is_file()

    def boom(*_args, **_kwargs):
        raise OSError("witness persistence failed")

    monkeypatch.setattr(env.mirror, "_write_authority_witness", boom)
    with pytest.raises(OSError):
        env.mirror._write_dest_binding(str(env.vault), env.mirror.consent.marker, True)
    assert binding.read_bytes() == before


def test_io_unlink_without_worker_refuses_and_retains(env):
    target = env.vault / "keep.bin"
    target.write_bytes(b"retain-without-isolated-worker")
    env.mirror._vault_io = None
    with pytest.raises(OSError):
        env.mirror._io_unlink(target)
    assert target.read_bytes() == b"retain-without-isolated-worker"


def test_unknown_temp_record_has_no_deletion_authority(env):
    export(env)
    uoink = env.vault / mirror.MIRROR_ROOT
    target = uoink / "Library" / "guess.tmp"
    target.write_bytes(b"do-not-guess-this-file")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    env.mirror._start_vault_io(str(env.vault))
    try:
        status = env.mirror._try_unlink_recorded_temp(
            uoink, str(target.relative_to(uoink)), digest, expected_file_id=None,
        )
        assert status == "failed"
        assert target.read_bytes() == b"do-not-guess-this-file"
    finally:
        env.mirror._stop_vault_io()


def test_worker_unlink_preserves_same_byte_replacement(tmp_path_factory):
    root = tmp_path_factory.mktemp("u")
    session = mirror._VaultIoSession.start(str(root))
    try:
        original = root / "t.bin"
        data = b"same-bytes-are-not-identity"
        written = session.write_file(str(original), data)
        file_id = int(written["file_id"])
        volume_id = int(written["volume_id"])
        moved = root / "kept.bin"
        original.rename(moved)
        original.write_bytes(data)
        result = session.unlink(
            str(original),
            expected_file_id=file_id,
            expected_volume_id=volume_id,
            expected_hash=hashlib.sha256(data).hexdigest(),
        )
        assert result.get("not_ours")
        assert original.read_bytes() == data
        assert moved.read_bytes() == data
        assert original.stat().st_ino != file_id
    finally:
        session.terminate()


def test_newer_consent_authorizes_destination_change(env):
    export(env)
    other = env.root / "v2"
    other.mkdir()
    env.mirror.consent = replace(
        env.mirror.consent,
        destination=str(other),
        consented_at_ms=int(env.mirror.consent.consented_at_ms) + 5,
    )
    result = env.mirror.resync()
    assert result["ok"], result
    assert (other / mirror.MIRROR_ROOT / mirror.item_relpath("a")).is_file()


def test_staged_vault_worker_writes_without_source_tree():
    root = Path(mirror.__file__).resolve().parent
    stage = root / "_scratch" / ("a2s-" + uuid.uuid4().hex[:8])
    assert stage.resolve().is_relative_to(root)
    assert not stage.exists()
    staged = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(root / "build.ps1"),
         "-StageSourceOnly", "-SourceStagePath", str(stage)],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert staged.returncode == 0, staged.stdout + staged.stderr
    worker = stage / "library_mirror_vault_io.py"
    assert worker.is_file()
    dest = stage / "d"
    dest.mkdir()
    target = dest / "w.bin"
    payload = b"isolated-stage-write"
    envp = os.environ.copy()
    envp["PYTHONDONTWRITEBYTECODE"] = "1"
    envp["PYTHONPATH"] = str(stage)
    envp.pop("ANTHROPIC_API_KEY", None)
    proc = subprocess.Popen(
        [sys.executable, "-B", "-I", str(worker)],
        cwd=str(stage),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=envp,
    )
    try:
        ready_line = proc.stdout.readline()
        ready = json.loads(ready_line.decode("utf-8"))
        assert ready.get("ready")
        request = {
            "cmd": "write",
            "path": str(target),
            "b64": base64.b64encode(payload).decode("ascii"),
        }
        proc.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        proc.stdin.flush()
        result = json.loads(proc.stdout.readline().decode("utf-8"))
        assert result.get("ok"), result
        assert target.read_bytes() == payload
        assert result.get("file_id")
        proc.stdin.write(b'{"cmd":"shutdown"}\n')
        proc.stdin.flush()
        shutdown = json.loads(proc.stdout.readline().decode("utf-8"))
        assert shutdown.get("shutdown")
        proc.wait(timeout=5)
        assert proc.returncode == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(3)
    assert Path(envp["PYTHONPATH"]).resolve() == stage.resolve()
    assert Path(proc.args[-1]).resolve() == worker.resolve()
    # Isolated mode (-I) ignores PYTHONPATH and user site; the worker script
    # directory is the stage, not the live source tree.
