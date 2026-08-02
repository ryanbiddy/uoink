"""Automatic podcast metadata watch and opt-in ingestion contracts."""

from __future__ import annotations

from datetime import datetime, timezone

import index as index_mod
import podcasts
import server


def _episode(guid: str, title: str) -> dict:
    return {
        "guid": guid,
        "title": title,
        "audio_url": f"https://cdn.example/{guid}.mp3",
        "episode_page_url": f"https://show.example/{guid}",
        "published_at": "2026-08-01T12:00:00Z",
    }


def test_watch_migration_defaults_off_and_marks_only_future_opt_in_rows(
        tmp_path):
    db_path = tmp_path / "index.db"
    idx = index_mod.Index.open(db_path)
    feed = podcasts.add_feed(
        idx, "https://show.example/feed.xml", poll_interval_min=60)
    assert feed["auto_ingest"] == 0
    assert podcasts.upsert_episodes(
        idx, feed["id"], [_episode("before", "Before opt-in")]) == (1, 0)

    assert podcasts.set_feed_auto_ingest(idx, feed["id"], True)
    assert podcasts.upsert_episodes(
        idx, feed["id"], [_episode("after", "After opt-in")]) == (1, 0)
    candidates = podcasts.list_auto_ingest_candidates(
        idx, feed_id=feed["id"], limit=10)
    assert [row["guid"] for row in candidates] == ["after"]

    with idx.write_transaction() as conn:
        conn.execute(
            "UPDATE podcast_feeds SET last_polled_at=? WHERE id=?",
            ("2026-08-01T12:00:00Z", feed["id"]))
    assert podcasts.list_due_feeds(
        idx, now=datetime(2026, 8, 1, 12, 59, tzinfo=timezone.utc)) == []
    assert [row["id"] for row in podcasts.list_due_feeds(
        idx, now=datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc))] == [
            feed["id"]]
    idx.close()

    idx = index_mod.Index.open(db_path)
    assert podcasts.get_feed(idx, feed["id"])["auto_ingest"] == 1
    assert podcasts.list_auto_ingest_candidates(
        idx, feed_id=feed["id"], limit=10)[0]["guid"] == "after"
    assert idx._conn.execute(
        "SELECT MAX(version) FROM schema_version").fetchone()[0] == 23
    idx.close()


def test_scheduler_tick_polls_only_due_feeds_and_toasts_new_episode(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    due = podcasts.add_feed(idx, "https://due.example/feed.xml")
    future = podcasts.add_feed(idx, "https://future.example/feed.xml")
    podcasts.upsert_episodes(idx, due["id"], [_episode("new", "Fresh episode")])
    episode_id = podcasts.list_episodes(idx, feed_id=due["id"])[0]["id"]
    with idx.write_transaction() as conn:
        conn.execute(
            "UPDATE podcast_feeds SET last_polled_at=? WHERE id=?",
            ("2999-01-01T00:00:00Z", future["id"]))
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    polled = []

    def fake_poll(_idx, feed_id):
        polled.append(feed_id)
        return {
            "ok": True, "feed_id": feed_id, "inserted": 1,
            "new_episode_ids": [episode_id], "title": "Due Show",
        }

    toasts = []
    monkeypatch.setattr(podcasts, "poll_feed", fake_poll)
    monkeypatch.setattr(server, "maybe_toast",
                        lambda title, body, **_kw: toasts.append((title, body)))
    monkeypatch.setattr(
        server, "_auto_ingest_podcast_feed",
        lambda _feed_id: (_ for _ in ()).throw(
            AssertionError("metadata-only feed must not auto-ingest")))

    results = server._podcast_feed_scheduler_tick()
    assert polled == [due["id"]]
    assert results[0]["inserted"] == 1
    assert toasts == [
        ("New podcast episode", "Due Show: Fresh episode.")]
    idx.close()


def test_auto_ingest_downloads_and_queues_publish_without_model_consent(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    feed = podcasts.add_feed(
        idx, "https://auto.example/feed.xml", auto_ingest=True)
    podcasts.upsert_episodes(idx, feed["id"], [_episode("auto", "Auto")])
    episode_id = podcasts.list_episodes(idx, feed_id=feed["id"])[0]["id"]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_read_settings", lambda: {
        "whisper_model": "base", "diarization_default": False})
    audio = tmp_path / "auto.mp3"
    audio.write_bytes(b"audio")

    def fake_download(_idx, requested_id, **_kwargs):
        podcasts._record_audio_result(
            idx, requested_id, local_path=str(audio),
            size_bytes=audio.stat().st_size, error=None,
            status=podcasts.EPISODE_STATUS_DOWNLOADED)
        return {"ok": True, "episode_id": requested_id,
                "local_path": str(audio)}

    queued = []
    monkeypatch.setattr(podcasts, "download_episode_audio", fake_download)
    monkeypatch.setattr(
        server, "_queue_podcast_transcription",
        lambda requested_id, **kwargs: (
            queued.append((requested_id, kwargs)) or
            ({"ok": True, "job_id": "watch-job"}, 202)))

    result = server._auto_ingest_podcast_feed(feed["id"])
    assert result[0]["job_id"] == "watch-job"
    assert queued == [(episode_id, {
        "model": "base", "diarize": False, "consent_given": False,
        "publish_to_corpus": True,
    })]
    idx.close()


def test_scheduler_routes_auto_ingest_only_for_opted_in_feed(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    feed = podcasts.add_feed(
        idx, "https://auto-tick.example/feed.xml", auto_ingest=True)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(podcasts, "poll_feed", lambda _idx, feed_id: {
        "ok": True, "feed_id": feed_id, "inserted": 0,
        "new_episode_ids": [], "title": "Auto tick",
    })
    called = []
    monkeypatch.setattr(
        server, "_auto_ingest_podcast_feed",
        lambda feed_id: called.append(feed_id) or [{"ok": True}])

    result = server._podcast_feed_scheduler_tick()
    assert called == [feed["id"]]
    assert result[0]["auto_ingest"] == [{"ok": True}]
    idx.close()
