"""BD-2: ownership must cover the inputs read by the real publishing owner.

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


def test_bd2_capture_owner_cannot_rebase_already_read_cues_onto_a_new_publication(sandbox):
    idx = _open_index(sandbox)
    try:
        old = _youtube_sidecar(sandbox, "bd2-capture", transcript=[(0.0, 10.0, "Older captured input.")])
        newer = _youtube_sidecar(sandbox, "bd2-capture", transcript=[(0.0, 10.0, "Newer completed publication.")])
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


def test_bd2_podcast_owner_cannot_rebase_already_read_transcript_onto_a_new_publication(sandbox):
    import podcasts
    idx = _open_index(sandbox)
    try:
        episode_id, transcript_path = _seed_episode(sandbox, idx)
        first = podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        original_begin = idx.begin_media_publication
        completed = []

        def competing_publication_before_ticket(*args, **kwargs):
            sandbox.patch.setattr(idx, "begin_media_publication", original_begin)
            transcript_path.write_text(json.dumps({
                "model": "base", "language": "en", "diarization_ran": False,
                "segments": [{"start": 0.0, "end": 5.0, "text": "Newer completed podcast input."}],
            }), encoding="utf-8")
            newer = podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
            completed.append(_publication(idx, newer["video_id"], newer["sidecar_path"]))
            return original_begin(*args, **kwargs)

        sandbox.patch.setattr(idx, "begin_media_publication", competing_publication_before_ticket)
        try:
            podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(completed) == 1
        assert _publication(idx, first["video_id"], first["sidecar_path"]) == completed[0], \
            "Podcast owner minted a current ticket for already-read stale transcript and replaced the newer publication"
    finally:
        idx.close()


def test_bd2_podcast_owner_cannot_publish_never_seen_stale_input_after_a_newer_owner(sandbox):
    import podcasts
    idx = _open_index(sandbox)
    try:
        episode_id, transcript_path = _seed_episode(sandbox, idx)
        first = podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        transcript_path.write_text(json.dumps({
            "model": "base", "language": "en", "diarization_ran": False,
            "segments": [{"start": 0.0, "end": 5.0, "text": "Never-published pending input A."}],
        }), encoding="utf-8")
        original_begin = idx.begin_media_publication
        completed = []

        def competing_publication_before_ticket(*args, **kwargs):
            sandbox.patch.setattr(idx, "begin_media_publication", original_begin)
            transcript_path.write_text(json.dumps({
                "model": "base", "language": "en", "diarization_ran": False,
                "segments": [{"start": 0.0, "end": 5.0, "text": "Completed newer input B."}],
            }), encoding="utf-8")
            newer = podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
            completed.append({
                "media_revision": _rows(idx._conn, "media_depth", newer["video_id"])[0]["media_revision"],
                "texts": [r["text"] for r in idx.get_citations(newer["video_id"])],
                "sidecar": Path(newer["sidecar_path"]).read_bytes(),
                "corpus": Path(newer["corpus_path"]).read_bytes(),
            })
            return original_begin(*args, **kwargs)

        sandbox.patch.setattr(idx, "begin_media_publication", competing_publication_before_ticket)
        try:
            podcasts.episode_to_corpus(idx, episode_id, data_root=sandbox.root)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(completed) == 1
        after = {
            "media_revision": _rows(idx._conn, "media_depth", first["video_id"])[0]["media_revision"],
            "texts": [r["text"] for r in idx.get_citations(first["video_id"])],
            "sidecar": Path(first["sidecar_path"]).read_bytes(),
            "corpus": Path(first["corpus_path"]).read_bytes(),
        }
        assert after == completed[0], "Never-published stale podcast A replaced completed B"
    finally:
        idx.close()
