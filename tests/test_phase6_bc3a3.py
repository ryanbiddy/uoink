"""BC-3a3 implementation tests: omitted tickets and sidecar dependency preservation.

Successful setup acquires a build-time ticket explicitly. Frozen acceptance
files are not edited, replaced, or deselected.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from tests.test_phase6_bc2 import _open_index
from tests.test_phase6_evaluation import (  # noqa: F401 -- sandbox is a fixture
    RAW_FIXTURES, _db, _fixture, _published, _rows, _seed, _snapshot, media, sandbox,
)


def _publish_raw(conn, f, ticket):
    return media.publish_transcript(
        conn, f.item["video_id"], cues=f.cues, media_block=f.block,
        artifacts=f.files, ticket=ticket)


def _publish_index(idx, f, ticket):
    return idx.publish_media_snapshot(
        f.item["video_id"], cues=f.cues, media_block=f.block,
        artifacts=f.files, ticket=ticket)


@pytest.mark.parametrize("entry", ["raw", "index"])
def test_bc3a3_stale_empty_build_without_a_ticket_is_refused(sandbox, entry):
    """An old empty snapshot cannot publish by omitting the build-time ticket."""
    env = sandbox
    idx = _open_index(env) if entry == "index" else None
    conn = idx._conn if idx else _db(env)
    try:
        _seed(conn, _fixture(env, key="bc3a3-empty", origin="none"))
        newer = _fixture(
            env, key="bc3a3-empty", raw=RAW_FIXTURES[1][:3], origin="none",
            corpus="# Newer published source\n")
        if idx:
            ticket = idx.begin_media_publication("bc3a3-empty")
            _published(_publish_index(idx, newer, ticket))
        else:
            ticket = media.begin_publication(conn, "bc3a3-empty")
            _published(_publish_raw(conn, newer, ticket))
        before = _snapshot(conn, newer)
        empty = _fixture(
            env, key="bc3a3-empty", raw=[], chapters=[], origin="none",
            corpus="# Empty stale build\n")
        with pytest.raises(media.MediaError) as caught:
            if idx:
                idx.publish_media_snapshot(
                    "bc3a3-empty", cues=empty.cues, media_block=empty.block,
                    artifacts=empty.files)
            else:
                media.publish_transcript(
                    conn, "bc3a3-empty", cues=empty.cues, media_block=empty.block,
                    artifacts=empty.files)
        assert caught.value.code == "invalid_request"
        assert caught.value.details["reason"] == "publication_ticket_required"
        assert _snapshot(conn, newer) == before

        if idx:
            owned = idx.begin_media_publication("bc3a3-empty")
            _published(_publish_index(idx, empty, owned))
        else:
            owned = media.begin_publication(conn, "bc3a3-empty")
            _published(_publish_raw(conn, empty, owned))
        assert _rows(conn, "citations", "bc3a3-empty") == []
        assert _rows(conn, "clips", "bc3a3-empty") == []
    finally:
        if idx:
            idx.close()


def test_bc3a3_stale_sidecar_reconstruction_refuses_after_ticketed_publication(sandbox):
    """Ledger-fenced reconstruction cannot restore a superseded sidecar."""
    env = sandbox
    conn = _db(env)
    old = _fixture(env, key="bc3a3-bd03")
    _seed(conn, old)
    newer = _fixture(env, key="bc3a3-bd03", origin="none")
    ticket = media.begin_publication(conn, "bc3a3-bd03")
    _published(_publish_raw(conn, newer, ticket))
    before = _snapshot(conn, newer)
    with pytest.raises(media.MediaError) as caught:
        media.rebuild_item(conn, "bc3a3-bd03", sidecar=copy.deepcopy(old.sidecar))
    assert caught.value.code == "revision_unavailable"
    assert _snapshot(conn, newer) == before
    assert not conn.in_transaction


def test_bc3a3_publication_preserves_removed_and_late_edited_sidecar_keys(sandbox):
    """Another owner's removed key stays gone; a late edit survives publication."""
    env = sandbox
    conn = _db(env)
    seeded = _fixture(env, key="bc3a3-side")
    _seed(conn, seeded)
    ticket = media.begin_publication(conn, "bc3a3-side")
    path = Path(seeded.item["sidecar_path"])
    disk = json.loads(path.read_text(encoding="utf-8"))
    assert disk["unrelated_owner"] == {"preserve": "concurrent-feature-value"}
    disk.pop("unrelated_owner")
    disk["late_owner"] = {"preserve": "edit after ticket mint"}
    path.write_text(json.dumps(disk), encoding="utf-8")
    replacement = _fixture(
        env, key="bc3a3-side", origin="none",
        corpus="# Replacement carrying the original ticket\n")
    assert "unrelated_owner" in replacement.sidecar
    _published(_publish_raw(conn, replacement, ticket))
    published = json.loads(path.read_text(encoding="utf-8"))
    assert "unrelated_owner" not in published
    assert published["late_owner"] == {"preserve": "edit after ticket mint"}
    assert published["media_depth"]["media_revision"] == replacement.block["media_revision"]


def test_bc3a3_final_sidecar_write_revalidates_intervening_dependency_edits(sandbox):
    """Non-owned sidecar edits made after the ledger claim still win."""
    env = sandbox
    conn = _db(env)
    seeded = _fixture(env, key="bc3a3-final")
    _seed(conn, seeded)
    ticket = media.begin_publication(conn, "bc3a3-final")
    path = Path(seeded.item["sidecar_path"])
    replacement = _fixture(
        env, key="bc3a3-final", origin="none",
        corpus="# Replacement that revalidates at the carrier write\n")
    real_replace = os.replace

    def edit_after_ledger(src, dst, *args, **kwargs):
        if Path(dst).name == media.PUBLICATION_LEDGER:
            disk = json.loads(path.read_text(encoding="utf-8"))
            disk.pop("unrelated_owner", None)
            disk["late_owner"] = {"preserve": "edit after ledger claim"}
            path.write_text(json.dumps(disk), encoding="utf-8")
        return real_replace(src, dst, *args, **kwargs)

    with env.patch.context() as patch:
        patch.setattr(os, "replace", edit_after_ledger)
        _published(_publish_raw(conn, replacement, ticket))
    published = json.loads(path.read_text(encoding="utf-8"))
    assert "unrelated_owner" not in published
    assert published["late_owner"] == {"preserve": "edit after ledger claim"}
    assert published["media_depth"]["media_revision"] == replacement.block["media_revision"]
