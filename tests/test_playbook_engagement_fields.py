"""T1: capture-time engagement snapshots and a bounded, local-only backfill."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import types
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("engagement tests must not use the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.fixture
def capture_env(tmp_path, monkeypatch, no_network):
    import index
    import server

    root = tmp_path / "corpus"
    root.mkdir()
    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "DESKTOP_ROOT", root)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_backfill_cancel", threading.Event())
        monkeypatch.setattr(server, "_read_settings", lambda: {})
        monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "")
        for name in ("_download_thumbnail", "_start_comments_thread",
                     "_start_entity_extraction_thread", "_incremental_index_update",
                     "_mirror_event"):
            monkeypatch.setattr(server, name, lambda *a, **k: None)
        monkeypatch.setattr(server, "_fetch_channel_context", lambda *a, **k: {})
        yield server, idx, root


@pytest.fixture
def ytdlp_metadata():
    return {
        "id": "fixture1234", "title": "Local engagement fixture",
        "channel": "Fixture creator", "duration": 12,
        "view_count": 1200, "like_count": 45, "upload_date": "20261001",
        "comment_count": 7, "channel_follower_count": 3200,
    }


def _mock_ytdlp_and_ffmpeg(cmd, **kwargs):
    parts = [str(part) for part in cmd]
    if parts[0].endswith("ffmpeg"):
        shot = Path(parts[-1].replace("%04d", "0001"))
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"fixture-jpeg")
    elif "-o" in parts:
        folder = Path(parts[parts.index("-o") + 1]).parent
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "video.mp4").write_bytes(b"fixture-media")
        (folder / "video.en.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nA fixture transcript.\n",
            encoding="utf-8")
    return subprocess.CompletedProcess(cmd, 0, b"", b"")


@pytest.mark.parametrize("url,source_type,platform", [
    ("https://www.youtube.com/watch?v=fixture1234", None, "youtube"),
    ("https://www.youtube.com/watch?v=fixture1234", "short_video", "youtube"),
    ("https://www.tiktok.com/@fixture/video/7300000000000000000", "short_video", "tiktok"),
    ("https://www.instagram.com/reel/Fixture1234/", "short_video", "instagram"),
])
@pytest.mark.parametrize("count", [7, 0, None])
def test_ytdlp_engagement_reaches_sidecar_and_index(
        capture_env, monkeypatch, ytdlp_metadata, url, source_type, platform, count):
    server, idx, root = capture_env
    metadata = dict(ytdlp_metadata, comment_count=count, channel_follower_count=count)
    if count is None:
        metadata.pop("comment_count")
        metadata.pop("channel_follower_count")
    monkeypatch.setattr(server, "_fetch_metadata", lambda *a, **k: metadata)
    monkeypatch.setattr(server, "_run_subprocess", _mock_ytdlp_and_ffmpeg)
    folder = root / "fixture"
    result = server._run_extraction(
        url, 30, folder, notify=False, source_type=source_type, generate_paste=False)
    assert result["ok"] is True
    sidecar = json.loads((folder / "fixture.json").read_text(encoding="utf-8"))
    row = idx.get_yoink(metadata["id"])
    assert row["platform"] == platform
    assert row["source_type"] == (source_type or "video")
    indexed = json.loads(row["metadata_json"])
    for data in (sidecar, indexed):
        assert data["comment_count"] == count
        assert data["channel_follower_count"] == count
        for key in ("view_count", "like_count", "upload_date"):
            assert data[key] == metadata[key]


@pytest.mark.parametrize("metrics", [
    {"view_count": 1200, "like_count": 45, "upload_date": "20261001"},
    {"view_count": 0, "like_count": 0, "upload_date": None},
    {},
])
def test_generic_capture_indexes_engagement(capture_env, monkeypatch, metrics):
    server, idx, _ = capture_env
    metadata = {"id": "generic-fixture", "title": "Generic fixture", **metrics}
    monkeypatch.setattr(server, "_fetch_metadata", lambda *a, **k: metadata)
    monkeypatch.setattr(server, "_extract_generic_transcript", lambda *a: [])
    handler = types.SimpleNamespace(_send_json=lambda status, body: (status, body))
    status, body = server.Handler._handle_extract_any(
        handler, {"url": "https://video.example.test/fixture"})
    assert status == 200
    assert body["ok"] is True
    # Generic extractor IDs are scoped to the URL by the capture lane. Locate
    # the saved capture through the handler's slug, not the upstream basename.
    row = idx.get_by_slug(body["video_slug"])
    indexed = json.loads(row["metadata_json"])
    sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
    for data in (indexed, sidecar):
        for key in ("view_count", "like_count", "upload_date"):
            assert data[key] == metrics.get(key)


def test_comment_id_and_timestamp_are_additive(capture_env):
    server, _, root = capture_env
    comment = {
        "id": "yt-comment-123", "timestamp": 1790812800,
        "author": "Fixture commenter", "text": "A fixture question?",
        "like_count": 0, "_time_text": "two weeks ago", "is_pinned": True,
        "is_favorited": False, "reply_count": 2, "author_thumbnail": "unused",
    }
    shaped = server._shape_comment_for_sidecar(comment)
    assert shaped == {
        "id": "yt-comment-123", "timestamp": 1790812800,
        "author": "Fixture commenter", "text": "A fixture question?",
        "like_count": 0, "time_text": "two weeks ago", "is_pinned": True,
        "is_favorited": False, "reply_count": 2,
    }
    absent = server._shape_comment_for_sidecar({"text": "legacy"})
    assert absent["id"] is None
    assert absent["timestamp"] is None
    assert server._shape_comment_for_sidecar({"timestamp": 0})["timestamp"] == 0
    sidecar = root / f"{root.name}.json"
    sidecar.write_text('{"title": "Preserved"}', encoding="utf-8")
    server._update_sidecar_comments(root, [shaped], "fetched")
    stored = json.loads(sidecar.read_text(encoding="utf-8"))
    assert stored == {"title": "Preserved", "comments": [shaped],
                      "comments_status": "fetched"}


def _legacy_capture(idx, root, video_id, *, metadata=None, sidecar=None, raw=None):
    folder = root / video_id
    folder.mkdir()
    sidecar_path = folder / f"{video_id}.json"
    sidecar_path.write_text(json.dumps(sidecar or {}), encoding="utf-8")
    corpus_path = folder / "corpus.md"
    corpus_path.write_text("Fixture corpus must remain unchanged.", encoding="utf-8")
    if raw is not None:
        (folder / "metadata.json").write_text(json.dumps(raw), encoding="utf-8")
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id,
        "title": "Preserved title", "source_type": "video",
        "yoinked_at": "2026-10-15T12:00:00", "sidecar_path": str(sidecar_path),
        "corpus_path": str(corpus_path), "metadata_json": json.dumps(metadata or {}),
    }, content="Preserved searchable corpus")
    return folder


def test_backfill_raw_fixture_updates_only_index_metadata(capture_env, ytdlp_metadata):
    server, idx, root = capture_env
    raw = dict(ytdlp_metadata, id="legacy", formats=[{"url": "unused"}])
    folder = _legacy_capture(
        idx, root, "legacy", metadata={"view_count": 0, "like_count": None,
                                      "custom": {"preserve": True}},
        sidecar={"video_id": "legacy", "like_count": 11}, raw=raw)
    files_before = {path: path.read_bytes() for path in folder.iterdir()}
    row_before = idx.get_yoink("legacy")
    fts_before = list(idx._conn.execute("SELECT * FROM yoinks_fts"))
    changes_before = idx._conn.total_changes
    result = server._run_engagement_backfill_tick()
    assert result["scanned"] == result["updated"] == 1
    assert result["bytes_read"] == sum(
        len(data) for path, data in files_before.items() if path.suffix == ".json")
    after = idx.get_yoink("legacy")
    assert json.loads(after.pop("metadata_json")) == {
        "view_count": 0, "like_count": 11, "upload_date": "20261001",
        "comment_count": 7, "channel_follower_count": 3200,
        "custom": {"preserve": True},
    }
    row_before.pop("metadata_json")
    assert after == row_before
    assert idx._conn.total_changes - changes_before == 1
    assert list(idx._conn.execute("SELECT * FROM yoinks_fts")) == fts_before
    assert {path: path.read_bytes() for path in folder.iterdir()} == files_before
    assert server._run_engagement_backfill_tick(result["after_video_id"])["complete"]
    assert server._run_engagement_backfill_tick()["updated"] == 0


def test_backfill_limits_rows_and_resumes_past_missing_files(capture_env):
    server, idx, root = capture_env
    for number in range(28):
        folder = _legacy_capture(idx, root, f"v{number:02d}", raw={"comment_count": 0})
        if number == 0:
            (folder / "metadata.json").unlink()
            (folder / "v00.json").unlink()
    first = server._run_engagement_backfill_tick()
    assert first["scanned"] == 25
    assert first["updated"] == 24
    assert first["after_video_id"] == "v24"
    assert json.loads(idx.get_yoink("v25")["metadata_json"]) == {}
    second = server._run_engagement_backfill_tick(first["after_video_id"])
    assert second["scanned"] == second["updated"] == 3
    assert server._run_engagement_backfill_tick(second["after_video_id"])["complete"]


def _padded_json(path, size):
    data = path.read_bytes()
    assert len(data) <= size
    with path.open("wb") as stream:
        stream.write(data)
        stream.write(b" " * (size - len(data)))


def test_backfill_32mb_budget_defers_rows_and_skips_oversized_files(capture_env, monkeypatch):
    server, idx, root = capture_env
    cap = 32 * 1024 * 1024
    assert server._ENGAGEMENT_BACKFILL_MAX_BYTES == cap
    for video_id, size in (("a", 20 * 1024 * 1024), ("b", 20 * 1024 * 1024),
                           ("c", cap + 1)):
        folder = _legacy_capture(idx, root, video_id, raw={"comment_count": 7})
        (folder / f"{video_id}.json").unlink()
        _padded_json(folder / "metadata.json", size)
    reads = []
    original_open = Path.open

    @contextmanager
    def tracked_open(path, mode="r", *args, **kwargs):
        with original_open(path, mode, *args, **kwargs) as stream:
            assert mode == "rb"
            assert path.parent.name != "c", "oversized input must not be opened"

            def read(size=-1):
                assert 0 <= size <= cap
                data = stream.read(size)
                reads.append(len(data))
                return data

            yield types.SimpleNamespace(read=read, fileno=stream.fileno)

    monkeypatch.setattr(Path, "open", tracked_open)
    first = server._run_engagement_backfill_tick()
    assert first["scanned"] == first["updated"] == 1
    assert first["bytes_read"] == 20 * 1024 * 1024
    assert sum(reads) == first["bytes_read"] <= cap
    reads.clear()
    second = server._run_engagement_backfill_tick(first["after_video_id"])
    assert second["scanned"] == 2
    assert second["updated"] == 1
    assert second["bytes_read"] == 20 * 1024 * 1024
    assert sum(reads) == second["bytes_read"] <= cap
    assert json.loads(idx.get_yoink("c")["metadata_json"]) == {}
    assert server._run_engagement_backfill_tick(second["after_video_id"])["complete"]


def test_backfill_accepts_exact_byte_cap_and_advances(capture_env):
    server, idx, root = capture_env
    folder = _legacy_capture(idx, root, "a", raw={"comment_count": 0})
    (folder / "a.json").unlink()
    _padded_json(folder / "metadata.json", 32 * 1024 * 1024)
    _legacy_capture(idx, root, "b", raw={"comment_count": 5})
    first = server._run_engagement_backfill_tick()
    assert first["bytes_read"] == 32 * 1024 * 1024
    assert first["updated"] == 1
    assert first["after_video_id"] == "a"
    assert json.loads(idx.get_yoink("a")["metadata_json"]) == {"comment_count": 0}
    second = server._run_engagement_backfill_tick(first["after_video_id"])
    assert second["updated"] == 1
    assert second["after_video_id"] == "b"


def test_backfill_oversized_row_does_not_starve_later_captures(capture_env):
    server, idx, root = capture_env
    folder = _legacy_capture(idx, root, "a", sidecar={"view_count": 12},
                             raw={"comment_count": 7})
    for filename in ("a.json", "metadata.json"):
        _padded_json(folder / filename, 20 * 1024 * 1024)
    _legacy_capture(idx, root, "b", raw={"comment_count": 9})
    result = server._run_engagement_backfill_tick()
    assert result["scanned"] == result["updated"] == 2
    assert result["bytes_read"] <= 32 * 1024 * 1024
    assert json.loads(idx.get_yoink("a")["metadata_json"]) == {"view_count": 12}
    assert json.loads(idx.get_yoink("b")["metadata_json"]) == {"comment_count": 9}


@pytest.mark.parametrize("bad", [b"not json", b"[]", b"null", b"\xff"])
def test_backfill_malformed_raw_does_not_block_later_rows(capture_env, bad):
    server, idx, root = capture_env
    folder = _legacy_capture(idx, root, "a")
    (folder / "metadata.json").write_bytes(bad)
    _legacy_capture(idx, root, "b", raw={"comment_count": 9})
    result = server._run_engagement_backfill_tick()
    assert result["scanned"] == 2
    assert result["updated"] == 1
    assert json.loads(idx.get_yoink("a")["metadata_json"]) == {}
    assert json.loads(idx.get_yoink("b")["metadata_json"])["comment_count"] == 9


def test_backfill_skips_deleted_mismatched_and_invalid_index_rows(capture_env):
    server, idx, root = capture_env
    for video_id in ("deleted", "mismatch", "invalid"):
        _legacy_capture(idx, root, video_id, raw={"id": "other", "comment_count": 5})
    with idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET deleted_at='2026-10-15' WHERE video_id='deleted'")
        conn.execute("UPDATE yoinks SET metadata_json='[]' WHERE video_id='invalid'")
    result = server._run_engagement_backfill_tick()
    assert result["scanned"] == 2
    assert result["updated"] == 0
    assert idx.get_yoink("invalid")["metadata_json"] == "[]"


@pytest.mark.parametrize("change", ["metadata", "deleted", "recaptured", "moved"])
def test_backfill_preserves_concurrent_changes(capture_env, change):
    _, idx, root = capture_env
    _legacy_capture(idx, root, "legacy")
    snapshot = idx.engagement_backfill_batch()[0]
    with idx.write_transaction() as conn:
        if change == "metadata":
            conn.execute("UPDATE yoinks SET metadata_json=? WHERE video_id='legacy'",
                         (json.dumps({"comment_count": 0, "new_field": "kept"}),))
        elif change == "deleted":
            conn.execute("UPDATE yoinks SET deleted_at='2026-10-15' WHERE video_id='legacy'")
        elif change == "recaptured":
            conn.execute("UPDATE yoinks SET yoinked_at='2026-10-16' WHERE video_id='legacy'")
        else:
            conn.execute("UPDATE yoinks SET sidecar_path='moved.json' WHERE video_id='legacy'")
    before = idx.get_yoink("legacy")
    assert not idx.backfill_engagement_metadata(snapshot, {"comment_count": 99, "url": "bad"})
    assert idx.get_yoink("legacy") == before


def test_backfill_respects_index_transaction_ownership(capture_env):
    _, idx, root = capture_env
    _legacy_capture(idx, root, "legacy")
    snapshot = idx.engagement_backfill_batch()[0]
    with idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET title='uncommitted' WHERE video_id='legacy'")
        with pytest.raises(RuntimeError, match="another transaction is active"):
            idx.backfill_engagement_metadata(snapshot, {"comment_count": 7})
        assert conn.in_transaction
        with pytest.raises(RuntimeError, match="another transaction is active"):
            idx.engagement_backfill_batch()


def test_startup_runs_bounded_ticks_until_complete(capture_env, monkeypatch):
    server, _, _ = capture_env
    starts, cursors, waits = [], [], []
    monkeypatch.setattr(server, "_run_backfill", lambda: None)
    monkeypatch.setattr(server, "_run_phase2_author_backfill_once", lambda: None)
    monkeypatch.setattr(server.threading, "Thread", lambda **kw:
                        types.SimpleNamespace(start=lambda: starts.append(kw["target"])))
    monkeypatch.setattr(server._backfill_cancel, "wait", lambda seconds: waits.append(seconds))

    def tick(cursor):
        cursors.append(cursor)
        return {"after_video_id": "v24", "complete": bool(cursor)}

    monkeypatch.setattr(server, "_run_engagement_backfill_tick", tick)
    server._start_backfill_thread()
    assert len(starts) == 1
    starts[0]()
    assert cursors == ["", "v24"]
    assert waits == [30]
