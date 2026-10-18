"""AV-5m4a3 focused tests: operation-bound temp identity at cleanup and publish.

Does not edit frozen AW-6 or parent-interceptor fixtures.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import pytest

import library_mirror as mirror
import library_mirror_vault_io as vault_io
from tests.library_work_astra.test_phase4_aw_acceptance import env, export, item_file, mutate_clip


def test_write_error_does_not_unlink_replacement_after_handle_close(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("w")
    target = root / "alloc.bin"
    personal = b"INDEPENDENT AFTER WRITE HANDLE CLOSED"
    real_close = os.close
    real_write = os.write

    def write_fails(_fd, _data):
        raise OSError("injected write failure")

    def close_then_plant(fd):
        real_close(fd)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        planted = os.open(str(target), flags, 0o644)
        try:
            real_write(planted, personal)
        finally:
            real_close(planted)

    monkeypatch.setattr(os, "write", write_fails)
    monkeypatch.setattr(os, "close", close_then_plant)
    payload = base64.b64encode(b"allocation-bytes").decode("ascii")
    with pytest.raises(OSError, match="injected write failure"):
        vault_io._handle({"cmd": "write", "path": str(target), "b64": payload})
    assert target.is_file()
    assert target.read_bytes() == personal


def test_worker_replace_does_not_adopt_replaced_temp(tmp_path_factory):
    root = tmp_path_factory.mktemp("r")
    session = mirror._VaultIoSession.start(str(root))
    try:
        src = root / "t.tmp"
        dst = root / "dest.bin"
        prior = b"PRIOR DEST BYTES"
        dst.write_bytes(prior)
        data = b"allocation-bytes"
        written = session.write_file(str(src), data)
        held = root / "t.tmp.held"
        src.rename(held)
        personal = b"INDEPENDENT USER FILE AT THE FORMER TEMP PATH"
        src.write_bytes(personal)
        with pytest.raises(OSError):
            session.replace(
                str(src),
                str(dst),
                expected_file_id=int(written["file_id"]),
                expected_volume_id=int(written["volume_id"]),
                expected_hash=hashlib.sha256(data).hexdigest(),
            )
        assert src.is_file() and src.read_bytes() == personal
        assert held.is_file() and held.read_bytes() == data
        assert dst.read_bytes() == prior
    finally:
        session.terminate()


def test_finally_cleanup_retains_intent_when_temp_name_changed_owners(env, monkeypatch):
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    target = item_file(env)
    prior = target.read_bytes()
    original_replace = env.mirror._io_replace
    replacements = []
    personal = b"INDEPENDENT USER FILE AT THE FORMER TEMP PATH"

    def replace_then_fail(src, dst):
        if Path(dst) != target:
            return original_replace(src, dst)
        temp = Path(src)
        moved = temp.with_name(temp.name + ".held")
        temp.rename(moved)
        temp.write_bytes(personal)
        replacements.append((temp, moved))
        raise OSError("publication unavailable after the temp name changed owners")

    monkeypatch.setattr(env.mirror, "_io_replace", replace_then_fail)
    env.mirror.resync()
    assert len(replacements) == 1
    temp, moved = replacements[0]
    assert moved.is_file()
    assert temp.is_file() and temp.read_bytes() == personal
    assert target.read_bytes() == prior
    intent = env.mirror._load_intents().get(mirror.item_key("a")) or {}
    pending = mirror._pending_temps_from_intent(intent)
    assert pending, "failed publication dropped unresolved temp intent"


def test_recorded_cleanup_still_preserves_same_byte_replacement(tmp_path_factory):
    root = tmp_path_factory.mktemp("u")
    session = mirror._VaultIoSession.start(str(root))
    try:
        original = root / "t.bin"
        data = b"same-bytes-are-not-identity"
        written = session.write_file(str(original), data)
        moved = root / "kept.bin"
        original.rename(moved)
        original.write_bytes(data)
        result = session.unlink(
            str(original),
            expected_file_id=int(written["file_id"]),
            expected_volume_id=int(written["volume_id"]),
            expected_hash=hashlib.sha256(data).hexdigest(),
        )
        assert result.get("not_ours")
        assert original.read_bytes() == data
        assert moved.read_bytes() == data
    finally:
        session.terminate()
