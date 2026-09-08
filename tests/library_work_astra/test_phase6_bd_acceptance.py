"""BD open-item reproductions on the integrated candidate.

Assertions express the required behavior and intentionally fail while a finding
is open. Synthetic storage only, inside the existing guarded Phase 6 sandbox.
No model, helper import, external network, live DB, or existing-test edits.
"""
import copy
import json
from pathlib import Path
import sqlite3

import pytest

from tests.test_phase6_evaluation import (
    RAW_FIXTURES, STAMP, _db, _export, _fixture, _publish, _published,
    _rows, _seed, _snapshot, media, sandbox,
)
from tests.test_phase6_bc2 import (
    _artifact_path, _open_index, _replace_original, _seed_episode, _seed_index,
    _server_namespace, _youtube_sidecar,
)


@pytest.mark.parametrize("entry", ["raw", "index"])
def test_bd01_never_published_stale_snapshot_requires_original_ticket(sandbox, entry):
    """A was built before B, but an omitted ticket lets A acquire B's base."""
    env = sandbox
    idx = _open_index(env) if entry == "index" else None
    conn = idx._conn if idx else _db(env)
    try:
        base = _fixture(env, key="bd01", origin="none")
        (_seed_index(idx, base) if idx else _seed(conn, base))
        raw_a = copy.deepcopy(RAW_FIXTURES[1])
        raw_b = copy.deepcopy(raw_a)
        raw_a[0] = (0.0, 22.0, "A was built against the original source.", None)
        raw_b[0] = (0.0, 22.0, "B is the newer published source.", None)
        stale = _fixture(env, key="bd01", raw=raw_a, origin="none")
        newer = _fixture(env, key="bd01", raw=raw_b, origin="none")
        _published(_publish(conn, newer))
        before = _snapshot(conn, newer)
        try:
            if idx:
                idx.publish_media_snapshot("bd01", cues=stale.cues,
                    media_block=stale.block, artifacts=stale.files)
            else:
                _publish(conn, stale)
        except media.MediaError as exc:
            assert exc.code in {"invalid_request", "revision_unavailable"}
        assert _snapshot(conn, newer) == before, "Unfenced stale A overwrote B"
    finally:
        if idx:
            idx.close()


@pytest.mark.parametrize("mutation", ["soft_delete", "hard_delete", "title", "media"])
def test_bd02_wal_export_refuses_a_committed_concurrent_change(sandbox, mutation):
    env = sandbox
    conn = _db(env)
    assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    f = _fixture(env, key="bd02")
    _seed(conn, f)
    writer = sqlite3.connect(env.root / "index.db")
    original = media._export_range
    committed = []

    def change_during_read(snap, request, check):
        if mutation == "soft_delete":
            writer.execute("UPDATE yoinks SET deleted_at=? WHERE video_id=?", (STAMP, "bd02"))
        elif mutation == "hard_delete":
            writer.execute("DELETE FROM yoinks WHERE video_id=?", ("bd02",))
        elif mutation == "title":
            writer.execute("UPDATE yoinks SET title=? WHERE video_id=?", ("New current title", "bd02"))
        else:
            writer.execute("UPDATE media_depth SET media_revision=? WHERE video_id=?", ("e" * 64, "bd02"))
        writer.commit()
        committed.append(True)
        return original(snap, request, check)

    try:
        env.patch.setattr(media, "_export_range", change_during_read)
        result = _export(env, conn, f, start=60, end=125)
        assert committed == [True]
        assert result["ok"] is False, "WAL final recheck read the old transaction snapshot"
        assert result["error"]["code"] in {
            "revision_unavailable", "resource_deleted", "resource_not_found"}
        assert "LSM trees" not in json.dumps(result)
    finally:
        writer.close()


def test_bd03_stale_sidecar_reconstruction_cannot_roll_back_media(sandbox):
    conn = _db(sandbox)
    old = _fixture(sandbox, key="bd03")
    _seed(conn, old)
    newer = _fixture(sandbox, key="bd03", origin="none")
    _published(_publish(conn, newer))
    before = _snapshot(conn, newer)
    try:
        media.rebuild_item(conn, "bd03", sidecar=copy.deepcopy(old.sidecar))
    except media.MediaError as exc:
        assert exc.code == "revision_unavailable"
    assert _snapshot(conn, newer) == before, "Reconstruction restored superseded annotations"


def test_bd04_podcast_projection_failure_preserves_coherent_old_snapshot(sandbox):
    import podcasts
    idx = _open_index(sandbox)
    try:
        episode_id, transcript_path = _seed_episode(sandbox, idx)
        first = podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        vid = first["video_id"]
        before = {table: _rows(idx._conn, table, vid) for table in ("citations", "clips", "media_depth")}
        old_corpus = Path(first["corpus_path"]).read_bytes()
        transcript_path.write_text(json.dumps({"model": "base", "language": "en", "diarization_ran": False,
            "segments": [{"start": 0.0, "end": 5.0, "text": "Replacement before projection failure."}]}), encoding="utf-8")

        def projection_failure(*args, **kwargs):
            raise media.MediaError("library_unavailable", details={"reason": "injected_projection_failure"})

        sandbox.patch.setattr(media, "project_clips", projection_failure)
        with pytest.raises(media.MediaError):
            podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        assert Path(first["corpus_path"]).read_bytes() == old_corpus
        after = {table: _rows(idx._conn, table, vid) for table in before}
        assert after == before, "Pre-publication citation commit left new cues bound to old media"
    finally:
        idx.close()


def test_bd05_publication_preserves_another_owners_sidecar_edit(sandbox):
    conn = _db(sandbox)
    f = _fixture(sandbox, key="bd05")
    _seed(conn, f)
    ticket = media.begin_publication(conn, "bd05")
    disk = copy.deepcopy(f.sidecar)
    disk["unrelated_owner"] = {"preserve": "new edit after ticket creation"}
    path = Path(f.item["sidecar_path"])
    path.write_text(json.dumps(disk), encoding="utf-8")
    try:
        media.publish_transcript(conn, "bd05", cues=f.cues, media_block=f.block,
                                 artifacts=f.files, ticket=ticket)
    except media.MediaError as exc:
        assert exc.code == "revision_unavailable"
    assert json.loads(path.read_text(encoding="utf-8"))["unrelated_owner"] == disk["unrelated_owner"]


def test_bd06_first_publication_preserves_a_user_edited_corpus(sandbox):
    conn = _db(sandbox)
    f = _fixture(sandbox, key="bd06")
    _seed(conn, f, materialized=False)
    ticket = media.begin_publication(conn, "bd06")
    path = Path(f.item["corpus_path"])
    edited = path.read_bytes() + b"\nUser edit after the capture plan was built.\n"
    path.write_bytes(edited)
    try:
        media.publish_transcript(conn, "bd06", cues=f.cues, media_block=f.block,
                                 artifacts=f.files, ticket=ticket)
    except media.MediaError as exc:
        assert exc.code == "revision_unavailable"
    assert path.read_bytes() == edited, "Unmaterialized corpus bytes were overwritten"


@pytest.mark.parametrize("origin", ["source", "run"])
def test_bd07_export_requires_the_attributed_label_in_the_original_artifact(sandbox, origin):
    conn = _db(sandbox)
    f = _fixture(sandbox, key="bd07", origin=origin)
    artifact = json.loads(f.files[str(_artifact_path(f))])
    for row in artifact["transcript"]:
        row.pop("speaker", None)
    _replace_original(f, artifact)
    _seed(conn, f)
    result = _export(sandbox, conn, f, start=60, end=125)
    assert result["ok"] is False, "Export attributed a label absent from the sealed producer artifact"
    assert result["error"]["code"] == "invalid_source_data"


def test_bd08_capture_seam_reports_publication_failure(sandbox):
    idx = _open_index(sandbox)
    try:
        y = _youtube_sidecar(sandbox, "bd08")
        ns = _server_namespace(idx)
        y.corpus_path.write_text("# Supplied capture\n", encoding="utf-8")
        y.sidecar_path.write_text(json.dumps(y.sidecar), encoding="utf-8")

        def refuse(*args, **kwargs):
            raise media.MediaError("library_unavailable", details={"reason": "injected_projection_failure"})

        sandbox.patch.setattr(idx, "publish_media_snapshot", refuse)
        try:
            result = ns["_index_yoink"](y.folder, y.sidecar, y.corpus_path, y.sidecar_path)
        except media.MediaError as exc:
            assert exc.code == "library_unavailable"
        else:
            assert result is False, "Capture reported success despite the publication refusal"
    finally:
        idx.close()


def test_bd09_empty_capture_replacement_removes_old_transcript_and_chapters(sandbox):
    idx = _open_index(sandbox)
    try:
        y = _youtube_sidecar(sandbox, "bd09")
        ns = _server_namespace(idx)
        y.corpus_path.write_text("# Supplied capture\n", encoding="utf-8")
        y.sidecar_path.write_text(json.dumps(y.sidecar), encoding="utf-8")
        assert ns["_index_yoink"](y.folder, y.sidecar, y.corpus_path, y.sidecar_path) is True
        empty = dict(y.sidecar, transcript=[], source_chapters=[], screenshots=[])
        empty.pop("media_depth", None)
        y.sidecar_path.write_text(json.dumps(empty), encoding="utf-8")
        assert ns["_index_yoink"](y.folder, empty, y.corpus_path, y.sidecar_path) is True
        assert [r for r in idx.get_citations("bd09") if r["kind"] == "transcript_chunk"] == []
        assert _rows(idx._conn, "chapters", "bd09") == []
    finally:
        idx.close()
