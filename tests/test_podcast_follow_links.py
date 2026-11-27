import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import index
import podcasts
import server
import show_capture
import source_subscriptions
import uoink_cli
import uoink_mcp_tools as tools


DATA = Path(__file__).parent / "fixtures"
SHOW = "https://podcasts.apple.com/us/podcast/signal-notes/id42"
FEED = "https://feeds.example.test/signal.xml"


class Response(io.BytesIO):
    headers = {}


@pytest.fixture
def library(tmp_path, monkeypatch):
    idx = index.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_source_service_instance", None)
    monkeypatch.setattr(server, "_podcast_suggestion_setup_problem", lambda: None)
    monkeypatch.setattr(tools, "_b", lambda: server)
    yield idx
    idx.close()


def wire(monkeypatch, *, feed=None, apple=None):
    calls = []

    def fetch(url, *, headers, timeout):
        calls.append(url)
        if urlparse(url).hostname == "itunes.apple.com":
            assert timeout <= 8
            return Response(apple if apple is not None else (DATA / "podcast_apple_lookup.json").read_bytes())
        assert url == FEED
        return Response(feed if feed is not None else (DATA / "podcast_apple_show.xml").read_bytes())

    monkeypatch.setattr(source_subscriptions, "public_http_open", fetch)
    return calls


def cli_capture(url):
    tool, args = uoink_cli.friendly_call(uoink_cli.parser().parse_args(["capture", url]), server)
    return tools.TOOL_REGISTRY[tool].handler(args)


@pytest.mark.parametrize(("track", "guid"), [(71, "episode-two"), (72, "episode-one"), (73, "episode-three")])
def test_apple_episode_paste_selects_only_matching_episode(library, tmp_path, monkeypatch, track, guid):
    calls = wire(monkeypatch)
    result = cli_capture(f"{SHOW}?i={track}")
    assert result["ok"], result
    assert result["feed"]["feed_url"] == FEED
    assert not result["feed"]["enabled"]
    assert podcasts.get_episode(library, result["episode_id"])["guid"] == guid
    [job] = show_capture.list_jobs(tmp_path)
    assert job["id"] == result["show_job_id"] and job["state"] == show_capture.RUNNING
    assert [episode["guid"] for episode in job["episodes"]] == [guid]
    assert parse_qs(urlparse(calls[0]).query) == {"id": ["42"], "entity": ["podcastEpisode"], "limit": ["200"]}
    assert cli_capture(f"{SHOW}?i={track}")["show_job_id"] == job["id"]


def test_apple_show_follows_the_real_feed_and_can_be_followed_again(library, monkeypatch):
    calls = wire(monkeypatch)
    result = cli_capture(SHOW)
    assert result["ok"], result
    feed = result["feed"]
    assert feed["feed_url"] == FEED and feed["title"] == "Signal Notes"
    assert feed["enabled"] and not feed["auto_ingest"]
    assert parse_qs(urlparse(calls[0]).query) == {"id": ["42"]}
    assert podcasts.remove_feed(library, feed["id"])
    assert cli_capture(SHOW)["feed"]["id"] == feed["id"]
    flags = library._conn.execute("SELECT archived,follow_feed,detection_enabled,consent_state FROM source_subscriptions").fetchone()
    assert tuple(flags) == (0, 1, 1, "off")


@pytest.mark.parametrize(("link", "kwargs", "message"), [
    (SHOW, {"apple": b"{invalid"}, "Apple"),
    (SHOW + "?i=74", {}, "episode"),
    (FEED, {"feed": b"<!doctype html><html><body>Home</body></html>"}, "That link is a web page, not a podcast feed"),
])
def test_bad_paste_leaves_no_subscription(library, monkeypatch, link, kwargs, message):
    wire(monkeypatch, **kwargs)
    result = cli_capture(link)
    assert result["ok"] is False and message in result["error"]
    assert not podcasts.list_feeds(library)


def test_name_is_read_in_background_after_feed_type_check(library, monkeypatch):
    monkeypatch.setattr(server, "_TOKEN_OWNED", True)
    title_requested, allow_title, title_read = (threading.Event() for _ in range(3))
    calls = []

    def feed(row, *, limit=None):
        assert row["feed_url"] == FEED
        calls.append(limit)
        if limit == 0:
            return b"<rss><channel /></rss>", {}
        title_requested.set()
        assert allow_title.wait(3)
        title_read.set()
        return (DATA / "podcast_apple_show.xml").read_bytes(), {}

    monkeypatch.setattr(podcasts, "fetch_feed", feed)
    try:
        result = cli_capture(FEED)
        assert result["ok"], result
        assert result["feed"]["title"] == "feeds.example.test"
        assert title_requested.wait(1) and not title_read.is_set()
    finally:
        allow_title.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and podcasts.get_feed(library, result["feed"]["id"])["title"] != "Signal Notes":
        time.sleep(0.01)
    assert podcasts.get_feed(library, result["feed"]["id"])["title"] == "Signal Notes"
    assert library._conn.execute("SELECT display_name FROM source_subscriptions").fetchone()[0] == "Signal Notes"
    assert calls == [0, 1]


@pytest.mark.parametrize("url", [FEED, SHOW + "?i=71"])
def test_offline_cli_hands_durable_work_to_helper(tmp_path, url):
    # End an actual one-shot CLI process before inspecting what its helper
    # will recover. Network, model setup, and the supervisor are fixture-only.
    code = """
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
import sys
with redirect_stdout(sys.stderr):
    import index, podcasts, server, source_subscriptions as ss, uoink_cli, uoink_agent_runtime as runtime
    from tests.test_podcast_follow_links import DATA, FEED, Response
    root = Path(sys.argv[1])
    server.DATA_ROOT = root
    idx = index.Index.open(root / 'index.db')
server._get_index = lambda: idx
server._podcast_suggestion_setup_problem = lambda: None
runtime.helper_running = lambda backend: False
podcasts.fetch_title_in_background = lambda *args: (root / 'client-title-worker').touch()
def fetch(url, **kwargs):
    fixture = 'podcast_apple_show.xml' if url == FEED else 'podcast_apple_lookup.json'
    return Response((DATA / fixture).read_bytes())
ss.public_http_open = fetch
def start(cmd, **kwargs):
    assert any(str(arg).endswith('uoink_supervisor.py') for arg in cmd) and '--quiet' in cmd
    assert kwargs['stdout'] == kwargs['stderr'] == runtime.subprocess.DEVNULL
    (root / 'started').touch()
with patch.object(runtime.subprocess, 'Popen', start):
    exit_code = uoink_cli.main(['capture', sys.argv[2]])
idx.close()
raise SystemExit(exit_code)
"""
    done = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path), url],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, (done.stdout, done.stderr)
    result = json.loads(done.stdout)
    assert result["ok"] and (tmp_path / "started").is_file()
    assert not (tmp_path / "client-title-worker").exists()
    if url == FEED:
        idx = index.Index.open(tmp_path / "index.db")
        try:
            service = source_subscriptions.SourceSubscriptionService(index=idx)
            adapter = source_subscriptions.PodcastRssAdapter(lambda url, headers:
                source_subscriptions.FetchResponse(200, {}, (DATA / "podcast_apple_show.xml").read_bytes()))
            service.adapters["podcast_rss_v1"] = adapter
            [outcome] = service.detection_pass()
            assert outcome["ok"]
            assert podcasts.get_feed(idx, result["feed"]["id"])["title"] == "Signal Notes"
        finally:
            idx.close()
    else:
        job = show_capture.load(tmp_path, result["show_job_id"])
        assert job["state"] == show_capture.RUNNING
        assert [episode["guid"] for episode in job["episodes"]] == ["episode-two"]
