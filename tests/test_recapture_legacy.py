"""Legacy recapture and duplicate-name regressions using only disposable files.

Every test exercises an observable behavior absent on main, including the
negative controls paired with successful in-place refreshes.
"""
from __future__ import annotations

from contextlib import nullcontext
import json
import logging
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import index

from test_unique_capture_folders import (
    ROOT, URL_A, URL_B, _load, _metadata, _snapshot, capture, _generic_handler,
    _playlist_job, _session_handler,
)
from test_publication_truth import publication, _request


X_URL = "https://x.com/fixture/status/2112657693802475696"
X_ID = "2112657636860612608"  # Media ID differs from the post ID, as in 3.7.0.


@pytest.fixture
def legacy(capture, tmp_path):
    with index.Index.open(tmp_path / "legacy.db") as idx:
        scope = capture.scope
        scope.update({
            "index": index, "_get_index": lambda: idx, "_get_existing_index": lambda: idx,
            "_backfill_lock": threading.Lock(), "_backfill_state": {},
            "_backfill_cancel": threading.Event(), "_index_recovering": False,
            "_trash_root": lambda: scope["DESKTOP_ROOT"] / "_yoink-trash",
            "_resolve_video_transcript": lambda *a, **k: ([(0, 2, "Recovered spoken words")], "asr", None),
            "_transcript_entries_with_links": lambda seed, entries: [
                {"start": start, "end": end, "text": text} for start, end, text in entries],
            "_build_yoink_md": lambda **k: "# Refreshed\n\n" + "\n".join(text for _, _, text in k["entries"]),
        })
        _load(ROOT / "server.py", {"_run_backfill", "_iter_corpus_folders", "doctor_payload"}, scope)
        for helper in ("_backfill_slug_conflict", "_duplicate_folder_names_status"):
            if f"def {helper}(" in (ROOT / "server.py").read_text(encoding="utf-8"):
                _load(ROOT / "server.py", {helper}, scope)

        def seed(*, url=X_URL, video_id=X_ID, name="Legacy_title_only", corpus_name=None,
                 folder_meta=None, row_url=None, row_id=None, sidecar=False):
            folder = scope["DESKTOP_ROOT"] / "Old topic" / name
            folder.mkdir(parents=True)
            metadata = _metadata(url, title="Changed title", id=video_id)
            (folder / "metadata.json").write_text(json.dumps(folder_meta or metadata), encoding="utf-8")
            corpus = folder / (corpus_name or f"{name}.md")
            corpus.write_text("# Legacy\nNo captions available", encoding="utf-8")
            (folder / "notes.txt").write_text("User notes", encoding="utf-8")
            if sidecar:
                (folder / f"{name}.json").write_text(json.dumps({
                    "url": url, "video_id": row_id or video_id, "title": "Legacy",
                }), encoding="utf-8")
            idx.upsert_yoink({
                "video_id": row_id or video_id, "slug": name, "title": "Legacy",
                "corpus_path": str(corpus), "sidecar_path": str(folder / f"{name}.json"),
                "metadata_json": json.dumps({"url": row_url or url}),
                "yoinked_at": "2026-01-01T00:00:00Z",
            }, content=corpus.read_text(encoding="utf-8"))
            idx.add_tags(row_id or video_id, ["my-tag"], source="user")
            return folder, metadata

        yield SimpleNamespace(scope=scope, idx=idx, seed=seed, capture=capture)


def _recapture(state, folder, metadata, *, url=X_URL):
    before = state.idx.get_by_slug(folder.name)
    result = state.capture.run(url, metadata=metadata)
    assert result["ok"] is True
    assert Path(result["folder"]) == folder
    assert result["video_slug"] == folder.name
    row = state.idx.get_by_slug(folder.name)
    assert row["corpus_path"] == before["corpus_path"]
    assert row["video_id"] == before["video_id"]
    assert state.idx.get_tags(row["video_id"]) == ["my-tag"]
    assert "Recovered spoken words" in Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "Recovered spoken words"
    assert (folder / "notes.txt").read_text(encoding="utf-8") == "User notes"
    return result


@pytest.mark.parametrize("corpus_name", [None, "yoink.md", "saved-transcript.md"])
def test_legacy_x_recapture_keeps_folder_row_and_corpus_path(legacy, corpus_name):
    folder, metadata = legacy.seed(corpus_name=corpus_name)
    expected_new = legacy.scope["_video_capture_folder"](folder.parent, X_URL, metadata)
    _recapture(legacy, folder, metadata)
    assert legacy.idx.count_corpus() == 1
    assert not expected_new.exists()
    assert list(legacy.scope["DESKTOP_ROOT"].rglob("metadata.json")) == [folder / "metadata.json"]


@pytest.mark.parametrize("key", ["url", "source_url", "webpage_url", "original_url"])
def test_recorded_source_alias_finds_legacy_library_id(legacy, key):
    folder, metadata = legacy.seed(url=URL_A, video_id="aaaaaaaaaaa", row_id="legacy-id", sidecar=True)
    with legacy.idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET metadata_json=?", (json.dumps({key: "https://youtu.be/aaaaaaaaaaa?t=4"}),))
    _recapture(legacy, folder, metadata, url=URL_A)
    # The claim and new sidecar must remain verifiable on a second refresh.
    _recapture(legacy, folder, metadata, url=URL_A)
    assert legacy.idx.count_corpus() == 1


@pytest.mark.parametrize("bad_record", ["foreign", "malformed", "ambiguous"])
def test_unverified_legacy_folder_is_untouched_and_reason_is_logged(legacy, caplog, bad_record):
    folder, metadata = legacy.seed()
    if bad_record == "foreign":
        (folder / "metadata.json").write_text(json.dumps(_metadata(URL_B)), encoding="utf-8")
    elif bad_record == "malformed":
        (folder / "metadata.json").write_text("{", encoding="utf-8")
    else:
        (folder / "metadata.json").unlink()
    before = _snapshot(folder)
    with caplog.at_level(logging.WARNING):
        result = legacy.capture.run(X_URL, metadata=metadata)
    assert Path(result["folder"]) != folder
    assert _snapshot(folder) == before
    reasons = [r for r in caplog.records if "capture: using new folder" in r.message]
    assert len(reasons) == 1
    assert reasons[0].exc_info is None


def test_multiple_live_url_matches_fall_back_without_picking_a_folder(legacy, caplog):
    # No row has the capture's own ID, so only recorded URLs can match.
    first, metadata = legacy.seed(row_id="first-id")
    second, _ = legacy.seed(name="Other_legacy", row_id="other-id", sidecar=True)
    before = [_snapshot(first), _snapshot(second)]
    with caplog.at_level(logging.WARNING):
        result = legacy.capture.run(X_URL, metadata=metadata)
    assert Path(result["folder"]) not in (first, second)
    assert [_snapshot(first), _snapshot(second)] == before
    assert "multiple live source rows" in caplog.text


def test_direct_id_match_wins_over_other_rows_with_the_same_url(legacy):
    folder, metadata = legacy.seed()
    legacy.seed(name="Other_legacy", row_id="other-id", sidecar=True)
    _recapture(legacy, folder, metadata)


def test_soft_deleted_row_is_ignored_then_restored_row_refreshes(legacy):
    folder, metadata = legacy.seed()
    before = _snapshot(folder)
    legacy.idx.soft_delete_yoink(X_ID)
    result = legacy.capture.run(X_URL, metadata=metadata)
    assert Path(result["folder"]) != folder
    assert _snapshot(folder) == before
    # Restore the fixture binding to prove the live/deleted distinction.
    with legacy.idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET deleted_at=NULL, slug=?, corpus_path=?, sidecar_path=?",
                     (folder.name, str(folder / f"{folder.name}.md"), str(folder / f"{folder.name}.json")))
    _recapture(legacy, folder, metadata)


@pytest.mark.parametrize("entry", ["session", "playlist"])
def test_session_and_playlist_entries_still_make_new_folders(legacy, tmp_path, entry):
    folder, metadata = legacy.seed(url=URL_A, video_id="aaaaaaaaaaa")
    _recapture(legacy, folder, metadata, url=URL_A)
    before = _snapshot(folder)
    if entry == "session":
        handler, _, _ = _session_handler(legacy.capture, tmp_path)
        legacy.scope["_handle_session_add"](handler, {"url": URL_A})
        assert handler.response[1]["ok"] is True
    else:
        job, _ = _playlist_job(legacy.capture, tmp_path)
        legacy.scope["_playlist_worker"]("playlist-test")
        assert job["state"] == "completed"
    assert _snapshot(folder) == before
    assert len(list(tmp_path.rglob("metadata.json"))) == 2


def test_generic_prepare_entry_refreshes_legacy_path(legacy):
    url = "https://example.test/clip.mp4"
    folder, _ = legacy.seed(url=url, video_id="clip", row_id="old-generic-id", sidecar=True)
    handler = _generic_handler(legacy.capture)
    legacy.scope["_fetch_metadata"] = lambda url: _metadata(url, id="clip")
    legacy.scope["_handle_extract_any"](handler, {"url": url})
    assert handler.response[0] == 200
    assert Path(handler.response[1]["folder"]) == folder
    assert legacy.idx.count_corpus() == 1
    assert Path(legacy.idx.get_by_slug(folder.name)["corpus_path"]) == folder / f"{folder.name}.md"
    assert (folder / "notes.txt").read_text(encoding="utf-8") == "User notes"


@pytest.mark.parametrize("entry", ["extension", "mcp_video", "mcp_url", "cli", "queue"])
def test_capture_entry_points_refresh_the_legacy_item(legacy, entry):
    import uoink_cli

    url = URL_A if entry == "mcp_video" else X_URL
    video_id = "aaaaaaaaaaa" if entry == "mcp_video" else X_ID
    folder, metadata = legacy.seed(url=url, video_id=video_id)
    scope = legacy.scope
    recorded = Mock(return_value={"id": "job_fixture"})
    scope.update({
        "_fetch_metadata": lambda *a, **k: metadata,
        "_manual_extraction_ownership": lambda url: nullcontext(SimpleNamespace(
            ok=True, conflict=None, completed_while_waiting=False, reused=None,
            raise_if_unavailable=lambda: None)),
        "_normalize_long_video_mode": lambda mode: mode or "full",
        "_normalize_any_url": scope["_normalize_video_url"],
        "_reports_live_extract": lambda fn: fn,
        "_live_extract_begin": Mock(), "_live_extract_phase": Mock(),
        "_record_single_extract_job": recorded, "_make_job_id": lambda: "job_fixture",
        "_detect_live_state": lambda metadata: "none", "_is_youtube_rate_limit": lambda e: False,
        "LIVE_STATE_LIVE": "live", "LIVE_STATE_UPCOMING": "upcoming", "LIVE_STATE_POST_LIVE": "post_live",
        "_failure_phase": lambda error, phase: phase, "_sanitize_error": str,
        "_pending_long_video_mode": lambda *a, **k: "full",
    })
    _load(ROOT / "server.py", {"_handle_extract", "_validate_url_interval"}, scope, class_name="Handler")
    _load(ROOT / "server.py", {"_classify_capture_url", "_normalize_short_video_url",
                               "_is_short_video_url", "_is_youtube_short_url",
                               "_normalize_playlist_url", "_retry_pending_one"}, scope,
          constants={"_CAPTURE_SOURCES", "_PLAYLIST_ID_RE"})
    handler_class = type("Handler", (), {
        name: scope[name] for name in ("_handle_extract", "_handle_extract_any", "_validate_url_interval")})
    backend = SimpleNamespace(**scope, Handler=handler_class)
    tools_scope = {"Any": object, "Path": Path, "_b": lambda: backend}
    _load(ROOT / "uoink_mcp_tools.py", {"uoink_video", "uoink_url", "_ok", "_err", "_limit_int"}, tools_scope)
    if entry == "extension":
        handler = handler_class()
        handler._send_json = lambda status, result: setattr(handler, "response", (status, result))
        handler._handle_extract({"url": url})
        assert handler.response[0] == 200
        result = handler.response[1]
    elif entry == "queue":
        legacy.idx.enqueue_pending(url, 30, "2026-01-01T00:00:00", "full")
        assert scope["_retry_pending_one"]() is True
        pending, = legacy.idx.list_pending(include_terminal=True)
        assert pending["status"] == "succeeded"
        result = recorded.call_args.kwargs["result"]
    else:
        name = "uoink_video" if entry == "mcp_video" else "uoink_url"
        args = {"url": url}
        if entry == "cli":
            name, args = uoink_cli.friendly_call(uoink_cli.parser().parse_args(["capture", url]), backend)
        result = tools_scope[name](args)
    assert result["ok"] is True, result
    assert Path(result["folder"]) == folder
    assert legacy.idx.count_corpus() == 1
    assert legacy.idx.get_yoink(video_id)["slug"] == folder.name
    assert legacy.idx.get_tags(video_id) == ["my-tag"]
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "Recovered spoken words"


def test_legacy_refresh_publication_retry_keeps_the_saved_binding(legacy, publication, monkeypatch):
    folder, metadata = legacy.seed(url=URL_A, video_id="aaaaaaaaaaa", row_id="legacy-id", sidecar=True)
    state = publication
    state.idx = legacy.idx
    state.folder = folder
    state.scope["_get_index"] = lambda: legacy.idx
    state.scope["_fetch_metadata"] = lambda *a, **k: metadata
    with monkeypatch.context() as patch:
        patch.setattr(legacy.idx, "upsert_yoink", Mock(side_effect=sqlite3.OperationalError("fixture save failure")))
        result = _request(state)
    assert result["ok"] is False
    _, receipt = state.queue.next_pending()
    assert Path(receipt["folder"]) == folder
    assert "One publication retry is queued" in result["error"]
    before_retry = list(legacy.capture.calls)
    assert state.scope["_retry_publication_one"]() is True
    assert state.queue.next_pending() is None
    assert legacy.capture.calls == before_retry
    row = legacy.idx.get_yoink("legacy-id")
    assert row["slug"] == folder.name
    assert Path(row["corpus_path"]) == folder / f"{folder.name}.md"
    assert legacy.idx.count_corpus() == 1
    assert legacy.idx.get_tags("legacy-id") == ["my-tag"]


def _doctor(state, monkeypatch):
    import uoink_supervisor
    monkeypatch.setattr(uoink_supervisor, "status", lambda root: {})
    monkeypatch.setattr(index, "schema_migration_status", lambda path: {})
    state.scope.update({
        "DATA_ROOT": state.scope["DESKTOP_ROOT"], "INDEX_PATH": state.idx._path,
        "_helper_health_status": lambda: {"ok": True},
        "_doctor_heartbeat": lambda health: {}, "_diagnose_payload": lambda: {},
        "migrate_install": SimpleNamespace(migration_status=lambda: {}),
        "_mcp_stdio_selfcheck": lambda **k: {}, "_mcp_modern_stdio_selfcheck": lambda **k: {},
        "_path_integrity_status": lambda **k: {}, "_podcast_corpus_reconciliation_status": lambda: {},
    })
    return state.scope["doctor_payload"]()


@pytest.mark.parametrize("same_id,same_path", [(False, False), (True, False), (False, True)])
def test_backfill_duplicate_slug_warns_once_skips_and_appears_in_doctor(
        legacy, monkeypatch, caplog, same_id, same_path):
    folder, _ = legacy.seed(sidecar=True)
    duplicate = folder if same_path else legacy.scope["DESKTOP_ROOT"] / "Other topic" / folder.name
    duplicate.mkdir(parents=True, exist_ok=True)
    (duplicate / f"{duplicate.name}.md").write_text("duplicate transcript", encoding="utf-8")
    (duplicate / f"{duplicate.name}.json").write_text(json.dumps({
        "video_id": X_ID if same_id else "different-id", "url": X_URL,
    }), encoding="utf-8")
    before = _snapshot(duplicate)
    row = legacy.idx.get_yoink(X_ID)
    # Restrict this pass to the conflict, just as an incremental discovery would.
    legacy.scope["_iter_corpus_folders"] = lambda root=None: [(duplicate, duplicate / f"{duplicate.name}.md")]
    with caplog.at_level(logging.WARNING):
        legacy.scope["_run_backfill"]()
    records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    if same_id:
        # A known ID keeps the incremental skip, so startup stays quiet;
        # the doctor below still lists the duplicate folder.
        assert records == []
    else:
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert records[0].message == (
            f"backfill: skipped {duplicate}: folder name already used by {folder} (video {X_ID})")
        assert records[0].exc_info is None
    assert _snapshot(duplicate) == before
    assert legacy.idx.get_yoink(X_ID) == row
    assert legacy.idx.count_corpus() == 1
    assert not legacy.idx._conn.in_transaction
    status = _doctor(legacy, monkeypatch)["duplicate_folder_names"]
    assert status == {"count": 1, "folders": [{"path": str(duplicate), "other_path": str(folder), "video_id": X_ID}]}


def test_backfill_keeps_the_incremental_skip_for_indexed_rows(legacy, monkeypatch, caplog):
    # Startup must not re-index every known folder on each boot.
    folder, _ = legacy.seed(sidecar=True)
    sidecar = folder / f"{folder.name}.json"
    sidecar.write_text(json.dumps({"video_id": X_ID, "url": X_URL, "title": "Backfilled update"}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        legacy.scope["_run_backfill"]()
    assert legacy.idx.get_yoink(X_ID)["title"] == "Legacy"
    assert legacy.idx.get_tags(X_ID) == ["my-tag"]
    assert legacy.idx.count_corpus() == 1
    assert caplog.records == []
    assert _doctor(legacy, monkeypatch)["duplicate_folder_names"] == {"count": 0, "folders": []}
