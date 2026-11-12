"""3.17 podcast suggestions: engine, HTTP handlers and the dashboard states.

No real network anywhere: the engine takes an injected fetch, and the handlers
are called directly with a stubbed response writer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import index as index_mod  # noqa: E402
import podcasts  # noqa: E402
import server  # noqa: E402
import suggestions  # noqa: E402
from test_dashboard_runthrough_fixes import run_js  # noqa: E402

NOW = 1_800_000_000.0
DAY = 86400.0


@pytest.fixture
def idx(tmp_path):
    index = index_mod.Index.open(tmp_path / "index.db")
    yield index
    index.close()


def _seed(index, root, n, title, channel="Chan", topic="Business"):
    folder = Path(root) / f"v{n}"
    folder.mkdir(parents=True, exist_ok=True)
    index.upsert_yoink({
        "video_id": f"vid{n:08d}", "slug": f"vid{n}", "channel": channel, "title": title,
        "topic": topic, "hook_type": "other", "yoinked_at": "2026-10-01T09:00:00",
        "corpus_path": str(folder / "c.md"), "sidecar_path": "", "source_type": "youtube",
    }, content=f"{title} body")


def _seed_library(index, root):
    titles = ["Pricing your product", "Pricing is a story", "Pricing and packaging",
              "Launch week notes", "Launch plan for agents", "Writing every day"]
    for i, title in enumerate(titles):
        _seed(index, root, i, title, channel=f"Chan{i}")
    return titles


def _row(track, title, show="Show A", *, audio=None, desc="", art="https://img.example.test/a.jpg",
         feed="https://feeds.example.test/a.xml", cid=11):
    return {"trackId": track, "trackName": title, "collectionName": show, "collectionId": cid,
            "episodeUrl": audio or f"https://cdn.example.test/{track}.mp3",
            "trackViewUrl": f"https://pod.example.test/{track}", "feedUrl": feed,
            "releaseDate": "2026-11-01T00:00:00Z", "trackTimeMillis": 2_700_000,
            "artworkUrl160": art, "description": desc}


class Fake:
    def __init__(self, by_term):
        self.by_term = by_term
        self.calls = []

    def __call__(self, term, limit):
        self.calls.append((term, limit))
        got = self.by_term.get(term)
        if isinstance(got, Exception):
            raise got
        return {"results": got or []}


def _refresh(idx, tmp_path, fake, *, now=NOW, force=False, enabled=True):
    return suggestions.refresh(idx, tmp_path, enabled=enabled, fetch=fake, now=lambda: now,
                               sleep=lambda s: None, force=force)


# ---- engine ------------------------------------------------------------------

def test_off_by_default_and_never_fetches_when_off(idx, tmp_path):
    assert server._default_settings()["suggest_podcasts"] is False
    assert server._normalize_settings({"suggest_podcasts": "yes"})["suggest_podcasts"] is False
    _seed_library(idx, tmp_path)
    fake = Fake({})
    assert _refresh(idx, tmp_path, fake, enabled=False)["status"] == "off"
    assert fake.calls == []


def test_small_library_explains_itself_and_calls_nothing(idx, tmp_path):
    for i in range(4):
        _seed(idx, tmp_path, i, "Pricing talk")
    fake = Fake({})
    assert _refresh(idx, tmp_path, fake)["status"] == "not_enough"
    assert fake.calls == []
    ready = suggestions.readiness(idx)
    assert ready["enough"] is False and ready["terms"] == [] and ready["library_size"] == 4


def test_terms_come_from_recurring_words_and_followed_shows(idx, tmp_path):
    _seed_library(idx, tmp_path)
    assert [w for w, _ in suggestions.top_terms(idx)][:2] == ["pricing", "launch"]
    counts = dict(suggestions.top_terms(idx))
    assert counts["pricing"] == 3 and counts["launch"] == 2
    # A followed show adds its title words (one vote per show).
    podcasts.add_feed(idx, "https://feeds.example.test/w.xml")
    podcasts.add_feed(idx, "https://feeds.example.test/x.xml")
    for feed in podcasts.list_feeds(idx):
        podcasts.record_feed_meta(idx, feed["id"], title="Daily Writing Show", description=None,
                                  homepage=None, etag=None, last_modified=None, ok=True)
    # Two followed shows share the phrase "daily writing", so the phrase wins
    # over its single words (it searches far more precisely).
    terms = dict(suggestions.top_terms(idx, limit=10))
    assert terms["daily writing"] >= 2
    assert "writing" not in terms and "daily" not in terms


def test_recurring_phrases_come_before_single_words(idx, tmp_path):
    for i, title in enumerate(["Claude Code tips", "Shipping with Claude Code", "Pricing basics",
                               "Pricing pages", "Pricing tiers", "Notes"]):
        _seed(idx, tmp_path, i, title, channel=f"Chan{i}")
    ranked = [w for w, _ in suggestions.top_terms(idx)]
    assert ranked[0] == "claude code"
    assert "pricing" in ranked and "claude" not in ranked and "code" not in ranked


def test_episodes_must_mention_the_term_themselves():
    assert suggestions.mentions_term("claude code", "Claude Code in practice", "")
    assert suggestions.mentions_term("pricing", "Episode 12", "We talk pricing pages.")
    assert not suggestions.mentions_term("launch", "Raising toddlers", "A parenting show")
    assert not suggestions.mentions_term("claude code", "Claude Monet", "Painting in Giverny")


def test_only_topic_words_are_sent_and_calls_are_capped(idx, tmp_path):
    titles = _seed_library(idx, tmp_path)
    fake = Fake({})
    _refresh(idx, tmp_path, fake)
    sent = [term for term, _ in fake.calls]
    assert sent == ["pricing", "launch"]               # exact words, nothing else
    assert len(fake.calls) <= suggestions.MAX_TERMS
    blob = json.dumps(fake.calls).lower()
    for title in titles:
        assert title.lower() not in blob
    assert "http" not in blob and "vid0000" not in blob


def test_dedupe_dismissed_scoring_order_and_reason(idx, tmp_path):
    _seed_library(idx, tmp_path)
    podcasts.add_feed(idx, "https://feeds.example.test/own.xml")
    fid = podcasts.list_feeds(idx)[0]["id"]
    podcasts.upsert_episodes(idx, fid, [{"guid": "g1", "title": "Saved ep",
                                         "audio_url": "https://cdn.example.test/saved.mp3"}])
    with idx.write_transaction() as conn:
        conn.execute("UPDATE podcast_episodes SET yoink_video_id='vidx' WHERE guid='g1'")
    rows = [
        _row(1, "Pricing your product"),                                  # same title as a saved item
        _row(2, "Anything", audio="https://cdn.example.test/saved.mp3"),  # same audio as a saved episode
        _row(3, "A pricing deep dive", "Show B", cid=12),                 # in the title: ranks first
        _row(4, "Weekly roundup", "Show C", desc="we cover pricing too", cid=13),
        _row(5, "Dismissed one", "Show D", cid=14),
    ]
    fake = Fake({"pricing": rows})
    dismissed_id = suggestions.parse_episodes({"results": [rows[4]]})[0]["id"]
    suggestions.dismiss(tmp_path, dismissed_id)
    result = _refresh(idx, tmp_path, fake)
    assert result["status"] == "refreshed"
    items = suggestions.current(tmp_path, idx)["items"]
    assert [i["title"] for i in items] == ["A pricing deep dive", "Weekly roundup"]
    assert items[0]["score"] > items[1]["score"]
    assert items[0]["reason"] == "Because you saved 3 things about pricing"
    assert all(i["artwork"].startswith("https://") for i in items)


def test_show_cap_and_item_cap(idx, tmp_path):
    _seed_library(idx, tmp_path)
    many = [_row(100 + n, f"Pricing episode {n}", show=f"Show {n // 3}", cid=n) for n in range(60)]
    _refresh(idx, tmp_path, Fake({"pricing": many}))
    items = suggestions.current(tmp_path)["items"]
    assert len(items) <= suggestions.MAX_ITEMS
    shows = [i["show"] for i in items]
    assert max(shows.count(s) for s in set(shows)) <= suggestions.MAX_PER_SHOW


def test_daily_cache_offline_and_failure_keep_last_good_list(idx, tmp_path):
    _seed_library(idx, tmp_path)
    good = Fake({"pricing": [_row(7, "Pricing for makers")]})
    assert _refresh(idx, tmp_path, good)["status"] == "refreshed"
    # Within a day: served from the cache, no calls.
    again = Fake({})
    assert _refresh(idx, tmp_path, again, now=NOW + 3600)["status"] == "fresh"
    assert again.calls == []
    # Offline later: the list still reads from the cache file alone.
    assert [i["title"] for i in suggestions.current(tmp_path)["items"]] == ["Pricing for makers"]
    # Due, but the network is down: failure, last good list stays.
    down = Fake({"pricing": OSError("offline"), "launch": OSError("offline")})
    assert _refresh(idx, tmp_path, down, now=NOW + DAY + 10)["status"] == "failed"
    assert [i["title"] for i in suggestions.current(tmp_path)["items"]] == ["Pricing for makers"]
    # And it does not hammer: another try within the backoff hour does nothing.
    third = Fake({})
    assert _refresh(idx, tmp_path, third, now=NOW + DAY + 60)["status"] == "fresh"
    assert third.calls == []
    # Manual refresh is limited to once per ten minutes.
    assert _refresh(idx, tmp_path, third, now=NOW + DAY + 120, force=True)["status"] == "fresh"
    assert _refresh(idx, tmp_path, good, now=NOW + DAY + 4000, force=True)["status"] == "refreshed"


def test_rate_limit_stops_further_calls(idx, tmp_path):
    _seed_library(idx, tmp_path)

    class Limited(Exception):
        code = "rate_limited"

    fake = Fake({"pricing": Limited()})
    assert _refresh(idx, tmp_path, fake)["status"] == "failed"
    assert len(fake.calls) == 1


def test_parse_drops_unsafe_urls():
    parsed = suggestions.parse_episodes({"results": [
        _row(1, "Ok", art="http://img.example.test/a.jpg"),
        {"trackName": "No links"},
        {"trackName": "Bad", "episodeUrl": "javascript:alert(1)"},
    ]})
    assert len(parsed) == 1 and parsed[0]["artwork"] == ""


def test_feed_url_lookup_when_missing(tmp_path):
    suggestions.save_cache(tmp_path, {**suggestions._empty_cache(), "items": [
        {"id": "sg_aaaaaaaaaaaa", "title": "T", "show": "S", "show_id": "42", "feed_url": ""}]})
    seen = []
    url = suggestions.resolve_feed_url(
        tmp_path, "sg_aaaaaaaaaaaa",
        lookup=lambda cid: seen.append(cid) or {"results": [{"feedUrl": "https://feeds.example.test/s.xml"}]})
    assert url == "https://feeds.example.test/s.xml" and seen == ["42"]
    with pytest.raises(suggestions.SuggestionError):
        suggestions.resolve_feed_url(tmp_path, "sg_bbbbbbbbbbbb")


# ---- handlers ----------------------------------------------------------------

class Resp:
    def __init__(self):
        self.sent = []


def _handler(monkeypatch, idx, tmp_path, *, enabled=True, token=True):
    resp = Resp()
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: resp.sent.append((status, payload))
    handler._check_token = lambda: token
    handler.command, handler.path = "GET", "/suggestions/podcasts"
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_read_settings", lambda: {"suggest_podcasts": enabled})
    monkeypatch.setattr(server, "_podcast_suggestions_refresh_async", lambda **kw: False)
    server._podcast_suggestion_saves.clear()
    return handler, resp


def _cache_item(tmp_path, sid="sg_aaaaaaaaaaaa", **over):
    item = {"id": sid, "title": "Pricing for makers", "show": "Show A", "show_id": "11",
            "episode_url": "https://cdn.example.test/e1.mp3", "page_url": "https://pod.example.test/e1",
            "feed_url": "https://feeds.example.test/a.xml", "artwork": "", "duration_s": 2700,
            "released": "2026-11-01T00:00:00Z", "description": "", "score": 0.4,
            "term": "pricing", "reason": "Because you saved 3 things about pricing", **over}
    cache = suggestions.load_cache(tmp_path)
    cache["items"].append(item)
    suggestions.save_cache(tmp_path, cache)
    return item


def test_list_requires_token(monkeypatch, idx, tmp_path):
    handler, resp = _handler(monkeypatch, idx, tmp_path, token=False)
    handler._handle_podcast_suggestions_list()
    assert resp.sent[0][0] == 403


def test_list_off_returns_nothing_and_no_words_sent(monkeypatch, idx, tmp_path):
    _cache_item(tmp_path)
    handler, resp = _handler(monkeypatch, idx, tmp_path, enabled=False)
    handler._handle_podcast_suggestions_list()
    status, body = resp.sent[0]
    assert status == 200 and body["enabled"] is False and body["items"] == []
    assert "itunes.apple.com" in body["disclosure"]


def test_list_on_shows_cache_and_the_words(monkeypatch, idx, tmp_path):
    _seed_library(idx, tmp_path)
    _cache_item(tmp_path)
    handler, resp = _handler(monkeypatch, idx, tmp_path)
    handler._handle_podcast_suggestions_list()
    body = resp.sent[0][1]
    assert body["enabled"] and body["count"] == 1 and body["enough"]
    assert body["send_terms"] == ["pricing", "launch"]


def test_refresh_save_follow_refuse_when_off(monkeypatch, idx, tmp_path):
    _cache_item(tmp_path)
    handler, resp = _handler(monkeypatch, idx, tmp_path, enabled=False)
    handler._handle_podcast_suggestions_refresh({})
    handler._handle_podcast_suggestions_save({"id": "sg_aaaaaaaaaaaa"})
    handler._handle_podcast_suggestions_follow({"id": "sg_aaaaaaaaaaaa"})
    assert [s for s, _ in resp.sent] == [409, 409, 409]


def test_bad_ids_are_rejected(monkeypatch, idx, tmp_path):
    handler, resp = _handler(monkeypatch, idx, tmp_path)
    for fn in (handler._handle_podcast_suggestions_dismiss, handler._handle_podcast_suggestions_save,
               handler._handle_podcast_suggestions_follow):
        fn({"id": "../x"})
        fn({})
    assert {s for s, _ in resp.sent} == {400}


def test_dismiss_hides_the_item(monkeypatch, idx, tmp_path):
    _cache_item(tmp_path)
    handler, resp = _handler(monkeypatch, idx, tmp_path)
    handler._handle_podcast_suggestions_dismiss({"id": "sg_aaaaaaaaaaaa"})
    assert resp.sent[0][0] == 200
    assert suggestions.current(tmp_path)["items"] == []


def test_save_unknown_is_404(monkeypatch, idx, tmp_path):
    handler, resp = _handler(monkeypatch, idx, tmp_path)
    handler._handle_podcast_suggestions_save({"id": "sg_cccccccccccc"})
    assert resp.sent[0][0] == 404


def test_save_registers_one_episode_without_subscribing(monkeypatch, idx, tmp_path):
    item = _cache_item(tmp_path)
    handler, resp = _handler(monkeypatch, idx, tmp_path)
    polled, queued = [], []
    monkeypatch.setattr(server, "_poll_podcast_feed_for_watch", lambda fid: polled.append(fid))
    monkeypatch.setattr(podcasts, "download_episode_audio", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(server, "_queue_podcast_transcription",
                        lambda eid, **kw: queued.append((eid, kw)) or ({"ok": True}, 202))
    server._run_podcast_suggestion_save(item["id"], item)
    assert polled == []                                    # no feed fetch, no polling
    feed = podcasts.list_feeds(idx)[0]
    assert feed["enabled"] == 0 and feed["auto_ingest"] == 0   # not followed, nothing ingested
    episodes = podcasts.list_episodes(idx, feed_id=feed["id"])
    assert len(episodes) == 1 and episodes[0]["audio_url"] == item["episode_url"]
    assert queued and queued[0][1]["publish_to_corpus"] is True
    assert server._podcast_suggestion_saves[item["id"]]["state"] == "saved"
    assert suggestions.current(tmp_path)["items"] == []   # saved items leave the shelf


def test_save_reports_missing_transcription_setup(monkeypatch, idx, tmp_path):
    item = _cache_item(tmp_path)
    _handler(monkeypatch, idx, tmp_path)
    monkeypatch.setattr(podcasts, "download_episode_audio", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(server, "_queue_podcast_transcription",
                        lambda eid, **kw: ({"ok": False}, 412))
    server._run_podcast_suggestion_save(item["id"], item)
    state = server._podcast_suggestion_saves[item["id"]]
    assert state["state"] == "failed" and "transcription" in state["message"].lower()
    assert suggestions.get_item(tmp_path, item["id"]) is not None   # can try again


def test_follow_turns_a_saved_show_on(monkeypatch, idx, tmp_path):
    item = _cache_item(tmp_path)
    handler, resp = _handler(monkeypatch, idx, tmp_path)
    server._register_suggested_episode(idx, item["feed_url"], item)
    assert podcasts.list_feeds(idx)[0]["enabled"] == 0
    handler._handle_podcast_suggestions_follow({"id": item["id"]})
    assert resp.sent[-1][0] == 200
    assert podcasts.list_feeds(idx)[0]["enabled"] == 1


def test_new_module_is_registered_for_every_package():
    root = Path(__file__).resolve().parent.parent
    for rel in ("build.ps1", "installer/uoink.iss", "installer/verify_install.ps1",
                "scripts/mac/payload.json"):
        assert "suggestions.py" in (root / rel).read_text(encoding="utf-8"), rel


# ---- dashboard states ----------------------------------------------------------

def test_dashboard_teaser_states():
    out = run_js("""({
      loading: forYouPodTeaserHtml(null),
      tiny: forYouPodTeaserHtml({enabled:false, library_size:3}),
      offer: forYouPodTeaserHtml({enabled:false, library_size:9, send_terms:["pricing","launch"]}),
      dismissed: forYouPodTeaserHtml({enabled:false, library_size:9}, {dismissed:true}),
      notEnough: forYouPodTeaserHtml({enabled:true, enough:false, items:[]}),
      refreshing: forYouPodTeaserHtml({enabled:true, enough:true, items:[], refreshing:true}),
      error: forYouPodTeaserHtml({enabled:true, enough:true, items:[], error:"fetch_failed"}),
      some: forYouPodTeaserHtml({enabled:true, enough:true, items:[{id:"a"},{id:"b"},{id:"c"}]}),
    })""")
    assert out["loading"] == "" and out["tiny"] == "" and out["dismissed"] == ""
    assert "Get podcast suggestions from what you save" in out["offer"]
    assert "pricing, launch" in out["offer"] and "Turn on" in out["offer"]
    assert "No titles, links or transcripts" in out["offer"]
    assert "Save a few things" in out["notEnough"]
    assert "Looking for" in out["refreshing"]
    assert "Couldn&#39;t reach" in out["error"] or "Couldn't reach" in out["error"]
    assert "3 podcast episodes picked for you" in out["some"] and 'href="#for-you"' in out["some"]
    assert 'id="forYouShelfTitle"' in out["some"]


def test_dashboard_panel_states_and_card_safety():
    nasty = '<img src=x onerror=alert(1)>' + "x" * 300
    out = run_js("""(() => {
      const item = {id:"sg_aaaaaaaaaaaa", title: %s, show:"A Show", duration_s: 5400,
                    reason:"Because you saved 3 things about pricing", artwork:"https://img.example.test/a.jpg"};
      return {
        loading: forYouPodPanelHtml(null, ""),
        failed: forYouPodPanelHtml(null, "boom"),
        off: forYouPodPanelHtml({enabled:false, send_terms:["pricing"]}),
        notEnough: forYouPodPanelHtml({enabled:true, enough:false, items:[]}),
        empty: forYouPodPanelHtml({enabled:true, enough:true, items:[]}),
        cards: forYouPodPanelHtml({enabled:true, enough:true, items:[item,
          {...item, id:"sg_bbbbbbbbbbbb", save_state:"saving"},
          {...item, id:"sg_cccccccccccc", save_state:"saved", save_message:"Saved. Transcribing now."},
          {...item, id:"sg_dddddddddddd", save_state:"failed", save_message:"Set up transcription in Settings first, then save it again.", artwork:""}]}),
      };
    })()""" % json.dumps(nasty))
    assert "Looking for podcast episodes" in out["loading"]
    assert "Try again" in out["failed"] and "boom" in out["failed"]
    assert "Turn on" in out["off"] and "pricing" in out["off"]
    assert "Save a few things" in out["notEnough"]
    assert "No new podcast picks" in out["empty"]
    cards = out["cards"]
    assert "<img src=x" not in cards and "&lt;img" in cards      # titles are escaped
    assert 'loading="lazy"' in cards and "for-you-pod-title" in cards and 'title="' in cards
    assert "1 hr 30 min" in cards
    for label in ("Save", "Follow show", "Not interested", "Saving...", "Saved", "Try again"):
        assert label in cards, label
    assert cards.count("data-for-you-pod=\"save\"") == 4


def test_shared_container_is_exact_and_shelf_is_the_only_target():
    html = (Path(__file__).resolve().parent.parent / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
    block = ('          <div class="home-shelves" id="homeShelves">\n'
             '            <section class="home-shelf hidden" id="rediscoverShelf" aria-labelledby="rediscoverShelfTitle"></section>\n'
             '            <section class="home-shelf hidden" id="forYouShelf" aria-labelledby="forYouShelfTitle"></section>\n'
             '          </div>\n'
             '          <div id="libraryGrid" class="library-list"></div>')
    assert block in html.replace("\r\n", "\n")
    assert "rediscoverShelf" not in html[html.index("function forYouPodRender"):html.index("function forYouPodSchedule")]
