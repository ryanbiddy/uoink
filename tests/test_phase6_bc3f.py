"""BC-3f implementation tests: consumed capture inputs inside publication.

Successful setup uses the real owner or an explicit build-time ticket.
Frozen acceptance files are not edited, replaced, or deselected. A caller
check before invoking the publisher is not the publication lock.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from tests.test_phase6_bc2 import _open_index, _seed_episode, _server_namespace, _youtube_sidecar
from tests.test_phase6_bc3a3 import _publish_raw
from tests.test_phase6_evaluation import (  # noqa: F401 -- sandbox is a fixture
    _db, _fixture, _rows, _seed, media, sandbox,
)


def _publication(idx, video_id, sidecar_path):
    return {
        "rows": {name: _rows(idx._conn, name, video_id)
                 for name in ("citations", "clips", "media_depth", "chapters")},
        "sidecar": Path(sidecar_path).read_bytes(),
    }


def _db_rows(conn, video_id):
    return {name: _rows(conn, name, video_id)
            for name in ("citations", "clips", "media_depth", "chapters")}


def _rewrite_caption(path, text):
    disk = json.loads(Path(path).read_text(encoding="utf-8"))
    disk["transcript"][0]["text"] = text
    Path(path).write_text(json.dumps(disk), encoding="utf-8")
    return Path(path).read_bytes()


def test_bc3f_publisher_entry_preserves_late_caption_correction(sandbox):
    """A caption rewrite at Index.publish_media_snapshot entry is kept."""
    idx = _open_index(sandbox)
    try:
        item = _youtube_sidecar(sandbox, "bc3f-entry", transcript=[(0.0, 10.0, "Held caption A.")])
        item.corpus_path.write_text("# Held capture\n", encoding="utf-8")
        item.sidecar_path.write_text(json.dumps(item.sidecar), encoding="utf-8")
        owner = _server_namespace(idx)["_index_yoink"]
        assert owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path) is True
        original_publish = idx.publish_media_snapshot
        edited = []

        def change_dependency_at_entry(*args, **kwargs):
            edited.append(_rewrite_caption(
                item.sidecar_path, "Independent pending caption correction B."))
            return original_publish(*args, **kwargs)

        sandbox.patch.setattr(idx, "publish_media_snapshot", change_dependency_at_entry)
        try:
            owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(edited) == 1
        assert json.loads(item.sidecar_path.read_text(encoding="utf-8"))["transcript"][0]["text"] == \
            "Independent pending caption correction B."
        assert item.sidecar_path.read_bytes() == edited[0]
    finally:
        idx.close()


def test_bc3f_raw_publisher_entry_preserves_late_caption_correction(sandbox):
    """Raw publish_transcript rechecks consumed inputs before any write."""
    env = sandbox
    conn = _db(env)
    seeded = _fixture(env, key="bc3f-raw")
    _seed(conn, seeded)
    ticket = media.begin_publication(conn, "bc3f-raw")
    path = Path(seeded.item["sidecar_path"])
    replacement = _fixture(
        env, key="bc3f-raw", origin="none",
        corpus="# Replacement carrying the original ticket\n")
    before = _db_rows(conn, "bc3f-raw")
    edited = [_rewrite_caption(path, "Independent pending caption correction B.")]
    try:
        _publish_raw(conn, replacement, ticket)
    except media.MediaError as exc:
        assert exc.code in {"revision_unavailable", "invalid_request"}
        assert exc.details["reason"] == "publication_input_changed"
    else:
        raise AssertionError("changed caption at raw publication entry was written")
    assert _db_rows(conn, "bc3f-raw") == before
    assert path.read_bytes() == edited[0]


def test_bc3f_final_sidecar_replace_preserves_late_caption_correction(sandbox):
    """A caption rewrite after the ledger claim is not overwritten."""
    env = sandbox
    conn = _db(env)
    seeded = _fixture(env, key="bc3f-final")
    _seed(conn, seeded)
    ticket = media.begin_publication(conn, "bc3f-final")
    path = Path(seeded.item["sidecar_path"])
    replacement = _fixture(
        env, key="bc3f-final", origin="none",
        corpus="# Replacement that revalidates at the carrier write\n")
    before = _db_rows(conn, "bc3f-final")
    real_replace = os.replace
    edited = []

    def edit_after_ledger(src, dst, *args, **kwargs):
        if Path(dst).name == media.PUBLICATION_LEDGER:
            edited.append(_rewrite_caption(
                path, "Independent pending caption correction B."))
        return real_replace(src, dst, *args, **kwargs)

    with env.patch.context() as patch:
        patch.setattr(os, "replace", edit_after_ledger)
        try:
            _publish_raw(conn, replacement, ticket)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
            assert exc.details["reason"] == "publication_input_changed"
        else:
            raise AssertionError("changed caption at the final carrier write was overwritten")
    assert len(edited) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["transcript"][0]["text"] == \
        "Independent pending caption correction B."
    assert path.read_bytes() == edited[0]
    assert _db_rows(conn, "bc3f-final") == before


def test_bc3f_publisher_refuses_sidecar_removal_without_replacing_it(sandbox):
    """A sidecar removed at publisher entry stays gone."""
    idx = _open_index(sandbox)
    try:
        item = _youtube_sidecar(sandbox, "bc3f-removed", transcript=[(0.0, 10.0, "Held caption A.")])
        item.corpus_path.write_text("# Held capture\n", encoding="utf-8")
        item.sidecar_path.write_text(json.dumps(item.sidecar), encoding="utf-8")
        owner = _server_namespace(idx)["_index_yoink"]
        assert owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path) is True
        original_publish = idx.publish_media_snapshot
        removed = []

        def remove_at_entry(*args, **kwargs):
            item.sidecar_path.unlink()
            removed.append(True)
            return original_publish(*args, **kwargs)

        sandbox.patch.setattr(idx, "publish_media_snapshot", remove_at_entry)
        try:
            owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert removed == [True]
        assert not item.sidecar_path.exists()
    finally:
        idx.close()


def test_bc3f_publisher_entry_preserves_changed_transcript_source(sandbox):
    """A consumed non-transcript field changed at publisher entry is kept."""
    idx = _open_index(sandbox)
    try:
        item = _youtube_sidecar(sandbox, "bc3f-source")
        item.corpus_path.write_text("# Held capture\n", encoding="utf-8")
        item.sidecar_path.write_text(json.dumps(item.sidecar), encoding="utf-8")
        owner = _server_namespace(idx)["_index_yoink"]
        assert owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path) is True
        original_publish = idx.publish_media_snapshot
        edited = []

        def change_source_at_entry(*args, **kwargs):
            disk = json.loads(item.sidecar_path.read_text(encoding="utf-8"))
            disk["transcript_source"] = "corrected_captions"
            item.sidecar_path.write_text(json.dumps(disk), encoding="utf-8")
            edited.append(item.sidecar_path.read_bytes())
            return original_publish(*args, **kwargs)

        sandbox.patch.setattr(idx, "publish_media_snapshot", change_source_at_entry)
        try:
            owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(edited) == 1
        assert json.loads(item.sidecar_path.read_text(encoding="utf-8"))["transcript_source"] == \
            "corrected_captions"
        assert item.sidecar_path.read_bytes() == edited[0]
    finally:
        idx.close()


def test_bc3f_podcast_publisher_entry_preserves_changed_transcript_file(sandbox):
    """A podcast transcript rewrite at publish_media_snapshot entry is kept."""
    import podcasts
    idx = _open_index(sandbox)
    try:
        episode_id, transcript_path = _seed_episode(sandbox, idx)
        first = podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        before = _publication(idx, first["video_id"], first["sidecar_path"])
        original_publish = idx.publish_media_snapshot
        edited = []

        def change_transcript_at_entry(*args, **kwargs):
            transcript_path.write_text(json.dumps({
                "model": "base", "language": "en", "diarization_ran": False,
                "segments": [{"start": 0.0, "end": 5.0,
                              "text": "Independent pending podcast correction B."}],
            }), encoding="utf-8")
            edited.append(transcript_path.read_bytes())
            return original_publish(*args, **kwargs)

        sandbox.patch.setattr(idx, "publish_media_snapshot", change_transcript_at_entry)
        try:
            podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(edited) == 1
        assert transcript_path.read_bytes() == edited[0]
        assert json.loads(transcript_path.read_text(encoding="utf-8"))["segments"][0]["text"] == \
            "Independent pending podcast correction B."
        assert _publication(idx, first["video_id"], first["sidecar_path"]) == before
    finally:
        idx.close()
