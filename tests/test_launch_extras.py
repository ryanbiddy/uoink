"""Launch findings F1, F11, F14, F16, F17, F19 and A4, without live I/O."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import notes
import podcasts
import server
import source_subscriptions as ss
import uoink_mcp_tools as mcp_tools
from tests.source_subscriptions_fixtures import (
    FEED_URL, REGISTRY, make_service, open_index, turn_on,
)
from tests.test_dashboard_runthrough_fixes import run_js

ROOT = Path(__file__).resolve().parents[1]
ART = "https://cdn.example/show.jpg"
FEED = b'''<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel><title>Space stories</title><itunes:image href="https://cdn.example/show.jpg"/>
<item><guid>episode-1</guid><title>First flight</title>
<link>https://show.example/first</link><enclosure url="https://cdn.example/first.mp3"/>
<pubDate>Thu, 05 Nov 2026 00:00:00 GMT</pubDate></item></channel></rss>'''


@pytest.fixture
def feed_env(tmp_path, monkeypatch):
    idx = open_index(tmp_path)
    calls = []

    def fetch(url, headers):
        calls.append(url)
        return ss.FetchResponse(200, {}, FEED)

    service = make_service(idx, clock=lambda: int(time.time() * 1000), adapter=ss.PodcastRssAdapter(fetch))
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_source_service", lambda: service)
    monkeypatch.setattr(mcp_tools, "_sources_service", lambda: service)
    monkeypatch.setattr(mcp_tools, "_sources_context", lambda *_: REGISTRY)
    monkeypatch.setitem(mcp_tools._SOURCES_RATE_LIMITERS, "register_source", SimpleNamespace(check=lambda: None))
    monkeypatch.setattr(server, "_mcp_tools_module", lambda: mcp_tools)
    handler = object.__new__(server.Handler)
    handler._send_json = lambda code, body: (code, body)
    yield idx, service, calls, handler
    idx.close()


def test_subscribe_fetches_title_and_first_episode_with_capture_off(feed_env):
    idx, service, calls, handler = feed_env
    code, result = handler._handle_sources_tool(
        "register_source", {"kind": "podcast_rss", "url": FEED_URL})
    assert code == 200
    source = result["source"]
    assert source["display_name"] == "Space stories"
    assert source["consent_state"] == "off"
    assert source["latest_episode"]["title"] == "First flight"
    assert source["latest_episode"]["video_id"] is None
    assert calls == [FEED_URL]
    assert idx._conn.execute("SELECT COUNT(*) FROM source_capture_starts").fetchone()[0] == 0
    handler._handle_sources_tool("register_source", {"kind": "podcast_rss", "url": FEED_URL})
    assert calls == [FEED_URL], "duplicate registration must not fetch again"


def test_registry_tool_subscribe_fetches_title_on_the_dashboard_transport(feed_env):
    _, _, calls, _ = feed_env
    result = mcp_tools.register_source({"kind": "podcast_rss", "url": FEED_URL})
    assert result["source"]["display_name"] == "Space stories"
    assert result["source"]["latest_episode"]["title"] == "First flight"
    assert calls == [FEED_URL]


def test_subscribe_preserves_custom_name_and_falls_back_on_fetch_failure(feed_env):
    _, service, calls, handler = feed_env
    _, result = handler._handle_sources_tool("register_source", {
        "kind": "podcast_rss", "url": FEED_URL, "display_name": "My space feed"})
    assert result["source"]["display_name"] == "My space feed"

    def fail(*_):
        raise OSError("offline")

    service.adapters[ss.ADAPTERS["podcast_rss"]] = ss.PodcastRssAdapter(fail)
    code, result = handler._handle_sources_tool("register_source", {
        "kind": "podcast_rss", "url": "https://offline.example/feed.xml"})
    assert code == 200 and result["created"] is True
    source = result["source"]
    assert (source["display_name"] or source["canonical_url"]) == "https://offline.example/feed.xml"
    assert source["detection"]["consecutive_failures"] == 1
    assert source["latest_episode"] is None


def test_legacy_subscribe_fetches_feed_title(feed_env):
    _, _, calls, handler = feed_env
    code, result = handler._handle_podcasts_feed_add({"feed_url": FEED_URL})
    assert code == 200 and result["feed"]["title"] == "Space stories"
    assert calls == [FEED_URL]


def test_first_consent_does_not_wait_an_hour_after_subscribe(feed_env):
    _, service, _, handler = feed_env
    _, result = handler._handle_sources_tool("register_source", {"kind": "podcast_rss", "url": FEED_URL})
    source_id = result["source"]["source_id"]
    turn_on(service, source_id)
    polled = service.detection_pass()
    assert len(polled) == 1
    assert polled[0]["enrollment"]["enrolled"] == 1


def test_first_consent_preserves_feed_failure_backoff(feed_env):
    _, service, _, handler = feed_env
    service.adapters[ss.ADAPTERS["podcast_rss"]] = ss.PodcastRssAdapter(
        lambda *_: ss.FetchResponse(429, {"Retry-After": "7200"}, b""))
    _, result = handler._handle_sources_tool("register_source", {"kind": "podcast_rss", "url": FEED_URL})
    source = result["source"]
    turn_on(service, source["source_id"])
    assert service.detection_pass() == []
    updated = service.source_status(REGISTRY, {"source_id": source["source_id"]})["source"]
    assert updated["detection"]["next_poll_at_ms"] == source["detection"]["next_poll_at_ms"]


@pytest.mark.parametrize("body", [
    FEED,
    b'<rss><channel><title>Space stories</title><image><url>https://cdn.example/show.jpg</url></image>'
    b'<item><guid>one</guid><title>First flight</title></item></channel></rss>',
    b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Space stories</title>'
    b'<logo>https://cdn.example/show.jpg</logo><entry><id>one</id><title>First flight</title></entry></feed>',
])
def test_podcast_parser_retains_feed_artwork(body):
    parsed = ss.PodcastRssAdapter().parse(body, {})
    assert parsed.observations[0].metadata["artwork_url"] == ART


def test_podcast_artwork_reaches_job_and_published_library_row(feed_env, tmp_path, monkeypatch):
    idx, service, _, handler = feed_env
    handler._handle_sources_tool("register_source", {"kind": "podcast_rss", "url": FEED_URL})
    episode = podcasts.list_episodes(idx)[0]
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fixture")
    transcript = tmp_path / "audio.transcript.json"
    transcript.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "First flight"}]}))
    with idx.write_transaction() as conn:
        conn.execute("UPDATE podcast_episodes SET audio_local_path=?, transcript_local_path=?, "
                     "transcript_status='done' WHERE id=?", (str(audio), str(transcript), episode["id"]))
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server.whisper_runner, "is_transcription_available", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda *_: True)
    monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
    monkeypatch.setattr(server, "_ensure_podcast_transcription_worker", lambda: None)
    monkeypatch.setattr(server, "_podcast_transcription_queue", SimpleNamespace(put=lambda *_: None))
    monkeypatch.setattr(server, "_jobs", {})
    result, code = server._queue_podcast_transcription(episode["id"])
    assert code == 202 and result["job"]["artwork_url"] == ART
    published = podcasts.episode_to_corpus(idx, episode["id"], data_root=tmp_path)
    row = idx.get_yoink(published["video_id"])
    assert json.loads(row["metadata_json"])["artwork_url"] == ART
    assert json.loads(Path(row["sidecar_path"]).read_text())["artwork_url"] == ART
    assert server._enrich_yoink_rows(idx, [row])[0]["artwork_url"] == ART


@pytest.mark.parametrize("text", ["Launch video ideas", "AI and ML", "   one   two\nthree   "])
def test_short_notes_skip_topic_classifier(tmp_path, text):
    idx = open_index(tmp_path)
    calls = []
    try:
        built = notes.build_note(text=text)
        vid = notes.persist_note(idx, built, data_root=tmp_path, topic_classifier=lambda meta: calls.append(meta) or "AI and ML")
        assert idx.get_yoink(vid)["topic"] in (None, "", "Uncategorized")
        assert calls == []
    finally:
        idx.close()


def test_library_empty_state_tracks_in_progress_rows():
    result = run_js('''(() => {
      state.libraryState = "empty_corpus"; state.library = [];
      renderLibrary();
      const empty = els.libraryEmpty.classList.contains("hidden");
      state.libraryRuns = [{id: "first", state: "running", url: "https://show.example/one", label: "Podcast", platform: "podcast"}];
      renderLibraryCaptures();
      const running = els.libraryEmpty.classList.contains("hidden");
      renderLibrary();
      const reload = els.libraryEmpty.classList.contains("hidden");
      state.libraryRuns = []; renderLibraryCaptures();
      return {empty, running, reload, cleared: els.libraryEmpty.classList.contains("hidden")};
    })()''')
    assert result == {"empty": False, "running": True, "reload": True, "cleared": False}


@pytest.mark.parametrize("job_state", ["running", "failed"])
def test_podcast_background_row_uses_kind_and_artwork(job_state):
    result = run_js('''(() => {
      state.jobs = [{id: "episode", kind: "podcast_transcribe", state: %s,
        title: "First flight", source_url: "https://show.example/first",
        artwork_url: "https://cdn.example/show.jpg", updated_at: new Date().toISOString()}];
      return libraryCaptureItems().map(libraryCaptureRowHtml).join("");
    })()''' % json.dumps(job_state))
    assert 'src="https://cdn.example/show.jpg"' in result
    assert "Podcast" in result and "Web" not in result
    assert '>capture<' not in result


def test_item_toolbar_requires_connected_agent_and_updates_after_setup():
    result = run_js('''(() => {
      state.selectedYoink = {video_id: "one"}; state.agents = [];
      renderYoinkWriteFrom();
      const fresh = {disabled: els.yoinkWriteFrom.disabled, hint: els.yoinkWriteHint.textContent,
        hidden: els.yoinkWriteHint.classList.contains("hidden")};
      state.agents = [{connected: true}]; renderAgentSetup();
      return {fresh, connected: els.yoinkWriteFrom.disabled, hintHidden: els.yoinkWriteHint.classList.contains("hidden")};
    })()''')
    assert result == {"fresh": {"disabled": True, "hint": "Connect Claude first", "hidden": False},
                      "connected": False, "hintHidden": True}


def test_sources_show_poll_progress_then_episode_and_keep_refreshing():
    result = run_js('''(async () => {
      state.activeTab = "sources";
      const timers = []; setTimeout = (fn, delay) => { timers.push({fn, delay}); return timers.length; };
      const source = {source_id: "one", kind: "podcast_rss", consent_state: "on", enrollment: {pending: true},
        detection: {poll_in_progress: true}};
      callRegistryTool = async () => ({sources: [source]});
      await loadStandingSubscriptions();
      const waiting = els.standingSubscriptionList.innerHTML;
      const count = timers.length;
      source.enrollment = {pending: false}; source.detection = {last_poll_success_ms: Date.now()};
      source.latest_episode = {title: "First <flight>", canonical_url: "https://show.example/first", video_id: "saved-one", capture_state: "committed"};
      await timers[0].fn();
      return {waiting, count, arrived: els.standingSubscriptionList.innerHTML};
    })()''')
    assert "Looking for episodes" in result["waiting"]
    assert result["count"] == 1
    assert "First &lt;flight&gt;" in result["arrived"]
    assert '#item/saved-one' in result["arrived"]


def test_sources_paste_refreshes_subscriptions_after_adding_podcast():
    result = run_js('''(async () => {
      let refreshed = 0;
      loadStandingSubscriptions = async () => { refreshed += 1; };
      refreshActivity = () => {};
      authFetch = async () => ({ok: true, feed: {id: 1}});
      Object.assign(universalState, {source: "podcast_feed", endpoint: "/podcasts/feeds",
        payloadKey: "feed_url", canonical: "https://show.example/feed.xml"});
      await runUniversalCapture();
      return refreshed;
    })()''')
    assert result == 1


def test_library_paste_opens_sources_for_the_first_podcast_episode():
    result = run_js('''(() => {
      const destinations = [];
      navigateTo = hash => destinations.push(hash);
      refreshActivity = () => {};
      finishLibraryRun({id: "first", source: "podcast_feed"}, {ok: true, feed: {id: 1}});
      return destinations;
    })()''')
    assert result == ["#sources"]


def test_extension_suggests_nasa_without_hardcoded_capture():
    script = (ROOT / "extension/setup.js").read_text(encoding="utf-8")
    markup = (ROOT / "extension/setup.html").read_text(encoding="utf-8")
    assert "all 99 tools" in script
    assert "91" not in script + markup
    assert "NASA" in markup and "public-domain" in markup
    assert "8rABwKRsec4" not in script + markup
    assert "Karpathy" not in script + markup
    assert 'id="first-capture-url"' in markup
