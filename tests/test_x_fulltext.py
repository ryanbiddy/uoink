"""3.18.0 full X post text: long posts, quoted posts, gone posts, X Articles
and rate limits, against made-up saved fixtures. No real network.

Sources: X's syndication endpoint for every post; the open X tab through
the extension (dom_post, stays on the computer); FxTwitter only when the
user turned it on."""
import copy
import json
import urllib.error
from pathlib import Path

import pytest

import page_extractor
import x_article_extractor
import x_extractor
import x_fulltext
from uoink_core import x_evidence

CASES = json.loads((Path(__file__).parent / "fixtures" / "x_fulltext_cases.json")
                   .read_text(encoding="utf-8"))["cases"]
FXTWITTER_HOST = "https://api.fxtwitter.com/"


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def _http_error(url, code, headers=None):
    return urllib.error.HTTPError(url, code, "fixture", headers or {}, None)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    x_extractor.reset_fxtwitter_state()

    def forbidden(*_args, **_kwargs):
        pytest.fail("tests must not reach the network")
    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", forbidden)
    yield
    x_extractor.reset_fxtwitter_state()


def route(monkeypatch, *, syndication=None, fxtwitter=None):
    """Answer by URL prefix. A value is a payload, an exception to raise, or
    None (the test fails if that host is asked)."""
    calls = []

    def urlopen(request, timeout=None, **_kwargs):
        url = request.full_url
        calls.append(request)
        for prefix, answer in ((x_extractor.SYNDICATION_URL, syndication), (FXTWITTER_HOST, fxtwitter)):
            if url.startswith(prefix):
                if answer is None:
                    pytest.fail(f"unexpected request to {prefix}")
                if isinstance(answer, BaseException):
                    raise answer
                return _Resp(answer)
        pytest.fail(f"unexpected request {url}")
    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", urlopen)
    return calls


def hosts(calls):
    return ["fxtwitter" if r.full_url.startswith(FXTWITTER_HOST) else "syndication" for r in calls]


# ---- the cause -------------------------------------------------------------------
def test_long_post_marker_is_the_cause_and_is_detected():
    case = CASES["long_post"]
    evidence = x_evidence.shape(case["syndication"])
    assert evidence["text_completeness"] == "truncated"
    assert evidence["text_completeness_reason"] == "response marks omitted text"
    assert len(case["syndication"]["text"]) < 280 < len(case["full_text"])
    assert x_fulltext.looks_cut_off(case["syndication"]["text"])


# ---- short post ------------------------------------------------------------------
def test_short_post_asks_syndication_only(monkeypatch):
    case = CASES["short_post"]
    calls = route(monkeypatch, syndication=case["syndication"])
    record = x_extractor.post_text_record(case["tweet_id"], fxtwitter=True)
    assert hosts(calls) == ["syndication"]  # whole already: FxTwitter is never asked
    assert record["long_post"] is False and record["complete"] is True
    result = x_extractor.extract_x_thread(f"https://x.com/example_writer/status/{case['tweet_id']}")
    assert result["ok"] and result["metadata"]["text_cut_off"] is None


# ---- long post -------------------------------------------------------------------
def test_long_post_by_default_saves_what_x_gave_and_marks_it_cut_off(monkeypatch):
    case = CASES["long_post"]
    calls = route(monkeypatch, syndication=case["syndication"])
    result = x_extractor.extract_x_thread(f"https://x.com/example_writer/status/{case['tweet_id']}")
    assert result["ok"], result
    assert "fxtwitter" not in hosts(calls)
    assert case["syndication"]["text"] in result["markdown"]
    assert "FULL-TEXT-END" not in result["markdown"]
    assert result["metadata"]["text_cut_off"] == {
        "reason": "long_post", "open_url": f"https://x.com/example_writer/status/{case['tweet_id']}"}
    assert result["text_cut_off"] == result["metadata"]["text_cut_off"]
    assert "Text: truncated" in result["markdown"]


def test_open_tab_text_completes_a_long_post_without_any_third_party(monkeypatch):
    case = CASES["long_post"]
    calls = route(monkeypatch, syndication=case["syndication"])
    result = x_extractor.extract_x_thread(
        f"https://x.com/example_writer/status/{case['tweet_id']}", dom_post=case["dom_post"])
    assert hosts(calls) == ["syndication"]
    post = result["metadata"]["x_capture"]["posts"][-1]
    assert post["text"].endswith("FULL-TEXT-END")
    assert post["capture_provider"] == "X page" and post["text_completeness"] == "complete"
    assert "https://example.com/notes-checker" in result["markdown"]
    assert result["metadata"]["text_cut_off"] is None
    assert result["extraction_engine"] == "x-syndication+x-page"


def test_open_tab_text_that_does_not_match_is_ignored(monkeypatch):
    case = CASES["long_post"]
    route(monkeypatch, syndication=case["syndication"])
    other = dict(case["dom_post"], text="Something else entirely. " * 30)
    result = x_extractor.extract_x_thread(
        f"https://x.com/example_writer/status/{case['tweet_id']}", dom_post=other)
    post = result["metadata"]["x_capture"]["posts"][-1]
    assert post["text"] == case["syndication"]["text"]
    assert post["provider_status"]["X page"].startswith("not used")
    wrong_id = dict(case["dom_post"], id="1900000000000000999")
    result = x_extractor.extract_x_thread(
        f"https://x.com/example_writer/status/{case['tweet_id']}", dom_post=wrong_id)
    assert result["metadata"]["x_capture"]["posts"][-1]["text"] == case["syndication"]["text"]


def test_open_tab_still_showing_show_more_is_not_called_complete(monkeypatch):
    case = CASES["long_post"]
    route(monkeypatch, syndication=case["syndication"])
    partial = dict(case["dom_post"], show_more=True)
    record = x_extractor.post_text_record(case["tweet_id"], dom_post=partial)
    assert record["text"].endswith("FULL-TEXT-END")
    assert record["text_completeness"] == "unknown" and record["complete"] is False


def test_fxtwitter_opt_in_gets_the_full_long_post_with_a_named_agent(monkeypatch):
    case = CASES["long_post"]
    calls = route(monkeypatch, syndication=case["syndication"], fxtwitter=case["fxtwitter"])
    result = x_extractor.extract_x_thread(
        f"https://x.com/example_writer/status/{case['tweet_id']}", fxtwitter=True)
    assert hosts(calls) == ["syndication", "fxtwitter"]
    agent = calls[1].get_header("User-agent")
    assert agent.startswith("Uoink/") and "uoink.app" in agent
    post = result["metadata"]["x_capture"]["posts"][-1]
    assert post["text"].endswith("FULL-TEXT-END") and post["text_completeness"] == "complete"
    assert result["extraction_engine"] == "x-syndication+fxtwitter-v2"
    assert result["metadata"]["text_cut_off"] is None


def test_open_tab_text_means_fxtwitter_is_not_asked(monkeypatch):
    case = CASES["long_post"]
    calls = route(monkeypatch, syndication=case["syndication"])
    x_extractor.post_text_record(case["tweet_id"], fxtwitter=True, dom_post=case["dom_post"])
    assert hosts(calls) == ["syndication"]


def test_fxtwitter_answers_are_cached(monkeypatch):
    case = CASES["long_post"]
    calls = route(monkeypatch, syndication=case["syndication"], fxtwitter=case["fxtwitter"])
    x_extractor.fetch_tweet_json(case["tweet_id"], fxtwitter=True)
    x_extractor.fetch_tweet_json(case["tweet_id"], fxtwitter=True)
    assert hosts(calls).count("fxtwitter") == 1


def test_long_post_with_media_keeps_syndication_media(monkeypatch):
    case = CASES["long_post_media"]
    route(monkeypatch, syndication=case["syndication"], fxtwitter=case["fxtwitter"])
    record = x_extractor.post_text_record(case["tweet_id"], fxtwitter=True)
    assert record["long_post"] and record["complete"]
    assert record["text"].endswith("MEDIA-TEXT-END")
    media = record["evidence"]["media"]
    assert [m["type"] for m in media] == ["photo"]
    assert media[0]["alt_text"].startswith("A wooden desk")


# ---- quoted post -----------------------------------------------------------------
def test_quoted_post_text_is_saved_and_marked_when_cut(monkeypatch):
    case = CASES["quoted_post"]
    route(monkeypatch, syndication=case["syndication"])
    result = x_extractor.extract_x_thread(f"https://x.com/example_reader/status/{case['tweet_id']}")
    # The quoted post's words are saved, even though X cut them short.
    assert case["syndication"]["quoted_tweet"]["text"] in result["markdown"]
    assert result["metadata"]["text_cut_off"]["reason"] == "long_post"
    record = x_extractor.post_text_record(case["tweet_id"])
    assert "Quoting @example_quoter" in record["description"]


def test_quoted_post_is_completed_with_the_opt_in(monkeypatch):
    case = CASES["quoted_post"]
    route(monkeypatch, syndication=case["syndication"], fxtwitter=case["fxtwitter"])
    record = x_extractor.post_text_record(case["tweet_id"], fxtwitter=True)
    quote = record["evidence"]["quote"]
    assert record["long_post"] is False  # the quoting post itself is short
    assert quote["text"].endswith("QUOTE-TEXT-END") and record["quote_complete"]
    assert record["description"].rstrip().endswith("QUOTE-TEXT-END")


# ---- post gone -------------------------------------------------------------------
def test_deleted_post_is_gone_on_syndication(monkeypatch):
    route(monkeypatch, syndication=_http_error(x_extractor.SYNDICATION_URL, 404))
    with pytest.raises(x_extractor.XFetchError) as caught:
        x_extractor.post_text_record("1900000000000000008")
    assert caught.value.kind == "gone" and "404" in str(caught.value)


def test_post_gone_on_fxtwitter_keeps_the_syndication_copy(monkeypatch):
    case = CASES["long_post"]
    route(monkeypatch, syndication=case["syndication"], fxtwitter=_http_error(FXTWITTER_HOST, 404))
    record = x_extractor.post_text_record(case["tweet_id"], fxtwitter=True)
    assert record["long_post"] and not record["complete"]
    assert record["text"] == case["syndication"]["text"]
    assert record["evidence"]["provider_status"]["FxTwitter"] == "post unavailable"


# ---- rate limits and back-off ----------------------------------------------------
def test_syndication_rate_limit_is_typed_with_retry_after(monkeypatch):
    route(monkeypatch, syndication=_http_error(x_extractor.SYNDICATION_URL, 429, {"Retry-After": "30"}))
    with pytest.raises(x_extractor.XFetchError) as caught:
        x_extractor.fetch_syndication_json("1900000000000000009")
    assert caught.value.kind == "rate_limited" and caught.value.retry_after == 30.0
    assert "rate-limiting" in str(caught.value)


def test_fxtwitter_rate_limit_backs_off_instead_of_retrying(monkeypatch):
    case = CASES["long_post"]
    calls = route(monkeypatch, syndication=case["syndication"],
                  fxtwitter=_http_error(FXTWITTER_HOST, 429, {"Retry-After": "90"}))
    record = x_extractor.post_text_record(case["tweet_id"], fxtwitter=True)
    assert record["text"] == case["syndication"]["text"]
    assert record["evidence"]["provider_status"]["FxTwitter"] == "rate limited"
    # The next save during the cool-down does not ask FxTwitter at all.
    x_extractor.post_text_record(case["tweet_id"], fxtwitter=True)
    assert hosts(calls).count("fxtwitter") == 1
    with pytest.raises(x_extractor.XFetchError) as caught:
        x_extractor.fetch_fxtwitter_status(case["tweet_id"])
    assert caught.value.kind == "rate_limited" and caught.value.retry_after > 60


# ---- X Articles ------------------------------------------------------------------
def test_bare_article_link_fails_honestly_with_the_article_one_click_away(monkeypatch):
    url = CASES["article_only"]["article_url"]
    monkeypatch.setattr(page_extractor, "_CRAWL4AI_AVAILABLE", False)
    monkeypatch.setattr(page_extractor, "_extract_article_page", lambda u, **_k: {
        "ok": True, "extraction_engine": "stdlib", "url": u, "title": None,
        "markdown": "# JavaScript is not available.\n\nWe've detected that JavaScript is disabled in this browser.",
        "metadata": {}, "links": [], "images": []})
    result = page_extractor.extract_page(None, url, enforce_allowlist=False, include_screenshot=False)
    assert result["ok"] is False and result["code"] == "x_login_wall"
    assert result["open_url"] == url
    assert "logged-in" in result["error"] and "Uoink this article" in result["error"]
    assert "—" not in result["error"] and ";" not in result["error"]
    assert page_extractor.persist_page_yoink(None, result) is None


def test_post_that_only_links_to_an_article_is_saved_and_marked(monkeypatch):
    case = CASES["article_only"]
    calls = route(monkeypatch, syndication=case["syndication"])
    result = x_extractor.extract_x_thread(f"https://x.com/example_author/status/{case['tweet_id']}")
    assert result["ok"] and "source_type" not in result
    assert result["title"] == "@example_author: How we cut our build time in half"
    assert result["metadata"]["text_cut_off"] == {
        "reason": "article", "open_url": case["article_url"], "title": "How we cut our build time in half"}
    assert "Our builds took eleven minutes" in result["markdown"]  # X's preview is kept
    assert "fxtwitter" not in hosts(calls)


def test_a_post_with_its_own_words_is_not_an_article():
    post = x_evidence.shape(dict(CASES["article_only"]["syndication"],
                                 text="Wrote this up last night: https://t.co/ArticleL1"))
    assert x_extractor.linked_article(post) is None


def test_fxtwitter_opt_in_saves_the_article_body(monkeypatch):
    case = CASES["article_only"]
    calls = route(monkeypatch, syndication=case["syndication"], fxtwitter=case["fxtwitter"])
    result = x_extractor.extract_x_thread(
        f"https://x.com/example_author/status/{case['tweet_id']}", fxtwitter=True)
    assert result["ok"] and result["source_type"] == x_article_extractor.SOURCE_TYPE
    assert result["url"] == case["article_url"]
    assert result["title"] == "How we cut our build time in half"
    md = result["markdown"]
    for piece in ("**Author:** Example Author (@example_author)", "## Measure before you cache",
                  "- Time every step for a week.\n- Sort by total time",
                  "[our notes](https://example.com/build-notes)",
                  "[Image](https://pbs.example.test/media/build-chart.jpg)",
                  "```\nmake build --profile\n```",
                  "> Most of the time went to one test nobody owned. ARTICLE-BODY-END",
                  "Provider: FxTwitter"):
        assert piece in md, piece
    assert "![" not in md  # images are links, never embeds
    assert result["extraction_engine"] == "fxtwitter-article"
    assert result["metadata"]["x_capture"]["posts"][0]["text_completeness"] == "complete"
    assert hosts(calls).count("fxtwitter") == 1


def test_fxtwitter_without_a_body_keeps_the_marked_post(monkeypatch):
    case = CASES["article_only"]
    empty = copy.deepcopy(case["fxtwitter"])
    del empty["status"]["article"]
    route(monkeypatch, syndication=case["syndication"], fxtwitter=empty)
    result = x_extractor.extract_x_thread(
        f"https://x.com/example_author/status/{case['tweet_id']}", fxtwitter=True)
    assert result["ok"] and result["metadata"]["text_cut_off"]["reason"] == "article"


# ---- offline helpers -------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Short post.", False),
    ("word " * 55, True),                         # ~275 weighted, X's cut length
    ("word " * 55 + "https://t.co/Abc123", True),  # media link after the cut
    ("word " * 80, False),                        # longer than any cut copy
    ("A thought that trails off and goes on for a while longer than this…", False),
    ("x" * 120 + "…", True),
])
def test_looks_cut_off(text, expected):
    assert x_fulltext.looks_cut_off(text) is expected


def test_extends_only_accepts_a_longer_version_of_the_same_text():
    full = CASES["long_post"]["full_text"]
    saved = CASES["long_post"]["syndication"]["text"]
    assert x_fulltext.extends(saved, full)
    assert x_fulltext.extends(saved + " https://t.co/Abc123", full)
    assert not x_fulltext.extends(full, full)
    assert not x_fulltext.extends(saved, "Something else entirely, and long enough to pass. " * 9)
    assert x_fulltext.extends("@someone " + saved, "@someone " + full)


# ---- server wiring ---------------------------------------------------------------
def test_fxtwitter_is_off_by_default_in_settings():
    import server
    assert server._normalize_settings({})["fxtwitter_enrichment_enabled"] is False
    assert server._normalize_settings({"fxtwitter_enrichment_enabled": "yes"})["fxtwitter_enrichment_enabled"] is False
    assert server._normalize_settings({"fxtwitter_enrichment_enabled": True})["fxtwitter_enrichment_enabled"] is True
    assert server._x_fxtwitter_kwargs({}) == {}
    assert server._x_fxtwitter_kwargs({"fxtwitter_enrichment_enabled": True}) == {"fxtwitter": True}


def test_dom_post_from_the_extension_is_cleaned():
    import server
    assert server._clean_dom_post({"id": "12", "text": "hi", "show_more": "yes", "html": "<b>"}) == {
        "id": "12", "text": "hi", "show_more": False}
    assert server._clean_dom_post({"id": "abc", "text": "hi"}) is None
    assert server._clean_dom_post("text") is None


def test_x_video_description_gets_text_links_and_quote(monkeypatch):
    import server
    case = CASES["quoted_post"]
    route(monkeypatch, syndication=case["syndication"])
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    metadata = {"extractor": "twitter", "id": case["tweet_id"], "description": "yt-dlp copy"}
    enriched = server._enrich_x_video_metadata(f"https://x.com/example_reader/status/{case['tweet_id']}", metadata)
    assert enriched is not metadata and metadata["description"] == "yt-dlp copy"
    assert "Quoting @example_quoter" in enriched["description"]
    assert enriched["x_text"]["long_post"] is False


def test_non_x_video_and_failures_keep_the_description(monkeypatch):
    import server
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    youtube = {"extractor": "youtube", "description": "keep"}
    assert server._enrich_x_video_metadata("https://www.youtube.com/watch?v=abc", youtube) is youtube
    route(monkeypatch, syndication=_http_error(x_extractor.SYNDICATION_URL, 404))
    x_meta = {"extractor_key": "Twitter", "description": "keep"}
    assert server._enrich_x_video_metadata("https://x.com/a/status/1900000000000000001", x_meta) is x_meta


def test_no_guest_web_client_ships():
    """3.18.0 decision: no X internal web API, no forged client headers."""
    source = (Path(__file__).resolve().parent.parent / "x_fulltext.py").read_text(encoding="utf-8")
    source += (Path(__file__).resolve().parent.parent / "x_extractor.py").read_text(encoding="utf-8")
    for banned in ("guest/activate", "TweetResultByRestId", "x-guest-token", "X-Client-Transaction-Id"):
        assert banned not in source
