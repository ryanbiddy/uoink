"""Exercise podcast media boundaries with in-memory responses and stubbed media tools."""
import io
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

import index
import podcasts
import server
import show_capture
import source_subscriptions as ss


class Response(io.BytesIO):
    headers = {}


def test_distinct_recordings_with_identical_titles_and_owned_legacy_file(tmp_path, monkeypatch):
    def run(args, **kw):
        path = Path(args[args.index("-o") + 1].replace("%(ext)s", "mp3"))
        path.write_bytes(args[-1].encode())
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("uoink_processes.run_owned", run)
    monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
    with index.Index.open(tmp_path / "index.db") as idx:
        rows = []
        for fid, count in (("first", 2), ("second", 1)):
            feed = podcasts.add_feed(idx, f"https://{fid}.test/rss", title="The show")
            eps = [{"guid": str(n), "title": "Episode", "audio_url": f"https://audio.test/{fid}/{n}"}
                   for n in range(count)]
            podcasts.upsert_episodes(idx, feed["id"], eps)
            rows.extend(podcasts.list_episodes(idx, feed_id=feed["id"]))
        legacy = tmp_path / "Podcasts" / "the-show" / "episode.mp3"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"old recording")
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET audio_local_path=? WHERE id=?", (str(legacy), rows[0]["id"]))
        paths = []
        for number, row in enumerate(rows):
            opts = dict(data_root=tmp_path, ytdlp_cmd=["fixture"], resolve_url=lambda url, **kw: url)
            result = podcasts.download_episode_audio(idx, row["id"], **opts)
            assert result["ok"], result
            path = Path(result["local_path"])
            assert path.read_bytes() == (b"old recording" if number == 0 else row["audio_url"].encode())
            assert podcasts.download_episode_audio(idx, row["id"], **opts)["skipped_existing"]
            paths.append(path)
        assert len(set(paths)) == 3


def test_unowned_file_at_target_is_never_adopted(tmp_path):
    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.test/rss")
        podcasts.upsert_episodes(idx, feed["id"], [dict(guid="1", title="episode", audio_url="https://audio.test/one")])
        row, = podcasts.list_episodes(idx)
        path = podcasts._episode_audio_path(tmp_path, feed, row)
        path.write_bytes(b"unclaimed")
        result = podcasts.download_episode_audio(idx, row["id"], data_root=tmp_path,
                                                  resolve_url=Mock(side_effect=ValueError("offline")))
        assert not result["ok"] and not podcasts.get_episode(idx, row["id"])["audio_local_path"]


def test_ambiguous_legacy_claims_stay_unusable_for_both_episodes(tmp_path):
    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.test/rss", title="Show")
        podcasts.upsert_episodes(idx, feed["id"], [
            {"guid": guid, "title": "Episode", "audio_url": f"https://audio.test/{guid}"} for guid in ("one", "two")])
        legacy = tmp_path / "Podcasts" / "show" / "episode.mp3"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"ambiguous recording")
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET audio_local_path=?", (str(legacy),))
        offline = Mock(side_effect=ValueError("offline"))
        for row in podcasts.list_episodes(idx):
            result = podcasts.download_episode_audio(idx, row["id"], data_root=tmp_path, resolve_url=offline)
            assert not result["ok"]
            assert podcasts.get_episode(idx, row["id"])["audio_local_path"] is None
        assert offline.call_count == 2 and legacy.read_bytes() == b"ambiguous recording"


@pytest.mark.parametrize("purpose", ["show", "thumbnail"])
def test_download_deadline_closes_slow_stream(tmp_path, monkeypatch, purpose):
    clock = [0.0]
    class Slow(Response):
        def read(self, size=-1):
            clock[0] += 60
            return super().read(size)
    body = Slow(b"<rss><channel><title>show</title></channel></rss>")
    monkeypatch.setattr(ss.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ss, "public_http_open", lambda *a, **kw: body)
    child = Mock()
    monkeypatch.setattr(server, "_run_subprocess", child)
    if purpose == "show":
        with pytest.raises(show_capture.ShowCaptureError):
            server._ServerShowBackend().fetch_feed("https://feed.test/rss")
    else:
        assert server._download_thumbnail({"thumbnail": "https://images.test/a"}, tmp_path) is None
        child.assert_not_called()
    assert body.closed and not list(tmp_path.iterdir())


def test_thumbnail_bounds_reads_pixels_and_conversion(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    class Chunked(Response):
        def read(self, size=-1):
            assert 0 < size <= 65536
            return super().read(size)
    def convert(args, **kw):
        assert 0 < kw["timeout"] <= 30
        assert 0 < int(args[args.index("-max_pixels") + 1]) <= 20_000_000
        assert args.index("-max_pixels") < args.index("-i")
        Path(args[-1]).write_bytes(b"fixture jpeg")
    monkeypatch.setattr(server, "_run_subprocess", convert)
    jpg = server._download_thumbnail({"thumbnail": "https://images.test/a"}, tmp_path,
                                     http_open=lambda *a, **kw: Chunked(b"\xff\xd8\xff" + bytes(16)))
    assert jpg and jpg.read_bytes() == b"fixture jpeg"


def test_thumbnail_size_ceiling_cleans_partial_file(tmp_path, monkeypatch):
    class Large(Response):
        read_bytes = 0
        def read(self, size=-1):
            batch = min(size, 64 * 1024) if size > 0 else 32
            self.read_bytes += batch
            return bytes(batch) if self.read_bytes <= 9 * 1024 * 1024 else b""
    body = Large()
    convert = Mock()
    monkeypatch.setattr(server, "_run_subprocess", convert)
    assert server._download_thumbnail({"thumbnail": "https://images.test/a"}, tmp_path,
                                      http_open=lambda *a, **kw: body) is None
    assert body.closed and body.read_bytes <= 8 * 1024 * 1024 + 1
    convert.assert_not_called()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("atom", [True, False])
def test_show_listing_consumes_entries_without_serializing_feed(monkeypatch, atom):
    from tests.test_podcast_stream import archive, FeedStream
    body = FeedStream(archive(atom), chunk_size=2048)
    monkeypatch.setattr(ss, "public_http_open", lambda *a, **kw: body)
    monkeypatch.setattr(show_capture, "MAX_EPISODES", 5)
    monkeypatch.setattr(podcasts.ET, "tostring", Mock(side_effect=AssertionError("serialized the XML tree")))
    result = server._ServerShowBackend().fetch_feed("https://feed.test/rss")
    assert result["feed"]["title"] == "Orbit"
    assert [ep["guid"] for ep in result["episodes"]] == ["0", "1", "2", "3", "4", "5"]
    assert all(len(ep["description"]) == 2000 for ep in result["episodes"])
    assert body.bytes_read < 60_000 and body.closed


def test_thumbnail_conversion_timeout_cleans_partial_output(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    existing = tmp_path / "thumbnail.jpg"
    existing.write_bytes(b"previous thumbnail")
    def timeout(args, **kw):
        Path(args[-1]).write_bytes(b"incomplete")
        raise subprocess.TimeoutExpired(args, kw.get("timeout", 0))
    converter = Mock(side_effect=timeout)
    monkeypatch.setattr(server, "_run_subprocess", converter)
    path = server._download_thumbnail({"thumbnail": "https://images.test/a"}, tmp_path,
                                      http_open=lambda *a, **kw: Response(b"\xff\xd8\xff" + bytes(16)))
    converter.assert_called_once()
    assert path is None and list(tmp_path.iterdir()) == [existing]
    assert existing.read_bytes() == b"previous thumbnail"


@pytest.mark.parametrize("platform", ["win32", "linux"])
@pytest.mark.parametrize("admit", [True, False])
def test_podcast_reliability_checks_saved_url_before_download(tmp_path, monkeypatch, platform, admit):
    url = "https://episode.test/page"
    final = "https://episode.test/final"
    from tests.test_podcast_corpus_bridge import _seed_episode
    idx, episode_id, _, _ = _seed_episode(tmp_path, page_url=url)
    published = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(ss, "_check_resolved_host", lambda host: ["8.8.8.8"])
    monkeypatch.setattr(server._platform.sys, "platform", platform)
    monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
    monkeypatch.setattr(server._platform, "require_media", lambda: None)
    monkeypatch.setattr(server, "_reliability_model_status", lambda *a: {"cached": True})
    monkeypatch.setattr(server, "_selected_reliability_model", lambda: "fixture")
    probe = Mock(return_value=final, side_effect=None if admit else ValueError("fixture refused"))
    monkeypatch.setattr(ss, "resolve_public_http_url", probe)
    child = Mock(side_effect=RuntimeError("stop after inspecting arguments"))
    monkeypatch.setattr(server, "_run_subprocess", child)
    try:
        server._compute_transcript_reliability(published["video_id"])
    finally:
        idx.close()
    assert probe.call_args.args == (url,)
    if admit:
        assert child.call_args.args[0][-2:] == ["--", final]
    else:
        child.assert_not_called()
