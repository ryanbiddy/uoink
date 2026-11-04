"""Offline fixture, ranking, consent and persistence tests for research runs."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

import pytest

import list_imports
import research as r

FIXTURES = Path(__file__).parent / "fixtures" / "research"
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fetchers():
    return {
        "library": lambda q, n: [{"video_id": "evaltalk001", "title": "Agent evals: measuring useful work",
                                  "channel": "Systems Forum", "duration": 2700}],
        "youtube": lambda q, n: fixture("ytsearch_evals.json"),
        "hn": lambda q, n: fixture("hn_search_evals.json"),
        "podcast": lambda q, n: fixture("itunes_episodes.json"),
        "hackertube": lambda: fixture("hackertube_list.json"),
        "sleep": lambda seconds: None,
    }


@pytest.fixture(autouse=True)
def no_http(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Research tests must inject network fetchers")
    monkeypatch.setattr(r.urllib.request, "urlopen", fail)


def test_parsers_preserve_fields_and_capturability():
    yt = r.parse_ytsearch(fixture("ytsearch_evals.json"))
    assert len(yt) == 6
    assert yt[0]["key"] == "yt:evaltalk001" and yt[0]["published"] == "2026-10-01"
    assert yt[0]["signals"]["view_count"] == 12000
    assert yt[1]["published"] == "2026-01-01" and yt[1]["channel"] == "Systems Forum"
    assert yt[-1]["duration_s"] is None
    assert all(c["has_captions"] is None and c["capturable"] for c in yt)
    hn = r.parse_hn_search(fixture("hn_search_evals.json"))
    assert [c["key"] for c in hn] == ["yt:evaltalk001", "yt:evaltalk002", "hn:90000003"]
    assert hn[0]["signals"] == {"found_by": [], "hn_points": 140, "hn_comments": 52,
                                "hn_url": "https://news.ycombinator.com/item?id=90000001"}
    assert hn[0]["published"] is None  # submission date is not publication date
    assert hn[-1]["capturable"] is False
    podcast = r.parse_itunes_episodes(fixture("itunes_episodes.json"))
    assert len(podcast) == 2 and podcast[0]["duration_s"] == 3000
    assert podcast[0]["published"] == "2026-10-12"
    assert podcast[0]["episodeUrl"] == podcast[0]["url"] and podcast[0]["feedUrl"]
    assert podcast[0]["capturable"] is True and podcast[1]["capturable"] is False
    assert all(re.fullmatch(r"pod:[0-9a-f]{12}", c["key"]) for c in podcast)
    assert r.parse_itunes_episodes(fixture("itunes_episodes.json")) == podcast
    ht = r.parse_hackertube(fixture("hackertube_list.json"), "evals")
    assert [c["key"] for c in ht] == ["yt:evaltalk001", "yt:evaltalk007"]
    assert all(c["credit"] == list_imports.HACKERTUBE_CREDIT for c in ht)
    assert ht[0]["signals"]["hackertube_quality"] == 25
    assert r.parse_hackertube(fixture("hackertube_list.json"), "SOUND")[0]["key"] == "yt:evaltalk008"


@pytest.mark.parametrize("url,kept", [
    ("https://talks.libsyn.com/evals", True), ("https://show.simplecast.com/episodes/evals", True),
    ("https://show.transistor.fm/evals", True), ("https://show.buzzsprout.com/evals", True),
    ("https://show.megaphone.fm/evals", True), ("https://anchor.fm/evals", True),
    ("https://podcasters.spotify.com/evals", True), ("https://open.spotify.com/show/evals", False),
    ("https://libsyn.com.example.org/evals", False), ("https://notlibsyn.com/evals", False),
    ("https://example.org/?url=https://youtu.be/evaltalk001", False), ("javascript:alert(1)", False),
])
def test_hn_host_allowlist(url, kept):
    assert bool(r.parse_hn_search({"hits": [{"objectID": "1", "url": url}]})) is kept


@pytest.mark.parametrize("value", ["../outside", "rr_20261103000000_123456ab/../x",
    "rr_20261103000000_123456AB", "rr_20261103000000_123456ab\n", "rr_2026113_123456ab", "", None])
def test_run_id_rejected_before_filesystem(tmp_path, value, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Invalid ids must not reach the filesystem")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", fail)
        for operation in (lambda: r.load_run(tmp_path, value),
                          lambda: r.save_run(tmp_path, {"run_id": value})):
            with pytest.raises(r.ResearchError) as error:
                operation()
            assert error.value.code == "invalid_run_id"


def test_store_roundtrip_list_and_atomic_failure(tmp_path, monkeypatch):
    first = r.create_run(tmp_path, {"question": "  agent evals  "}, now=NOW)
    second = r.create_run(tmp_path, {"question": "Another question"}, now=NOW)
    assert re.fullmatch(r.RUN_ID_PATTERN, first["run_id"])
    assert first["run_id"] != second["run_id"]
    assert r.load_run(tmp_path, first["run_id"]) == first
    assert len(r.list_runs(tmp_path, 1)) == 1 and len(r.list_runs(tmp_path, 20)) == 2
    path = tmp_path / "research" / first["run_id"] / "run.json"
    original = path.read_bytes()
    first["candidates"] = [{"key": "test"}]
    def fail(*args):
        raise OSError("private/path/must/not/escape")
    monkeypatch.setattr(r.os, "replace", fail)
    with pytest.raises(r.ResearchError) as error:
        r.save_run(tmp_path, first)
    assert error.value.code == "store_failed" and "private" not in str(error.value)
    assert path.read_bytes() == original and not list(path.parent.glob("*.tmp"))


def test_scope_defaults_and_bounds():
    assert r.normalize_scope({"question": "  evals  "}) == {
        "question": "evals", "max_sources": 12, "source_kinds": list(r.DEFAULT_SOURCE_KINDS), "max_asr_minutes": 120}
    assert r.normalize_scope({"question": "x" * 500, "max_sources": 30,
                              "max_asr_minutes": 1440, "source_kinds": [], "since": "2024-02-29"})["since"] == "2024-02-29"
    assert r.normalize_scope({"question": "x", "max_sources": 1, "max_asr_minutes": 0})["max_asr_minutes"] == 0


@pytest.mark.parametrize("fields", [
    {"question": " "}, {"question": 2}, {"question": "x" * 501}, {"max_sources": 0},
    {"max_sources": 31}, {"max_sources": True}, {"max_sources": "12"},
    {"max_asr_minutes": -1}, {"max_asr_minutes": 1441}, {"max_asr_minutes": 1.5},
    {"source_kinds": ["unknown"]}, {"source_kinds": "youtube"}, {"source_kinds": ["hn", "hn"]},
    {"since": "2026-02-30"}, {"since": "2026-2-01"}, {"since": None}, {"consent": ["youtube"]},
])
def test_scope_refuses_invalid_fields(fields):
    with pytest.raises(r.ResearchError) as error:
        r.normalize_scope({"question": "evals", **fields})
    assert error.value.code


def test_consent_gates_fetchers_and_reddit_never_runs(tmp_path):
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise AssertionError("Unconsented fetcher called")
    run = r.create_run(tmp_path, {"question": "evals", "source_kinds": list(r.SOURCE_KINDS)})
    fakes = {kind: forbidden for kind in r.NETWORK_KINDS}
    fakes["library"] = fetchers()["library"]
    result = r.discover(run, ["evals"], fetchers=fakes, consented_kinds=[], now=NOW)
    assert calls == [] and not result["errors"]
    assert result["by_source"]["library"] == 1
    assert result["candidates"][0]["in_library"] is True
    assert {s["kind"] for s in result["skipped"] if s["reason"] == "needs_consent"} == set(r.NETWORK_KINDS) - {"reddit"}
    run["scope"]["source_kinds"] = ["reddit"]
    result = r.discover(run, ["evals"], fetchers=fakes, consented_kinds=["reddit"], now=NOW)
    assert calls == [] and result["skipped"] == [{"kind": "reddit", "reason": "reddit_search_off_in_mvp"}]


def test_merging_ranking_determinism_channel_cap_and_cost(tmp_path):
    run = r.create_run(tmp_path, {"question": "agent evals"})
    before = deepcopy(run)
    args = dict(fetchers=fetchers(), consented_kinds=list(r.NETWORK_KINDS), now=NOW)
    first = r.discover(run, ["agent evals"], **args)
    assert first == r.discover(run, ["agent evals"], **args) and run == before
    assert first["capped_by_channel"] == 1
    candidates = first["candidates"]
    assert sum(c["channel"].casefold() == "systems forum" for c in candidates) == 3
    merged = next(c for c in candidates if c["key"] == "yt:evaltalk001")
    assert merged["signals"]["hn_points"] == 140 and merged["signals"]["hackertube_quality"] == 25
    assert merged["credit"] == list_imports.HACKERTUBE_CREDIT
    assert {f["source"] for f in merged["signals"]["found_by"]} == {"library", "youtube", "hn", "hackertube"}
    assert merged["est_capture"] == "captions"
    assert "HackerTube quality: +0.750000" in merged["why_ranked"]
    assert f"HN points: +{math.log1p(140) * 0.5:.6f}" in merged["why_ranked"]
    assert next(c for c in candidates if c["key"] == "yt:evaltalk006")["est_capture"] == "unknown"
    assert next(c for c in candidates if c["key"] == "yt:evaltalk007")["est_capture"] == "asr ~14 min"
    assert all(c["why_ranked"] for c in candidates)


def test_bm25_and_prior_contributions_are_numeric_and_ties_use_key():
    scope = r.normalize_scope({"question": "evals"})
    items = r.parse_ytsearch({"entries": [
        {"id": "evaltalk002", "title": "evals", "channel": "B", "duration": 900},
        {"id": "evaltalk001", "title": "evals", "channel": "A", "duration": 900}]})
    ranked, capped = r.rank_candidates(items, ["evals"], scope, now=NOW)
    assert [c["key"] for c in ranked] == ["yt:evaltalk001", "yt:evaltalk002"]
    assert capped == 0
    assert ranked[0]["score"] == pytest.approx(math.log1p(0.5 / 2.5) + 0.5, abs=1e-6)
    assert ranked[0]["est_capture"] == "asr ~3 min"
    assert items[0]["score"] == 0  # pure ranker


def test_since_filter_recency_and_pool_bound(tmp_path):
    run = r.create_run(tmp_path, {"question": "evals", "since": "2026-01-01", "max_sources": 2})
    result = r.discover(run, ["evals"], fetchers=fetchers(), consented_kinds=["youtube"], now=NOW)
    assert len(result["candidates"]) <= 4
    assert all(c["key"] != "yt:evaltalk005" for c in result["candidates"])
    run["scope"]["max_sources"] = 12
    result = r.discover(run, ["evals"], fetchers=fetchers(), consented_kinds=["youtube"], now=NOW)
    assert any(c["published"] is None for c in result["candidates"])
    assert all(c["key"] != "yt:evaltalk005" for c in result["candidates"])
    assert all(any(reason.startswith("Recency:") for reason in c["why_ranked"]) for c in result["candidates"])
    recent = next(c for c in result["candidates"] if c["key"] == "yt:evaltalk001")
    assert f"Recency: +{math.exp(-33 / 365) * 0.5:.6f}" in recent["why_ranked"]


def test_source_failure_isolation_and_redaction(tmp_path):
    run = r.create_run(tmp_path, {"question": "evals"})
    def broken(*args):
        raise OSError("private/path/must/not/escape")
    result = r.discover(run, ["evals"], fetchers={**fetchers(), "youtube": broken},
                        consented_kinds=list(r.NETWORK_KINDS), now=NOW)
    assert result["errors"] == [{"kind": "youtube", "query": "evals", "code": "fetch_failed",
                                 "message": "youtube discovery could not complete."}]
    assert result["candidates"] and result["by_source"]["podcast"] == 2
    assert "private" not in json.dumps(result)


def test_itunes_four_call_cap_sleep_and_hackertube_single_fetch(tmp_path):
    run = r.create_run(tmp_path, {"question": "evals", "source_kinds": ["podcast", "hackertube"]})
    calls, sleeps, ht_calls = [], [], []
    def podcast(query, n):
        calls.append((query, n))
        return fixture("itunes_episodes.json")
    def hackertube():
        ht_calls.append(True)
        return fixture("hackertube_list.json")
    result = r.discover(run, [f"evals {i}" for i in range(8)], 3,
                        fetchers={"podcast": podcast, "hackertube": hackertube, "sleep": sleeps.append},
                        consented_kinds=["podcast", "hackertube"], now=NOW)
    assert len(calls) == 4 and all(n == 3 for _, n in calls)
    assert sleeps == [3, 3, 3] and ht_calls == [True]
    assert {"kind": "podcast", "reason": "itunes_call_cap"} in result["skipped"]


def test_fetchers_use_fixed_hosts_and_encoded_queries(monkeypatch):
    urls = []
    monkeypatch.setattr(r, "http_get_json", lambda url: urls.append(url))
    r.fetch_hn("evals & tests", 7)
    r.fetch_itunes("evals & tests", 7)
    r.fetch_hackertube()
    assert [urlparse(url).hostname for url in urls] == ["hn.algolia.com", "itunes.apple.com", "hackertube.org"]
    assert parse_qs(urlparse(urls[0]).query) == {"query": ["evals & tests"], "tags": ["story"], "hitsPerPage": ["7"]}
    assert parse_qs(urlparse(urls[1]).query)["entity"] == ["podcastEpisode"]


def test_http_fetcher_timeout_agent_and_safe_failure(monkeypatch):
    import io
    calls = []
    def response(request, timeout):
        calls.append((request, timeout))
        return io.BytesIO(b'{"hits": []}')
    monkeypatch.setattr(r.urllib.request, "urlopen", response)
    assert r.fetch_hn("evals", 2) == {"hits": []}
    assert calls[0][1] == 20 and calls[0][0].get_header("User-agent") == r.USER_AGENT
    def broken(*args, **kwargs):
        raise OSError("private/path/must/not/escape")
    monkeypatch.setattr(r.urllib.request, "urlopen", broken)
    with pytest.raises(r.ResearchError) as error:
        r.fetch_hn("evals", 2)
    assert error.value.code == "fetch_failed" and "private" not in str(error.value)


def test_http_fetcher_rejects_oversized_response(monkeypatch):
    import io
    monkeypatch.setattr(r, "FETCH_MAX_BYTES", 16)
    monkeypatch.setattr(r.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"x" * 17))
    with pytest.raises(r.ResearchError) as error:
        r.fetch_hn("evals", 2)
    assert error.value.code == "too_large"


@pytest.mark.parametrize("duration,expected", [(180, -0.5), (900, 0.5), (5400, 0.5), (10801, -0.5), (None, 0)])
def test_length_prior_and_caption_bonus(duration, expected):
    item = r.parse_ytsearch({"entries": [{"id": "evaltalk001", "title": "evals", "duration": duration}]})[0]
    item["has_captions"] = True
    ranked, _ = r.rank_candidates([item], ["evals"], r.normalize_scope({"question": "evals"}), now=NOW)
    assert f"Length: {expected:+.6f}" in ranked[0]["why_ranked"]
    assert "Library or captions: +0.300000" in ranked[0]["why_ranked"]
    assert ranked[0]["est_capture"] == "captions"


def test_empty_channels_are_exempt_from_diversity_cap():
    items = r.parse_ytsearch({"entries": [
        {"id": f"evals{i:06d}", "title": "evals", "channel": channel}
        for i, channel in enumerate(["", None, " ", "", "", "", "Forum", "forum", "Forum", "Forum"])]})
    ranked, capped = r.rank_candidates(items, ["evals"], r.normalize_scope({"question": "evals"}), now=NOW)
    assert len(ranked) == 9 and capped == 1
    assert sum(not c["channel"] for c in ranked) == 6


def test_pool_retains_candidates_before_channel_and_response_caps(tmp_path):
    run = r.create_run(tmp_path, {"question": "evals", "max_sources": 1})
    collected = {"candidates": [
        r._candidate(f"yt:{n:011d}", "youtube", list_imports.watch_url(f"{n:011d}"),
                     "evals", "Forum", signals={"hackertube_quality": n})
        for n in range(520)], "by_source": {}, "errors": [], "skipped": []}
    before = deepcopy((run, collected))
    result = r.merge_and_rank(run, collected, ["evals"], now=NOW)
    assert (run, collected) == before
    assert len(result["candidates_pool"]) == 500 and len(result["candidates"]) == 2
    assert result["capped_by_channel"] == 497
    assert result["candidates_pool"][0]["key"] == "yt:00000000519"
    assert result["candidates_pool"][-1]["key"] == "yt:00000000020"


@pytest.mark.parametrize("query", ["the and of", "how to be", "AI ML go", "and the xyz"])
def test_hackertube_ignores_stop_words_and_short_terms(query):
    assert r.parse_hackertube([{"vid": "evaltalk001", "title": "The AI and ML of how to be"}], query) == []


@pytest.mark.parametrize("field", ["title", "channel", "why_hn", "note", "summary", "category"])
def test_hackertube_matches_all_searchable_fields(field):
    rows = [{"vid": "evaltalk001", field: "A talk on EVALS"},
            {"vid": "evaltalk002", "title": "The unrelated talk"}]
    assert [c["key"] for c in r.parse_hackertube(rows, "the evals")] == ["yt:evaltalk001"]


def test_hackertube_ranks_all_matches_up_to_100(tmp_path):
    run = r.create_run(tmp_path, {"question": "evals", "source_kinds": ["hackertube"], "max_sources": 1})
    listing = [{"vid": f"evals{i:06d}", "title": "evals", "score": i} for i in range(105)]
    result = r.discover(run, ["evals"], per_query=1, fetchers={"hackertube": lambda: listing},
                        consented_kinds=["hackertube"], now=NOW)
    assert result["by_source"] == {"hackertube": 100}
    assert len(result["candidates_pool"]) == 100
    assert result["candidates"][0]["key"] == "yt:evals000099"


def test_hn_extracts_story_text_and_dedupes_direct_link():
    rows = r.parse_hn_search({"hits": [{
        "objectID": "123", "title": "Ask HN: evals talks?", "url": "https://youtu.be/evaltalk001",
        "story_text": '<p>Try https:&#x2F;&#x2F;youtu.be&#x2F;evaltalk002 and '
                      '<a href="https://www.youtube.com/watch?v=evaltalk001">this</a>',
        "points": 42, "num_comments": 7,
    }, {"objectID": "124", "title": "Show HN: evals", "url": None,
        "story_text": "Demo: https://www.youtube.com/watch?v=evaltalk003"},
        {"objectID": "125", "story_text": {"invalid": True}}]})
    assert [c["key"] for c in rows] == ["yt:evaltalk001", "yt:evaltalk002", "yt:evaltalk003"]
    assert all(c["capturable"] for c in rows)
    assert rows[1]["signals"]["hn_points"] == 42
    assert rows[1]["signals"]["hn_url"].endswith("id=123")


@pytest.mark.parametrize("url", [
    "http://localhost/a", "https://LOCALHOST./a", "https://show.localhost/a", "https://show.local/a",
    "http://127.0.0.1/", "http://10.0.0.1/", "http://172.16.1.1/", "http://192.168.1.1/",
    "http://169.254.1.1/", "http://0.0.0.0/", "http://240.0.0.1/", "http://[::1]/",
    "http://[fc00::1]/", "http://[fe80::1]/", "http://[::ffff:10.0.0.1]/",
    "https://example.com/" + "a" * 4096, "https://example.com/a\nb", "https://example.com/\x00",
    "https://example.com/\x7f", "https://example.com/\x85", "https://example.com/\u200b",
    " https://example.com/", "https://example.com/a b", "https://exam\tple.com/",
    "https://@example.com/", "https://:@example.com/", "https://user@example.com/",
    "https://example.com:abc/", "https://example.com:65536/", "https://example.com:-1/",
    "https://example.com:0/", "https://example.com:/", "https://[::1/", "file:///tmp/episode.mp3",
])
def test_rejects_unsafe_urls(url):
    assert r._url(url) == ""
    assert r.parse_itunes_episodes({"results": [{"episodeUrl": url, "trackViewUrl": url}]}) == []


@pytest.mark.parametrize("url", ["https://example.com:8443/a?q=evals", "http://8.8.8.8/episode",
                                  "https://[2606:4700:4700::1111]/episode", "https://example.com/a%20b"])
def test_keeps_public_urls(url):
    assert r._url(url) == url


def test_text_strips_unicode_controls_and_collapses_whitespace():
    value = "  A\x00\x1b\u200b\u202e\ufeffB\tC\nD\u00a0E\x7f\x85 F  "
    assert r._text(value) == "AB C D E F"
    row = r.parse_hackertube([{"vid": "evaltalk001", "title": value, "channel": value,
                              "summary": value, "note": value, "category": "evals"}], "evals")[0]
    assert all(row[field] == "AB C D E F" for field in ("title", "channel", "description", "note"))


@pytest.mark.parametrize("value", [True, False, float("inf"), float("nan"), "inf"])
def test_parsers_keep_first_rows_long_titles_and_invalid_numbers_unknown(value):
    title = "evals " + "x" * 394
    yt = r.parse_ytsearch({"entries": [
        {"id": "evaltalk001", "title": title, "duration": value, "view_count": value},
        {"id": "evaltalk001", "title": "duplicate", "duration": 900, "view_count": 20}]})
    ht = r.parse_hackertube([
        {"vid": "evaltalk001", "title": title, "duration_s": value, "score": value},
        {"vid": "evaltalk001", "title": "duplicate evals", "duration_s": 900, "score": 20}], "evals")
    assert len(yt) == len(ht) == 1
    assert yt[0]["title"] == ht[0]["title"] == title
    assert yt[0]["duration_s"] is ht[0]["duration_s"] is None
    assert yt[0]["signals"]["view_count"] is ht[0]["signals"]["hackertube_quality"] is None
    json.dumps(yt + ht, allow_nan=False)


@pytest.mark.parametrize("capturable,in_library,captions,duration,expected", [
    (False, False, False, 900, "unknown"), (False, False, True, 900, "unknown"),
    (False, True, False, 900, "captions"), (True, False, True, 900, "captions"),
    (True, False, False, 0, "unknown"), (True, False, False, None, "unknown"),
    (True, False, False, 0.1, "asr ~1 min"), (True, False, False, 301, "asr ~2 min"),
])
def test_capture_estimate(capturable, in_library, captions, duration, expected):
    candidate = r._candidate("pod:example", "podcast", "https://example.com/episode", "evals",
                             duration=duration, in_library=in_library, capturable=capturable)
    candidate["has_captions"] = captions
    ranked, _ = r.rank_candidates([candidate], ["evals"], r.normalize_scope({"question": "evals"}), now=NOW)
    assert ranked[0]["est_capture"] == expected


@pytest.mark.parametrize("kind", ["library", "youtube", "hn", "podcast"])
@pytest.mark.parametrize("code", ["fetch_failed", "invalid_response", "rate_limited"])
def test_query_failures_continue_except_rate_limit(tmp_path, kind, code):
    other = "hn" if kind != "hn" else "youtube"
    run = r.create_run(tmp_path, {"question": "evals", "source_kinds": [kind, other]})
    calls = []
    def flaky(query, limit):
        calls.append(query)
        if query == "first":
            raise r.ResearchError("private failure", code)
        return fetchers()[kind](query, limit)
    result = r.discover(run, ["first", "evals", "last"], fetchers={**fetchers(), kind: flaky},
                        consented_kinds=list(r.NETWORK_KINDS), now=NOW)
    assert calls == (["first"] if code == "rate_limited" else ["first", "evals", "last"])
    assert result["errors"] == [{"kind": kind, "query": "first", "code": code,
                                 "message": f"{kind} discovery could not complete."}]
    assert result["by_source"][other] > 0
    assert bool(result["by_source"][kind]) is (code != "rate_limited")
    assert "private failure" not in json.dumps(result)


def test_bad_query_response_does_not_skip_next_query(tmp_path):
    run = r.create_run(tmp_path, {"question": "evals", "source_kinds": ["youtube"]})
    result = r.discover(run, ["bad", "evals"], fetchers={
        "youtube": lambda q, n: {"entries": None} if q == "bad" else fixture("ytsearch_evals.json")},
        consented_kinds=["youtube"], now=NOW)
    assert result["errors"][0]["query"] == "bad"
    assert result["errors"][0]["code"] == "invalid_response"
    assert result["by_source"]["youtube"] == 6
