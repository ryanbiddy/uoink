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
    Clock, FakeBackend, FakeFetch, FEED_URL, MINUTE_MS, http, open_index, publish, register,
    turn_on,
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
        sid = register(service, "podcast_rss", FEED_URL)["source_id"]
        turn_on(service, sid)
        assert service.detection_pass()[0]["ok"]
        episode = podcasts.list_episodes(idx)[0]
        assert podcasts.get_episode_with_feed(idx, episode["id"])["podcast_title"] == "Channel title"
        transcript = tmp_path / "transcript.json"
        transcript.write_text(json.dumps({"segments": [{"start": 0, "end": 2, "text": "Example."}]}), encoding="utf-8")
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_episodes SET transcript_local_path=? WHERE id=?",
                         (str(transcript), episode["id"]))
        published = podcasts.episode_to_corpus(idx, episode["id"], data_root=tmp_path)
        saved = idx.get_yoink(published["video_id"])
        assert saved["channel"] == "Channel title"
        assert Path(published["corpus_path"]).parent.parent.name == "channel-title"
        assert json.loads(Path(published["sidecar_path"]).read_text(encoding="utf-8"))["podcast_title"] == "Channel title"
        assert "**Podcast:** Channel title" in Path(published["corpus_path"]).read_text(encoding="utf-8")
        before = _saved_podcast_state(idx, saved)
        clock.advance(61 * MINUTE_MS)
        assert service.detection_pass()[0]["ok"]
        assert podcasts.get_episode_with_feed(idx, episode["id"])["podcast_title"] == "Updated show"
        assert _saved_podcast_state(idx, saved) == before
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
        turn_on(service, sid)
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


def _saved_podcast_state(idx, saved):
    return {
        "files": {key: Path(saved[key]).read_bytes() for key in ("sidecar_path", "corpus_path")},
        "yoinks": [tuple(r) for r in idx._conn.execute("SELECT * FROM yoinks")],
        "fts": [tuple(r) for r in idx._conn.execute("SELECT * FROM yoinks_fts")],
    }


@pytest.mark.parametrize("placeholder", [None, "Untitled podcast", "  UNTITLED PODCAST  "])
@pytest.mark.parametrize("read_only", [False, True])
def test_old_podcast_titles_are_display_only_after_boot_and_reads(tmp_path, monkeypatch, placeholder, read_only):
    import library_cards
    import library_media
    import library_resources
    import uoink_cli
    import uoink_mcp_tools
    from tests.phase4_fixtures import parse_fenced_document, seed_shelf

    idx, episode_id, _, _ = _seed_episode(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_get_existing_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(uoink_mcp_tools, "_b", lambda: server)
    fetch = FakeFetch([AssertionError("title reads must stay local")])
    monkeypatch.setattr(ss, "default_http_fetch", fetch)
    try:
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_feeds SET title=?", (placeholder,))
        published = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        saved = idx.get_yoink(published["video_id"])
        seed_shelf(idx, member_video_ids=[saved["video_id"]])
        before = _saved_podcast_state(idx, saved)
        snapshot = library_media._read_snapshot(idx._conn, saved["video_id"]).block
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_feeds SET title='The Grounded Show'")
        server._repair_podcast_titles_at_boot()
        assert _saved_podcast_state(idx, saved) == before
        if read_only:
            idx.close()
            idx = type(idx).open_existing(tmp_path / "index.db")
            monkeypatch.setattr(idx, "initialize_for_write", lambda: pytest.fail("display must stay read-only"))
        changes = idx._conn.total_changes
        library = server._enrich_yoink_rows(idx, [dict(saved)])[0]
        assert library["channel"] == library["podcast_title"] == "The Grounded Show"
        assert library["title"] == "Episode Forty Two"
        assert saved == idx.get_yoink(saved["video_id"]), "display must not mutate its input"
        provider = corpus_provider.UoinkCorpusProvider(idx, tmp_path)
        assert provider.search(corpus_contract.SearchRequest(q="durable"))["items"][0]["author"] == "The Grounded Show"
        assert provider.get(saved["video_id"])["item"]["author"] == "The Grounded Show"
        probe = SimpleNamespace(_send_json=lambda status, data: (status, data))
        status, details = server.Handler._handle_yoink_details(probe, f'/yoinks/{saved["video_id"]}/details')
        assert status == 200
        assert details["details"]["podcast_title"] == "The Grounded Show"
        assert uoink_cli.text_library_row({"slug": saved["slug"]}, idx)["channel"] == "The Grounded Show"
        clips = uoink_mcp_tools.search_clips({"query": "durable", "mode": "keyword"})
        assert clips["results"][0]["channel"] == "The Grounded Show"
        activity = run_js("state.library = " + json.dumps([library]) + ";" + """
          state.jobs = [{id:'old-job',kind:'podcast_transcribe',state:'completed',
            result:{corpus:{video_id:state.library[0].video_id}},
            source_url:state.library[0].source_url,channel:'Untitled podcast'}];
          activityEntries({}).map(activityRowHtml).join('');
        """)
        assert "The Grounded Show" in activity and "Untitled podcast" not in activity
        card = uoink_mcp_tools.get_evidence_card({"video_id": saved["video_id"]})
        assert card["channel"] == "The Grounded Show"
        assert card["source_revision"] == snapshot["source_revision"]
        reader = library_resources.LibraryReader(idx, data_root=tmp_path)
        assert reader.search("durable", mode="keyword")["hits"][0]["channel"] == "The Grounded Show"
        item = reader.get_item(video_id=saved["video_id"])
        assert item["card"]["channel"] == "The Grounded Show"
        assert item["card"]["source_revision"] == snapshot["source_revision"]
        assert reader.read(item["uris"]["card"])["contents"][0]["text"] == library_cards.card_text(item["card"])
        chunk = parse_fenced_document(reader.read(item["uris"]["corpus"])["contents"][0]["text"])
        assert chunk["labels"]["channel"] == "The Grounded Show"
        shelf_uri = next(r["uri"] for r in reader.list_resources() if r["name"].startswith("Shelf:"))
        shelf = parse_fenced_document(reader.read(shelf_uri)["contents"][0]["text"])
        assert shelf["page"]["members"][0]["channel"] == "The Grounded Show"
        for missing in (None, "", "Untitled podcast", "  UNTITLED PODCAST  "):
            row = dict(saved, channel=missing, author=missing)
            display = podcasts.repair_corpus_titles(idx, [row])[0]
            assert display["channel"] == display["author"] == "The Grounded Show"
            assert row["channel"] == missing
        named_host = dict(saved, channel="Named host", author="Named host")
        display = podcasts.repair_corpus_titles(idx, [named_host])[0]
        assert display["channel"] == display["author"] == "Named host"
        assert uoink_mcp_tools.query_by_facets({})["yoinks"][0]["channel"] == "The Grounded Show"
        assert _saved_podcast_state(idx, saved) == before
        assert idx._conn.total_changes == changes
        assert library_media._read_snapshot(idx._conn, saved["video_id"]).block == snapshot
        assert not fetch.requests
    finally:
        idx.close()


@pytest.mark.parametrize("kind", ["rss", "atom"])
def test_nonlegacy_podcast_observations_supply_display_titles(tmp_path, kind):
    idx = open_index(tmp_path)
    body = (b'<rss><channel><title>Channel title</title><item><guid>one</guid>'
            b'<title>Episode title</title></item></channel></rss>' if kind == "rss" else
            b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Channel title</title>'
            b'<entry><id>one</id><title>Episode title</title></entry></feed>')
    fetch = FakeFetch([http(200, body)])
    service = ss.SourceSubscriptionService(index=idx, clock=Clock(), adapters=ss.default_adapters(fetch),
                                           backend=FakeBackend(), instance_id="nonlegacy-title")
    try:
        sid = register(service, "podcast_rss", FEED_URL)["source_id"]
        turn_on(service, sid)
        with idx.write_transaction() as conn:
            conn.execute("UPDATE source_subscriptions SET legacy_feed_id=NULL WHERE source_id=?", (sid,))
        assert service.detection_pass()[0]["ok"]
        item = dict(idx._conn.execute("SELECT * FROM source_items WHERE source_id=?", (sid,)).fetchone())
        assert json.loads(item["metadata_json"])["feed_title"] == "Channel title"
        assert idx._conn.execute("SELECT display_name FROM source_subscriptions WHERE source_id=?",
                                 (sid,)).fetchone()[0] == "Channel title"
        video_id = ss.podcast_corpus_id(FEED_URL, "one")
        publish(idx, video_id, root=tmp_path, platform="podcast", source_type="episode")
        with idx.write_transaction() as conn:
            conn.execute("UPDATE source_items SET video_id=? WHERE item_id=?", (video_id, item["item_id"]))
            conn.execute("UPDATE yoinks SET channel='Untitled podcast', author='Named host' WHERE video_id=?",
                         (video_id,))
        saved = idx.get_yoink(video_id)
        before = _saved_podcast_state(idx, saved)
        changes = idx._conn.total_changes
        row = podcasts.repair_corpus_titles(idx, [saved], data_root=tmp_path)[0]
        assert row["channel"] == "Channel title" and row["author"] == "Named host"
        assert json.loads(row["metadata_json"])["podcast_title"] == "Channel title"
        assert _saved_podcast_state(idx, saved) == before
        assert idx._conn.total_changes == changes
        assert len(fetch.requests) == 1
    finally:
        idx.close()


def test_saved_show_name_displays_on_read_only_provider_without_writes(tmp_path, monkeypatch):
    idx, episode_id, _, _ = _seed_episode(tmp_path)
    try:
        published = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_feeds SET title=NULL")
            conn.execute("UPDATE yoinks SET channel='Untitled podcast', author='Untitled podcast', "
                         "metadata_json=json_set(metadata_json,'$.podcast_title','Untitled podcast')")
        saved = idx.get_yoink(published["video_id"])
        before = _saved_podcast_state(idx, saved)
        idx.close()
        idx = type(idx).open_existing(tmp_path / "index.db")
        fetch = FakeFetch([AssertionError("read must stay local")])
        monkeypatch.setattr(ss, "default_http_fetch", fetch)
        monkeypatch.setattr(idx, "initialize_for_write", lambda: pytest.fail("read must not request write access"))
        provider = corpus_provider.UoinkCorpusProvider(idx, tmp_path)
        assert provider.get(published["video_id"])["item"]["author"] == "The Grounded Show"
        assert _saved_podcast_state(idx, saved) == before
        assert podcasts.list_feeds(idx)[0]["title"] is None
        assert not fetch.requests
    finally:
        idx.close()


def test_provider_search_does_not_query_feed_titles_per_item(tmp_path):
    idx = open_index(tmp_path)
    try:
        for n in range(3):
            publish(idx, f"episode-{n}", root=tmp_path, platform="podcast", source_type="episode",
                    metadata={"podcast_title": "Saved show"})
        with idx.write_transaction() as conn:
            conn.execute("UPDATE yoinks SET channel='Saved show', author='Saved show'")
        statements = []
        idx._conn.set_trace_callback(statements.append)
        result = corpus_provider.UoinkCorpusProvider(idx, tmp_path).search(corpus_contract.SearchRequest())
        idx._conn.set_trace_callback(None)
        assert len(result["items"]) == 3
        assert all(item["author"] == "Saved show" for item in result["items"])
        assert sum("JOIN podcast_feeds" in sql for sql in statements) <= 1
    finally:
        idx.close()


def test_consented_poll_recovers_missing_show_without_republishing(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    body = (b'<rss><channel><image><url>https://cdn.example/first.jpg</url></image>'
            b'<item><guid>one</guid><title>Episode title</title>'
            b'</item></channel></rss>')
    fetch = FakeFetch([http(200, body), http(200, body.replace(
        b'<channel>', b'<channel><title>Recovered show</title>').replace(b'first.jpg', b'next.jpg'))])
    service = ss.SourceSubscriptionService(index=idx, clock=clock, adapters=ss.default_adapters(fetch),
                                           backend=FakeBackend(), instance_id="consented-title")
    try:
        sid = register(service, "podcast_rss", FEED_URL)["source_id"]
        assert service.detection_pass() == [] and not fetch.requests
        turn_on(service, sid)
        assert service.detection_pass()[0]["ok"]
        episode = podcasts.list_episodes(idx)[0]
        transcript = tmp_path / "transcript.json"
        transcript.write_text('{"segments":[{"start":0,"end":2,"text":"Example."}]}', encoding="utf-8")
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_episodes SET transcript_local_path=? WHERE id=?",
                         (str(transcript), episode["id"]))
        published = podcasts.episode_to_corpus(idx, episode["id"], data_root=tmp_path)
        saved = idx.get_yoink(published["video_id"])
        assert json.loads(saved["metadata_json"])["artwork_url"] == "https://cdn.example/first.jpg"
        before = _saved_podcast_state(idx, saved)
        clock.advance(61 * MINUTE_MS)
        assert service.detection_pass()[0]["ok"]
        assert podcasts.repair_corpus_titles(idx, [saved])[0]["channel"] == "Recovered show"
        metadata = json.loads(idx._conn.execute(
            "SELECT metadata_json FROM source_items WHERE source_id=?", (sid,)).fetchone()[0])
        assert metadata["feed_title"] == "Recovered show"
        assert metadata["artwork_url"] == "https://cdn.example/next.jpg"
        assert podcasts.episode_artwork_url(idx, episode["id"]) == metadata["artwork_url"]
        assert _saved_podcast_state(idx, saved) == before
        assert len(fetch.requests) == 2
    finally:
        idx.close()


@pytest.mark.parametrize("title_source", ["sidecar", "subscription", "observation"])
def test_boot_repairs_only_placeholder_registry_labels_from_local_data(tmp_path, monkeypatch, title_source):
    idx = open_index(tmp_path)
    body = (b'<rss><channel><title>Local show</title><item><guid>one</guid>'
            b'<title>Episode title</title></item></channel></rss>')
    fetch = FakeFetch([http(200, body)])
    service = ss.SourceSubscriptionService(index=idx, clock=Clock(), adapters=ss.default_adapters(fetch),
                                           backend=FakeBackend(), instance_id="local-title")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(ss, "default_http_fetch", fetch)
    try:
        sid = register(service, "podcast_rss", FEED_URL)["source_id"]
        turn_on(service, sid)
        assert service.detection_pass()[0]["ok"]
        video_id = ss.podcast_corpus_id(FEED_URL, "one")
        publish(idx, video_id, root=tmp_path, platform="podcast", source_type="episode",
                metadata={"feed_url": FEED_URL})
        saved = idx.get_yoink(video_id)
        if title_source == "sidecar":
            sidecar = Path(saved["sidecar_path"])
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            sidecar.write_text(json.dumps(dict(data, podcast_title="Local show")), encoding="utf-8")
        with idx.write_transaction() as conn:
            conn.execute("UPDATE source_items SET video_id=? WHERE source_id=?", (video_id, sid))
            conn.execute("UPDATE podcast_feeds SET title='Untitled podcast'")
            if title_source != "subscription":
                conn.execute("UPDATE source_subscriptions SET display_name=NULL")
            if title_source != "observation":
                conn.execute("UPDATE source_items SET metadata_json=json_set(metadata_json,'$.feed_title','Untitled podcast')")
        before = _saved_podcast_state(idx, saved)
        server._repair_podcast_titles_at_boot()
        assert podcasts.list_feeds(idx)[0]["title"] == "Local show"
        assert idx._conn.execute("SELECT display_name FROM source_subscriptions WHERE source_id=?", (sid,)).fetchone()[0] == "Local show"
        metadata = idx._conn.execute("SELECT metadata_json FROM source_items WHERE source_id=?", (sid,)).fetchone()[0]
        assert json.loads(metadata)["feed_title"] == "Local show"
        assert _saved_podcast_state(idx, saved) == before
        assert len(fetch.requests) == 1
        with idx.write_transaction() as conn:
            conn.execute("UPDATE source_subscriptions SET display_name='My saved label'")
            conn.execute("UPDATE source_items SET metadata_json=json_set(metadata_json,'$.feed_title','Saved feed title')")
        server._repair_podcast_titles_at_boot()
        assert idx._conn.execute("SELECT display_name FROM source_subscriptions WHERE source_id=?", (sid,)).fetchone()[0] == "My saved label"
        metadata = idx._conn.execute("SELECT metadata_json FROM source_items WHERE source_id=?", (sid,)).fetchone()[0]
        assert json.loads(metadata)["feed_title"] == "Saved feed title"
    finally:
        idx.close()


@pytest.mark.parametrize("local_title", [False, True])
def test_startup_uses_only_local_titles_and_leaves_saved_media_unchanged(tmp_path, monkeypatch, local_title):
    idx, episode_id, _, _ = _seed_episode(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    try:
        if not local_title:
            with idx.write_transaction() as conn:
                conn.execute("UPDATE podcast_feeds SET title=NULL")
        published = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        saved = idx.get_yoink(published["video_id"])
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_feeds SET title=NULL")
            conn.execute("UPDATE source_subscriptions SET display_name=NULL")
        before = _saved_podcast_state(idx, saved)
        cursors = [tuple(r) for r in idx._conn.execute("SELECT * FROM source_detection_cursors")]
        episodes = [tuple(r) for r in idx._conn.execute("SELECT * FROM podcast_episodes")]
        fetch = FakeFetch([http(200, b'<rss><channel><title>Must not fetch</title></channel></rss>')])
        monkeypatch.setattr(ss, "default_http_fetch", fetch)
        server._repair_podcast_titles_at_boot()
        assert not fetch.requests
        assert _saved_podcast_state(idx, saved) == before
        assert podcasts.list_feeds(idx)[0]["title"] == ("The Grounded Show" if local_title else None)
        assert [tuple(r) for r in idx._conn.execute("SELECT * FROM source_detection_cursors")] == cursors
        assert [tuple(r) for r in idx._conn.execute("SELECT * FROM podcast_episodes")] == episodes
        changes = idx._conn.total_changes
        server._repair_podcast_titles_at_boot()
        assert idx._conn.total_changes == changes
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


@pytest.mark.parametrize("mode", ["tweet", "thread", "blog", "newsletter", "script", "research"])
def test_picker_uses_sentence_case_and_stays_hidden_for_research(mode):
    result = run_js("selectedWritingMode = () => " + json.dumps(mode) + ";" + """
      renderWritingScreenshots();
      ({label:getEl('pickBestScreenshots').textContent,
        hidden:els.writingScreenshotPanel.classList.contains('hidden')});
    """)
    assert result["hidden"] == (mode == "research")
    if mode != "research":
        assert result["label"] == f"Pick best for {mode}"
    else:
        assert result["label"] != "Pick best for research"


def test_script_examples_follow_agent_connection_and_mode():
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
        const hidden = els.generateResearchPanel.classList.contains('hidden');
        state.agents = [{label:'Example agent',connected:true}]; renderAgentSetup();
        const restored = !els.generateResearchPanel.classList.contains('hidden');
        selectedWritingMode = () => 'tweet'; syncWritingGenerateState();
        return {shown, hidden, restored, otherModeHidden:els.generateResearchPanel.classList.contains('hidden')};
      })();
    """)
    assert result == {"shown": True, "hidden": True, "restored": True, "otherModeHidden": True}


def test_agent_hint_waits_for_detection():
    import re

    hint = re.search(r'<div\b[^>]*id="writingAgentHint"[^>]*>', DASHBOARD).group()
    assert "hidden" in hint
    result = run_js("""
      selectedWritingMode = () => 'script';
      syncWritingGenerateState();
      const checking = getEl('writingAgentHint').classList.contains('hidden');
      state.agentDetectionLoaded = true; renderAgentSetup();
      ({checking, missing:getEl('writingAgentHint').classList.contains('hidden')});
    """)
    assert result == {"checking": True, "missing": False}


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


@pytest.mark.parametrize("timezone", ["UTC", "America/Los_Angeles", "Asia/Tokyo"])
@pytest.mark.parametrize("day, next_day", [("2026-11-01", "2026-11-02"),
                                          ("2026-03-08", "2026-03-09")])
def test_insights_custom_dates_include_the_end_day_and_validate_order(monkeypatch, timezone, day, next_day):
    monkeypatch.setenv("TZ", timezone)
    result = run_js("const day = " + json.dumps(day) + ";" + """
      const handlers = {};
      getEl('activityApplyCustomBtn').addEventListener = (event, fn) => {handlers[event] = fn;};
      document.addEventListener = () => {}; window.addEventListener = () => {};
      let loads = 0; loadLibraryActivity = () => {loads++;}; wireLibraryActivityEvents();
      getEl('activityStartInput').value = day; getEl('activityEndInput').value = day;
      handlers.click();
      const interval = libraryActivityState.interval;
      libraryActivityState.packet = {interval}; renderLibraryActivityUI();
      const shown = getEl('activityUtcInterval').textContent;
      const date = formatActivityDate(day + 'T00:00:00Z', true);
      getEl('activityEndInput').value = '2026-01-01'; handlers.click();
      ({interval, shown, expectedLabel:date + ' to ' + date, loads,
        error:getEl('activityCustomError').textContent});
    """)
    assert result["interval"] == {"start": f"{day}T00:00:00.000Z", "end": f"{next_day}T00:00:00.000Z"}
    assert result["shown"] == result["expectedLabel"]
    assert result["loads"] == 1 and "end date" in result["error"].lower()


def test_insights_shelves_keep_identifier_fallback():
    result = run_js("""
      renderActivityShelves([{shelf_id:'Shelf <one>'}, {shelf_id:'two', label:'Named shelf'}, {}]);
      getEl('activityShelvesBody').innerHTML;
    """)
    assert "Shelf &lt;one&gt;" in result
    assert "Named shelf" in result
    assert result.count("Unnamed shelf") == 1
