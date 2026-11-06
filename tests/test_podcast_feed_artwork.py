"""Feed artwork is cached once per feed at poll time and never loaded remotely.

Run: python -m pytest -q tests/test_podcast_feed_artwork.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    Clock, FEED_URL, FakeBackend, FakeFetch, http, open_index, register, turn_on,
)

import podcasts  # noqa: E402
import server  # noqa: E402
import source_subscriptions as ss  # noqa: E402

ART_URL = "https://show.example/cover.jpg"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class _Resp(io.BytesIO):
    def __init__(self, body, content_type, length=None):
        super().__init__(body)
        self.headers = {"Content-Type": content_type}
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _opener(body, content_type, length=None, calls=None):
    def open_(url, headers=None):
        if calls is not None:
            calls.append(url)
        return _Resp(body, content_type, length)
    return open_


FEED = {"id": 7, "title": "The Show"}


def test_caches_one_copy_as_artwork_ext_and_the_library_finds_it(tmp_path):
    calls = []
    path = podcasts.cache_feed_artwork(tmp_path, FEED, ART_URL,
                                       opener=_opener(JPEG, "image/jpeg; charset=binary", calls=calls))
    assert path == tmp_path / "Podcasts" / "the-show" / "artwork.jpg" and path.read_bytes() == JPEG
    # Once per feed: a later poll finds the file and fetches nothing.
    again = podcasts.cache_feed_artwork(tmp_path, FEED, ART_URL, opener=_opener(PNG, "image/png", calls=calls))
    assert again == path and len(calls) == 1
    episode_folder = path.parent / "episode-one-abc123"
    assert server._local_podcast_artwork(episode_folder) == str(path)


def test_refuses_other_content_types_oversize_and_mismatched_bytes(tmp_path):
    big = b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024)
    cases = [
        _opener(b"<svg/>", "image/svg+xml"),
        _opener(b"<html>", "text/html"),
        _opener(big, "image/jpeg"),
        _opener(JPEG, "image/jpeg", length=6 * 1024 * 1024),
        _opener(b"not really a png", "image/png"),
    ]
    for opener in cases:
        assert podcasts.cache_feed_artwork(tmp_path, FEED, ART_URL, opener=opener) is None
    assert not list((tmp_path / "Podcasts").rglob("artwork*"))


def test_no_title_or_link_means_nothing_to_cache(tmp_path):
    def boom(*a, **k):
        raise AssertionError("must not fetch")
    assert podcasts.cache_feed_artwork(tmp_path, {"id": 1, "title": "Untitled podcast"}, ART_URL, opener=boom) is None
    assert podcasts.cache_feed_artwork(tmp_path, FEED, "file:///etc/passwd", opener=boom) is None
    assert podcasts.cache_feed_artwork(tmp_path, FEED, None, opener=boom) is None


class _ArtBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.artwork = []

    def cache_feed_artwork(self, source, artwork_url):
        self.artwork.append((source["legacy_feed_id"], artwork_url))


def test_a_poll_hands_the_backend_the_feed_artwork_link(tmp_path):
    body = (b'<?xml version="1.0"?><rss version="2.0"><channel><title>The Show</title>'
            b'<image><url>' + ART_URL.encode() + b'</url></image>'
            b'<item><guid>g1</guid><title>One</title>'
            b'<enclosure url="https://cdn.example/1.mp3" type="audio/mpeg"/></item></channel></rss>')
    idx = open_index(tmp_path)
    backend = _ArtBackend()
    service = ss.SourceSubscriptionService(
        index=idx, clock=Clock(), adapters=ss.default_adapters(FakeFetch([http(200, body)])),
        backend=backend, instance_id="t")
    sid = register(service, "podcast_rss", FEED_URL)["source_id"]
    turn_on(service, sid)
    assert service.detection_pass()[0]["ok"]
    assert [url for _feed, url in backend.artwork] == [ART_URL]
    idx.close()


def test_an_artwork_failure_never_fails_the_poll(tmp_path):
    class Broken(_ArtBackend):
        def cache_feed_artwork(self, source, artwork_url):
            raise OSError("disk full")
    body = (b'<?xml version="1.0"?><rss version="2.0"><channel><title>The Show</title>'
            b'<image><url>' + ART_URL.encode() + b'</url></image>'
            b'<item><guid>g1</guid><title>One</title></item></channel></rss>')
    idx = open_index(tmp_path)
    service = ss.SourceSubscriptionService(
        index=idx, clock=Clock(), adapters=ss.default_adapters(FakeFetch([http(200, body)])),
        backend=Broken(), instance_id="t")
    sid = register(service, "podcast_rss", FEED_URL)["source_id"]
    turn_on(service, sid)
    assert service.detection_pass()[0]["ok"]
    idx.close()
