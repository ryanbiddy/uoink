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


def test_subscribe_waits_for_consent_before_fetching(feed_env):
    idx, service, calls, handler = feed_env
    code, result = handler._handle_sources_tool(
        "register_source", {"kind": "podcast_rss", "url": FEED_URL})
    assert code == 200
    source = result["source"]
    assert source["display_name"] == "show.example"
    assert source["consent_state"] == "off"
    assert source["latest_episode"] is None
    assert calls == []
    assert idx._conn.execute("SELECT COUNT(*) FROM source_items").fetchone()[0] == 0
    assert idx._conn.execute("SELECT COUNT(*) FROM source_capture_starts").fetchone()[0] == 0
    handler._handle_sources_tool("register_source", {"kind": "podcast_rss", "url": FEED_URL})
    assert calls == [], "duplicate registration must not fetch either"


def test_registry_tool_subscribe_does_not_fetch(feed_env):
    _, _, calls, _ = feed_env
    result = mcp_tools.register_source({"kind": "podcast_rss", "url": FEED_URL})
    assert result["source"]["display_name"] == "show.example"
    assert result["source"]["latest_episode"] is None
    assert calls == []


def test_subscribe_preserves_custom_name_and_never_tries_an_offline_feed(feed_env):
    _, service, calls, handler = feed_env
    _, result = handler._handle_sources_tool("register_source", {
        "kind": "podcast_rss", "url": FEED_URL, "display_name": "My space feed"})
    assert result["source"]["display_name"] == "My space feed"

    def fail(*_):
        calls.append("offline")
        raise OSError("offline")

    service.adapters[ss.ADAPTERS["podcast_rss"]] = ss.PodcastRssAdapter(fail)
    code, result = handler._handle_sources_tool("register_source", {
        "kind": "podcast_rss", "url": "https://offline.example/feed.xml"})
    assert code == 200 and result["created"] is True
    source = result["source"]
    assert source["display_name"] == "offline.example"
    assert source["detection"]["consecutive_failures"] == 0
    assert source["latest_episode"] is None
    assert calls == []


def test_legacy_subscribe_does_not_fetch_feed_title(feed_env):
    _, _, calls, handler = feed_env
    code, result = handler._handle_podcasts_feed_add({"feed_url": FEED_URL})
    assert code == 200 and result["feed"]["title"] == "show.example"
    assert calls == []


def test_podcast_poll_gates_wait_for_first_consent(feed_env):
    idx, service, calls, _ = feed_env
    source = service.register_source(REGISTRY, {"kind": "podcast_rss", "url": FEED_URL})["source"]
    sid = source["source_id"]
    assert service.due_poll_ids() == []
    assert service.claim_poll(sid) is None
    assert service.detection_pass() == []
    refreshed = service.refresh_source(REGISTRY, {"source_id": sid})
    assert refreshed["outcome"] == "consent_required"
    assert calls == []
    assert idx._conn.execute("SELECT COUNT(*) FROM source_items").fetchone()[0] == 0


@pytest.mark.parametrize("name, expected_name", [
    (None, "Space stories"), ("My space feed", "My space feed"),
    ("Untitled podcast", "Space stories"), ("  UNTITLED PODCAST  ", "Space stories"),
])
def test_consented_poll_persists_feed_title_and_preserves_custom_name(feed_env, name, expected_name):
    idx, service, calls, handler = feed_env
    args = {"kind": "podcast_rss", "url": FEED_URL}
    if name:
        args["display_name"] = name
    _, registered = handler._handle_sources_tool("register_source", args)
    sid = registered["source"]["source_id"]
    turn_on(service, sid)
    assert service.detection_pass()[0]["enrollment"]["enrolled"] == 1
    source = service.source_status(REGISTRY, {"source_id": sid})["source"]
    assert source["display_name"] == expected_name
    assert source["latest_episode"]["title"] == "First flight"
    assert podcasts.get_feed(idx, source["legacy"]["feed_id"])["title"] == "Space stories"
    episode = podcasts.list_episodes(idx)[0]
    assert podcasts.get_episode_with_feed(idx, episode["id"])["podcast_title"] == "Space stories"
    metadata = json.loads(idx._conn.execute(
        "SELECT metadata_json FROM source_items WHERE source_id=?", (sid,)).fetchone()[0])
    assert metadata["feed_title"] == "Space stories" and metadata["artwork_url"] == ART
    assert podcasts.episode_artwork_url(idx, episode["id"]) == ART
    assert calls == [FEED_URL]


def test_first_consent_ignores_old_preview_validators_and_enrolls_observed_items(feed_env):
    idx, service, _, _ = feed_env
    sid = service.register_source(REGISTRY, {"kind": "podcast_rss", "url": FEED_URL})["source"]["source_id"]
    validators = {"ETag": '"preview"', "Last-Modified": "Thu, 05 Nov 2026 00:00:00 GMT"}
    # Model data left by the old preview, without making an unconsented request.
    with idx.write_transaction() as conn:
        source = dict(conn.execute("SELECT * FROM source_subscriptions WHERE source_id=?", (sid,)).fetchone())
        service._persist_observations(conn, source, ss.PodcastRssAdapter().parse(FEED, {}).observations,
                                      service._now(), 1, None)
        conn.execute("UPDATE source_detection_cursors SET etag=?, last_modified=?, next_poll_at_ms=? "
                     "WHERE source_id=?", (validators["ETag"], validators["Last-Modified"], service._now() + 3600000, sid))
    headers_seen = []

    def fetch(url, headers):
        headers_seen.append(headers)
        conditional = "If-None-Match" in headers or "If-Modified-Since" in headers
        return ss.FetchResponse(304 if conditional else 200, validators, b"" if conditional else FEED)

    service.adapters[ss.ADAPTERS["podcast_rss"]] = ss.PodcastRssAdapter(fetch)
    turn_on(service, sid)
    polled = service.detection_pass()[0]
    assert polled["outcome"] == "snapshot" and polled["enrollment"]["enrolled"] == 1
    assert len(headers_seen) == 1
    assert not {"If-None-Match", "If-Modified-Since"}.intersection(headers_seen[0])
    item = idx._conn.execute("SELECT * FROM source_items WHERE source_id=?", (sid,)).fetchone()
    assert item["first_seen_consent_epoch"] is None
    assert item["state"] == "eligible" and item["enrolled_epoch"] == 1


def test_first_consent_does_not_wait_an_hour_after_subscribe(feed_env):
    _, service, _, handler = feed_env
    _, result = handler._handle_sources_tool("register_source", {"kind": "podcast_rss", "url": FEED_URL})
    source_id = result["source"]["source_id"]
    turn_on(service, source_id)
    polled = service.detection_pass()
    assert len(polled) == 1
    assert polled[0]["enrollment"]["enrolled"] == 1


def test_first_consent_preserves_feed_failure_backoff(feed_env):
    idx, service, calls, _ = feed_env
    source = service.register_source(REGISTRY, {"kind": "podcast_rss", "url": FEED_URL})["source"]
    retry_at = service._now() + 7200000
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_detection_cursors SET error_count=1, next_poll_at_ms=? WHERE source_id=?",
                     (retry_at, source["source_id"]))
    turn_on(service, source["source_id"])
    assert service.detection_pass() == []
    updated = service.source_status(REGISTRY, {"source_id": source["source_id"]})["source"]
    assert updated["detection"]["next_poll_at_ms"] == retry_at
    assert calls == []


@pytest.mark.parametrize("body", [
    FEED,
    b'<rss><channel><title>Space stories</title><image><url>https://cdn.example/show.jpg</url></image>'
    b'<item><guid>one</guid><title>First flight</title></item></channel></rss>',
    b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Space stories</title>'
    b'<logo>https://cdn.example/show.jpg</logo><entry><id>one</id><title>First flight</title></entry></feed>',
])
@pytest.mark.parametrize("title, expected", [
    ("Space stories", "Space stories"), (" \tSpace\n" + "x" * 205 + "\t ", "Space " + "x" * 194),
])
def test_podcast_parser_retains_safe_feed_title_and_artwork(body, title, expected):
    parsed = ss.PodcastRssAdapter().parse(body.replace(b"Space stories", title.encode()), {})
    assert parsed.feed_title == expected
    assert parsed.observations[0].metadata["feed_title"] == expected
    assert parsed.observations[0].metadata["artwork_url"] == ART


def test_poll_commit_sanitizes_feed_title_without_dropping_artwork(feed_env):
    idx, service, calls, _ = feed_env
    source = service.register_source(REGISTRY, {
        "kind": "podcast_rss", "url": FEED_URL, "display_name": "Untitled podcast"})["source"]
    sid = source["source_id"]
    turn_on(service, sid)
    claim = service.claim_poll(sid)
    parsed = ss.PodcastRssAdapter().parse(FEED, {})
    parsed.feed_title = " \tSpace\n" + "x" * 205 + "\t "
    parsed.observations[0].metadata.pop("feed_title")
    assert service.commit_poll(sid, claim["owner_token"], parsed)["ok"]
    expected = "Space " + "x" * 194
    source = service.source_status(REGISTRY, {"source_id": sid})["source"]
    assert source["display_name"] == expected
    assert podcasts.get_feed(idx, source["legacy"]["feed_id"])["title"] == expected
    metadata = json.loads(idx._conn.execute(
        "SELECT metadata_json FROM source_items WHERE source_id=?", (sid,)).fetchone()[0])
    assert metadata["feed_title"] == expected and metadata["artwork_url"] == ART
    assert calls == []


def test_podcast_artwork_reaches_job_and_published_library_row(feed_env, tmp_path, monkeypatch):
    idx, service, _, handler = feed_env
    _, registered = handler._handle_sources_tool("register_source", {"kind": "podcast_rss", "url": FEED_URL})
    turn_on(service, registered["source"]["source_id"])
    service.detection_pass()
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


@pytest.mark.parametrize("run_state", ["running", "failed"])
def test_library_no_matches_remains_visible_beside_capture_rows(run_state):
    result = run_js('''(() => {
      state.libraryState = "no_matches"; state.library = [];
      state.libraryRuns = [{id: "one", state: %s, url: "https://show.example/one", label: "Podcast"}];
      renderLibrary();
      const rendered = els.libraryEmpty.classList.contains("hidden");
      renderLibraryCaptures();
      return {rendered, refreshed: els.libraryEmpty.classList.contains("hidden"), copy: els.libraryEmpty.innerHTML};
    })()''' % json.dumps(run_state))
    assert result["rendered"] is False and result["refreshed"] is False
    assert "No Library matches" in result["copy"]


def test_library_capture_dismissal_uses_empty_fallback_when_state_is_unset():
    result = run_js('''(() => {
      state.libraryState = null; state.library = [];
      state.libraryRuns = [{id: "one", state: "failed", url: "https://show.example/one"}];
      renderLibrary();
      state.libraryRuns = []; renderLibraryCaptures();
      return {hidden: els.libraryEmpty.classList.contains("hidden"), copy: els.libraryEmpty.innerHTML};
    })()''')
    assert result["hidden"] is False and "No saved uoinks yet" in result["copy"]


@pytest.mark.parametrize("artwork", ["https://cdn.example/show.jpg", "http://cdn.example/show.jpg", ""])
def test_saved_podcast_never_loads_remote_artwork(artwork):
    result = run_js('''(async () => {
      const img = getEl("thumb"); img.classList.add("hidden");
      document.querySelector = () => img;
      globalThis.CSS = {escape: value => value};
      const fetched = []; fetch = async url => { fetched.push(url); throw Error("offline"); };
      const row = {video_id: "episode", platform: "podcast", source_type: "episode", title: "First flight",
        artwork_url: %s};
      await loadThumbnail(row);
      return {src: img.src || "", hidden: img.classList.contains("hidden"), fetched, html: cardHtml(row)};
    })()''' % json.dumps(artwork))
    assert result["src"] == "" and result["hidden"] is True and result["fetched"] == []
    assert '<span class="source-type-chip">Podcast</span>' in result["html"]
    assert "cdn.example" not in result["html"]


@pytest.mark.parametrize("job_state", ["running", "failed"])
def test_podcast_background_row_uses_local_placeholder(job_state):
    result = run_js('''(() => {
      state.jobs = [{id: "episode", kind: "podcast_transcribe", state: %s,
        title: "First flight", source_url: "https://show.example/first",
        artwork_url: "https://cdn.example/show.jpg", updated_at: new Date().toISOString()}];
      return libraryCaptureItems().map(libraryCaptureRowHtml).join("");
    })()''' % json.dumps(job_state))
    assert "<img" not in result and "cdn.example" not in result
    assert "Podcast" in result and "Web" not in result
    assert '>capture<' not in result


@pytest.mark.parametrize("job_state", ["running", "failed"])
def test_activity_labels_podcast_jobs_without_remote_artwork(job_state):
    result = run_js('''(() => {
      const row = {id: "episode", kind: "podcast_transcribe", state: %s, title: "First flight",
        source_url: "https://show.example/first", artwork_url: "https://cdn.example/show.jpg"};
      return activityRowHtml({key: "job:episode", row, job: row});
    })()''' % json.dumps(job_state))
    assert "Podcast" in result and "Web" not in result
    assert "<img" not in result and "cdn.example" not in result


def test_item_toolbar_requires_connected_agent_and_updates_after_setup():
    result = run_js('''(() => {
      selectedWritingMode = () => "tweet";
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


@pytest.mark.parametrize("extra", [
    {"consent_state": "off", "consent_epoch": 0},
    {"detection": {"consecutive_failures": 1, "error": {"code": "offline"}, "next_poll_at_ms": 9999999999999}},
    {"capture_status": "allowance_exhausted", "item_counts": {"eligible": 4}, "detection": {"last_poll_success_ms": 1}},
    {"capture_outcome": "settled_failed", "capture_status": "ready", "item_counts": {"eligible": 1, "started": 1}, "detection": {"last_poll_success_ms": 1}},
    {"capture_outcome": "uncertain", "in_flight": [{"item_id": "one", "state": "uncertain"}], "detection": {"last_poll_success_ms": 1}},
])
def test_sources_do_not_fast_poll_without_progress(extra):
    result = run_js('''(async () => {
      state.activeTab = "sources";
      const timers = []; setTimeout = (fn, delay) => { timers.push(delay); return timers.length; };
      const source = Object.assign({source_id: "one", kind: "podcast_rss", consent_state: "on"}, %s);
      callRegistryTool = async () => ({sources: [source]});
      await loadStandingSubscriptions();
      return {timers, html: els.standingSubscriptionList.innerHTML};
    })()''' % json.dumps(extra))
    assert result["timers"] == []
    if extra.get("consent_state") == "off":
        assert "Looking for episodes" not in result["html"]
        assert "Turn on automatic capture to check for episodes." in result["html"]


def test_sources_fast_refresh_stops_even_if_progress_is_stuck():
    result = run_js('''(async () => {
      state.activeTab = "sources";
      const timers = new Map(); let next = 0; let calls = 0;
      setTimeout = fn => { timers.set(++next, fn); return next; };
      clearTimeout = id => timers.delete(id);
      callRegistryTool = async () => { calls++; return {sources: [{source_id: "one", kind: "podcast_rss",
        consent_state: "on", detection: {poll_in_progress: true}}]}; };
      await loadStandingSubscriptions();
      for (let n = 0; timers.size && n < 100; n++) {
        const [id, fn] = timers.entries().next().value; timers.delete(id); await fn();
      }
      const stopped = timers.size === 0;
      const automaticCalls = calls;
      await loadStandingSubscriptions();
      return {stopped, automaticCalls, manualRestart: timers.size};
    })()''')
    assert result["stopped"] is True and 1 < result["automaticCalls"] <= 21
    assert result["manualRestart"] == 1


def test_overlapping_source_refreshes_keep_only_the_latest_response_and_timer():
    result = run_js('''(async () => {
      state.activeTab = "sources";
      const timers = new Map(); let next = 0; const replies = [];
      setTimeout = fn => { timers.set(++next, fn); return next; };
      clearTimeout = id => timers.delete(id);
      callRegistryTool = () => new Promise(resolve => replies.push(resolve));
      const first = loadStandingSubscriptions(); const second = loadStandingSubscriptions();
      const source = id => ({source_id: id, kind: "podcast_rss", consent_state: "on", detection: {poll_in_progress: true}});
      replies[1]({sources: [source("new")]}); await second;
      replies[0]({sources: [source("old")]}); await first;
      return {source: state.standingSources[0].source_id, timers: timers.size};
    })()''')
    assert result == {"source": "new", "timers": 1}


@pytest.mark.parametrize("in_flight", [False, True])
def test_known_episode_does_not_show_discovery_progress_or_duplicate(in_flight):
    result = run_js('''(() => {
      state.standingSources = [{source_id: "one", kind: "podcast_rss", consent_state: "on",
        enrollment: {pending: true}, detection: {poll_in_progress: true},
        latest_episode: {item_id: "episode-1", title: "First flight", capture_state: "started"},
        in_flight: %s}];
      renderStandingSubscriptions(); return els.standingSubscriptionList.innerHTML;
    })()''' % json.dumps([{"item_id": "episode-1", "title": "First flight", "state": "started"}] if in_flight else []))
    assert "Looking for episodes" not in result
    assert result.count("First flight") == 1
    assert ("Latest episode" in result) is not in_flight


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
