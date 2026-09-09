"""BD-3 review probe: capture ownership includes provenance, not only cue text.

Synthetic files and the existing isolated Phase 6 fixture only. Each competing
publication completes through its real owner. No existing test is changed.
"""
import json
from pathlib import Path

from tests.test_phase6_evaluation import _rows, media, sandbox
from tests.test_phase6_bc2 import _open_index, _seed_episode, _server_namespace, _youtube_sidecar


def _publication(idx, video_id, sidecar_path):
    return {
        "rows": {name: _rows(idx._conn, name, video_id)
                 for name in ("citations", "clips", "media_depth", "chapters")},
        "sidecar": Path(sidecar_path).read_bytes(),
    }


def test_bd3_capture_owner_cannot_replace_newer_provenance_with_identical_cue_text(sandbox):
    idx = _open_index(sandbox)
    try:
        old = _youtube_sidecar(sandbox, "bd2-capture", transcript=[(0.0, 10.0, "Older captured input.")])
        newer = _youtube_sidecar(sandbox, "bd2-capture", transcript=[(0.0, 10.0, "Older captured input.")])
        old.sidecar["transcript_source"] = "older_captions"
        newer.sidecar["transcript_source"] = "corrected_captions"
        ns = _server_namespace(idx)
        old.corpus_path.write_text("# Supplied capture\n", encoding="utf-8")
        old.sidecar_path.write_text(json.dumps(old.sidecar), encoding="utf-8")
        original_begin = idx.begin_media_publication
        completed = []

        def competing_publication_before_ticket(*args, **kwargs):
            # The intercepted operation has read its inputs already on the
            # defective candidate. A complete newer owner wins before mint.
            sandbox.patch.setattr(idx, "begin_media_publication", original_begin)
            newer.sidecar_path.write_text(json.dumps(newer.sidecar), encoding="utf-8")
            assert ns["_index_yoink"](newer.folder, newer.sidecar, newer.corpus_path, newer.sidecar_path) is True
            completed.append(_publication(idx, "bd2-capture", newer.sidecar_path))
            return original_begin(*args, **kwargs)

        sandbox.patch.setattr(idx, "begin_media_publication", competing_publication_before_ticket)
        try:
            ns["_index_yoink"](old.folder, old.sidecar, old.corpus_path, old.sidecar_path)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(completed) == 1
        assert _publication(idx, "bd2-capture", newer.sidecar_path) == completed[0], \
            "Capture owner minted a current ticket for already-read stale cues and replaced the newer publication"
    finally:
        idx.close()

