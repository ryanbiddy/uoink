"""Launch footer, podcast names, Generate gating, and Insights regressions."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import corpus_contract
import corpus_provider
import podcasts
import server
import source_subscriptions as ss
from tests.source_subscriptions_fixtures import (
    Clock, FakeBackend, FakeFetch, FEED_URL, MINUTE_MS, http, open_index, register,
)
from tests.test_dashboard_runthrough_fixes import DASHBOARD, run_js
from tests.test_podcast_corpus_bridge import _seed_episode


@pytest.mark.parametrize("platform, label", [("MacIntel", "Mac"), ("Win32", "PC")])
def test_running_footer_keeps_diagnostics_in_hover(platform, label):
    result = run_js(f"""
      navigator.platform = {json.dumps(platform)};
      renderHelperStatus(true, {{available:true, status:'running', reason:'Helper is ready.',
        last_exit_code:null, restart_count:0, last_start_at:'2026-11-05T12:00:00Z'}});
      ({{text:els.helperStatusText.textContent, hidden:els.helperOfflineFix.classList.contains('hidden'),
        details:els.runningPill.title}});
    """)
    assert result["text"] == f"Running on this {label}"
    assert result["hidden"]
    assert "2026-11-05T12:00:00Z" in result["details"]


@pytest.mark.parametrize("location", ["system", "user"])
def test_mac_detects_claude_before_first_launch(tmp_path, monkeypatch, location):
    monkeypatch.setattr(server, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    marker = Path("/Applications/Claude.app") if location == "system" else tmp_path / "Applications/Claude.app"
    monkeypatch.setattr(Path, "exists", lambda path: path == marker)
    client = next(c for c in server._detect_ai_clients() if c["name"] == "claude-desktop")
    assert client["installed"]
    assert not client["connected"] and not client["config_exists"]


@pytest.mark.parametrize("kind", ["rss", "atom"])
def test_subscription_feed_title_reaches_new_episodes(tmp_path, kind):
    idx = open_index(tmp_path)
    body = (b'<rss><channel><title>Channel title</title><item><guid>one</guid>'
            b'<title>Episode title</title></item></channel></rss>' if kind == "rss" else
            b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Channel title</title>'
            b'<entry><id>one</id><title>Episode title</title></entry></feed>')
    clock = Clock()
    fetch = FakeFetch([http(200, body), http(200, body.replace(b"Channel title", b"Updated show"))])
    service = ss.SourceSubscriptionService(index=idx, clock=clock, adapters=ss.default_adapters(fetch),
                                           backend=FakeBackend(), instance_id="title-test")
    try:
        register(service, "podcast_rss", FEED_URL)
        assert service.detection_pass()[0]["ok"]
        episode = podcasts.list_episodes(idx)[0]
        assert podcasts.get_episode_with_feed(idx, episode["id"])["podcast_title"] == "Channel title"
        transcript = tmp_path / "transcript.json"
        transcript.write_text(json.dumps({"segments": [{"start": 0, "end": 2, "text": "Example."}]}), encoding="utf-8")
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_episodes SET transcript_local_path=? WHERE id=?",
                         (str(transcript), episode["id"]))
        published = podcasts.episode_to_corpus(idx, episode["id"], data_root=tmp_path)
        assert idx.get_yoink(published["video_id"])["channel"] == "Channel title"
        assert Path(published["corpus_path"]).parent.parent.name == "channel-title"
        clock.advance(61 * MINUTE_MS)
        assert service.detection_pass()[0]["ok"]
        assert podcasts.get_episode_with_feed(idx, episode["id"])["podcast_title"] == "Updated show"
    finally:
        idx.close()


def test_old_feed_without_title_is_refetched_then_uses_conditional_requests(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    fetch = FakeFetch([http(200, b'<rss><channel><title>Recovered show</title></channel></rss>',
                            {"ETag": '"unchanged"'}), http(304, b"")])
    service = ss.SourceSubscriptionService(index=idx, clock=clock, adapters=ss.default_adapters(fetch),
                                           backend=FakeBackend(), instance_id="title-repair")
    try:
        sid = register(service, "podcast_rss", FEED_URL)["source_id"]
        with idx.write_transaction() as conn:
            conn.execute("UPDATE source_detection_cursors SET etag=?, last_modified=? WHERE source_id=?",
                         ('"unchanged"', "Wed, 04 Nov 2026 12:00:00 GMT", sid))
        assert service.detection_pass()[0]["ok"]
        assert "If-None-Match" not in fetch.requests[0]["headers"]
        assert "If-Modified-Since" not in fetch.requests[0]["headers"]
        assert podcasts.list_feeds(idx)[0]["title"] == "Recovered show"
        clock.advance(61 * MINUTE_MS)
        assert service.detection_pass()[0]["outcome"] == "not_modified"
        assert fetch.requests[1]["headers"]["If-None-Match"] == '"unchanged"'
    finally:
        idx.close()


def test_old_podcast_titles_repaired_on_read_without_moving_files(tmp_path, monkeypatch):
    idx, episode_id, _, _ = _seed_episode(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    try:
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_feeds SET title=NULL")
        published = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        saved = idx.get_yoink(published["video_id"])
        paths = [Path(saved[key]) for key in ("corpus_path", "sidecar_path")]
        before = [path.read_bytes() for path in paths]
        assert paths[0].parent.parent.name == "untitled-podcast"
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_feeds SET title='The Grounded Show'")
        library = server._enrich_yoink_rows(idx, [saved])[0]
        assert library["channel"] == library["podcast_title"] == "The Grounded Show"
        assert library["title"] == "Episode Forty Two"
        provider = corpus_provider.UoinkCorpusProvider(idx, tmp_path)
        assert provider.search(corpus_contract.SearchRequest())["items"][0]["author"] == "The Grounded Show"
        assert provider.get(saved["video_id"])["item"]["author"] == "The Grounded Show"
        probe = SimpleNamespace(_send_json=lambda status, data: (status, data))
        status, details = server.Handler._handle_yoink_details(probe, f'/yoinks/{saved["video_id"]}/details')
        assert status == 200
        assert details["details"]["podcast_title"] == "The Grounded Show"
        assert [path.read_bytes() for path in paths] == before
        assert idx.get_yoink(saved["video_id"])["corpus_path"] == saved["corpus_path"]
        assert not (paths[0].parent.parent.parent / "the-grounded-show").exists()
        named_host = dict(saved, channel="Named host", author="Named host")
        assert podcasts.repair_corpus_titles(idx, [named_host])[0]["author"] == "Named host"
    finally:
        idx.close()


def test_generate_requires_connection_and_updates_after_detection():
    result = run_js("""
      selectedWritingMode = () => 'tweet';
      state.writingSelectedSourceRow = {video_id:'one'}; els.writingSource.value = 'one';
      state.agentDetectionLoaded = true;
      syncWritingGenerateState();
      const disconnected = {disabled:getEl('generateWriting').disabled,
        hint:getEl('writingAgentHint').textContent};
      state.agents = [{name:'claude-desktop', label:'Claude Desktop', installed:true, connected:true}];
      renderAgentSetup();
      ({disconnected, connected:getEl('generateWriting').disabled,
        hintHidden:getEl('writingAgentHint').classList.contains('hidden')});
    """)
    assert result["disconnected"]["disabled"]
    assert result["disconnected"]["hint"] == "Connect a writing agent to generate."
    assert not result["connected"] and result["hintHidden"]


def test_research_and_key_generation_keep_their_existing_paths():
    result = run_js("""
      selectedWritingMode = () => 'tweet';
      state.writingSelectedSourceRow = {video_id:'one'}; els.writingSource.value = 'one';
      state.settings = {anthropic_key_set:true};
      syncWritingGenerateState(); const keyDisabled = getEl('generateWriting').disabled;
      selectedWritingMode = () => 'script'; syncWritingGenerateState();
      const scriptDisabled = getEl('generateWriting').disabled;
      state.settings = {}; els.writingSource.value = ''; selectedWritingMode = () => 'research';
      syncWritingGenerateState();
      ({keyDisabled, scriptDisabled, researchDisabled:getEl('generateWriting').disabled});
    """)
    assert not result["keyDisabled"] and result["scriptDisabled"]
    assert not result["researchDisabled"]


def test_script_picker_and_grounding_do_not_claim_a_missing_agent():
    result = run_js("""
      (async () => {
        selectedWritingMode = () => 'script'; renderWritingScreenshots();
        state.writingSelectedSourceRow = {video_id:'one'};
        generateAssemblyBody = async () => ({});
        requestCorpusAssembly = async () => ({assembled:[{}]});
        await generateScriptGrounding();
        return {label:getEl('pickBestScreenshots').textContent,
          hidden:els.generateResearchPanel.classList.contains('hidden'),
          content:els.generateResearchPanel.innerHTML};
      })();
    """)
    assert result["label"] == "Pick best for script"
    assert result["hidden"] or "connected writing agent" not in result["content"]


def test_script_examples_hide_if_the_agent_disconnects():
    result = run_js("""
      (async () => {
        selectedWritingMode = () => 'script';
        state.writingSelectedSourceRow = {video_id:'one'};
        state.agents = [{label:'Example agent',connected:true}];
        generateAssemblyBody = async () => ({});
        requestCorpusAssembly = async () => ({assembled:[{}]});
        await generateScriptGrounding();
        const shown = !els.generateResearchPanel.classList.contains('hidden');
        state.agents = []; renderAgentSetup();
        return {shown, hidden:els.generateResearchPanel.classList.contains('hidden')};
      })();
    """)
    assert result == {"shown": True, "hidden": True}


def test_for_you_ignores_default_topics_on_server_and_fallback(monkeypatch):
    rows = [{"video_id": str(i), "topic": topic, "yoinked_at": f"2026-01-0{i + 1}"}
            for i, topic in enumerate([None, "", "Uncategorized", " uncategorized ", "Space", "Space"])]
    idx = SimpleNamespace(search_yoinks_for_memory=lambda **_: {"results": rows}, top_engaged=lambda **_: [])
    monkeypatch.setattr(server, "_enrich_yoink_rows", lambda _, items: items)
    monkeypatch.setattr(server, "_safe_imported_for_you", lambda _: [])
    assert [c["topic"] for c in server._resurface_payload(idx)["connections"]] == ["Space"]
    result = run_js(f"buildConnections({json.dumps(rows)}).map(c => c.topic);")
    assert result == ["Space"]


def test_insights_date_controls_and_plain_labels():
    from html.parser import HTMLParser

    class Controls(HTMLParser):
        def __init__(self):
            super().__init__()
            self.nodes = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get("id"):
                self.nodes[attrs["id"]] = (tag, attrs)

    parser = Controls()
    parser.feed(DASHBOARD)
    for name in ("activityStartInput", "activityEndInput"):
        assert parser.nodes[name][1]["type"] == "date"
        assert f'for="{name}"' in DASHBOARD
    result = run_js("""
      libraryActivityState.packet = {as_of:'2026-11-05T12:00:00Z',
        interval:{start:'2026-11-01T00:00:00Z',end:'2026-11-06T00:00:00Z'},
        items:{total:{value:3},coverage_ref:'cov_capture',deleted_items_excluded:{value:1}},
        coverage:{cov_capture:{coverage_status:'retained_records'}},
        shelf_activity:{churn:{value:null,percent:null,reason:'baseline_unavailable'}},
        warnings:['capture_time_unavailable']};
      renderLibraryActivityUI();
      ['libraryActivityAsOf','activityUtcInterval','activityCoverageStatus','activityExclusions',
        'activityWarnings','activityChurnSub'].map(id => getEl(id).textContent + getEl(id).innerHTML.replace(/<[^>]*>/g, '')).join(' ');
    """)
    assert "2026-11-05T" not in result and "retained_records" not in result
    assert "tombstones" not in result and "baseline_unavailable" not in result
    assert "capture_time_unavailable" not in result


def test_insights_custom_dates_include_the_end_day_and_validate_order():
    result = run_js("""
      const handlers = {};
      getEl('activityApplyCustomBtn').addEventListener = (event, fn) => {handlers[event] = fn;};
      document.addEventListener = () => {}; window.addEventListener = () => {};
      let loads = 0; loadLibraryActivity = () => {loads++;}; wireLibraryActivityEvents();
      getEl('activityStartInput').value = '2026-11-05'; getEl('activityEndInput').value = '2026-11-05';
      handlers.click();
      const expected = {start:new Date(2026,10,5).toISOString(), end:new Date(2026,10,6).toISOString()};
      const interval = libraryActivityState.interval;
      getEl('activityEndInput').value = '2026-11-04'; handlers.click();
      ({interval, expected, loads, error:getEl('activityCustomError').textContent});
    """)
    assert result["interval"] == result["expected"]
    assert result["loads"] == 1 and "end date" in result["error"].lower()
