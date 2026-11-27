"""Podcast feeds read a bounded window and publish poll errors to both listings."""
import io

import pytest

import index
import podcasts
import source_subscriptions as ss
from tests.source_subscriptions_fixtures import (
    Clock, FEED_URL, MINUTE_MS, REGISTRY, make_service, open_index, register,
)


class FeedStream(io.BytesIO):
    status = 200
    headers = {"ETag": '"window"'}

    def __init__(self, body, *, chunk_size=None):
        super().__init__(body)
        self.bytes_read = 0
        self.chunk_size = chunk_size

    def read(self, size=-1):
        if self.chunk_size is not None:
            size = min(size, self.chunk_size) if size >= 0 else self.chunk_size
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


def archive(atom=False):
    if atom:
        start, end = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Orbit</title>', b'</feed>'
        item = b'<entry><id>%d</id><title>Episode</title><summary>%s</summary></entry>'
    else:
        start, end = b'<rss><channel><title>Orbit</title>', b'</channel></rss>'
        item = b'<item><guid>%d</guid><title>Episode</title><description>%s</description></item>'
    return start + b''.join(item % (n, b'x' * 9000) for n in range(1500)) + end


@pytest.mark.parametrize("atom", [False, True])
def test_poll_reads_only_recent_window_of_large_feed(monkeypatch, atom):
    response = FeedStream(archive(atom))
    monkeypatch.setattr(ss, "public_http_open", lambda *a, **kw: response)
    result = ss.PodcastRssAdapter().poll({"source_key": FEED_URL}, {}, conditional=False)
    assert result.status == "snapshot", result
    assert result.feed_title == "Orbit" and result.etag == '"window"'
    assert result.truncated and result.coverage == "window"
    assert [item.entry_id for item in result.observations] == [
        str(i) for i in range(ss.PODCAST_ENTRIES_PER_POLL)]
    assert 0 < response.bytes_read < 600_000
    assert response.closed


def test_legacy_poll_reads_only_recent_window(tmp_path, monkeypatch):
    idx = open_index(tmp_path)
    with idx.write_transaction() as conn:
        fid = conn.execute("INSERT INTO podcast_feeds (feed_url, added_at) VALUES (?, '2026-01-01')",
                           (FEED_URL,)).lastrowid
    response = FeedStream(archive())
    monkeypatch.setattr(ss, "public_http_open", lambda *a, **kw: response)
    try:
        result = podcasts.poll_feed(idx, fid)
        assert result["ok"] and result["inserted"] == ss.PODCAST_ENTRIES_PER_POLL
        assert 0 < response.bytes_read < 600_000
    finally:
        idx.close()


def test_oversized_first_window_error_is_visible_and_cleared(tmp_path, monkeypatch):
    idx = open_index(tmp_path)
    clock = Clock()
    service = make_service(idx, clock=clock, adapter=ss.PodcastRssAdapter())
    source = register(service, "podcast_rss", FEED_URL)
    fid = source["legacy"]["feed_id"]
    body = b"<rss><channel><title>Orbit</title><item>" + b"x" * (ss.FEED_MAX_BYTES + 1)
    response = FeedStream(body)
    monkeypatch.setattr(ss, "public_http_open", lambda *a, **kw: response)

    def refresh(source_id):
        return service.refresh_source(REGISTRY, {"source_id": source_id})

    try:
        result = podcasts.poll_feed(idx, fid, refresh=refresh)
        assert not result["ok"]
        row = podcasts.list_feeds(idx)[0]
        assert row["error_count"] == 1
        assert row["last_error"] == result["error"] and "8 MiB" in result["error"]
        assert podcasts.get_feed(idx, fid)["last_error"] == row["last_error"]
        assert response.closed and response.bytes_read <= ss.FEED_MAX_BYTES + 1
        retry = podcasts.poll_feed(idx, fid, refresh=refresh)
        assert retry["outcome"] == "not_due" and retry["last_error"] == row["last_error"]
        clock.advance(61 * MINUTE_MS)
        response = FeedStream(b"<rss><channel><title>Small</title></channel></rss>")
        assert podcasts.poll_feed(idx, fid, refresh=refresh)["ok"]
        row = podcasts.get_feed(idx, fid)
        assert row["error_count"] == 0 and row["last_error"] is None
    finally:
        idx.close()


def test_podcast_poller_refuses_document_type(monkeypatch):
    response = FeedStream(b"<!DOCTYPE rss><rss><channel><title>Orbit</title></channel></rss>",
                          chunk_size=3)
    monkeypatch.setattr(ss, "public_http_open", lambda *a, **kw: response)
    result = ss.PodcastRssAdapter().poll({"source_key": FEED_URL}, {}, conditional=False)
    assert result.status == "error" and result.error_code == "malformed_feed"
    assert "document type" in result.error_message.lower()


def test_upgrade_exposes_existing_subscription_backoff(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.db"
    through_39 = [(version, file) for version, file in index._discover_migrations() if version <= 39]
    with monkeypatch.context() as old:
        old.setattr(index, "_discover_migrations", lambda: through_39)
        with index.Index.open(path) as idx:
            source = register(make_service(idx), "podcast_rss", FEED_URL)
            fid = source["legacy"]["feed_id"]
            with idx.write_transaction() as conn:
                conn.execute("UPDATE source_detection_cursors SET error_count=2, "
                             "last_error_code='feed_too_large', last_error_message='Feed body exceeds the bounded byte budget' "
                             "WHERE source_id=?", (source["source_id"],))
            assert podcasts.get_feed(idx, fid)["error_count"] == 0
    with index.Index.open(path) as idx:
        row = podcasts.get_feed(idx, fid)
        assert row["error_count"] == 2
        assert "8 MiB" in row["last_error"]


@pytest.mark.parametrize("atom", [False, True])
def test_podcast_publish_date_has_priority_over_alternate(atom):
    later = "2026-12-01T12:00:00Z"
    earlier = "2025-03-01T12:00:00Z"
    if atom:
        body = (f"<feed><entry><id>one</id><updated>{later}</updated>"
                f"<published>{earlier}</published></entry>"
                f"<entry><id>two</id><published/><updated>{later}</updated></entry></feed>")
    else:
        body = (f"<rss><channel><item><guid>one</guid><published>{later}</published>"
                f"<pubDate>{earlier}</pubDate></item>"
                f"<item><guid>two</guid><pubDate/><published>{later}</published></item></channel></rss>")
    direct = podcasts.parse_feed_body(body)["episodes"]
    observed = ss.PodcastRssAdapter().parse(body.encode(), {}).observations
    assert [entry["published_at"] for entry in direct] == [earlier, later]
    assert [entry.metadata["published_raw"] for entry in observed] == [earlier, later]


@pytest.mark.parametrize("via_source", [False, True])
def test_repeat_observations_repair_dates_and_keep_identity(tmp_path, via_source):
    audio = "https://audio.example.test/one.mp3"
    with open_index(tmp_path) as idx:
        service = make_service(idx)
        source = register(service, "podcast_rss", FEED_URL)
        fid = source["legacy"]["feed_id"]
        # A manual suggestion save and a previously seen but undated episode.
        podcasts.upsert_episodes(idx, fid, [
            {"guid": ss.suggested_episode_guid(audio), "audio_url": audio, "title": "Adopted"},
            {"guid": "two", "title": "Second", "published_at": "missing"},
            {"guid": "third", "title": "Third", "published_at": "2026-10-01"},
        ])
        original = {e["title"]: e["id"] for e in podcasts.list_episodes(idx)}
        for when in ("2026-09-01", "2026-11-01", None):
            episodes = [{"guid": "one", "title": "Adopted", "audio_url": audio, "published_at": when},
                        {"guid": "two", "title": "Second", "published_at": when}]
            if via_source:
                observations = [ss.Observation(
                    entry_id=e["guid"], title=e["title"], canonical_url=None,
                    published_at_ms=ss.parse_published_ms(when),
                    metadata={"published_raw": when, "audio_url": e.get("audio_url")})
                    for e in episodes]
                with idx.write_transaction() as conn:
                    entry = service._source(conn, source["source_id"])
                    service._persist_observations(conn, entry, observations, 0, 1, None)
            else:
                podcasts.upsert_episodes(idx, fid, episodes)
            rows = podcasts.list_episodes(idx)
            expected = when or "2026-11-01"
            assert {e["title"]: e["id"] for e in rows} == original
            assert [(e["published_at"], e["published_at_ms"]) for e in rows if e["guid"] != "third"] == [
                (expected, ss.parse_published_ms(expected))] * 2
            assert rows[0]["title"] == ("Third" if expected == "2026-09-01" else "Second")
