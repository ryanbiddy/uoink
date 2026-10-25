"""Offline capture identity regressions without importing the server/profile.

Execute the production functions with synthetic media, temporary folders, and
the real index upsert against an in-memory copy of the schema.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager, nullcontext
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
import urllib.request

import pytest
import _platform
import uoink_usage


ROOT = Path(__file__).resolve().parents[1]
URL_A = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
URL_B = "https://www.youtube.com/watch?v=bbbbbbbbbbb"


def _load(path, names, scope, *, constants=(), class_name=None):
    scope.setdefault("uoink_usage", uoink_usage)
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    body = tree.body
    if class_name:
        body = next(n.body for n in body
                    if isinstance(n, ast.ClassDef) and n.name == class_name)
    nodes = [n for n in body if (
        isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names
    ) or (
        isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in constants for t in n.targets)
    ) or (
        isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
        and n.target.id in constants
    )]
    assert {n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef))} == set(names)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(module, str(path), "exec"), scope)


def _metadata(url, title="Weekly update", **extra):
    video_id = parse_qs(urlparse(url).query).get("v", [None])[0]
    return {"id": video_id, "title": title, "webpage_url": url,
            "duration": 30, "channel": "Example", **extra}


def _snapshot(folder):
    return {str(p.relative_to(folder)): p.read_bytes()
            for p in folder.rglob("*") if p.is_file()}


@pytest.fixture
def capture(tmp_path, monkeypatch):
    blocked = Mock(side_effect=AssertionError("unexpected external I/O"))
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setitem(sys.modules, "channels", SimpleNamespace(tag_if_self=lambda *a: None))
    monkeypatch.setitem(sys.modules, "provenance", SimpleNamespace(
        derive_source_type=lambda **k: "video", backfill_source_types=lambda idx: None))
    monkeypatch.setitem(sys.modules, "library_media", SimpleNamespace(schema_ready=lambda c: False))
    monkeypatch.setitem(sys.modules, "yt_extract", SimpleNamespace(chapters_from_metadata=lambda m: []))

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript((ROOT / "migrations/0001_initial_schema.sql").read_text(encoding="utf-8"))
    for column, kind in (("schema_version", "INTEGER"), ("source_type", "TEXT"),
                         ("platform", "TEXT"), ("author", "TEXT"), ("deleted_at", "TEXT")):
        conn.execute(f"ALTER TABLE yoinks ADD COLUMN {column} {kind}")
    index_scope = {"threading": threading, "unicodedata": unicodedata,
                   "contextmanager": contextmanager}
    _load(ROOT / "index.py", {"_search_title_key", "_entity_keyword_score", "_search_terms", "_fts_terms"},
          index_scope, constants={"_YOINK_COLUMNS", "CURRENT_YOINK_SCHEMA", "SEARCH_STOPWORDS"})
    _load(ROOT / "index.py", {"__init__", "upsert_yoink", "get_yoink", "get_by_slug", "_notify_source_changed",
                             "_rollback_on_error"},
          index_scope, class_name="Index")
    if "def list_capture_sources(" in (ROOT / "index.py").read_text(encoding="utf-8"):
        _load(ROOT / "index.py", {"list_capture_sources"}, index_scope, class_name="Index")
    index_class = type("Index", (), {name: value for name, value in index_scope.items()
                                    if callable(value)})
    idx = index_class(conn, tmp_path / "unused-index.db")
    idx._invalidate_library_sources = Mock()
    idx.insert_citations = Mock()

    calls = []

    def fake_subprocess(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ffmpeg":
            Path(cmd[-1].replace("%04d", "0001")).write_bytes(b"jpeg")
        else:
            template = cmd[cmd.index("-o") + 1]
            Path(template.replace("%(ext)s", "mp4")).write_bytes(b"media")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def write_text(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    scope = {
        "_platform": _platform,
        "Path": Path, "json": json, "hashlib": hashlib, "re": re,
        "threading": threading, "datetime": datetime, "shutil": shutil,
        "urlparse": urlparse, "parse_qs": parse_qs, "subprocess": subprocess,
        "tempfile": tempfile, "time": time,
        "log": logging.getLogger(__name__), "index": SimpleNamespace(sqlite3=sqlite3),
        "LONG_VIDEO_MODE_FULL": "full", "LONG_VIDEO_MODE_LITE": "lite",
        "LONG_VIDEO_MODE_CHUNKED": "chunked", "LONG_VIDEO_SECONDS": 1800,
        "LITE_SHOT_INTERVAL_SEC": 120, "MAX_SCREENSHOTS": 100,
        "YTDLP_CMD": ["yt-dlp"], "YTDLP_MAX_FILESIZE_BYTES": 1024,
        "CURRENT_SIDECAR_SCHEMA": 2, "DESKTOP_ROOT": tmp_path / "library",
        "_get_index": lambda: idx, "_classify_topic": lambda m: "Test",
        "_normalize_long_video_mode": lambda mode: mode,
        "_screenshot_interval_for": lambda d, i: i,
        "_estimated_screenshot_count": lambda ds, i: 1,
        "_ytdlp_timeout_for": lambda d: 10, "_ffmpeg_timeout_for": lambda d: 10,
        "_run_subprocess": fake_subprocess, "_fetch_video_subtitles": lambda *a, **k: False,
        "_download_thumbnail": Mock(), "_fetch_channel_context": lambda *a, **k: {},
        "_screenshot_ffmpeg_command": lambda v, i, p: ["ffmpeg", str(p)],
        "_resolve_video_transcript": lambda *a, **k: ([], None, None),
        "_transcript_entries_with_links": lambda *a: [],
        "_capture_media_plan": lambda *a, **k: None,
        "_build_yoink_md": lambda **k: f"# {k['metadata']['title']}\n\nBody for {k['url']}\n",
        "_atomic_write_text": write_text, "_should_start_hook_type": lambda m: False,
        "_read_settings": lambda: {}, "_anthropic_key_for_feature": lambda f: None,
        "compute_health": lambda s: {}, "_now_iso": lambda: "2026-10-15T12:00:00",
        "_incremental_index_update": Mock(), "_start_entity_extraction_thread": Mock(),
        "_start_comments_thread": Mock(), "_generate_paste_corpus": lambda p: "paste",
        "maybe_toast": Mock(), "fmt_time": str, "_citations_from_sidecar": lambda *a: [],
        "_mirror_event": Mock(), "friendly_error": str, "machine_error_detail": str,
        "_topic_folder_name": lambda topic: topic,
        "page_extractor": SimpleNamespace(PLATFORM_YOUTUBE="youtube",
                                          platform_for=lambda *a: "youtube",
                                          author_for=lambda *a: "Example"),
    }
    _load(ROOT / "yt_extract.py", {"slugify"}, scope, constants={"_WINDOWS_RESERVED_NAMES"})
    _load(ROOT / "server.py", {
        "ExtractionPhaseError",
        "_video_capture_source", "_video_capture_id", "_video_capture_folder",
        "_verify_video_capture_folder", "_create_video_entry_folder",
        "_prepare_video_capture_folder", "_run_extraction",
        "_normalize_video_url", "_normalize_youtube_url", "_normalize_twitter_url",
        "_normalize_tiktok_url", "_normalize_instagram_url", "_detect_platform_from_url",
        "_index_yoink", "_corpus_path", "_resolve_corpus_path", "_build_corpus", "_demote_headings",
        "_playlist_worker", "_unique_child_folder", "_write_failed_marker",
        "_build_playlist_corpus", "_strip_image_refs", "_raise_if_cancelled", "_finish_job_cancelled",
    }, scope, constants={
        "_YOUTUBE_HOSTS", "_TWITTER_HOSTS", "_TIKTOK_HOSTS", "_INSTAGRAM_HOSTS",
        "_VIDEO_ID_RE", "_TWITTER_STATUS_RE", "_TWITTER_HANDLE_RE", "_INSTAGRAM_KIND_RE",
        "_PLATFORM_HOST_HINTS", "PLATFORM_YOUTUBE", "PLATFORM_TWITTER", "PLATFORM_TIKTOK",
        "PLATFORM_INSTAGRAM", "PLATFORM_GENERIC", "SOURCE_TYPE_SHORT_VIDEO",
        "_IMAGE_REF_LINE_RE",
    })
    _load(ROOT / "server.py", {"_handle_session_add", "_handle_session_close",
                               "_handle_extract_any"}, scope, class_name="Handler")
    # Optional on the base revision so recapture tests can prove behavioral
    # failures there, rather than failing to compile a newly added helper.
    if "def _indexed_video_capture(" in (ROOT / "server.py").read_text(encoding="utf-8"):
        _load(ROOT / "server.py", {"_indexed_video_capture"}, scope)

    def run(url, *, parent=None, metadata=None, folder=None):
        metadata = metadata if metadata is not None else _metadata(url)
        folder = folder or scope["_video_capture_folder"](parent or tmp_path / "Test", url, metadata)
        return scope["_run_extraction"](url, 30, folder, metadata=metadata,
                                        topic="Test", notify=False, generate_paste=False)

    state = SimpleNamespace(scope=scope, idx=idx, conn=conn, calls=calls, run=run)
    yield state
    conn.close()
    blocked.assert_not_called()


@pytest.mark.parametrize("different_topics", [False, True])
def test_same_title_captures_keep_both_files_and_index_rows(capture, tmp_path, different_topics):
    first = capture.run(URL_A, parent=tmp_path / "Topic A")
    folder_a = Path(first["folder"])
    before = _snapshot(folder_a)
    second = capture.run(URL_B, parent=tmp_path / ("Topic B" if different_topics else "Topic A"))
    folder_b = Path(second["folder"])
    assert folder_a.name != folder_b.name
    assert _snapshot(folder_a) == before
    for url, result, folder in ((URL_A, first, folder_a), (URL_B, second, folder_b)):
        assert result["ok"] is True
        assert result["video_slug"] == folder.name
        sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
        row = capture.idx.get_yoink(sidecar["video_id"])
        assert sidecar["url"] == url
        assert row["slug"] == folder.name
        assert Path(row["corpus_path"]).read_text(encoding="utf-8").count(url) == 1
    assert capture.conn.execute("SELECT count(*) FROM yoinks").fetchone()[0] == 2


def test_slug_is_stable_safe_and_keeps_identity_after_title_truncation(capture, tmp_path):
    folder = capture.scope["_video_capture_folder"]
    title = "A" * 100 + "/../CON"
    a = folder(tmp_path, URL_A, _metadata(URL_A, title))
    alias = folder(tmp_path, "https://youtu.be/aaaaaaaaaaa?t=20", _metadata(URL_A, title))
    b = folder(tmp_path, URL_B, _metadata(URL_B, title))
    assert a == alias
    assert a != b
    assert len(a.name) <= 80
    assert re.fullmatch(r"[A-Za-z0-9_-]+", a.name)


def test_url_hash_fallback_indexes_sources_without_video_ids(capture):
    urls = ["https://example.test/watch/first", "https://example.test/watch/second"]
    results = [capture.run(url, metadata=_metadata(url)) for url in urls]
    assert results[0]["video_slug"] != results[1]["video_slug"]
    rows = capture.conn.execute("SELECT * FROM yoinks").fetchall()
    assert len(rows) == 2
    assert all(row["video_id"].startswith("url_") for row in rows)
    repeated = capture.run(urls[0], metadata=_metadata(urls[0]))
    assert repeated["folder"] == results[0]["folder"]
    assert capture.conn.execute("SELECT count(*) FROM yoinks").fetchone()[0] == 2


def test_generic_metadata_id_is_verified_separately_from_library_id(capture):
    url = "https://a.example/v/clip.mp4"
    metadata = _metadata(url, id="clip")
    first = capture.run(url, metadata=metadata)
    repeated = capture.run(url, metadata=metadata)
    assert repeated["ok"] is True
    assert repeated["folder"] == first["folder"]
    folder = Path(first["folder"])
    stored_metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert stored_metadata["id"] == "clip"
    row = capture.idx.get_by_slug(folder.name)
    assert row["video_id"] != stored_metadata["id"]
    assert capture.conn.execute("SELECT count(*) FROM yoinks").fetchone()[0] == 1
    before = _snapshot(folder)
    calls_before = len(capture.calls)
    with pytest.raises(FileExistsError, match="another source"):
        capture.run(url, metadata=dict(metadata, id="different-id"))
    assert _snapshot(folder) == before
    assert len(capture.calls) == calls_before


@pytest.mark.parametrize("host", ["vm.tiktok.com", "vt.tiktok.com"])
def test_resolved_metadata_alias_allows_recapture_but_refuses_other_source(capture, host):
    url = f"https://{host}/first"
    metadata = _metadata(url, id="1234567890",
                         webpage_url="https://www.tiktok.com/@example/video/1234567890",
                         original_url=f"{url}/?share=1")
    first = capture.run(url, metadata=metadata)
    repeated = capture.run(url, metadata=metadata)
    assert repeated["ok"] is True
    assert repeated["folder"] == first["folder"]
    assert repeated["video_slug"] == first["video_slug"]
    assert capture.conn.execute("SELECT count(*) FROM yoinks").fetchone()[0] == 1

    folder = Path(first["folder"])
    before = _snapshot(folder)
    calls_before = len(capture.calls)
    # Even the same extractor ID cannot authorize a different source URL.
    other_url = f"https://{host}/second"
    with pytest.raises(FileExistsError, match="another source"):
        capture.run(other_url, metadata=_metadata(other_url, id=metadata["id"]), folder=folder)
    assert _snapshot(folder) == before
    assert len(capture.calls) == calls_before


@pytest.mark.parametrize("url_field", ["webpage_url", "original_url"])
def test_metadata_url_alias_is_ownership_evidence_without_sidecar(capture, tmp_path, url_field):
    short_url = "https://vm.tiktok.com/first"
    resolved_url = "https://www.tiktok.com/@example/video/1234567890"
    metadata = _metadata(short_url, id="1234567890",
                         webpage_url=resolved_url, original_url=short_url)
    folder = tmp_path / "legacy"
    folder.mkdir()
    (folder / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    result = capture.run(metadata[url_field], metadata=metadata, folder=folder)
    assert result["ok"] is True
    assert result["video_slug"] == folder.name


def test_matching_metadata_alias_does_not_override_conflicting_id(capture, tmp_path):
    url = "https://vm.tiktok.com/first"
    metadata = _metadata(url, id="1234567890",
                         webpage_url="https://www.tiktok.com/@example/video/1234567890",
                         original_url=url)
    folder = tmp_path / "conflicting-id"
    folder.mkdir()
    (folder / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    before = _snapshot(folder)
    with pytest.raises(FileExistsError, match="another source"):
        capture.run(url, metadata=dict(metadata, id="different-id"), folder=folder)
    assert _snapshot(folder) == before
    assert capture.calls == []


@pytest.mark.parametrize("evidence", ["sidecar", "legacy", "metadata", "unknown", "malformed"])
def test_existing_foreign_or_unverifiable_folder_is_untouched(capture, tmp_path, evidence):
    folder = tmp_path / "Weekly_update"
    folder.mkdir()
    (folder / "yoink.md").write_text("original corpus", encoding="utf-8")
    (folder / "video.mp4").write_bytes(b"original media")
    if evidence in ("sidecar", "legacy"):
        name = "yoink.json" if evidence == "legacy" else f"{folder.name}.json"
        (folder / name).write_text(json.dumps({"url": URL_A, "video_id": "aaaaaaaaaaa"}), encoding="utf-8")
    elif evidence == "metadata":
        (folder / "metadata.json").write_text(json.dumps(_metadata(URL_A)), encoding="utf-8")
    elif evidence == "malformed":
        (folder / f"{folder.name}.json").write_text("{broken", encoding="utf-8")
    before = _snapshot(folder)
    with pytest.raises((FileExistsError, ValueError)):
        capture.run(URL_B, folder=folder)
    assert _snapshot(folder) == before
    assert capture.calls == []


def test_old_title_only_folder_stays_readable_and_separate(capture, tmp_path):
    legacy = tmp_path / "Weekly_update"
    legacy.mkdir()
    (legacy / "yoink.md").write_text("old corpus", encoding="utf-8")
    (legacy / "yoink.json").write_text(json.dumps({"url": URL_A, "video_id": "aaaaaaaaaaa"}), encoding="utf-8")
    before = _snapshot(legacy)
    result = capture.run(URL_B, parent=tmp_path)
    assert Path(result["folder"]) != legacy
    assert _snapshot(legacy) == before
    assert capture.scope["_resolve_corpus_path"](legacy).read_text(encoding="utf-8") == "old corpus"
    # Explicit refresh of the old folder preserves its name and reports it.
    refreshed = capture.run(URL_A, folder=legacy)
    assert refreshed["folder"] == str(legacy)
    assert refreshed["video_slug"] == legacy.name


@pytest.mark.parametrize("failure", ["read", "claim", "mkdir"])
def test_filesystem_errors_stop_before_media_and_preserve_files(capture, tmp_path, monkeypatch, failure):
    folder = tmp_path / "existing"
    folder.mkdir()
    sidecar = folder / "existing.json"
    sidecar.write_text(json.dumps({"url": URL_A, "video_id": "aaaaaaaaaaa"}), encoding="utf-8")
    (folder / "video.mp4").write_bytes(b"keep this media")
    before = _snapshot(folder)
    if failure == "read":
        original = Path.read_text

        def fail(path, *args, **kwargs):
            if path == sidecar:
                raise PermissionError("sidecar locked")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fail)
    elif failure == "claim":
        original = Path.open

        def fail(path, *args, **kwargs):
            if path.name == ".capture-source.json":
                raise OSError("disk full")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", fail)
    else:
        monkeypatch.setattr(Path, "mkdir", Mock(side_effect=PermissionError("read-only folder")))
    with pytest.raises(OSError):
        capture.run(URL_A, folder=folder)
    assert capture.calls == []
    assert _snapshot(folder) == before


def test_claim_conflict_cannot_overwrite_an_incomplete_capture(capture, tmp_path):
    folder = tmp_path / "reserved"
    capture.scope["_prepare_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    before = _snapshot(folder)
    with pytest.raises(FileExistsError):
        capture.run(URL_B, folder=folder)
    assert _snapshot(folder) == before
    assert capture.calls == []


def test_id_without_source_url_cannot_prove_folder_ownership(capture, tmp_path):
    folder = tmp_path / "ambiguous"
    folder.mkdir()
    (folder / "metadata.json").write_text(json.dumps({"id": "aaaaaaaaaaa"}), encoding="utf-8")
    (folder / "video.mp4").write_bytes(b"original media")
    before = _snapshot(folder)
    with pytest.raises(FileExistsError, match="cannot verify"):
        capture.run(URL_A, folder=folder)
    assert _snapshot(folder) == before
    assert capture.calls == []


def test_matching_claim_does_not_override_conflicting_sidecar(capture, tmp_path):
    folder = tmp_path / "conflicting-evidence"
    capture.scope["_prepare_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    (folder / f"{folder.name}.json").write_text(
        json.dumps({"url": URL_B, "video_id": "bbbbbbbbbbb"}), encoding="utf-8")
    before = _snapshot(folder)
    with pytest.raises(FileExistsError, match="another source"):
        capture.run(URL_A, folder=folder)
    assert _snapshot(folder) == before
    assert capture.calls == []


def test_competing_claim_is_checked_before_any_capture_write(capture, tmp_path, monkeypatch):
    folder = tmp_path / "racing-capture"
    original = Path.open
    competing_claim = json.dumps({"url": URL_B, "video_id": "bbbbbbbbbbb"})

    def raced_open(path, mode="r", *args, **kwargs):
        if path == folder / ".capture-source.json" and mode == "x":
            with original(path, "x", encoding="utf-8") as stream:
                stream.write(competing_claim)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced_open)
    with pytest.raises(FileExistsError, match="another source"):
        capture.run(URL_A, folder=folder)
    assert _snapshot(folder) == {".capture-source.json": competing_claim.encode("utf-8")}
    assert capture.calls == []


@pytest.mark.parametrize("competing_url", [URL_A, URL_B])
def test_entry_reservation_checks_competing_directory(capture, tmp_path, monkeypatch, competing_url):
    folder = capture.scope["_video_capture_folder"](tmp_path, URL_A, _metadata(URL_A))
    original = Path.mkdir
    before = {}

    def raced_mkdir(path, *args, **kwargs):
        if path == folder and not before:
            original(path)
            (path / "metadata.json").write_text(json.dumps(_metadata(competing_url)), encoding="utf-8")
            (path / "video.mp4").write_bytes(b"competing media")
            before.update(_snapshot(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", raced_mkdir)
    reserve = capture.scope["_create_video_entry_folder"]
    if competing_url == URL_A:
        target = reserve(folder, URL_A, _metadata(URL_A))
        assert target != folder
        assert target.is_dir()
        assert list(target.iterdir()) == []
    else:
        with pytest.raises(FileExistsError, match="another source"):
            reserve(folder, URL_A, _metadata(URL_A))
    assert _snapshot(folder) == before
    assert capture.calls == []


def test_entry_reservation_mkdir_failure_preserves_first_capture(capture, monkeypatch):
    first = Path(capture.run(URL_A)["folder"])
    before = _snapshot(first)
    calls_before = len(capture.calls)
    original = Path.mkdir

    def fail(path, *args, **kwargs):
        if path.parent == first.parent and path != first:
            raise PermissionError("entry creation refused")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(PermissionError, match="entry creation refused"):
        capture.scope["_create_video_entry_folder"](first, URL_A, _metadata(URL_A))
    assert _snapshot(first) == before
    assert len(capture.calls) == calls_before


def test_subprocess_failure_preserves_other_same_title_capture(capture, monkeypatch):
    first = capture.run(URL_A)
    folder = Path(first["folder"])
    before = _snapshot(folder)
    monkeypatch.setitem(capture.scope, "_run_subprocess", Mock(
        side_effect=subprocess.CalledProcessError(1, ["yt-dlp"], stderr=b"download failed")))
    with pytest.raises(subprocess.CalledProcessError):
        capture.run(URL_B)
    assert _snapshot(folder) == before
    assert capture.idx.get_yoink("aaaaaaaaaaa")["slug"] == folder.name
    assert capture.idx.get_yoink("bbbbbbbbbbb") is None


def test_sqlite_slug_conflict_is_visible_and_preserves_original(capture, tmp_path):
    first = capture.run(URL_A)
    original = Path(first["folder"])
    before = _snapshot(original)
    conflicting = tmp_path / "another-topic" / original.name
    with pytest.raises(sqlite3.IntegrityError, match="yoinks.slug"):
        capture.run(URL_B, folder=conflicting)
    assert _snapshot(original) == before
    assert capture.idx.get_yoink("aaaaaaaaaaa")["corpus_path"].startswith(str(original))
    assert capture.idx.get_yoink("bbbbbbbbbbb") is None
    assert (conflicting / f"{conflicting.name}.md").is_file()


def test_injected_sqlite_constraint_error_is_not_reported_as_success(capture, monkeypatch):
    monkeypatch.setattr(capture.idx, "upsert_yoink", Mock(side_effect=sqlite3.IntegrityError("injected constraint")))
    with pytest.raises(sqlite3.IntegrityError, match="injected constraint"):
        capture.run(URL_A)
    capture.scope["_start_comments_thread"].assert_not_called()


def _session_handler(capture, tmp_path, *, reused=None):
    scope = capture.scope
    session = {"slug": "research", "name": "Research", "status": "open", "videos": []}
    folder = tmp_path / "sessions" / "research"
    scope["_session_folder"] = lambda sid: folder
    scope["_read_session"] = lambda sid: session
    scope["_write_session"] = lambda sid, value: scope["_atomic_write_text"](
        folder / "session.json", json.dumps(value))
    scope["_session_lock"] = threading.RLock()
    scope["_fetch_metadata"] = lambda url: _metadata(url)
    scope["_manual_extraction_ownership"] = lambda url: nullcontext(SimpleNamespace(
        ok=True, conflict=None, completed_while_waiting=bool(reused), reused=reused))
    handler = SimpleNamespace(
        _validate_session_id=lambda body: ("research", None),
        _validate_url_interval=lambda body: (body["url"], 30, None))
    handler._send_json = lambda status, payload: setattr(handler, "response", (status, payload))
    return handler, folder, session


def test_session_persists_actual_folders_and_close_includes_both_sources(capture, tmp_path):
    handler, folder, session = _session_handler(capture, tmp_path)
    for url in (URL_A, URL_B):
        capture.scope["_handle_session_add"](handler, {"url": url})
        assert handler.response[1]["ok"] is True
        assert session["videos"][-1]["video_slug"] == Path(handler.response[1]["folder"]).name
    saved = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    assert len({v["video_slug"] for v in saved["videos"]}) == 2
    capture.scope["_handle_session_close"](handler, {})
    assert handler.response[1]["ok"] is True
    corpus = (folder / "corpus.md").read_text(encoding="utf-8")
    assert corpus.count(f"Body for {URL_A}") == 1
    assert corpus.count(f"Body for {URL_B}") == 1


@pytest.mark.parametrize("fail_second", [False, True])
def test_repeated_session_source_keeps_first_capture(capture, tmp_path, monkeypatch, fail_second):
    handler, folder, session = _session_handler(capture, tmp_path)
    capture.scope["_handle_session_add"](handler, {"url": URL_A})
    assert handler.response[1]["ok"] is True
    first = Path(handler.response[1]["folder"])
    # Retained media must survive even if a later entry cannot finish.
    (first / "video.mp4").write_bytes(b"retained first media")
    before = _snapshot(first)
    original = capture.scope["_run_subprocess"]
    second_ffmpeg = Mock()

    def run(cmd, **kwargs):
        if cmd[0] == "ffmpeg":
            second_ffmpeg(cmd)
            if fail_second:
                raise subprocess.CalledProcessError(1, cmd, stderr=b"second ffmpeg failed")
        return original(cmd, **kwargs)

    monkeypatch.setitem(capture.scope, "_run_subprocess", run)
    capture.scope["_handle_session_add"](handler, {"url": URL_A})
    second_ffmpeg.assert_called_once()
    assert handler.response[1]["ok"] is (not fail_second)
    assert _snapshot(first) == before
    saved = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    assert len(saved["videos"]) == (1 if fail_second else 2)
    assert saved["videos"][0]["video_slug"] == first.name
    if fail_second:
        assert "ffmpeg" in handler.response[1]["error"]
        assert capture.idx.get_yoink("aaaaaaaaaaa")["slug"] == first.name
    else:
        second = Path(handler.response[1]["folder"])
        assert second != first
        assert saved["videos"][1]["video_slug"] == second.name
        assert capture.scope["_resolve_corpus_path"](second).is_file()
    capture.scope["_handle_session_close"](handler, {})
    assert handler.response[1]["ok"] is True
    assert handler.response[1]["corpus_md"].count(f"Body for {URL_A}") == len(saved["videos"])
    assert _snapshot(first) == before


@pytest.mark.parametrize("legacy_name", [False, True])
def test_reused_session_capture_keeps_resolvable_filenames(capture, tmp_path, legacy_name):
    original = capture.run(URL_A, folder=tmp_path / "Weekly_update" if legacy_name else None)
    handler, folder, session = _session_handler(capture, tmp_path, reused=original)
    capture.scope["_handle_session_add"](handler, {"url": URL_A})
    assert handler.response[1]["ok"] is True
    target = folder / session["videos"][0]["video_slug"]
    assert capture.scope["_resolve_corpus_path"](target).is_file()
    before = _snapshot(target)
    # A second copy must never merge into or overwrite an occupied folder.
    capture.scope["_handle_session_add"](handler, {"url": URL_A})
    assert handler.response[1]["ok"] is False
    assert len(session["videos"]) == 1
    assert _snapshot(target) == before


def _playlist_job(capture, tmp_path, *, urls=(URL_A,), reused=None):
    scope = capture.scope
    folder = tmp_path / "playlist"
    job = {"_folder": str(folder), "_interval": 30, "state": "queued",
           "_videos": [{"index": i, "url": url, "title": "Weekly update"}
                       for i, url in enumerate(urls, 1)]}
    scope.update({
        "_jobs": {"playlist-test": job}, "_jobs_lock": threading.RLock(),
        "_get_public_job": lambda job_id: job,
        "_update_job": lambda job_id, **values: job.update(values),
        "_job_cancel_event": lambda job_id: threading.Event(),
        "_persist_jobs_locked": Mock(), "PLAYLIST_SLEEP_SEC": 0,
        "PlaylistJobCancelled": type("PlaylistJobCancelled", (Exception,), {}),
        "_failure_phase": lambda error, phase: phase, "_is_rate_limit_error": lambda error: False,
        "_fetch_metadata": lambda url, **kwargs: _metadata(url),
        "_manual_extraction_ownership": lambda url: nullcontext(SimpleNamespace(
            raise_if_unavailable=lambda: None, conflict=None,
            completed_while_waiting=bool(reused), reused=reused)),
    })
    return job, folder


def test_playlist_success_records_actual_hash_folders(capture, tmp_path):
    job, folder = _playlist_job(capture, tmp_path, urls=(URL_A, URL_B))
    capture.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == "completed"
    assert job["videos_done"] == 2
    assert job["videos_failed"] == 0
    assert len({item["folder"] for item in job["per_video"]}) == 2
    for item in job["per_video"]:
        expected = capture.scope["_video_capture_folder"](folder, item["url"], _metadata(item["url"]))
        assert item["ok"] is True
        assert Path(item["folder"]) == expected
        assert Path(item["md_path"]) == expected / f"{expected.name}.md"
        assert Path(item["json_path"]).is_file()
        assert capture.idx.get_by_slug(expected.name)["corpus_path"] == item["md_path"]
    corpus = (folder / "corpus.md").read_text(encoding="utf-8")
    assert corpus.count(f"Body for {URL_A}") == 1
    assert corpus.count(f"Body for {URL_B}") == 1


@pytest.mark.parametrize("fail_second", [False, True])
def test_repeated_playlist_source_keeps_first_capture(capture, tmp_path, monkeypatch, fail_second):
    job, folder = _playlist_job(capture, tmp_path, urls=(URL_A, URL_A))
    first = capture.scope["_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    original_extract = capture.scope["_run_extraction"]
    snapshots = []

    def extract(*args, **kwargs):
        result = original_extract(*args, **kwargs)
        if not snapshots:
            (first / "video.mp4").write_bytes(b"retained first media")
            snapshots.append(_snapshot(first))
        return result

    original_subprocess = capture.scope["_run_subprocess"]
    ffmpeg_calls = []

    def run(cmd, **kwargs):
        if cmd[0] == "ffmpeg":
            ffmpeg_calls.append(cmd)
            if fail_second and len(ffmpeg_calls) == 2:
                raise subprocess.CalledProcessError(1, cmd, stderr=b"second ffmpeg failed")
        return original_subprocess(cmd, **kwargs)

    monkeypatch.setitem(capture.scope, "_run_extraction", extract)
    monkeypatch.setitem(capture.scope, "_run_subprocess", run)
    capture.scope["_playlist_worker"]("playlist-test")
    assert len(ffmpeg_calls) == 2
    assert job["state"] == "completed"
    assert job["videos_done"] == (1 if fail_second else 2)
    assert job["videos_failed"] == int(fail_second)
    first_item, second_item = job["per_video"]
    assert first_item["ok"] is True
    assert Path(first_item["folder"]) == first
    second = Path(second_item["folder"])
    assert second != first
    assert second_item["ok"] is (not fail_second)
    assert _snapshot(first) == snapshots[0]
    assert not (first / "FAILED.txt").exists()
    assert Path(first_item["md_path"]).is_file()
    if fail_second:
        assert Path(second_item["failed_marker_path"]) == second / "FAILED.txt"
        assert "ffmpeg" in (second / "FAILED.txt").read_text(encoding="utf-8")
        assert capture.idx.get_yoink("aaaaaaaaaaa")["slug"] == first.name
    else:
        assert Path(second_item["md_path"]).is_file()
        assert Path(second_item["json_path"]).is_file()
    corpus = (folder / "corpus.md").read_text(encoding="utf-8")
    assert corpus.count(f"Body for {URL_A}") == job["videos_done"]


@pytest.mark.parametrize("command, phase", [("yt-dlp", "download"), ("ffmpeg", "screenshots")])
def test_playlist_failure_marker_stays_with_partial_capture(capture, tmp_path, monkeypatch, command, phase):
    job, folder = _playlist_job(capture, tmp_path)
    target = capture.scope["_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    original = capture.scope["_run_subprocess"]

    def fail(cmd, **kwargs):
        result = original(cmd, **kwargs)
        if cmd[0] == command:
            raise subprocess.CalledProcessError(1, cmd, stderr=b"injected media failure")
        return result

    monkeypatch.setitem(capture.scope, "_run_subprocess", fail)
    capture.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == "failed"
    assert job["videos_failed"] == 1
    item, = job["per_video"]
    assert item["ok"] is False
    assert item["error_phase"] == phase
    assert Path(item["folder"]) == target
    assert Path(item["failed_marker_path"]) == target / "FAILED.txt"
    assert URL_A in (target / "FAILED.txt").read_text(encoding="utf-8")
    assert (target / ".capture-source.json").is_file()
    assert (target / "metadata.json").is_file()
    assert (target / "video.mp4").read_bytes() == b"media"
    assert list(folder.iterdir()) == [target]


def test_playlist_ownership_refusal_preserves_foreign_folder(capture, tmp_path):
    job, folder = _playlist_job(capture, tmp_path)
    target = capture.scope["_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    capture.run(URL_B, folder=target)
    before = _snapshot(target)
    calls_before = len(capture.calls)
    capture.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == "failed"
    item, = job["per_video"]
    assert item["ok"] is False
    assert "another source" in item["error"]
    assert Path(item["folder"]) != target
    assert Path(item["failed_marker_path"]).is_file()
    assert _snapshot(target) == before
    assert len(capture.calls) == calls_before


@pytest.mark.parametrize("failure", ["metadata", "claim"])
def test_playlist_failure_before_claim_uses_separate_marker(capture, tmp_path, monkeypatch, failure):
    job, folder = _playlist_job(capture, tmp_path)
    target = capture.scope["_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    if failure == "metadata":
        monkeypatch.setitem(capture.scope, "_fetch_metadata", Mock(side_effect=OSError("metadata failed")))
    else:
        original = Path.open

        def fail(path, mode="r", *args, **kwargs):
            if path == target / ".capture-source.json" and mode == "x":
                raise PermissionError("claim refused")
            return original(path, mode, *args, **kwargs)

        monkeypatch.setattr(Path, "open", fail)
    capture.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == "failed"
    item, = job["per_video"]
    assert item["ok"] is False
    assert Path(item["folder"]) != target
    assert Path(item["failed_marker_path"]).is_file()
    assert _snapshot(target) == {}
    assert capture.calls == []


@pytest.mark.parametrize("legacy_name", [False, True])
def test_reused_playlist_keeps_source_name_and_refuses_occupied_target(capture, tmp_path, legacy_name):
    original = capture.run(URL_A, folder=tmp_path / "Weekly_update" if legacy_name else None)
    source = Path(original["folder"])
    before = _snapshot(source)
    job, folder = _playlist_job(capture, tmp_path, reused=original)
    capture.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == "completed"
    item, = job["per_video"]
    target = folder / source.name
    assert Path(item["folder"]) == target
    assert Path(item["md_path"]).is_file()
    assert _snapshot(target) == before
    assert _snapshot(source) == before

    # Occupied copies must be refused, with diagnostics outside that folder.
    job, _ = _playlist_job(capture, tmp_path, reused=original)
    calls_before = len(capture.calls)
    capture.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == "failed"
    item, = job["per_video"]
    assert item["ok"] is False
    assert Path(item["folder"]) != target
    assert Path(item["failed_marker_path"]).is_file()
    assert _snapshot(target) == before
    assert _snapshot(source) == before
    assert len(capture.calls) == calls_before


def test_reused_playlist_copy_failure_keeps_marker_with_partial_copy(capture, tmp_path, monkeypatch):
    original = capture.run(URL_A)
    source = Path(original["folder"])
    before = _snapshot(source)
    job, folder = _playlist_job(capture, tmp_path, reused=original)
    target = folder / source.name

    def fail(source_folder, destination, **kwargs):
        (destination / ".capture-source.json").write_bytes(
            (source_folder / ".capture-source.json").read_bytes())
        raise OSError("injected copy failure")

    monkeypatch.setattr(shutil, "copytree", fail)
    capture.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == "failed"
    item, = job["per_video"]
    assert item["ok"] is False
    assert Path(item["folder"]) == target
    assert Path(item["failed_marker_path"]) == target / "FAILED.txt"
    assert "injected copy failure" in (target / "FAILED.txt").read_text(encoding="utf-8")
    assert (target / ".capture-source.json").read_bytes() == before[".capture-source.json"]
    assert _snapshot(source) == before
    assert list(folder.iterdir()) == [target]


def _generic_handler(capture):
    scope = capture.scope
    scope["_normalize_any_url"] = lambda url: (url, "generic")
    scope["_ManualOwnership"] = lambda: SimpleNamespace(process_slot=nullcontext)
    scope["_fetch_metadata"] = lambda url: _metadata(url)
    scope["_extract_generic_transcript"] = lambda metadata: []
    handler = SimpleNamespace()
    handler._send_json = lambda status, payload: setattr(handler, "response", (status, payload))
    return handler


def test_generic_same_title_captures_keep_distinct_folders_and_rows(capture):
    handler = _generic_handler(capture)
    results = []
    for url in ("https://example.test/first", "https://example.test/second"):
        capture.scope["_handle_extract_any"](handler, {"url": url})
        assert handler.response[0] == 200
        result = handler.response[1]
        assert result["ok"] is True
        folder = Path(result["folder"])
        assert result["video_slug"] == folder.name
        row = capture.idx.get_by_slug(folder.name)
        assert Path(row["corpus_path"]).read_text(encoding="utf-8").count(url) == 1
        results.append(result)
    assert results[0]["folder"] != results[1]["folder"]
    assert capture.conn.execute("SELECT count(*) FROM yoinks").fetchone()[0] == 2


@pytest.mark.parametrize("second_url", ["https://b.example/v/clip.mp4",
                                      "https://a.example/other/clip.mp4"])
def test_generic_duplicate_extractor_ids_keep_both_library_rows(capture, second_url):
    handler = _generic_handler(capture)
    capture.scope["_fetch_metadata"] = lambda url: _metadata(url, title="clip", id="clip")
    urls = ["https://a.example/v/clip.mp4", second_url]
    results = []
    for url in urls:
        capture.scope["_handle_extract_any"](handler, {"url": url})
        assert handler.response[0] == 200
        result = handler.response[1]
        assert result["ok"] is True
        folder = Path(result["folder"])
        row = capture.idx.get_by_slug(folder.name)
        sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
        assert row["video_id"] == sidecar["video_id"]
        assert sidecar["url"] == url
        results.append((folder, row, _snapshot(folder)))
    assert results[0][1]["video_id"] != results[1][1]["video_id"]
    assert results[0][0] != results[1][0]
    for folder, row, before in results:
        assert capture.idx.get_yoink(row["video_id"]) == row
        assert _snapshot(folder) == before
        indexed = capture.conn.execute(
            "SELECT content FROM yoinks_fts WHERE video_id=?", (row["video_id"],)).fetchone()
        assert indexed["content"] == Path(row["corpus_path"]).read_text(encoding="utf-8")
    capture.scope["_handle_extract_any"](handler, {"url": urls[1]})
    assert handler.response[0] == 200
    assert handler.response[1]["ok"] is True
    assert Path(handler.response[1]["folder"]) == results[1][0]
    assert capture.conn.execute("SELECT count(*) FROM yoinks").fetchone()[0] == 2
    assert capture.idx.get_yoink(results[0][1]["video_id"]) == results[0][1]
    assert _snapshot(results[0][0]) == results[0][2]


def test_generic_index_conflict_returns_failure_and_keeps_artifacts(capture, monkeypatch):
    handler = _generic_handler(capture)
    monkeypatch.setattr(capture.idx, "upsert_yoink", Mock(side_effect=sqlite3.IntegrityError("injected constraint")))
    capture.scope["_handle_extract_any"](handler, {"url": "https://example.test/first"})
    status, result = handler.response
    assert status == 500
    assert result["ok"] is False
    assert "injected constraint" in result["error"]
    assert (Path(result["folder"]) / "corpus.md").is_file()


def test_mcp_capture_uses_the_source_derived_folder(tmp_path):
    from contextlib import contextmanager

    meta = _metadata(URL_A)
    unique = tmp_path / "Test" / "Weekly_update_0123456789abcdef"

    @contextmanager
    def ownership(_url):
        yield SimpleNamespace(raise_if_unavailable=lambda: None, conflict=None,
                              completed_while_waiting=False, reused=None)

    backend = SimpleNamespace(
        DESKTOP_ROOT=tmp_path,
        _normalize_youtube_url=lambda url: url,
        _now_iso=lambda: "2026-10-15T00:00:00Z",
        _manual_extraction_ownership=ownership,
        _fetch_metadata=lambda _url: meta,
        _classify_topic=lambda _meta: "Test",
        _topic_folder_name=lambda topic: topic,
        slugify=lambda text: text.replace(" ", "_"),
        _video_capture_folder=Mock(return_value=unique),
        _run_extraction=Mock(side_effect=lambda url, interval, folder, **_k: {
            "folder": str(folder), "yoink_md": "fixture"}),
        _record_single_extract_job=Mock(),
        friendly_error=str,
        machine_error_detail=str,
        _failure_phase=lambda _e, phase: phase,
        LONG_VIDEO_MODE_FULL="full",
    )
    scope = {"Any": object, "Path": Path}
    _load(ROOT / "uoink_mcp_tools.py", {"uoink_video", "_ok", "_err", "_limit_int"}, scope)
    scope["_b"] = lambda: backend

    result = scope["uoink_video"]({"url": URL_A})

    assert result["ok"] is True
    backend._video_capture_folder.assert_called_once_with(tmp_path / "Test", URL_A, meta)
    assert backend._run_extraction.call_args.args[2] == unique
