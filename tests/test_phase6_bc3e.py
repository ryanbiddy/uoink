"""BC-3e implementation tests: capture ownership binds every consumed input.

Successful setup uses the real capture owner. Frozen acceptance files are
not edited, replaced, or deselected. Comparing only start/end/text cannot
certify an unchanged capture plan.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests.test_phase6_bc2 import _open_index, _server_namespace, _youtube_sidecar
from tests.test_phase6_evaluation import (  # noqa: F401 -- sandbox is a fixture
    _rows, media, sandbox,
)


def _publication(idx, video_id, sidecar_path):
    return {
        "rows": {name: _rows(idx._conn, name, video_id)
                 for name in ("citations", "clips", "media_depth", "chapters")},
        "sidecar": Path(sidecar_path).read_bytes(),
    }


def _mutate(sidecar, kind):
    sidecar = copy.deepcopy(sidecar)
    if kind == "transcript_source":
        sidecar["transcript_source"] = "corrected_captions"
    elif kind == "cue_link":
        sidecar["transcript"][0]["source_url"] = "https://example.invalid/other"
        sidecar["transcript"][0]["source_deep_link"] = "https://example.invalid/other?t=0"
        sidecar["transcript"][0]["youtube_deep_link"] = None
    elif kind == "speaker_provenance":
        sidecar["transcript"][0]["speaker"] = "Host"
        sidecar["transcript"][0]["speaker_provenance"] = {
            "origin": "source", "cue_revision": "0" * 64, "cue_hash": "0" * 64,
            "source": None, "run_id": None,
        }
    elif kind == "playback_identity":
        sidecar["url"] = "https://example.invalid/watch?v=other-id"
        sidecar["source_url"] = sidecar["url"]
    elif kind == "chapter_metadata":
        sidecar["source_chapters"][0]["extra"] = "corrected chapter metadata"
    else:
        raise AssertionError(kind)
    return sidecar


@pytest.mark.parametrize("kind", [
    "transcript_source",
    "cue_link",
    "speaker_provenance",
    "playback_identity",
    "chapter_metadata",
])
def test_bc3e_capture_owner_binds_every_consumed_input(sandbox, kind):
    """A newer owner that corrects a consumed field keeps that snapshot."""
    idx = _open_index(sandbox)
    try:
        old = _youtube_sidecar(
            sandbox, "bc3e-bind", transcript=[(0.0, 10.0, "Identical cue text.")])
        newer = _youtube_sidecar(
            sandbox, "bc3e-bind", transcript=[(0.0, 10.0, "Identical cue text.")])
        old.sidecar["transcript_source"] = "older_captions"
        newer.sidecar = _mutate(newer.sidecar, kind)
        if kind != "transcript_source":
            newer.sidecar["transcript_source"] = "older_captions"
        ns = _server_namespace(idx)
        old.corpus_path.write_text("# Supplied capture\n", encoding="utf-8")
        old.sidecar_path.write_text(json.dumps(old.sidecar), encoding="utf-8")
        original_begin = idx.begin_media_publication
        completed = []

        def competing_publication_before_ticket(*args, **kwargs):
            sandbox.patch.setattr(idx, "begin_media_publication", original_begin)
            newer.sidecar_path.write_text(json.dumps(newer.sidecar), encoding="utf-8")
            assert ns["_index_yoink"](
                newer.folder, newer.sidecar, newer.corpus_path, newer.sidecar_path) is True
            completed.append(_publication(idx, "bc3e-bind", newer.sidecar_path))
            return original_begin(*args, **kwargs)

        sandbox.patch.setattr(idx, "begin_media_publication", competing_publication_before_ticket)
        try:
            ns["_index_yoink"](old.folder, old.sidecar, old.corpus_path, old.sidecar_path)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(completed) == 1
        assert _publication(idx, "bc3e-bind", newer.sidecar_path) == completed[0]
    finally:
        idx.close()


def test_bc3e_sealed_artifact_override_requires_bound_consumed_inputs(sandbox):
    """Sealed producer bytes may differ only while consumed inputs match."""
    idx = _open_index(sandbox)
    try:
        y = _youtube_sidecar(sandbox, "bc3e-override")
        ns = _server_namespace(idx)
        y.corpus_path.write_text("# Supplied capture\n", encoding="utf-8")
        y.sidecar_path.write_text(json.dumps(y.sidecar), encoding="utf-8")
        assert ns["_index_yoink"](y.folder, y.sidecar, y.corpus_path, y.sidecar_path) is True
        before = _publication(idx, "bc3e-override", y.sidecar_path)
        plan = ns["_capture_media_plan"](y.sidecar, y.folder, item=idx.get_yoink("bc3e-override"))
        record = json.loads(plan["artifact"].decode("utf-8"))
        record["bd_original_metadata_provenance"] = {"keep": "sealed-study-artifact"}
        plan["artifact"] = media.canonical_json(record).encode("utf-8")
        plan["digest"] = hashlib.sha256(plan["artifact"]).hexdigest()
        assert ns["_publish_capture_media"](
            idx, y.folder, y.sidecar, y.corpus_path, y.sidecar_path, plan) is True
        stored = json.loads((y.folder / media.MEDIA_INPUTS_DIR / (plan["digest"] + ".json"))
                            .read_text(encoding="utf-8"))
        assert stored["bd_original_metadata_provenance"] == {"keep": "sealed-study-artifact"}

        stale = copy.deepcopy(y.sidecar)
        stale["transcript_source"] = "older_captions"
        stale_plan = ns["_capture_media_plan"](stale, y.folder, item=idx.get_yoink("bc3e-override"))
        stale_record = json.loads(stale_plan["artifact"].decode("utf-8"))
        stale_record["bd_original_metadata_provenance"] = {"keep": "stale-override"}
        stale_plan["artifact"] = media.canonical_json(stale_record).encode("utf-8")
        stale_plan["digest"] = hashlib.sha256(stale_plan["artifact"]).hexdigest()
        original_begin = idx.begin_media_publication
        completed = []

        def competing_publication_before_ticket(*args, **kwargs):
            sandbox.patch.setattr(idx, "begin_media_publication", original_begin)
            newer = copy.deepcopy(y.sidecar)
            newer["transcript_source"] = "corrected_captions"
            y.sidecar_path.write_text(json.dumps(newer), encoding="utf-8")
            assert ns["_index_yoink"](y.folder, newer, y.corpus_path, y.sidecar_path) is True
            completed.append(_publication(idx, "bc3e-override", y.sidecar_path))
            return original_begin(*args, **kwargs)

        bound = _publication(idx, "bc3e-override", y.sidecar_path)
        sandbox.patch.setattr(idx, "begin_media_publication", competing_publication_before_ticket)
        try:
            ns["_publish_capture_media"](
                idx, y.folder, stale, y.corpus_path, y.sidecar_path, stale_plan)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(completed) == 1
        assert _publication(idx, "bc3e-override", y.sidecar_path) == completed[0]
        assert completed[0] != bound
        assert completed[0] != before
    finally:
        idx.close()


def test_bc3e_publication_boundary_rereads_disk_after_mint(sandbox):
    """A standalone file check after mint is not a lock on later writes."""
    idx = _open_index(sandbox)
    try:
        y = _youtube_sidecar(sandbox, "bc3e-boundary")
        ns = _server_namespace(idx)
        y.corpus_path.write_text("# Supplied capture\n", encoding="utf-8")
        y.sidecar_path.write_text(json.dumps(y.sidecar), encoding="utf-8")
        assert ns["_index_yoink"](y.folder, y.sidecar, y.corpus_path, y.sidecar_path) is True
        real_snapshot = media.capture_snapshot
        completed = []

        def complete_newer_owner_after_mint(*args, **kwargs):
            sandbox.patch.setattr(media, "capture_snapshot", real_snapshot)
            newer = copy.deepcopy(y.sidecar)
            newer["transcript_source"] = "corrected_captions"
            newer.pop("media_depth", None)
            y.sidecar_path.write_text(json.dumps(newer), encoding="utf-8")
            assert ns["_index_yoink"](
                y.folder, newer, y.corpus_path, y.sidecar_path) is True
            completed.append(_publication(idx, "bc3e-boundary", y.sidecar_path))
            return real_snapshot(*args, **kwargs)

        sandbox.patch.setattr(media, "capture_snapshot", complete_newer_owner_after_mint)
        try:
            ns["_index_yoink"](y.folder, y.sidecar, y.corpus_path, y.sidecar_path)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(completed) == 1
        assert _publication(idx, "bc3e-boundary", y.sidecar_path) == completed[0]
        assert json.loads(y.sidecar_path.read_text(encoding="utf-8"))["transcript_source"] == \
            "corrected_captions"
    finally:
        idx.close()


def test_bc3e_non_owned_sidecar_key_is_not_a_consumed_capture_input(sandbox):
    """Another owner's unrelated sidecar key is merged, not treated as a plan input."""
    idx = _open_index(sandbox)
    try:
        y = _youtube_sidecar(sandbox, "bc3e-unrelated")
        ns = _server_namespace(idx)
        y.corpus_path.write_text("# Supplied capture\n", encoding="utf-8")
        y.sidecar_path.write_text(json.dumps(y.sidecar), encoding="utf-8")
        assert ns["_index_yoink"](y.folder, y.sidecar, y.corpus_path, y.sidecar_path) is True
        original_begin = idx.begin_media_publication

        def edit_unrelated_before_ticket(*args, **kwargs):
            sandbox.patch.setattr(idx, "begin_media_publication", original_begin)
            disk = json.loads(y.sidecar_path.read_text(encoding="utf-8"))
            disk["unrelated_owner"] = {"preserve": "not a capture input"}
            y.sidecar_path.write_text(json.dumps(disk), encoding="utf-8")
            return original_begin(*args, **kwargs)

        sandbox.patch.setattr(idx, "begin_media_publication", edit_unrelated_before_ticket)
        assert ns["_index_yoink"](y.folder, y.sidecar, y.corpus_path, y.sidecar_path) is True
        published = json.loads(y.sidecar_path.read_text(encoding="utf-8"))
        assert published["unrelated_owner"] == {"preserve": "not a capture input"}
        assert published["transcript_source"] == y.sidecar["transcript_source"]
    finally:
        idx.close()
