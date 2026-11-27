"""Upgrade, helper ownership, and podcast follow regressions."""
import http.client
import io
import threading
import urllib.error
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import index
import podcasts
import server
import source_subscriptions as ss
from tests.source_subscriptions_fixtures import USER, make_service, register
from tests.test_podcast_follow_links import FEED, SHOW, library, wire
from tests.test_podcast_job_transports import episode


def test_follow_upgrade_through_38_39_40(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.db"
    migrations = index._discover_migrations()
    def open_at(version):
        monkeypatch.setattr(index, "_discover_migrations", lambda: [
            entry for entry in migrations if entry[0] <= version])
        return index.Index.open(path)

    with open_at(38) as idx:
        assert idx.schema_version() == 38
        with idx.write_transaction() as db:
            for name in ("direct", "large", "success", "paused", "archived", "untouched"):
                url = f"https://{name}.example.test/rss"
                fid = db.execute("INSERT INTO podcast_feeds(feed_url,title,added_at) VALUES (?,?,?)",
                                 (url, name, "2026-05-01")).lastrowid
                sid = ss.source_identity("podcast_rss", url)
                ss.SourceSubscriptionService._insert_source(
                    db, source_id=sid, kind="podcast_rss", source_key=url, canonical_url=url,
                    display_name=name, interval=60, now=1, legacy_feed_id=fid)
                if name == "direct":
                    db.execute("UPDATE podcast_feeds SET last_polled_at='2026-05-02', error_count=1 WHERE id=?", (fid,))
                if name in ("large", "success", "paused", "archived"):
                    db.execute("UPDATE source_detection_cursors SET last_poll_attempt_ms=10, "
                               "last_poll_success_ms=?, error_count=?, last_error_code=? WHERE source_id=?",
                               (10 if name == "success" else None, int(name == "large"),
                                "feed_too_large" if name == "large" else None, sid))
                if name == "paused":
                    db.execute("UPDATE source_subscriptions SET detection_enabled=0 WHERE source_id=?", (sid,))
                if name == "archived":
                    db.execute("UPDATE source_subscriptions SET archived=1,detection_enabled=0 WHERE source_id=?", (sid,))
    with open_at(39) as idx:
        assert idx.schema_version() == 39
        assert idx._conn.execute("SELECT last_polled_at FROM podcast_feeds WHERE title='direct'").fetchone()[0] is None
        assert not idx._conn.execute("SELECT 1 FROM source_subscriptions WHERE follow_feed=1").fetchall()
    with open_at(40) as idx:
        assert idx.schema_version() == 40
        due = set(make_service(idx).due_poll_ids())
        assert {row[0] for row in idx._conn.execute(
            "SELECT display_name,source_id FROM source_subscriptions") if row[1] in due} == {"direct", "large", "success"}
        assert all(row[0] == "off" for row in idx._conn.execute("SELECT consent_state FROM source_subscriptions"))


@pytest.mark.parametrize("managed", [False, True])
def test_pre_40_read_only_auto_candidates(tmp_path, monkeypatch, managed):
    path = tmp_path / "old.db"
    old = [entry for entry in index._discover_migrations() if entry[0] <= 39]
    monkeypatch.setattr(index, "_discover_migrations", lambda: old)
    with index.Index.open(path):
        pass
    with index.Index.open_existing(path) as idx:
        monkeypatch.setattr(ss, "tables_present", lambda db: managed)
        assert podcasts.list_auto_ingest_candidates(idx) == []
        assert idx.schema_version() == 39


@pytest.mark.parametrize("defer", [True, False])
def test_disk_job_adoption_preserves_flags_before_worker(episode, monkeypatch, defer):
    idx = server._get_index()
    first, _ = server._queue_podcast_transcription(episode, defer_worker=True)
    jid = first["job_id"]
    if not defer:
        with idx.write_transaction() as db:
            db.execute("UPDATE jobs SET metadata_json=json_set(metadata_json,'$.current_video_phase','queued')")
    launches = []
    def started():
        launches.append(server._jobs[jid].copy())
        server._podcast_transcription_queue.get_nowait()
        server._podcast_transcription_queue.task_done()
    monkeypatch.setattr(server, "_ensure_podcast_transcription_worker", started)
    result, status = server._queue_podcast_transcription(
        episode, defer_worker=defer, publish_to_corpus=True,
        source_start_id="start-example", source_owner_token="fixture-owner")
    assert status == 202 and result["job_id"] == jid
    saved = podcasts.saved_transcription_job(idx, jid)
    assert saved["source_start_id"] == "start-example" and saved["publish_to_corpus"]
    assert "_source_owner_token" not in saved
    if defer:
        assert saved["current_video_phase"] == "awaiting_helper" and not launches
    else:
        assert len(launches) == 1 and launches[0]["_source_owner_token"] == "fixture-owner"


def test_invalid_waiting_job_is_not_started(monkeypatch):
    worker = Mock()
    monkeypatch.setattr(server, "_ensure_podcast_transcription_worker", worker)
    assert server._start_waiting_podcast_job({"kind": "podcast_transcribe"}) is None
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(podcasts, "active_transcription_jobs", lambda *a, **kw: [{"kind": "podcast_transcribe"}])
    server._pickup_waiting_podcast_jobs()
    worker.assert_not_called()


def test_restore_includes_active_job_below_history_limit(episode):
    idx = server._get_index()
    result, _ = server._queue_podcast_transcription(episode, defer_worker=True)
    jid = result["job_id"]
    with idx.write_transaction() as db:
        db.execute("UPDATE jobs SET updated_at='2000-01-01', "
                   "metadata_json=json_set(metadata_json,'$.current_video_phase','queued')")
        db.executemany("INSERT INTO jobs(job_id,kind,status,updated_at,metadata_json) "
                       "VALUES (?, 'single','completed','2026-01-01','{}')",
                       [(f"other-{n}",) for n in range(1000)])
    assert jid not in {r["job_id"] for r in idx.list_jobs(limit=1000)}
    server._restore_jobs_from_disk()
    assert server._jobs[jid]["state"] == "queued"


@pytest.mark.parametrize("dashboard_first", [True, False])
def test_source_linked_removal_reports_changes_once(library, dashboard_first):
    service = make_service(library)
    src = register(service, "podcast_rss", FEED)
    fid = src["legacy"]["feed_id"]
    if dashboard_first:
        assert service.archive_source(USER, {"source_id": src["source_id"]})["changed"]
    else:
        assert podcasts.remove_feed(library, fid)
    row = podcasts.get_feed(library, fid)
    assert (row["enabled"], row["auto_ingest"]) == (0, 0)
    assert not podcasts.remove_feed(library, fid)
    assert podcasts.get_feed(library, fid)


@pytest.mark.parametrize("apple", [True, False])
@pytest.mark.parametrize("protocol", [True, False])
def test_paste_wraps_protocol_error_and_closes_error_body(monkeypatch, apple, protocol):
    body = io.BytesIO(b"")
    error = (http.client.IncompleteRead(b"") if protocol else
             urllib.error.HTTPError(FEED, 404, "missing", {}, body))
    monkeypatch.setattr(ss, "public_http_open", Mock(side_effect=error))
    with pytest.raises(ValueError, match="Apple Podcasts" if apple else "podcast feed"):
        if apple:
            podcasts.resolve_apple_podcast("42", None)
        else:
            podcasts.read_pasted_feed(FEED, limit=0)
    if not protocol:
        assert body.closed


def test_follow_requires_a_feed_projection(library, monkeypatch):
    wire(monkeypatch)
    service = SimpleNamespace(follow_podcast=lambda *a, **kw: {
        "source": {"source_id": "test", "legacy": {"feed_id": None}}, "created": False})
    monkeypatch.setattr(server, "_source_service", lambda: service)
    with pytest.raises(ValueError, match="feed"):
        server._follow_podcast_link(FEED)


def test_missing_feed_rolls_back_new_follow(library, monkeypatch):
    wire(monkeypatch)
    monkeypatch.setattr(ss.SourceSubscriptionService, "_legacy_feed_projection", staticmethod(lambda *a: None))
    with pytest.raises(ValueError, match="feed"):
        server._follow_podcast_link(FEED)
    assert library._conn.execute("SELECT COUNT(*) FROM source_subscriptions").fetchone()[0] == 0


def test_resident_episode_capture_wakes_show_worker(library, monkeypatch):
    wire(monkeypatch)
    wake = threading.Event()
    monkeypatch.setattr(server, "_show_capture_wake", wake)
    monkeypatch.setattr(server, "_TOKEN_OWNED", True)
    result = server._follow_podcast_link(SHOW + "?i=71")
    assert result["show_job_id"] and wake.is_set()
    assert "Sources under Save a whole show" in result["message"]


def test_one_shot_follow_leaves_title_work_to_helper(library, monkeypatch):
    wire(monkeypatch)
    monkeypatch.setattr(server, "_TOKEN_OWNED", False)
    title = Mock()
    monkeypatch.setattr(podcasts, "fetch_title_in_background", title)
    result = server._follow_podcast_link(FEED)
    assert result["title_pending"]
    title.assert_not_called()


def test_episode_dashboard_displays_worker_message():
    from tests.test_dashboard_runthrough_fixes import run_js
    note = run_js("""(() => {
      let note; setLibraryCaptureNote = text => { note = text; };
      renderLibraryCaptures = () => {}; state.libraryRuns = [];
      finishLibraryRun({source:'podcast_episode'}, {message:'This episode capture is paused.'});
      return note;
    })()""")
    assert note == "This episode capture is paused."


def test_exact_window_with_next_chunk_containing_only_closing_tags():
    prefix = b"<rss><channel>" + b"<item><guid>one</guid></item>" * 50
    from tests.test_podcast_stream import FeedStream
    _, truncated = ss.read_podcast_window(FeedStream(prefix + b"</channel></rss>", chunk_size=len(prefix)), 50)
    assert not truncated


def test_second_helper_refuses_before_token_or_boot_work(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_existing_server_responds", lambda: False)
    monkeypatch.setattr(server, "_apply_output_root_fallback", lambda: None)
    httpd = Mock()
    monkeypatch.setattr(server, "_YoinkHTTPServer", lambda *a: httpd)
    monkeypatch.setattr(ss.CaptureLock, "acquire", lambda *a, **kw: None)
    token = Mock(side_effect=AssertionError("second helper reached token persistence"))
    monkeypatch.setattr(server, "_persist_token", token)
    with pytest.raises(RuntimeError, match="Another helper"):
        server.main(quiet=True)
    token.assert_not_called()
    httpd.server_close.assert_called_once()


def test_boot_failure_releases_library_before_process_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_existing_server_responds", lambda: False)
    monkeypatch.setattr(server, "_apply_output_root_fallback", lambda: None)
    httpd = Mock()
    monkeypatch.setattr(server, "_YoinkHTTPServer", lambda *a: httpd)
    def fail_boot(token):
        assert ss.CaptureLock.in_use(tmp_path, podcasts.PODCAST_WORKER_LOCK)
        raise OSError("fixture boot failure")
    monkeypatch.setattr(server, "_persist_token", fail_boot)
    with pytest.raises(OSError, match="fixture boot failure"):
        server.main(quiet=True)
    assert not ss.CaptureLock.in_use(tmp_path, podcasts.PODCAST_WORKER_LOCK)
    assert not server._TOKEN_OWNED
    httpd.server_close.assert_called_once()
