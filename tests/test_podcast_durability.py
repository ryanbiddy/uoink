"""Podcast state transitions must survive a process restart."""

from __future__ import annotations

import sqlite3

import pytest

import index as index_mod
import podcasts
import whisper_runner


def _reopen(idx, db_path):
    assert idx._conn.in_transaction is False
    idx.close()
    return index_mod.Index.open(db_path)


def _one_episode(guid: str = "episode-1") -> dict:
    return {
        "guid": guid,
        "title": "Durable episode",
        "audio_url": "https://cdn.example.test/episode.mp3",
        "duration_seconds": 123,
        "published_at": "2026-08-01T12:00:00Z",
        "description": "Restart test",
    }


def test_all_podcast_state_transitions_survive_close_reopen(tmp_path):
    db_path = tmp_path / "index.db"
    idx = index_mod.Index.open(db_path)

    feed = podcasts.add_feed(idx, "https://example.test/feed.xml")
    feed_id = feed["id"]
    idx = _reopen(idx, db_path)
    assert podcasts.get_feed(idx, feed_id)["feed_url"] == (
        "https://example.test/feed.xml"
    )

    duplicate = podcasts.add_feed(idx, "https://example.test/feed.xml")
    assert duplicate["id"] == feed_id
    idx = _reopen(idx, db_path)
    assert len(podcasts.list_feeds(idx)) == 1

    assert podcasts.set_feed_enabled(idx, feed_id, False)
    idx = _reopen(idx, db_path)
    assert podcasts.get_feed(idx, feed_id)["enabled"] == 0
    assert podcasts.set_feed_enabled(idx, feed_id, True)
    idx = _reopen(idx, db_path)
    assert podcasts.get_feed(idx, feed_id)["enabled"] == 1

    assert podcasts.upsert_episodes(idx, feed_id, [_one_episode()]) == (1, 0)
    idx = _reopen(idx, db_path)
    episode = podcasts.list_episodes(idx, feed_id=feed_id)[0]
    episode_id = episode["id"]
    assert episode["guid"] == "episode-1"

    podcasts.record_feed_meta(
        idx,
        feed_id,
        title="Durable Show",
        description="A show",
        homepage="https://example.test/show",
        etag='"v1"',
        last_modified="Fri, 01 Aug 2026 12:00:00 GMT",
        ok=True,
    )
    idx = _reopen(idx, db_path)
    feed = podcasts.get_feed(idx, feed_id)
    assert (feed["title"], feed["error_count"], feed["last_error"]) == (
        "Durable Show",
        0,
        None,
    )

    podcasts.record_feed_meta(
        idx,
        feed_id,
        title=None,
        description=None,
        homepage=None,
        etag=None,
        last_modified=None,
        ok=False,
        error="network down",
    )
    idx = _reopen(idx, db_path)
    feed = podcasts.get_feed(idx, feed_id)
    assert (feed["error_count"], feed["last_error"]) == (1, "network down")

    assert podcasts.set_episode_status(
        idx, episode_id, podcasts.EPISODE_STATUS_QUEUED
    )
    idx = _reopen(idx, db_path)
    assert podcasts.get_episode(idx, episode_id)["status"] == "queued"

    podcasts._record_audio_result(
        idx,
        episode_id,
        local_path=str(tmp_path / "episode.mp3"),
        size_bytes=456,
        error=None,
        status=podcasts.EPISODE_STATUS_DOWNLOADED,
    )
    idx = _reopen(idx, db_path)
    episode = podcasts.get_episode(idx, episode_id)
    assert (episode["audio_size_bytes"], episode["status"]) == (456, "downloaded")

    whisper_runner.update_episode_transcript_state(
        idx,
        episode_id,
        status=whisper_runner.STATUS_RUNNING,
        model_used="base",
    )
    idx = _reopen(idx, db_path)
    assert podcasts.get_episode(idx, episode_id)["transcript_status"] == "running"

    transcript_path = tmp_path / "episode.transcript.json"
    whisper_runner.update_episode_transcript_state(
        idx,
        episode_id,
        status=whisper_runner.STATUS_DONE,
        transcript_path=transcript_path,
        model_used="base",
        diarization_ran=True,
    )
    idx = _reopen(idx, db_path)
    episode = podcasts.get_episode(idx, episode_id)
    assert (
        episode["transcript_status"],
        episode["transcript_local_path"],
        episode["transcript_model_used"],
        episode["diarization_ran"],
    ) == ("done", str(transcript_path), "base", 1)

    # Phase 3 (contract phase3-v1, "legacy delete routes"): a feed linked to a source
    # subscription is archived, not deleted; the row and its episodes survive restart
    # with detection and ingestion off.
    assert podcasts.remove_feed(idx, feed_id)
    idx = _reopen(idx, db_path)
    feed = podcasts.get_feed(idx, feed_id)
    assert (feed["enabled"], feed["auto_ingest"]) == (0, 0)
    assert [e["id"] for e in podcasts.list_episodes(idx, feed_id=feed_id)] == [episode_id]
    idx.close()


def test_episode_batch_rolls_back_on_write_error(tmp_path):
    db_path = tmp_path / "index.db"
    idx = index_mod.Index.open(db_path)
    feed_id = podcasts.add_feed(idx, "https://example.test/feed.xml")["id"]
    invalid = _one_episode("episode-bad")
    invalid["duration_seconds"] = object()

    with pytest.raises(sqlite3.ProgrammingError):
        podcasts.upsert_episodes(
            idx, feed_id, [_one_episode("episode-good"), invalid]
        )

    assert idx._conn.in_transaction is False
    assert podcasts.list_episodes(idx, feed_id=feed_id) == []
    idx = _reopen(idx, db_path)
    assert podcasts.list_episodes(idx, feed_id=feed_id) == []
    idx.close()


def test_poll_success_and_failure_metadata_survive_restart(tmp_path, monkeypatch):
    db_path = tmp_path / "index.db"
    idx = index_mod.Index.open(db_path)
    feed_id = podcasts.add_feed(idx, "https://example.test/feed.xml")["id"]
    body = b"""<?xml version="1.0"?>
    <rss><channel><title>Restart Show</title>
      <item><guid>poll-episode</guid><title>First</title>
        <enclosure url="https://cdn.example.test/first.mp3" />
      </item>
    </channel></rss>"""
    monkeypatch.setattr(
        podcasts,
        "fetch_feed",
        lambda _feed: (body, {"ETag": '"poll-v1"'}),
    )

    # Phase 3 (contract phase3-v1, "Scheduler and adapter boundaries"): a linked feed is
    # polled only through the subscription service's gate. The ungated legacy poll refuses
    # without network I/O, and the refusal names the source that owns the feed; the feed
    # row, its link and its (empty) episode list survive restart unchanged.
    fetched = []
    monkeypatch.setattr(podcasts, "fetch_feed", lambda feed: fetched.append(feed) or (body, {}))
    result = podcasts.poll_feed(idx, feed_id)
    assert (result["ok"], result["error"]) == (False, "managed_by_subscription")
    assert result["source_id"] and fetched == []
    idx = _reopen(idx, db_path)
    feed = podcasts.get_feed(idx, feed_id)
    assert feed["feed_url"] == "https://example.test/feed.xml"
    assert podcasts.list_episodes(idx, feed_id=feed_id) == []
    assert podcasts.poll_feed(idx, feed_id)["source_id"] == result["source_id"]

    # Fetch failures recorded by the feed-metadata writer still survive restart.
    podcasts.record_feed_meta(idx, feed_id, title=None, description=None, homepage=None,
                              etag=None, last_modified=None, ok=False, error="offline")
    idx = _reopen(idx, db_path)
    feed = podcasts.get_feed(idx, feed_id)
    assert (feed["error_count"], feed["last_error"]) == (1, "offline")
    idx.close()


def test_podcast_write_refuses_to_commit_an_existing_transaction(tmp_path):
    db_path = tmp_path / "index.db"
    idx = index_mod.Index.open(db_path)
    idx._conn.execute(
        "INSERT INTO podcast_feeds (feed_url, poll_interval_min, added_at) "
        "VALUES ('https://uncommitted.example/feed', 60, '2026-08-01')"
    )

    with pytest.raises(RuntimeError, match="another transaction is active"):
        podcasts.add_feed(idx, "https://example.test/feed.xml")

    idx._conn.rollback()
    idx = _reopen(idx, db_path)
    assert podcasts.list_feeds(idx) == []
    idx.close()
